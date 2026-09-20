// [회귀] 2026-09-20 사용자 지시 — 요청을 전략 조건으로 해석하지 못한 턴에서 바로 위에
// '현재까지 이해한 전략입니다 / 첫 조건부터 하나씩 함께 정해보겠습니다.' 카드가 함께
// 떴다. 아무것도 해석하지 못했다고 알리는 자리에 같은 제목의 요약 카드가 붙으면 해석에
// 성공한 것처럼 보인다. 판정 근거는 백엔드 마커(clarification_priority=
// 'interpretation_failed')다 — 원문이나 문구를 다시 읽지 않는다.
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

const push = vi.fn();
const fetchMock = vi.fn();

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

function sseResultResponse(data: Record<string, unknown>) {
  const parsedFinal = JSON.stringify({ type: "parsed_final", ...data });
  const dslReady = JSON.stringify({
    type: "dsl_ready",
    backtest_request: { symbols: [], period: "5y", risk: {} },
    symbol_count: 0,
  });
  return new Response(
    `data: ${parsedFinal}\n\ndata: ${dslReady}\n\ndata: [DONE]\n\n`,
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

const FAILURE_QUESTION =
  "요청을 전략 조건으로 해석하지 못했어요. 진입·청산 규칙을 문장으로 알려주시면 그대로 " +
  "만들어 드릴게요. 예: '5일 이동평균이 20일 이동평균을 위로 뚫으면 매수하고 아래로 뚫으면 " +
  "매도, 손절 10%'";

const PROMPT =
  "시가총액 상위 500종목 중 최근 20영업일 잔차를 z-score로 표준화해 상위 50종목 매수, " +
  "하위 50종목 매도하는 달러 중립 포트폴리오를 구성한다";

describe("해석 실패 턴에는 전략 요약 카드를 보여주지 않는다", () => {
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

  it("'현재까지 이해한 전략입니다' 제목과 빈 안내가 함께 뜨지 않는다", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(
          createJsonResponse({ user: { name: "Tester", email: "tester@example.com" } })
        );
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }
      if (url === "/api/strategy/parse/stream") {
        // 백엔드 해석 실패 되묻기(main.py::_interpretation_failure_result) —
        // 전략은 원문만 담긴 빈 껍데기이고 우선순위 마커가 실려 온다.
        return Promise.resolve(sseResultResponse({
          parsed: {
            description: PROMPT,
            universe: [],
            sector: null,
            target_symbols: [],
            entry_signals: [],
            exit_signals: [],
            fundamental_filters: [],
            max_positions: null,
            rebalancing_period: null,
            rebalance_method: null,
            backtest_period: null,
            initial_capital: null,
            stop_loss_pct: null,
            take_profit_pct: null,
          },
          clarification_question: FAILURE_QUESTION,
          clarification_suggestions: null,
          clarification_priority: "interpretation_failed",
          pending_ask: null,
          explicit_fields: [],
          notices: null,
        }));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), { target: { value: PROMPT } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    await waitFor(() => {
      expect(screen.getByText(/전략 조건으로 해석하지 못했어요/)).toBeInTheDocument();
    }, { timeout: 5000 });

    expect(screen.queryByTestId("builder-strategy-summary")).not.toBeInTheDocument();
    expect(screen.queryByText("현재까지 이해한 전략입니다")).not.toBeInTheDocument();
    expect(
      screen.queryByText("첫 조건부터 하나씩 함께 정해보겠습니다."),
    ).not.toBeInTheDocument();
  });
});
