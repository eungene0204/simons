// 백테스트 결과 화면을 닫고(뒤로가기·결과 닫기·탑메뉴 '전략연구소') 대화 화면으로
// 돌아올 때 스크롤이 항상 맨 위에서 시작하는지 확인한다(2026-08-17 지시 — 이전의
// '대화 끝까지 올리기'를 대체). 회귀: 복귀 시 문서 끝(scrollHeight)으로 스크롤하던 동작.
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";
import { requestStrategyLabChatView } from "@/components/strategy/strategyTemplateSession";

const push = vi.fn();
const back = vi.fn();
const fetchMock = vi.fn();

const parsedStrategy = {
  description: "영업이익 흑자인 기업 투자 전략",
  universe: ["KOSPI"],
  fundamental_filters: [
    { metric: "operating_income_growth", operator: ">=", value: 0 },
  ],
  entry_signals: [],
  exit_signals: [],
  max_positions: 5,
  hold_period_days: null,
  rebalancing_period: "monthly",
  stop_loss_pct: 10,
  take_profit_pct: 30,
  trailing_stop_pct: null,
  backtest_period: "5y",
  initial_capital: 10000000,
};

const backtestRequest = {
  symbols: ["005930", "000660"],
  universe_id: "kospi",
  entry: {
    conditions: [
      { type: "filter", id: "operating_income_growth", params: { operator: ">=", value: 0 } },
    ],
  },
  exit: { conditions: [] },
  risk: {
    max_positions: 5,
    init_cash: 10000000,
    stop_loss_pct: 10,
    take_profit_pct: 30,
  },
  period: "5y",
  options: { fee_rate: 0.015, slippage_rate: 0.05 },
};

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, back }),
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

// 실제 대시보드는 recharts·동적 임포트 덩어리라 결과 화면 노출 여부만 확인하도록 대체한다.
vi.mock("@/components/strategy/backtest/BacktestDashboard", () => ({
  default: ({ result }: { result: { totalReturn?: number } }) => (
    <div data-testid="backtest-dashboard">결과 화면 {String(result?.totalReturn)}</div>
  ),
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      signInWithOAuth: vi.fn(),
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  }),
}));

function createJsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function createParseStreamResponse() {
  const encoder = new TextEncoder();
  const payload = [
    // 프롬프트가 다섯 설정을 모두 말했으므로 백엔드 provenance도 전부를 명시로 보고한다.
    `data: ${JSON.stringify({
      type: "parsed_final",
      parsed: parsedStrategy,
      explicit_fields: [
        "universe",
        "max_positions",
        "rebalancing",
        "backtest_period",
        "initial_capital",
      ],
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
    { status: 200 },
  );
}

/** status 이벤트만 먼저 흘리고, result는 테스트가 원하는 시점에 밀어 넣는 스트림. */
function createControlledBacktestStream(totalReturn: number) {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;

  const response = new Response(
    new ReadableStream<Uint8Array>({
      start(c) {
        controller = c;
        c.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: "status", message: "거래 내역 집계 중..." })}\n\n`),
        );
      },
    }),
    { status: 200 },
  );

  const finish = () => {
    controller.enqueue(
      encoder.encode(
        `data: ${JSON.stringify({
          type: "result",
          data: {
            metrics: { total_return: totalReturn },
            equity_curve: [],
            trades: [],
          },
        })}\n\n`,
      ),
    );
    controller.enqueue(encoder.encode("data: [DONE]\n\n"));
    controller.close();
  };

  return { response, finish };
}

describe("결과 화면 복귀 스크롤", () => {
  const scrollToMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.stubGlobal("scrollTo", scrollToMock);
    // jsdom Element에는 scrollTo가 없다 — 결과 화면 진입 시 스크롤 초기화가 크래시한다.
    Element.prototype.scrollTo = vi.fn();
    // jsdom은 문서 높이가 0이라 '맨 위'와 '문서 끝'이 구분되지 않는다 — 긴 문서로 흉내낸다.
    Object.defineProperty(document.documentElement, "scrollHeight", {
      value: 3000,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete (document.documentElement as unknown as Record<string, unknown>).scrollHeight;
  });

  function mockBacktestFlow(run: ReturnType<typeof createControlledBacktestStream>) {
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
        return Promise.resolve(createJsonResponse({ message: "전략 검증 완료" }));
      }
      if (url === "/api/strategy/backtest-stream") {
        return Promise.resolve(run.response);
      }
      return Promise.resolve(createJsonResponse({}));
    });
  }

  async function runToResultView() {
    const run = createControlledBacktestStream(0.5);
    mockBacktestFlow(run);

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: {
        value:
          "영업이익 흑자인 기업을 코스피에서 최대 5종목, 매월 리밸런싱, 손절 10%, 익절 30%, " +
          "최근 5년 데이터, 1,000만원으로 백테스트",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(await screen.findByText("전략 검증 완료", {}, { timeout: 5_000 })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "백테스트 시작하기" }));
    expect(await screen.findByText("백테스트 진행 중")).toBeInTheDocument();
    run.finish();
    expect(await screen.findByTestId("backtest-dashboard")).toBeInTheDocument();
    scrollToMock.mockClear();
  }

  it("뒤로가기(결과 닫기)로 대화 화면에 돌아오면 맨 위로 스크롤한다", async () => {
    await runToResultView();

    fireEvent.popState(window);
    await waitFor(() => {
      expect(screen.queryByTestId("backtest-dashboard")).not.toBeInTheDocument();
    });

    expect(scrollToMock).toHaveBeenCalledWith({ top: 0, behavior: "auto" });
    expect(scrollToMock).not.toHaveBeenCalledWith(expect.objectContaining({ top: 3000 }));
  });

  it("탑메뉴 '전략연구소'로 결과 화면을 내려도 맨 위로 스크롤한다", async () => {
    await runToResultView();

    requestStrategyLabChatView();
    await waitFor(() => {
      expect(screen.queryByTestId("backtest-dashboard")).not.toBeInTheDocument();
    });

    expect(scrollToMock).toHaveBeenCalledWith({ top: 0, behavior: "auto" });
    expect(scrollToMock).not.toHaveBeenCalledWith(expect.objectContaining({ top: 3000 }));
  });

  it("대화 화면에서 탑메뉴 '전략연구소'를 눌러도 대화 끝이 아니라 맨 위로 스크롤한다", async () => {
    await runToResultView();

    // 결과 닫기로 대화 화면에 돌아온 뒤 → 다시 탑메뉴
    fireEvent.popState(window);
    await waitFor(() => {
      expect(screen.queryByTestId("backtest-dashboard")).not.toBeInTheDocument();
    });
    scrollToMock.mockClear();

    requestStrategyLabChatView();

    expect(scrollToMock).toHaveBeenCalledWith({ top: 0, behavior: "auto" });
    expect(scrollToMock).not.toHaveBeenCalledWith(expect.objectContaining({ top: 3000 }));
  });
});
