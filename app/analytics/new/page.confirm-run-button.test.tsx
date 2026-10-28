// [2026-10-28 지시] 전략이 확정돼도 대화에 요약 카드·'백테스트 시작하기' 버튼을 그리지 않는다 —
// 실행은 상단 툴바의 백테스트 실행 버튼 하나다. 검증은 뒤에서 돌고, 알릴 문제가 있을 때만
// '전략 검증' 카드를 붙인다. 버튼은 검증 응답을 기다리지 않는다.
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

// 실행은 상단 툴바 버튼 하나다 — 준비가 끝나(활성) 누를 수 있을 때까지 기다린다.
const findRunButton = async (timeout = 5_000) => {
  await waitFor(() => expect(screen.getByTestId("lab-run-button")).toBeEnabled(), { timeout });
  return screen.getByTestId("lab-run-button");
};

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
  rebalance_method: "reconstitute",
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

function createParseStreamResponse(parsed: Record<string, unknown> = parsedStrategy) {
  const encoder = new TextEncoder();
  const payload = [
    // 프롬프트가 다섯 설정을 모두 말했으므로 백엔드 provenance도 전부를 명시로 보고한다.
    `data: ${JSON.stringify({
      type: "parsed_final",
      parsed,
      explicit_fields: [
        "universe",
        "max_positions",
        "rebalancing",
        "rebalance_method",
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

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

/** 진행 문구 하나만 흘리고 결과는 보내지 않는 백테스트 스트림 — 실행 중 화면을 붙잡아 둔다. */
function createPendingBacktestStream() {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: "status", message: "성과 지표 계산 중..." })}\n\n`),
        );
      },
    }),
    { status: 200 },
  );
}

function mockFetch(coachResponse: Promise<Response>, parsed: Record<string, unknown> = parsedStrategy) {
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/model/status") return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
    if (url === "/api/user") return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
    if (url === "/api/query/classify") return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
    if (url === "/api/strategy/parse/stream") return Promise.resolve(createParseStreamResponse(parsed));
    if (url === "/api/strategy/coach") return coachResponse;
    if (url === "/api/strategy/backtest-stream") return Promise.resolve(createPendingBacktestStream());
    return Promise.resolve(createJsonResponse({}));
  });
}

async function submitCompleteStrategy() {
  render(<StrategyLabPage />);
  fireEvent.change(await screen.findByRole("textbox"), {
    target: {
      value:
        "영업이익 흑자인 기업을 코스피에서 최대 5종목, 매월 리밸런싱, 손절 10%, 익절 30%, " +
        "최근 5년 데이터, 초기 자금 1,000만원으로 백테스트해줘",
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
}

describe("전략 확정 즉시 백테스트 버튼", () => {
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
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("확정 후 대화에 요약 카드·시작 버튼 없이 검증 응답 전부터 툴바 실행 버튼이 켜진다", async () => {
    const coach = createDeferred<Response>();
    mockFetch(coach.promise);
    await submitCompleteStrategy();

    // 검증 응답이 아직 오지 않았는데도 툴바 버튼이 켜진다.
    await findRunButton(5_000);
    expect(screen.queryByTestId("confirmed-strategy-summary")).not.toBeInTheDocument();
    expect(screen.queryByTestId("backtest-action")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "백테스트 시작하기" })).not.toBeInTheDocument();
    expect(screen.queryByText("전략 요약")).not.toBeInTheDocument();
    expect(screen.queryByTestId("strategy-coach-bubble")).not.toBeInTheDocument();
    expect(screen.queryByText("검증 중...")).not.toBeInTheDocument();

    // 문제 없는 검증 결과는 카드를 만들지 않는다.
    coach.resolve(createJsonResponse({ message: JSON.stringify({ is_valid: true, issues: [] }) }));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/coach")).toBe(true);
    });
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId("strategy-coach-bubble")).not.toBeInTheDocument();
    expect(screen.queryByText("전략 정의가 완료되었습니다. 백테스트를 실행할 수 있습니다.")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("lab-run-button")).toHaveLength(1);
  });

  it("검증이 문제를 알리면 '전략 검증' 카드를 붙이고 버튼은 그 아래 하나만 둔다", async () => {
    mockFetch(Promise.resolve(createJsonResponse({
      message: JSON.stringify({
        is_valid: false,
        issues: [{
          code: "CONFLICT",
          severity: "error",
          category: "logical_conflict",
          field: "entry_rule",
          message: "매수 조건이 서로 충돌합니다.",
        }],
      }),
    })));
    await submitCompleteStrategy();

    const bubble = await screen.findByTestId("strategy-coach-bubble", undefined, { timeout: 5_000 });
    expect(bubble).toHaveTextContent("매수 조건이 서로 충돌합니다.");
    expect(screen.queryByText("전략 요약")).not.toBeInTheDocument();
    const runButtons = screen.getAllByTestId("lab-run-button");
    expect(runButtons).toHaveLength(1);
    expect(bubble).not.toContainElement(runButtons[0]);
  });

  it("백테스트 진행 상황은 하단 진행 카드 한 곳에만 보인다", async () => {
    // [회귀 2026-09-29] 같은 진행 문구가 전략 메시지 아래 한 줄과 하단 진행 카드 두 곳에 떴다.
    mockFetch(Promise.resolve(createJsonResponse({ message: JSON.stringify({ is_valid: true, issues: [] }) })));
    await submitCompleteStrategy();

    fireEvent.click(await findRunButton(5_000));
    expect(await screen.findByRole("status")).toBeInTheDocument();
    await screen.findByText("성과 지표 계산 중...");
    expect(screen.getAllByText("성과 지표 계산 중...")).toHaveLength(1);
  });
});
