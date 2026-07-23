import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

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

function createParseStreamResponse() {
  const encoder = new TextEncoder();
  const payload = [
    `data: ${JSON.stringify({ type: "parsed_final", parsed: parsedStrategy })}\n\n`,
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
    `data: ${JSON.stringify({ type: "parsed_final", parsed })}\n\n`,
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
      clarification_question: complete
        ? null
        : "청산 조건 — 언제 팔까요?\n\n예: 데드크로스 발생 시 매도, 20일 보유 후 청산",
      clarification_suggestions: complete
        ? null
        : ["20일 보유 후 청산", "데드크로스 발생 시 매도"],
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
        return Promise.resolve(createParseStreamResponseWithClarification());
      }
      if (url === "/api/strategy/builder/step") {
        throw new Error(`파싱 결과를 다시 빌더로 보내면 안 되는 경로: ${url}`);
      }
      if (url === "/api/strategy/coach") {
        throw new Error(`누락 조건 입력 전에 호출되면 안 되는 경로: ${url}`);
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "영업이익률이 높은 조건도 넣어줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText("청산 조건이 빠져 있습니다. 어떤 조건에서 청산할까요?"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/영업이익률 몇 % 이상으로 설정할까요/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "데드크로스 발생 시 매도" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "20일 보유 후 청산" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "RSI 70 이상에서 매도" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 입력" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/builder/step")).toBe(false);
    expect(
      fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/coach")
    ).toBe(false);
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
      target: { value: "삼성전자와 SK하이닉스 중 하나로 완성해줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(
        "세부 조건이 빠져 있습니다. 여러 종목이 지정되었습니다. 어느 종목을 대상으로 할까요?",
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
      target: { value: "PER 10 이하 전략을 만들어줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(
        "리밸런싱 주기가 빠져 있습니다. 포트폴리오를 얼마나 자주 다시 구성할까요?",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "안 함" }));

    expect(
      await screen.findByText(
        "익절 기준이 빠져 있습니다. 익절 기준을 몇 %로 설정할까요?",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        "리밸런싱 주기가 빠져 있습니다. 포트폴리오를 얼마나 자주 다시 구성할까요?",
      ),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => String(input) === "/api/strategy/parse/stream",
      ),
    ).toHaveLength(2);
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
        expect(body.prompt).toBe("삼성전자에 투자 하는 전략");
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
          expect(body.state).toMatchObject({
            universe: "KOSPI200",
            holding_count: 1,
            rebalance_cycle: "none",
          });
          return Promise.resolve(createJsonResponse({
            state: body.state,
            reply: "어떤 방식으로 종목을 고를까요?",
            suggestions: ["모멘텀", "골든크로스", "저평가 가치주"],
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
          parsed: parsedStrategy,
          backtest_request: backtestRequest,
        }));
      }
      if (url === "/api/strategy/coach") {
        return Promise.resolve(createJsonResponse({ message: "전략 검증 완료" }));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "삼성전자에 투자 하는 전략" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText("삼성전자 (005930) 단일 종목 전략으로 설정했습니다. 어떤 진입 조건을 사용할까요?")
    ).toBeInTheDocument();
    expect(screen.queryByText("어떤 시장을 대상으로 할까요?")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "모멘텀" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "저평가 가치주" })).not.toBeInTheDocument();

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

  it("복원된 빌더가 채워진 이동평균 슬롯을 보존하고 청산 답변 뒤 이전 질문으로 돌아가지 않는다", async () => {
    const builderCalls: Array<Record<string, any>> = [];
    const riskQuestion =
      "마지막으로 청산 조건을 정해 주세요. 손절·익절·트레일링 스탑·보유기간 중 하나 이상을 자유롭게 말씀해 주세요.";

    sessionStorage.setItem("simons.strategyChatState", JSON.stringify({
      messages: [
        { role: "user", content: "삼성전자 골든크로스 전략" },
        {
          role: "assistant",
          infoText: "매수에 추가 필터를 넣을까요?",
          infoSuggestions: ["EMA200 위에서만"],
        },
      ],
      latestParsed: incompleteSingleAssetStrategy,
      backtestReq: incompleteSingleAssetBacktestRequest,
      stage: "ready",
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
        { role: "user", content: "삼성전자 골든크로스 전략" },
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
          universe: "KOSPI200",
          holding_count: 1,
          rebalance_cycle: "none",
        });
        return Promise.resolve(createJsonResponse({
          state: body.state,
          reply: "어떤 방식으로 종목을 고를까요?",
          suggestions: ["모멘텀", "골든크로스", "저평가 가치주"],
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
        "삼성전자 (005930) 단일 종목 전략으로 설정했습니다. 어떤 진입 조건을 사용할까요?",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("어떤 시장을 대상으로 할까요?")).not.toBeInTheDocument();
    expect(classifyCallCount).toBe(2);
    expect(builderCallCount).toBe(3);
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
    fireEvent.change(textarea, { target: { value: "PER 10 이하 전략 만들어줘" } });
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
    fireEvent.change(textarea, { target: { value: "PER 10 이하 전략 만들어줘" } });
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
