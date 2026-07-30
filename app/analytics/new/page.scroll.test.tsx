import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";
import {
  buildBuilderTurnPresentation,
  getDisplayBuilderProgressItems,
  makeBuilderQuestionFriendly,
} from "./builderProgressPresentation";
import {
  getNextMissingBacktestCondition,
  type MissingBacktestCondition,
} from "./backtestReadiness";
import { applyDeterministicConditionChoice } from "./deterministicConditionFlow";

const push = vi.fn();
const fetchMock = vi.fn();
const scrollToMock = vi.fn();

const parsedStrategy = {
  description: "PER 저평가 전략",
  universe: ["KOSPI"],
  fundamental_filters: [{ metric: "per", operator: "<=", value: 10 }],
  entry_signals: [],
  exit_signals: [{ indicator: "rsi", signal_type: "sell", threshold: 70 }],
  max_positions: 5,
  hold_period_days: null,
  rebalancing_period: "monthly",
  stop_loss_pct: 10,
  take_profit_pct: 20,
  trailing_stop_pct: null,
  backtest_period: "5y",
  initial_capital: 10000000,
};

const incompleteParsedStrategy = {
  ...parsedStrategy,
  exit_signals: [],
  rebalancing_period: "none",
  stop_loss_pct: null,
  take_profit_pct: null,
};

const incompleteSingleAssetStrategy = {
  ...incompleteParsedStrategy,
  description: "삼성전자 단일 종목 전략",
  universe: ["KOSPI200"],
  target_symbols: ["005930"],
  fundamental_filters: [],
  max_positions: 1,
};

const completeSingleAssetStrategy = {
  ...incompleteSingleAssetStrategy,
  entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
  exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
  stop_loss_pct: 10,
  take_profit_pct: 20,
};

const backtestRequest = {
  symbols: ["005930", "000660"],
  universe_id: "kospi",
  entry: { conditions: [{ id: "per" }] },
  exit: { conditions: [{ id: "rsi", params: { value: 70 }, signal_type: "sell" }] },
  risk: {
    max_positions: 5,
    init_cash: 10000000,
    stop_loss_pct: 10,
    take_profit_pct: 20,
  },
  period: "5y",
  options: {
    fee_rate: 0.015,
    slippage_rate: 0.05,
  },
};

const incompleteBacktestRequest = {
  ...backtestRequest,
  exit: { conditions: [] },
  risk: {
    max_positions: 5,
    init_cash: 10000000,
  },
};

const incompleteSingleAssetBacktestRequest = {
  ...incompleteBacktestRequest,
  symbols: ["005930"],
  universe_id: null,
  backtest_mode: "single_asset",
  target_stocks: [{ symbol: "005930", name: "삼성전자" }],
  risk: {
    ...incompleteBacktestRequest.risk,
    max_positions: 1,
    position_size_pct: 100,
    ranking_enabled: false,
  },
};

const completeSingleAssetBacktestRequest = {
  ...incompleteSingleAssetBacktestRequest,
  entry: { conditions: [{ id: "ma_crossover" }] },
  exit: { conditions: [{ id: "ma_crossover", signal_type: "sell" }] },
  risk: {
    ...incompleteSingleAssetBacktestRequest.risk,
    stop_loss_pct: 10,
    take_profit_pct: 20,
  },
};

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/analytics/chat",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/strategy/StrategyExampleTabs", () => ({
  StrategyExampleTabs: () => <div>예시 전략</div>,
}));

vi.mock("@/components/strategy/StrategyWaveBackground", () => ({
  StrategyWaveBackground: () => <div>배경</div>,
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      signInWithOAuth: vi.fn(),
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  }),
}));

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function createJsonResponse(body: unknown, headers?: Record<string, string>) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      ...(headers ?? {}),
    },
  });
}

// 각 목의 explicit_fields는 그 목이 흉내 내는 **프롬프트가 실제로 말한** 설정만 담는다.
// 값이 채워져 있어도(기본값 물질화) 사용자가 말하지 않았으면 넣지 않는다 — 이 구분이
// 되묻기 게이트의 전부이며, 실제 백엔드는 인터프리터 LLM의 구조화 출력에서 판정한다.
const ALL_EXPLICIT = [
  "universe",
  "max_positions",
  "rebalancing",
  "backtest_period",
  "initial_capital",
];

