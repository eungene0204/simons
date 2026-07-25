// 결과 화면을 닫은 뒤 채팅에서 '백테스트 시작하기'를 다시 누르면, state에 남아 있던 직전
// result 때문에 이전 결과 화면이 진행 바와 함께 되살아나던 회귀 테스트.
// 결과 화면 밖에서 시작한 실행은 채팅의 진행 표시만 보여야 한다.
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

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

describe("결과 닫기 후 재실행 화면", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.stubGlobal("scrollTo", vi.fn());
    // jsdom Element에는 scrollTo가 없다 — 결과 화면 진입 시 스크롤 초기화가 크래시한다.
    Element.prototype.scrollTo = vi.fn();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("결과를 닫고 다시 실행하면 이전 결과 화면 없이 진행 표시만 보인다", async () => {
    const firstRun = createControlledBacktestStream(0.5);
    const secondRun = createControlledBacktestStream(0.9);
    let backtestCallCount = 0;

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
        backtestCallCount += 1;
        return Promise.resolve(backtestCallCount === 1 ? firstRun.response : secondRun.response);
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: {
        value:
          "영업이익 흑자인 기업을 코스피에서 최대 5종목, 매월 리밸런싱, 손절 10%, 익절 30%, " +
          "최근 5년 데이터, 1,000만원으로 백테스트",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    // 1차 실행 → 결과 화면 진입
    expect(await screen.findByText("전략 검증 완료", {}, { timeout: 5_000 })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "백테스트 시작하기" }));
    expect(await screen.findByText("백테스트 진행 중")).toBeInTheDocument();
    firstRun.finish();
    expect(await screen.findByTestId("backtest-dashboard")).toBeInTheDocument();

    // 결과 닫기(= 뒤로가기) → 대화 화면 복귀
    fireEvent.popState(window);
    await waitFor(() => {
      expect(screen.queryByTestId("backtest-dashboard")).not.toBeInTheDocument();
    });

    // 2차 실행 — 진행 중에는 직전 결과 화면이 되살아나지 않는다.
    fireEvent.click(await screen.findByRole("button", { name: "백테스트 시작하기" }));
    expect(await screen.findByText("백테스트 진행 중")).toBeInTheDocument();
    expect(screen.queryByTestId("backtest-dashboard")).not.toBeInTheDocument();

    // 완료되면 새 결과 화면으로 전환된다.
    secondRun.finish();
    expect(await screen.findByTestId("backtest-dashboard")).toBeInTheDocument();
  });
});
