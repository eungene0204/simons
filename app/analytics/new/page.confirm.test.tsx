// '이 전략으로 확정'은 대화 전체를 LLM에 재파싱시키지 않고, 누적된 parsed를 그대로
// /api/strategy/compile로 컴파일한다 — 재해석이 규칙 파서가 표현 못 하는 조건
// ('영업이익 흑자' → operating_income_growth 필터)을 비결정적으로 잃어 완성 전략의
// 매수 조건을 다시 되묻던 사고의 회귀 테스트.
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

const push = vi.fn();
const fetchMock = vi.fn();

// LLM 해석으로만 얻는 진입 필터를 포함하고, 익절만 비어 있는 전략 — 결정적 칩 한 번으로
// 완성돼 확정 단계에 도달한다. 프롬프트에 유니버스·종목 수·리밸런싱·기간·자본이 명시돼
// 있어야 requireExplicitConfiguration 게이트를 통과한다.
const parsedWithLlmOnlyFilter = {
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
  take_profit_pct: null,
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

function createJsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function createParseStreamResponse() {
  const encoder = new TextEncoder();
  const payload = [
    `data: ${JSON.stringify({ type: "parsed_final", parsed: parsedWithLlmOnlyFilter })}\n\n`,
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

describe("deterministic strategy confirmation", () => {
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

  it("확정 시 재파싱 없이 누적 전략을 컴파일해 LLM 전용 매수 필터를 보존한다", async () => {
    let parseCallCount = 0;
    const compileBodies: Array<{ parsed: Record<string, unknown> }> = [];

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
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
        parseCallCount += 1;
        return Promise.resolve(createParseStreamResponse());
      }
      if (url === "/api/strategy/compile") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        compileBodies.push(body);
        return Promise.resolve(
          createJsonResponse({
            parsed: body.parsed,
            backtest_request: backtestRequest,
            notices: [],
          }),
        );
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: {
        value:
          "영업이익 흑자인 기업을 코스피에서 최대 5종목, 매월 리밸런싱, 손절 10%, " +
          "최근 5년 데이터, 1,000만원으로 백테스트",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    // 익절만 비어 있으므로 익절 질문 → 칩 선택으로 완성한다.
    fireEvent.click(await screen.findByRole("button", { name: "익절 30%" }));

    fireEvent.click(await screen.findByRole("button", { name: "이 전략으로 확정" }));

    await waitFor(() => {
      expect(compileBodies).toHaveLength(1);
    });

    // 누적 parsed가 그대로 컴파일 요청에 실린다 — LLM 전용 필터·칩으로 채운 익절 포함.
    expect(compileBodies[0].parsed.fundamental_filters).toEqual([
      { metric: "operating_income_growth", operator: ">=", value: 0 },
    ]);
    expect(compileBodies[0].parsed.take_profit_pct).toBe(30);

    // 확정은 대화 전체를 재파싱하지 않는다(최초 1회만).
    expect(parseCallCount).toBe(1);

    // 매수 조건이 사라져 다시 묻는 사고가 없어야 한다.
    expect(screen.queryByText(/어떤 조건에서 매수할지/)).not.toBeInTheDocument();
    expect(screen.queryByText(/매수 조건이 빠져 있습니다/)).not.toBeInTheDocument();
  });
});