function createParseStreamResponse() {
  const encoder = new TextEncoder();
  const payload = [
    `data: ${JSON.stringify({ type: "parsed_final", parsed: parsedStrategy, explicit_fields: ALL_EXPLICIT })}\n\n`,
    `data: ${JSON.stringify({ type: "dsl_ready", backtest_request: backtestRequest, symbol_count: 2 })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");

  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { status: 200 }
  );
}

function createParseStreamResponseWithClarification() {
  const encoder = new TextEncoder();
  const clarificationQuestion =
    "말씀하신 조건을 숫자로 구체화해 주세요. 어느 정도를 기준으로 할까요?\n\n" +
    "• 영업이익률 몇 % 이상으로 설정할까요?";
  const payload = [
    `data: ${JSON.stringify({
      type: "parsed_final",
      parsed: incompleteParsedStrategy,
      explicit_fields: [],
      clarification_question: clarificationQuestion,
      clarification_suggestions: ["영업이익률 10% 이상", "영업이익률 15% 이상"],
    })}\n\n`,
    `data: ${JSON.stringify({ type: "dsl_ready", backtest_request: incompleteBacktestRequest, symbol_count: 2 })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");

  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { status: 200 }
  );
}

function createParseStreamResponseWithNonConditionClarification() {
  const encoder = new TextEncoder();
  const payload = [
    `data: ${JSON.stringify({
      type: "parsed_final",
      parsed: parsedStrategy,
      explicit_fields: ALL_EXPLICIT,
      clarification_question: "여러 종목이 지정되었습니다. 어느 종목을 대상으로 할까요?",
      clarification_suggestions: ["삼성전자", "SK하이닉스"],
    })}\n\n`,
    `data: ${JSON.stringify({ type: "dsl_ready", backtest_request: backtestRequest, symbol_count: 2 })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");

  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { status: 200 }
  );
}

function createParseStreamResponseWithThemeUniverseReask() {
  const encoder = new TextEncoder();
  const parsed = {
    ...incompleteParsedStrategy,
    universe: [],
    fundamental_filters: [],
    sector: "미디어/엔터",
  };
  const themeQuestion =
    "'BTS'와(과) 사업적 관련 근거가 확인된 상장사 3곳이 있어요(등록 관계·공시·검색 출처 근거): " +
    "하이브, 에스엠, 넷마블. 이 종목들로만 백테스트할까요, 아니면 업종 전체로 할까요?";
  const payload = [
    `data: ${JSON.stringify({
      type: "parsed_final",
      parsed,
      explicit_fields: [],
      clarification_question: themeQuestion,
      clarification_suggestions: [
        "하이브, 에스엠, 넷마블 종목 전체를 함께 2026년부터 백테스트",
        "미디어/엔터 업종 전체로 백테스트",
      ],
      clarification_priority: "theme_universe",
    })}\n\n`,
    `data: ${JSON.stringify({ type: "dsl_ready", backtest_request: incompleteBacktestRequest, symbol_count: 3 })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");

  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { status: 200 }
  );
}

function createParseStreamResponseWithSectorNotFound() {
  const encoder = new TextEncoder();
  const parsed = {
    ...incompleteParsedStrategy,
    universe: [],
    fundamental_filters: [],
    sector: null,
  };
  const notFoundQuestion =
    "'리센즈' 관련 상장사를 확인하지 못했어요. " +
    "관련주를 찾을 수 없어 이 테마로는 전략을 만들 수 없어요. " +
    "다른 테마나 업종을 말씀해 주시면 그 범위로 전략을 만들 수 있어요.";
  const payload = [
    `data: ${JSON.stringify({
      type: "parsed_final",
      parsed,
      explicit_fields: [],
      clarification_question: notFoundQuestion,
      clarification_suggestions: [
        "반도체 관련주",
        "이차전지 관련주",
        "바이오/제약 관련주",
        "자동차 관련주",
      ],
      clarification_priority: "sector_unresolved",
    })}\n\n`,
    `data: ${JSON.stringify({ type: "dsl_ready", backtest_request: incompleteBacktestRequest, symbol_count: 0 })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");

  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { status: 200 }
  );
}

function createParseStreamResponseMissingRebalancing() {
  const encoder = new TextEncoder();
  const parsed = {
    ...parsedStrategy,
    rebalancing_period: "none",
    take_profit_pct: null,
  };
  const request = {
    ...backtestRequest,
    risk: {
      ...backtestRequest.risk,
      rebalancing_period: "none",
      take_profit_pct: null,
    },
  };
  const payload = [
    `data: ${JSON.stringify({ type: "parsed_final", parsed, explicit_fields: ALL_EXPLICIT.filter((f) => f !== "rebalancing") })}\n\n`,
    `data: ${JSON.stringify({ type: "dsl_ready", backtest_request: request, symbol_count: 2 })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");

  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { status: 200 },
  );
}

function createSingleAssetParseStreamResponse(complete = false) {
  const encoder = new TextEncoder();
  const parsed = complete ? completeSingleAssetStrategy : incompleteSingleAssetStrategy;
  const request = complete
    ? completeSingleAssetBacktestRequest
    : incompleteSingleAssetBacktestRequest;
  const payload = [
    `data: ${JSON.stringify({
      type: "parsed_final",
      parsed,
      // 이 목이 흉내 내는 프롬프트("…최근 5년 데이터, 초기 자금 1,000만원")가 실제로 말한 설정.
      // 유니버스는 지정 종목(target_symbols)이 그 자체로 명시라 목록에 넣지 않는다.
      explicit_fields: ["backtest_period", "initial_capital"],
      clarification_question: complete
        ? null
        : "청산 조건 — 언제 팔까요?\n\n예: 데드크로스(5일/20일) 발생 시 매도, 20일 보유 후 청산",
      clarification_suggestions: complete
        ? null
        : ["20일 보유 후 청산", "데드크로스(5일/20일) 발생 시 매도"],
    })}\n\n`,
    `data: ${JSON.stringify({ type: "dsl_ready", backtest_request: request, symbol_count: 1 })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");

  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { status: 200 }
  );
}

describe("StrategyLabPage scroll behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    // 모킹된 DashboardLayout에는 <main>이 없어 스크롤은 window 폴백 경로를 탄다.
    // 메시지 끝이 입력창에 가리는 상황(delta > 0)을 만들기 위해 bottom을 크게 잡는다.
    window.HTMLElement.prototype.getBoundingClientRect = () =>
      ({ bottom: 10000, top: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    vi.stubGlobal("scrollTo", scrollToMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("조건이 빠지면 파싱 결과를 다시 빌더로 보내지 않고 다음 누락 조건을 직접 묻는다", async () => {
    let classifyCallCount = 0;
    let parseCallCount = 0;
    const compileBodies: Array<{ parsed: Record<string, unknown> }> = [];
    const compileResponse = createDeferred<Response>();

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        classifyCallCount += 1;
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }
      if (url === "/api/strategy/parse/stream") {
        parseCallCount += 1;
        return Promise.resolve(createParseStreamResponseWithClarification());
      }
      if (url === "/api/strategy/compile") {
        compileBodies.push(JSON.parse(String(init?.body ?? "{}")));
        return compileResponse.promise;
      }
      if (url === "/api/strategy/builder/step") {
        throw new Error(`파싱 결과를 다시 빌더로 보내면 안 되는 경로: ${url}`);
      }
      if (url === "/api/strategy/coach") {
        if (compileBodies.length === 0) {
          throw new Error(`누락 조건 입력 전에 호출되면 안 되는 경로: ${url}`);
        }
        return Promise.resolve(createJsonResponse({ message: "전략 검증 완료" }));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "영업이익률이 높은 조건도 넣어줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText("먼저 어떤 시장·종목을 대상으로 할지 정해볼까요?"),
    ).toBeInTheDocument();
    expect(screen.getByText("현재까지 이해한 전략입니다")).toBeInTheDocument();
    const progressPanel = screen.getByTestId("strategy-progress-panel");
    expect(progressPanel).toHaveClass(
      "xl:fixed",
      "xl:right-4",
      "xl:top-[calc(var(--top-menu-bar-height,76px)+5rem)]",
    );
    expect(progressPanel).not.toHaveClass("xl:left-4");
    expect(within(progressPanel).getByTestId("strategy-progress-list")).toHaveClass("flex-col");
    expect(
      within(progressPanel)
        .getAllByRole("listitem")
        .map((item) => item.getAttribute("aria-label")),
    ).toEqual([
      "매수 조건: 완료",
      "유니버스: 진행 전",
      "매도 조건: 진행 전",
      "최대 보유: 진행 전",
      "리밸런싱: 진행 전",
      "리스크 관리: 진행 전",
      "백테스트 기간: 진행 전",
      "초기 자본: 진행 전",
    ]);
    expect(within(progressPanel).getByRole("listitem", { name: "유니버스: 진행 전" }))
      .toHaveAttribute("data-complete", "false");
    expect(within(progressPanel).getByRole("listitem", { name: "매수 조건: 완료" }))
      .toHaveAttribute("data-complete", "true");
    expect(within(progressPanel).getByRole("listitem", { name: "매도 조건: 진행 전" }))
      .toHaveAttribute("data-complete", "false");
    expect(
      within(screen.getByTestId("builder-strategy-summary")).queryByText("전략 진행률"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("선택 예시")).toBeInTheDocument();
    expect(screen.queryByText("기본값")).not.toBeInTheDocument();
    expect(screen.queryByText("10,000,000원")).not.toBeInTheDocument();
    expect(screen.queryByText(/빠져 있습니다|빠졌습니다/)).not.toBeInTheDocument();
    expect(screen.queryByText(/영업이익률 몇 % 이상으로 설정할까요/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "코스피200" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "코스피" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "코스닥" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "코스피+코스닥" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 입력" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/builder/step")).toBe(false);
    expect(
      fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/coach")
    ).toBe(false);
    // 최초 질문(유니버스 선택)에는 되돌아갈 이전 단계가 없으므로 '돌아가기' 버튼이 없다.
    expect(screen.queryByRole("button", { name: "돌아가기" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "코스피" }));
    expect(
      await screen.findByRole("button", { name: "데드크로스(5일/20일) 발생 시 매도" }),
    ).toBeInTheDocument();
    // 두 번째 질문(매도 조건)부터는 '돌아가기' 버튼으로 직전 조건 버블로 되돌아갈 수 있다.
    expect(screen.getByRole("button", { name: "돌아가기" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "돌아가기" }));
    expect(await screen.findByRole("button", { name: "코스피" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "돌아가기" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "코스피" }));
    expect(
      await screen.findByRole("button", { name: "데드크로스(5일/20일) 발생 시 매도" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "데드크로스(5일/20일) 발생 시 매도" }));
    expect(
      await screen.findByRole("button", { name: "최대 5종목" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "최대 5종목" }));
    expect(
      await screen.findByRole("button", { name: "매월 리밸런싱" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "매월 리밸런싱" }));
    expect(
      await screen.findByRole("button", { name: "손절 -10%" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "손절 -10%" }));
    expect(
      await screen.findByRole("button", { name: "익절 20%" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "익절 20%" }));
    expect(
      await screen.findByRole("button", { name: "최근 5년 데이터" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "최근 5년 데이터" }));
    expect(
      await screen.findByRole("button", { name: "1,000만원" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "1,000만원" }));
    expect(
      await screen.findByText(
        "모든 조건을 정했습니다. 현재까지의 전략을 확인하고 확정해 주세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("전략 확인")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "이 전략으로 확정" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "돌아가기" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "직접 입력" })).not.toBeInTheDocument();
    expect(parseCallCount).toBe(1);
    expect(classifyCallCount).toBe(1);
    expect(
      within(screen.getByTestId("strategy-progress-panel"))
        .getAllByRole("listitem")
        .every((item) => item.getAttribute("data-complete") === "true"),
    ).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "돌아가기" }));
    expect(await screen.findByRole("button", { name: "1,000만원" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "이 전략으로 확정" })).not.toBeInTheDocument();
    expect(parseCallCount).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: "1,000만원" }));
    fireEvent.click(screen.getByRole("button", { name: "이 전략으로 확정" }));

    // 확정은 대화 전체를 재파싱하지 않고, 누적된 parsed를 그대로 컴파일한다.
    await waitFor(() => {
      expect(compileBodies).toHaveLength(1);
    });
    expect(parseCallCount).toBe(1);
    expect(screen.queryByRole("button", { name: "백테스트 시작하기" })).not.toBeInTheDocument();

    compileResponse.resolve(createJsonResponse({
      parsed: compileBodies[0].parsed,
      backtest_request: backtestRequest,
      notices: [],
    }));

    expect(classifyCallCount).toBe(1);
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "이 전략으로 확정" }))
        .not.toBeInTheDocument();
    });

    // 칩으로 답한 모든 조건이 누적 parsed에 담겨 컴파일 요청에 실린다.
    const compiledParsed = compileBodies[0].parsed as Record<string, any>;
    expect(compiledParsed.universe).toEqual(["KOSPI"]);
    expect(compiledParsed.exit_signals).toEqual([
      // 칩 기간 명시화(2026-07-26) — 값은 엔진 실효 기본값(5/20)이라 결과 불변
      { indicator: "ma_crossover", signal_type: "sell", short_period: 5, long_period: 20 },
    ]);
    expect(compiledParsed.max_positions).toBe(5);
    expect(compiledParsed.rebalancing_period).toBe("monthly");
    expect(compiledParsed.stop_loss_pct).toBe(10);
    expect(compiledParsed.take_profit_pct).toBe(20);
    expect(compiledParsed.backtest_period).toBe("5y");
    expect(compiledParsed.initial_capital).toBe(10000000);
    // 파싱이 해석해 둔 매수 필터(재파싱이 잃을 수 있는 조건)가 그대로 보존된다.
    expect(compiledParsed.fundamental_filters).toEqual(
      incompleteParsedStrategy.fundamental_filters,
    );
  });

  it("테마 유니버스 되묻기(theme_universe)는 명시 설정 게이트가 삼키지 않고 먼저 보여준다", async () => {
    // 'bts 관련 종목 전략' 사고(2026-07-25): 백엔드가 컨셉 종목 제한 되묻기를 보냈는데
    // 프론트 explicit 게이트의 시장 질문이 이를 덮어써 업종 전체로 강등되던 회귀 가드.
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }
      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(createParseStreamResponseWithThemeUniverseReask());
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "bts 관련 종목 전략" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(/이 종목들로만 백테스트할까요, 아니면 업종 전체로 할까요/),
    ).toBeInTheDocument();
    // 컨셉 종목 제한 칩과 업종 전체 칩이 함께 제시된다
    expect(
      screen.getByRole("button", {
        name: "하이브, 에스엠, 넷마블 종목 전체를 함께 2026년부터 백테스트",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "미디어/엔터 업종 전체로 백테스트" }),
    ).toBeInTheDocument();
    // explicit 게이트의 시장 질문이 테마 되묻기를 덮어쓰면 안 된다
    expect(
      screen.queryByText("먼저 어떤 시장·종목을 대상으로 할지 정해볼까요?"),
    ).not.toBeInTheDocument();
  });

  it("검색으로도 못 찾은 테마(sector_unresolved)는 '전략을 만들 수 없다' 안내를 게이트가 삼키지 않는다", async () => {
    // '리센즈 관련주' 사고(2026-07-26): 검색 그라운딩까지 관련주를 못 찾아 백엔드가 종결
    // 안내를 보냈는데, 프론트 explicit 게이트의 시장 질문이 이를 덮어써 테마가 조용히
    // 일반 시장 질문으로 강등되던 회귀 가드.
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }
      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(createParseStreamResponseWithSectorNotFound());
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "리센즈 관련주 투자 하는 전략" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(/관련주를 찾을 수 없어 이 테마로는 전략을 만들 수 없어요/),
    ).toBeInTheDocument();
    // explicit 게이트의 시장 질문이 종결 안내를 덮어쓰면 안 된다
    expect(
      screen.queryByText("먼저 어떤 시장·종목을 대상으로 할지 정해볼까요?"),
    ).not.toBeInTheDocument();
  });

  it("조건 슬롯이 완성된 전략의 종목 명확화는 전략 빌더로 보내지 않는다", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }
      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(createParseStreamResponseWithNonConditionClarification());
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: {
        value:
          "코스피에서 최대 5종목, 매월 리밸런싱, 최근 5년 데이터, 초기 자금 1,000만원. 삼성전자와 SK하이닉스 중 하나로 완성해줘",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(
        "여러 종목이 지정되었습니다. 어느 종목을 대상으로 할까요?",
      )
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "삼성전자" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "SK하이닉스" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 입력" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/builder/step")).toBe(false);
  });

  it("리밸런싱 안 함을 선택하면 같은 질문을 반복하지 않고 다음 누락 조건으로 진행한다", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }
      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(createParseStreamResponseMissingRebalancing());
      }
      if (url === "/api/strategy/coach") {
        throw new Error(`누락 조건 입력 중 호출되면 안 되는 경로: ${url}`);
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: {
        value:
          "코스피에서 PER 10 이하, 최대 5종목, 최근 5년 데이터, 초기 자금 1,000만원 전략을 만들어줘",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(
        "다음으로 포트폴리오를 얼마나 자주 다시 구성할지 정해볼까요?",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "안 함" }));

    expect(
      await screen.findByText(
        "이제 익절 기준을 몇 %로 정할까요?",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        "다음으로 포트폴리오를 얼마나 자주 다시 구성할지 정해볼까요?",
      ),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => String(input) === "/api/strategy/parse/stream",
      ),
    ).toHaveLength(1);
  });

  it("단일 종목 빌더를 재파싱하지 않고 없음 답변 뒤 완성해 실행 버튼을 한 번 표시한다", async () => {
    let parseCallCount = 0;
    let builderCallCount = 0;
    const filterQuestion = "매수에 추가 필터를 넣을까요?";

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({
          intent: "STOCK_PICK",
          symbols: [{ symbol: "005930", name: "삼성전자" }],
        }));
      }
      if (url === "/api/strategy/parse/stream") {
        parseCallCount += 1;
        const body = JSON.parse(String(init?.body ?? "{}"));
        expect(parseCallCount).toBe(1);
        expect(body.prompt).toBe(
          "삼성전자에 투자 하는 전략, 최근 5년 데이터, 초기 자금 1,000만원",
        );
        return Promise.resolve(createSingleAssetParseStreamResponse());
      }
      if (url === "/api/strategy/builder/step") {
        builderCallCount += 1;
        const body = JSON.parse(String(init?.body ?? "{}"));
        if (builderCallCount === 1) {
          expect(body.state).toEqual({});
          expect(body.seed_parsed?.target_symbols).toEqual(["005930"]);
          return Promise.resolve(createJsonResponse({
            state: {},
            reply: "어떤 시장을 대상으로 할까요?",
            suggestions: ["코스피", "코스닥", "코스피200"],
          }));
        }
        if (builderCallCount === 2) {
          // 단일 종목 모드(FR-STR-068b): 프론트가 single_symbol을 전달하고, 백엔드가
          // 종목 프로파일 근거의 진입 방식 질문(횡단면 유형 제외)을 생성한다.
          expect(body.state).toMatchObject({
            single_symbol: "005930",
            single_label: "삼성전자 (005930)",
            universe: "KOSPI200",
            holding_count: 1,
            rebalance_cycle: "none",
          });
          return Promise.resolve(createJsonResponse({
            state: body.state,
            reply:
              "삼성전자 (005930) 단일 종목 전략이니 어떤 조건에서 사고팔지를 정하면 돼요. 어떤 진입 방식을 사용할까요?",
            suggestions: ["골든크로스", "MACD", "돌파", "거래량 급증", "과매도 반등"],
          }));
        }
        if (builderCallCount === 3) {
          expect(body.input).toBe("골든크로스");
          return Promise.resolve(createJsonResponse({
            state: {
              ...body.state,
              strategy_type: "golden_cross",
              ma_kind: "sma",
              ma_short: 5,
              ma_long: 20,
              stop_loss_pct: 10,
              take_profit_pct: 20,
              risk_done: true,
            },
            reply: filterQuestion,
            suggestions: ["없음"],
          }));
        }
        expect(body.input).toBe("없음");
        return Promise.resolve(createJsonResponse({
          state: { ...body.state, filters_asked: true },
          status: "confirmed",
          prompt: "코스피200 종목 중 골든크로스에서 매수하고 데드크로스에서 매도",
          parsed: completeSingleAssetStrategy,
          backtest_request: completeSingleAssetBacktestRequest,
        }));
      }
      if (url === "/api/strategy/coach") {
        return Promise.resolve(createJsonResponse({ message: "전략 검증 완료" }));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: {
        value: "삼성전자에 투자 하는 전략, 최근 5년 데이터, 초기 자금 1,000만원",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(
        "삼성전자 (005930) 단일 종목 전략이니 어떤 조건에서 사고팔지를 정하면 돼요. 어떤 진입 방식을 사용할까요?",
      )
    ).toBeInTheDocument();
    expect(screen.queryByText("어떤 시장을 대상으로 할까요?")).not.toBeInTheDocument();
    // 횡단면(종목 선별형) 유형은 단일 종목 선택지에 노출되지 않는다.
    expect(screen.queryByRole("button", { name: "모멘텀" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "저평가 가치주" })).not.toBeInTheDocument();
    // 자유 입력 진입로는 '직접 입력' 하나만 — '직접 설명하기'와 이중 노출하지 않는다.
    expect(screen.getAllByRole("button", { name: "직접 입력" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "직접 설명하기" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "골든크로스" }));

    expect(await screen.findByText(filterQuestion)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "없음" }));

    expect(await screen.findByText("전략 검증 완료", {}, { timeout: 5_000 })).toBeInTheDocument();
    expect(screen.getAllByText(filterQuestion)).toHaveLength(1);
    expect(screen.getByText("삼성전자 (005930)")).toBeInTheDocument();
    const runButton = screen.getByRole("button", { name: "백테스트 시작하기" });
    expect(screen.getAllByRole("button", { name: "백테스트 시작하기" })).toHaveLength(1);
    expect(screen.getByTestId("strategy-coach-bubble")).not.toContainElement(runButton);
    expect(screen.getByTestId("backtest-action")).toContainElement(runButton);
    expect(parseCallCount).toBe(1);
    expect(builderCallCount).toBe(4);
  });

  it("단일 종목 확정 카드에 종목명과 코드, 돌아가기 선택지를 표시한다", async () => {
    const awaitingCapital = {
      ...completeSingleAssetStrategy,
      initial_capital: 0,
    };
    sessionStorage.setItem("simons.strategyChatState", JSON.stringify({
      messages: [
        {
          role: "user",
          content: "삼성전자 골든크로스 전략, 최근 5년 데이터",
        },
        {
          role: "assistant",
          parsed: awaitingCapital,
          clarification: "초기 투자 자금을 얼마로 설정할까요?",
          clarificationSuggestions: ["500만원", "1,000만원", "3,000만원", "5,000만원"],
        },
      ],
      latestParsed: awaitingCapital,
      backtestReq: completeSingleAssetBacktestRequest,
      stage: "ready",
      // 초기 자금 질문에 도달한 세션이므로 그 앞 조건들은 이미 사용자가 답한 상태다.
      explicitFields: ["universe", "backtest_period"],
    }));
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      if (String(input) === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (String(input) === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.click(await screen.findByRole("button", { name: "1,000만원" }));

    const summary = await screen.findByTestId("builder-strategy-summary");
    expect(within(summary).getByText("유니버스")).toBeInTheDocument();
    expect(within(summary).getByText("삼성전자 (005930)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "이 전략으로 확정" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "돌아가기" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "돌아가기" }));

    expect(await screen.findByRole("button", { name: "1,000만원" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "이 전략으로 확정" })).not.toBeInTheDocument();
  });

  it("복원된 빌더가 채워진 이동평균 슬롯을 보존하고 청산 답변 뒤 이전 질문으로 돌아가지 않는다", async () => {
    const builderCalls: Array<Record<string, any>> = [];
    const riskQuestion =
      "마지막으로 청산 조건을 정해 주세요. 손절·익절·트레일링 스탑·보유기간 중 하나 이상을 자유롭게 말씀해 주세요.";

    sessionStorage.setItem("simons.strategyChatState", JSON.stringify({
      messages: [
        {
          role: "user",
          content: "삼성전자 골든크로스 전략, 최근 5년 데이터, 초기 자금 1,000만원",
        },
        {
          role: "assistant",
          infoText: "매수에 추가 필터를 넣을까요?",
          infoSuggestions: ["EMA200 위에서만"],
        },
      ],
      latestParsed: incompleteSingleAssetStrategy,
      backtestReq: incompleteSingleAssetBacktestRequest,
      stage: "ready",
      // 원문에서 사용자가 직접 말한 설정(최근 5년·1,000만원) — 복원되는 대화 상태의 일부다.
      explicitFields: ["backtest_period", "initial_capital"],
      builderMode: false,
      builderState: {
        universe: "KOSPI200",
        strategy_type: "golden_cross",
        ma_kind: "sma",
        ma_short: 5,
        ma_long: 20,
        filters_asked: false,
        holding_count: 1,
        rebalance_cycle: "none",
        risk_done: false,
      },
    }));

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify" || url === "/api/strategy/parse/stream") {
        throw new Error(`빌더 진행 중 호출되면 안 되는 경로: ${url}`);
      }
      if (url === "/api/strategy/builder/step") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        builderCalls.push(body);

        if (builderCalls.length === 1) {
          expect(body).toMatchObject({
            input: "EMA200 위에서만",
            state: {
              strategy_type: "golden_cross",
              ma_kind: "sma",
              ma_short: 5,
              ma_long: 20,
            },
          });
          // 일부 필드만 돌아와도 프론트가 기존 슬롯을 유지해야 한다.
          return Promise.resolve(createJsonResponse({
            state: {
              filters_asked: true,
              trend_filter_ma: 200,
            },
            reply: riskQuestion,
            suggestions: ["10% 손절·20% 익절"],
          }));
        }

        expect(body).toMatchObject({
          input: "10% 손절·20% 익절",
          state: {
            universe: "KOSPI200",
            strategy_type: "golden_cross",
            ma_kind: "sma",
            ma_short: 5,
            ma_long: 20,
            filters_asked: true,
            trend_filter_ma: 200,
            holding_count: 1,
            rebalance_cycle: "none",
          },
        });
        return Promise.resolve(createJsonResponse({
          state: {
            ...body.state,
            stop_loss_pct: 10,
            take_profit_pct: 20,
            risk_done: true,
          },
          status: "confirmed",
          prompt: "삼성전자 골든크로스, EMA200 위, 10% 손절, 20% 익절",
          parsed: completeSingleAssetStrategy,
          backtest_request: completeSingleAssetBacktestRequest,
        }));
      }
      if (url === "/api/strategy/coach") {
        return Promise.resolve(createJsonResponse({ message: "전략 정의가 완료되었습니다." }));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.click(await screen.findByRole("button", { name: "EMA200 위에서만" }));
    fireEvent.click(await screen.findByRole("button", { name: "10% 손절·20% 익절" }));

    expect(
      await screen.findByText("전략 정의가 완료되었습니다.", {}, { timeout: 5_000 })
    ).toBeInTheDocument();
    expect(screen.queryByText("어떤 이동평균을 쓸까요?")).not.toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "백테스트 시작하기" })
    ).toHaveLength(1);
    expect(builderCalls).toHaveLength(2);
  });

  it("빌더 확정 결과가 파싱 폴백을 거쳐도 채워진 슬롯을 유지하고 이전 질문으로 돌아가지 않는다", async () => {
    const builderCalls: Array<Record<string, any>> = [];

    sessionStorage.setItem("simons.strategyChatState", JSON.stringify({
      messages: [
        {
          role: "user",
          content: "삼성전자 골든크로스 전략, 최근 5년 데이터, 초기 자금 1,000만원",
        },
        {
          role: "assistant",
          infoText: "마지막으로 청산 조건을 정해 주세요.",
          infoSuggestions: ["10% 손절·20% 익절"],
          builderQuestion: true,
        },
      ],
      latestParsed: incompleteSingleAssetStrategy,
      backtestReq: incompleteSingleAssetBacktestRequest,
      stage: "ready",
      // 원문에서 사용자가 직접 말한 설정(최근 5년·1,000만원) — 복원되는 대화 상태의 일부다.
      explicitFields: ["backtest_period", "initial_capital"],
      builderMode: true,
      builderState: {
        universe: "KOSPI200",
        strategy_type: "golden_cross",
        ma_kind: "sma",
        ma_short: 5,
        ma_long: 20,
        filters_asked: true,
        trend_filter_ma: 200,
        holding_count: 1,
        rebalance_cycle: "none",
        risk_done: false,
      },
    }));

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/strategy/builder/step") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        builderCalls.push(body);

        expect(body.state).toMatchObject({
          strategy_type: "golden_cross",
          ma_kind: "sma",
          ma_short: 5,
          ma_long: 20,
          filters_asked: true,
          trend_filter_ma: 200,
        });

        if (builderCalls.length === 1) {
          expect(body.input).toBe("10% 손절·20% 익절");
          return Promise.resolve(createJsonResponse({
            state: {
              ...body.state,
              stop_loss_pct: 10,
              take_profit_pct: 20,
              risk_done: true,
            },
            status: "confirmed",
            prompt: "삼성전자 골든크로스, EMA200 위, 10% 손절, 20% 익절",
          }));
        }

        expect(body.input).toBe("");
        return Promise.resolve(createJsonResponse({
          state: body.state,
          status: "confirmed",
          prompt: "삼성전자 골든크로스, EMA200 위, 10% 손절, 20% 익절",
          parsed: completeSingleAssetStrategy,
          backtest_request: completeSingleAssetBacktestRequest,
        }));
      }
      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(createSingleAssetParseStreamResponse(false));
      }
      if (url === "/api/strategy/coach") {
        return Promise.resolve(createJsonResponse({ message: "전략 정의가 완료되었습니다." }));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.click(await screen.findByRole("button", { name: "10% 손절·20% 익절" }));

    expect(
      await screen.findByText("전략 정의가 완료되었습니다.", {}, { timeout: 5_000 })
    ).toBeInTheDocument();
    expect(screen.queryByText("어떤 이동평균을 쓸까요?")).not.toBeInTheDocument();
    expect(screen.getByText("삼성전자 (005930)")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "백테스트 시작하기" })).toHaveLength(1);
    expect(builderCalls).toHaveLength(2);
  });

  it("대화 종료 후 이전 빌더 상태를 버리고 새 질문의 조건을 다시 파싱한다", async () => {
    let classifyCallCount = 0;
    let builderCallCount = 0;

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        classifyCallCount += 1;
        return Promise.resolve(createJsonResponse(
          classifyCallCount === 1
            ? { intent: "STRATEGY_PICK", symbols: [] }
            : {
                intent: "STOCK_PICK",
                symbols: [{ symbol: "005930", name: "삼성전자" }],
              },
        ));
      }
      if (url === "/api/strategy/parse/stream") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        expect(body.prompt).toBe("삼성전자에 투자 하는 전략");
        return Promise.resolve(createSingleAssetParseStreamResponse());
      }
      if (url === "/api/strategy/builder/step") {
        builderCallCount += 1;
        const body = JSON.parse(String(init?.body ?? "{}"));
        if (builderCallCount <= 2) {
          return Promise.resolve(createJsonResponse({
            state: body.state ?? {},
            reply: "어떤 시장을 대상으로 할까요?",
            suggestions: ["코스피", "코스닥", "코스피200"],
          }));
        }
        expect(body.state).toMatchObject({
          single_symbol: "005930",
          universe: "KOSPI200",
          holding_count: 1,
          rebalance_cycle: "none",
        });
        return Promise.resolve(createJsonResponse({
          state: body.state,
          reply:
            "삼성전자 (005930) 단일 종목 전략이니 어떤 조건에서 사고팔지를 정하면 돼요. 어떤 진입 방식을 사용할까요?",
          suggestions: ["골든크로스", "MACD", "돌파", "거래량 급증", "과매도 반등"],
        }));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "어떤 전략이 좋아?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
    expect(await screen.findByText("어떤 시장을 대상으로 할까요?")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "대화 종료" }));

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "삼성전자에 투자 하는 전략" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(
        "삼성전자 (005930) 단일 종목 전략이니 어떤 조건에서 사고팔지를 정하면 돼요. 어떤 진입 방식을 사용할까요?",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("어떤 시장을 대상으로 할까요?")).not.toBeInTheDocument();
    expect(classifyCallCount).toBe(2);
    expect(builderCallCount).toBe(3);
  });

  it("유니버스 이후 조건에서는 뒤로가기를 제공하고 유니버스 질문으로 복원한다", async () => {
    const builderRequests: Array<{ state: Record<string, unknown>; input: string }> = [];

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_PICK", symbols: [] }));
      }
      if (url === "/api/strategy/builder/step") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        builderRequests.push({ state: body.state ?? {}, input: body.input ?? "" });
        if (body.input === "코스피" || body.state?.universe) {
          return Promise.resolve(createJsonResponse({
            state: { universe: "KOSPI" },
            reply: "어떤 방식으로 종목을 고를까요?",
            suggestions: ["모멘텀", "골든크로스", "MACD"],
          }));
        }
        if (!body.state?.universe) {
          return Promise.resolve(createJsonResponse({
            state: {},
            reply: "어떤 시장을 대상으로 할까요?",
            suggestions: ["코스피", "코스닥", "코스피200"],
          }));
        }
        return Promise.resolve(createJsonResponse({}));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "어떤 전략이 좋아?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(await screen.findByText("어떤 시장을 대상으로 할까요?")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("strategy-progress-panel")).getByRole("listitem", {
        name: "유니버스: 진행 전",
      }),
    ).toHaveAttribute("data-complete", "false");
    expect(screen.queryByRole("button", { name: "직접 입력" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "뒤로가기" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "코스피" }));

    expect(await screen.findByText("어떤 방식으로 종목을 고를까요?")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("strategy-progress-panel")).getByRole("listitem", {
        name: "유니버스: 완료",
      }),
    ).toHaveAttribute("data-complete", "true");
    expect(screen.getByRole("button", { name: "직접 입력" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "뒤로가기" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "뒤로가기" }));

    await waitFor(() => {
      expect(builderRequests.at(-1)).toEqual({ state: {}, input: "" });
      expect(screen.getAllByText("어떤 시장을 대상으로 할까요?")).toHaveLength(2);
      expect(
        within(screen.getByTestId("strategy-progress-panel")).getByRole("listitem", {
          name: "유니버스: 진행 전",
        }),
      ).toHaveAttribute("data-complete", "false");
    });
    expect(screen.queryByRole("button", { name: "직접 입력" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "뒤로가기" })).not.toBeInTheDocument();
  });

  it("scrolls to the bottom when a follow-up coach reply updates the existing assistant message", async () => {
    const followUpResponse = createDeferred<Response>();

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }

      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({
          user: {
            name: "Tester",
            email: "tester@example.com",
          },
        }));
      }

      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }

      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(createParseStreamResponse());
      }

      if (url === "/api/strategy/coach") {
        const body = JSON.parse(String(init?.body ?? "{}")) as { action?: string };

        if (body.action === "follow_up") {
          return followUpResponse.promise;
        }

        return Promise.resolve(createJsonResponse(
          { message: "첫 번째 코치 응답입니다." },
          { "X-Coach-Session-Id": "coach-session-1" }
        ));
      }

      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, {
      target: {
        value:
          "코스피에서 PER 10 이하, 최대 5종목, 매월 리밸런싱, 최근 5년 데이터, 초기 자금 1,000만원 전략 만들어줘",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    // 전략 검증은 의도된 최소 지연(~2.4s) 후 응답을 노출하므로 타임아웃을 넉넉히 둔다.
    expect(
      await screen.findByText("첫 번째 코치 응답입니다.", undefined, { timeout: 5000 })
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "백테스트 시작하기" })
    ).toHaveLength(1);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "어떻게 개선할까?" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(await screen.findByText("검증 중...")).toBeInTheDocument();
    scrollToMock.mockClear();

    followUpResponse.resolve(
      createJsonResponse({ message: "후속 코치 응답입니다. 손절 기준을 더 명확히 해보세요." })
    );

    expect(
      await screen.findByText("후속 코치 응답입니다. 손절 기준을 더 명확히 해보세요.", undefined, {
        timeout: 5000,
      })
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(scrollToMock).toHaveBeenCalled();
    });
  });

  it("asks for a percentage instead of reparsing when take profit is requested without a value", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }

      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({
          user: {
            name: "Tester",
            email: "tester@example.com",
          },
        }));
      }

      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }

      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(createParseStreamResponse());
      }

      if (url === "/api/strategy/coach") {
        return Promise.resolve(createJsonResponse(
          { message: "첫 번째 코치 응답입니다." },
          { "X-Coach-Session-Id": "coach-session-1" }
        ));
      }

      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, {
      target: {
        value:
          "코스피에서 PER 10 이하, 최대 5종목, 매월 리밸런싱, 최근 5년 데이터, 초기 자금 1,000만원 전략 만들어줘",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText("첫 번째 코치 응답입니다.", undefined, { timeout: 5000 })
    ).toBeInTheDocument();
    const summaryCountBeforeFollowUp = screen.getAllByText("전략 요약").length;

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "익절을 추가해 볼까?" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(
        "익절 기준은 매수가 대비 수익률로 설정합니다. 예시 값은 5%, 10%, 15%입니다. 적용할 익절 기준을 몇 %로 할까요?"
      )
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "익절 5%" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "익절 10%" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "익절 15%" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 입력" })).toBeInTheDocument();
    expect(screen.getAllByText("전략 요약")).toHaveLength(summaryCountBeforeFollowUp);
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/strategy/parse/stream")).toHaveLength(1);
  });

  it("shows a chat-only invitation with the strategy summary card for a symbols-change intent", async () => {
    // '종목을 변경 할 수 있나?' 사고(2026-07-26): 수정 파싱으로 흘러 무변경 재렌더링+다음
    // 조건 질문이 뜨던 회귀 가드 — 칩 없이 채팅 입력 안내만 보여주고, '현재까지 이해한
    // 전략입니다' 요약 카드를 항상 함께 표시한다(사용자 결정).
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }
      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(createParseStreamResponse());
      }
      if (url === "/api/strategy/coach") {
        return Promise.resolve(createJsonResponse(
          { message: "코치 응답입니다." },
          { "X-Coach-Session-Id": "coach-session-1" }
        ));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: {
        value:
          "코스피에서 PER 10 이하, 최대 5종목, 매월 리밸런싱, 최근 5년 데이터, 초기 자금 1,000만원 전략 만들어줘",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText("코치 응답입니다.", undefined, { timeout: 5000 })
    ).toBeInTheDocument();
    const parseCallsBeforeFollowUp = fetchMock.mock.calls.filter(
      ([input]) => String(input) === "/api/strategy/parse/stream",
    ).length;

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "종목을 변경 할 수 있나?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(/네, 대상 종목은 언제든 바꿀 수 있어요/)
    ).toBeInTheDocument();
    // 요약 카드가 안내와 함께 표시된다
    expect(screen.getByText("현재까지 이해한 전략입니다")).toBeInTheDocument();
    // 칩 없이 채팅 입력만 — 종목 선택 칩·다음 조건 질문이 뜨면 안 된다
    expect(screen.queryByText(/만으로 백테스트해줘$/)).not.toBeInTheDocument();
    expect(
      screen.queryByText("다음으로 어떤 조건에서 매수할지 정해볼까요?"),
    ).not.toBeInTheDocument();
    // 재파싱 없이 결정론 즉답이어야 한다
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input) === "/api/strategy/parse/stream"),
    ).toHaveLength(parseCallsBeforeFollowUp);
  });

  it("answers a short-term versus long-term comparison without starting the strategy builder", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }

      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({
          user: {
            name: "Tester",
            email: "tester@example.com",
          },
        }));
      }

      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "단기 전략 장기 전략 뭐가 좋을까?" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(/연구할 보유기간과 거래 빈도 가정이 다릅니다/)
    ).toBeInTheDocument();
    expect(screen.getByText(/수수료·슬리피지와 신호 변화의 영향/)).toBeInTheDocument();
    expect(screen.queryByText("어떤 시장을 대상으로 할까요?")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/builder/step")).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/parse/stream")).toBe(false);
  });

  it("asks for a long holding period before continuing with the remaining builder questions", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }

      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({
          user: {
            name: "Tester",
            email: "tester@example.com",
          },
        }));
      }

      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }

      if (url === "/api/strategy/builder/step") {
        const body = JSON.parse(String(init?.body ?? "{}")) as {
          seed?: string;
          state?: { hold_period_days?: number; risk_done?: boolean };
        };
        expect(body.seed).toBe("장기전략으로 만들어 볼까?");
        expect(body.state).toMatchObject({ hold_period_days: 504, risk_done: true });

        return Promise.resolve(createJsonResponse({
          state: {
            hold_period_days: 504,
            risk_done: true,
          },
          reply: "504거래일 보유 조건을 반영했습니다. 어떤 시장을 대상으로 할까요?",
          suggestions: ["코스피", "코스닥", "코스피200", "코스피·코스닥 전체"],
        }));
      }

      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "장기전략으로 만들어 볼까?" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText("바이 앤 홀드 전략으로 이해했어요. 얼마나 오래 보유할까요?")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "252거래일 (1년)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "504거래일 (2년)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "756거래일 (3년)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1,260거래일 (5년)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 입력" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/parse/stream")).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/builder/step")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "504거래일 (2년)" }));

    expect(
      await screen.findByText("504거래일 보유 조건을 반영했습니다. 어떤 시장을 대상으로 할까요?")
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/strategy/builder/step")).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/query/classify")).toHaveLength(1);
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/parse/stream")).toBe(false);
  });

  it("asks for a short holding period before continuing with the remaining builder questions", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }

      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({
          user: {
            name: "Tester",
            email: "tester@example.com",
          },
        }));
      }

      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }

      if (url === "/api/strategy/builder/step") {
        const body = JSON.parse(String(init?.body ?? "{}")) as {
          seed?: string;
          state?: { hold_period_days?: number; risk_done?: boolean };
        };
        expect(body.seed).toBe("단기 투자 전략을 만들어보자");
        expect(body.state).toMatchObject({ hold_period_days: 10, risk_done: true });

        return Promise.resolve(createJsonResponse({
          state: {
            hold_period_days: 10,
            risk_done: true,
          },
          reply: "10거래일 보유 조건을 반영했습니다. 어떤 시장을 대상으로 할까요?",
          suggestions: ["코스피", "코스닥", "코스피200", "코스피·코스닥 전체"],
        }));
      }

      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "단기 투자 전략을 만들어보자" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText("단기 매매 전략으로 이해했어요. 얼마나 오래 보유할까요?")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1거래일 (당일)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "5거래일 (1주)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "10거래일 (2주)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "20거래일 (약 1개월)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "60거래일 (약 3개월)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 입력" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/parse/stream")).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/builder/step")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "10거래일 (2주)" }));

    expect(
      await screen.findByText("10거래일 보유 조건을 반영했습니다. 어떤 시장을 대상으로 할까요?")
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/strategy/builder/step")).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/query/classify")).toHaveLength(1);
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/parse/stream")).toBe(false);
  });
});

describe("strategy builder progress presentation", () => {
  it("moves completed items first and normalizes the legacy target label", () => {
    expect(
      getDisplayBuilderProgressItems([
        { label: "투자 대상", complete: false },
        { label: "매수 조건", complete: true },
        { label: "매도 조건", complete: false },
        { label: "초기 자본", complete: true },
      ]),
    ).toEqual([
      { label: "매수 조건", complete: true },
      { label: "초기 자본", complete: true },
      { label: "유니버스", complete: false },
      { label: "매도 조건", complete: false },
    ]);
  });

  it("summarizes a profitable-company seed as EPS above zero only", () => {
    const parsed = {
      description: "작년도 흑자종목을 매수 하는 전략",
      universe: ["KOSPI200"],
      fundamental_filters: [{ metric: "eps", operator: ">", value: 0 }],
      entry_signals: [],
      exit_signals: [],
      max_positions: 10,
      hold_period_days: null,
      rebalancing_period: "none",
      stop_loss_pct: null,
      take_profit_pct: null,
      backtest_period: "5y",
      initial_capital: 10000000,
    };
    const result = buildBuilderTurnPresentation({
      state: {},
      reply: "청산 조건이 빠져 있습니다. 어떤 조건에서 청산할까요?",
      parsed,
      explicitFields: [],
    });

    expect(result.summaryItems).toContainEqual({
      label: "매수 조건",
      value: "흑자 기업 (EPS > 0)",
    });
    expect(
      result.summaryItems
        .some((item) =>
          ["유니버스", "최대 보유", "리밸런싱", "백테스트 기간", "초기 자본"]
            .includes(item.label),
        ),
    ).toBe(false);
    expect(result.progressItems).toEqual([
      { label: "유니버스", complete: false },
      { label: "매수 조건", complete: true },
      { label: "매도 조건", complete: false },
      { label: "최대 보유", complete: false },
      { label: "리밸런싱", complete: false },
      { label: "리스크 관리", complete: false },
      { label: "백테스트 기간", complete: false },
      { label: "초기 자본", complete: false },
    ]);
    expect(result.summaryItems.some((item) => item.value.includes("순이익증가율"))).toBe(false);
    expect(result.question).toBe("이제 언제 매도할지 정해볼까요?");

    const explicitResult = buildBuilderTurnPresentation({
      state: {},
      reply: "이제 언제 매도할지 정해볼까요?",
      parsed: { ...parsed, rebalancing_period: "weekly" },
      explicitFields: ["universe", "max_positions", "rebalancing"],
    });
    expect(explicitResult.summaryItems).toEqual(expect.arrayContaining([
      { label: "유니버스", value: "KOSPI 200" },
      { label: "최대 보유", value: "10종목" },
      { label: "리밸런싱", value: "매주" },
    ]));

    const explicitCapitalResult = buildBuilderTurnPresentation({
      state: {},
      reply: "이제 언제 매도할지 정해볼까요?",
      parsed: { ...parsed, initial_capital: 50_000_000 },
      explicitFields: ["initial_capital"],
    });
    expect(explicitCapitalResult.summaryItems).toContainEqual({
      label: "초기 자본",
      value: "50,000,000원",
    });
  });

  it("shows target stock names from backtest_request instead of raw codes", () => {
    const parsed = {
      description: "bts 관련 종목 골든크로스 전략",
      universe: [],
      target_symbols: ["352820", "035900"],
      fundamental_filters: [],
      entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
      exit_signals: [],
      max_positions: 10,
      hold_period_days: null,
      rebalancing_period: "none",
      stop_loss_pct: null,
      take_profit_pct: null,
      backtest_period: "5y",
      initial_capital: 10000000,
    };

    const result = buildBuilderTurnPresentation({
      state: {},
      reply: "이제 언제 매도할지 정해볼까요?",
      parsed,
      explicitFields: ["universe"],
      backtestRequest: {
        target_stocks: [
          { symbol: "352820", name: "하이브" },
          { symbol: "035900", name: "JYP Ent." },
        ],
      },
    });
    expect(result.summaryItems).toContainEqual({
      label: "유니버스",
      value: "하이브 (352820) · JYP Ent. (035900)",
    });

    // 요청 정보가 없으면 종전처럼 코드만 표시된다(이름 미해석 폴백).
    const withoutRequest = buildBuilderTurnPresentation({
      state: {},
      reply: "이제 언제 매도할지 정해볼까요?",
      parsed,
      explicitFields: ["universe"],
    });
    expect(withoutRequest.summaryItems).toContainEqual({
      label: "유니버스",
      value: "352820 · 035900",
    });
  });

  it("asks for each former default condition before allowing a backtest", () => {
    const explicitOptions = {
      requireExplicitConfiguration: true,
    };

    expect(getNextMissingBacktestCondition(parsedStrategy, {
      ...explicitOptions,
      explicitFields: [],
    })).toMatchObject({
      field: "universe",
      suggestions: ["코스피200", "코스피", "코스닥", "코스피+코스닥"],
    });
    expect(getNextMissingBacktestCondition(parsedStrategy, {
      ...explicitOptions,
      explicitFields: ["universe"],
    })).toMatchObject({
      field: "max_positions",
      suggestions: ["최대 5종목", "최대 10종목", "최대 20종목"],
    });
    expect(getNextMissingBacktestCondition(parsedStrategy, {
      ...explicitOptions,
      explicitFields: ["universe", "max_positions"],
    })?.field).toBe("rebalancing");
    expect(getNextMissingBacktestCondition(parsedStrategy, {
      ...explicitOptions,
      explicitFields: ["universe", "max_positions", "rebalancing"],
    })?.field).toBe("backtest_period");
    expect(getNextMissingBacktestCondition(parsedStrategy, {
      ...explicitOptions,
      explicitFields: ["universe", "max_positions", "rebalancing", "backtest_period"],
    })).toMatchObject({
      field: "initial_capital",
      suggestions: ["500만원", "1,000만원", "3,000만원", "5,000만원"],
    });
    expect(getNextMissingBacktestCondition(parsedStrategy, {
      ...explicitOptions,
      explicitFields: [
        "universe",
        "max_positions",
        "rebalancing",
        "backtest_period",
        "initial_capital",
      ],
    })).toBeNull();
  });

  it("uses collaborative wording for required strategy fields", () => {
    expect(
      makeBuilderQuestionFriendly(
        "리밸런싱 주기가 빠져 있습니다. 포트폴리오를 얼마나 자주 다시 구성할까요?",
      ),
    ).toBe("다음으로 포트폴리오를 얼마나 자주 다시 구성할지 정해볼까요?");
    expect(makeBuilderQuestionFriendly("마지막으로 청산 조건을 정해 주세요.")).toBe(
      "이제 언제 매도할지 정하면 전략이 완성됩니다. 매도 조건을 함께 정해볼까요?",
    );
  });
});

describe("deterministic condition selection", () => {
  it("applies every guided condition without another parser result", () => {
    let current = {
      ...incompleteParsedStrategy,
      universe: [],
      fundamental_filters: [],
      entry_signals: [],
      max_positions: 0,
      backtest_period: "",
      initial_capital: 0,
    };
    const choose = (
      field: MissingBacktestCondition["field"],
      choice: string,
    ) => {
      const result = applyDeterministicConditionChoice({
        parsed: current,
        condition: { field, question: "", suggestions: [choice] },
        choice,
      });
      expect(result).not.toBeNull();
      current = result!.parsed;
      return result!;
    };

    choose("universe", "코스피+코스닥");
    choose("entry", "RSI 30 이하에서 매수");
    choose("exit", "RSI 70 이상에서 매도");
    choose("max_positions", "최대 20종목");
    const rebalancing = choose("rebalancing", "안 함");
    choose("stop_loss", "손절 -15%");   // 부호는 표기 — 적용 값은 크기(15)
    choose("take_profit", "익절 30%");
    choose("backtest_period", "사용 가능한 전체 데이터");
    choose("initial_capital", "5,000만원");

    expect(current).toMatchObject({
      universe: ["KOSPI", "KOSDAQ"],
      max_positions: 20,
      rebalancing_period: "none",
      stop_loss_pct: 15,
      take_profit_pct: 30,
      backtest_period: "full",
      initial_capital: 50_000_000,
    });
    expect(current.entry_signals).toEqual([{
      indicator: "rsi",
      signal_type: "buy",
      operator: "<=",
      value: 30,
    }]);
    expect(current.exit_signals).toEqual([{
      indicator: "rsi",
      signal_type: "sell",
      operator: ">=",
      value: 70,
    }]);
    expect(rebalancing.allowNoRebalancing).toBe(true);
  });

  // 매수 조건 예시 칩 문구와 결정적 매핑 키가 어긋나면 칩 선택이 조용히 파서 폴백으로
  // 새어 나간다 — 제안된 모든 칩이 결정적으로 적용되는지 잠근다.
  it("applies every suggested entry chip deterministically", () => {
    const parsed = {
      ...incompleteParsedStrategy,
      fundamental_filters: [],
      entry_signals: [],
    };
    const condition = getNextMissingBacktestCondition(parsed, {
      requireExplicitConfiguration: true,
      explicitFields: ["universe"],
    });
    expect(condition?.field).toBe("entry");
    for (const choice of condition!.suggestions) {
      const result = applyDeterministicConditionChoice({
        parsed,
        condition: condition!,
        choice,
      });
      expect(result, `칩 "${choice}"이 결정적으로 적용되지 않음`).not.toBeNull();
      const next = result!.parsed;
      expect(
        (next.entry_signals?.length ?? 0) + (next.fundamental_filters?.length ?? 0),
      ).toBe(1);
    }
  });

  it("leaves free-form choices for the parser", () => {
    expect(
      applyDeterministicConditionChoice({
        parsed: incompleteParsedStrategy,
        condition: {
          field: "entry",
          question: "",
          suggestions: ["직접 입력"],
        },
        choice: "직접 입력",
      }),
    ).toBeNull();
  });
});
