// [회귀] "왜 반영되지 않았는지" 안내(notices)가 되묻기와 같은 턴에 오면 화면에서 사라졌다
// (2026-07-31). 안내 카드가 요약 블록(`!clarification`) 안에만 있어서, 되묻기가 뜨는 순간
// 통째로 렌더되지 않았다. 사실을 먼저 알리고 다음 질문으로 이어야 한다.
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

const NOTICE = "'수급' 조건은 지원하지 않아 전략에 넣지 못했어요. 나머지 조건은 그대로입니다.";

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

describe("미반영 안내는 되묻기와 함께 보인다", () => {
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

  it("반영하지 못한 이유와 다음에 정할 조건을 함께 보여준다", async () => {
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
        // 익절이 비어 있는 전략 + 미반영 안내가 한 턴에 함께 온다.
        return Promise.resolve(sseResultResponse({
          parsed: {
            description: "수급 좋은 종목 전략",
            universe: ["KOSPI"],
            sector: null,
            target_symbols: [],
            entry_signals: [{ type: "ma_crossover", direction: "golden_cross" }],
            exit_signals: [{ type: "ma_crossover", direction: "dead_cross" }],
            fundamental_filters: [],
            max_positions: 5,
            rebalancing_period: "monthly",
            backtest_period: "5y",
            initial_capital: 10000000,
            stop_loss_pct: 8,
            take_profit_pct: null,
          },
          clarification_question: null,
          clarification_suggestions: null,
          clarification_priority: null,
          pending_ask: null,
          explicit_fields: [
            "universe", "max_positions", "rebalancing", "backtest_period", "initial_capital",
          ],
          notices: [NOTICE],
        }));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "수급 좋은 종목을 골든크로스에 매수" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    await waitFor(() => {
      // 사실(왜 반영 못 했는지)과 다음 행동(무엇을 정할지)이 한 화면에 함께 있다.
      expect(screen.getByText(new RegExp("넣지 못했어요"))).toBeInTheDocument();
      expect(screen.getByText(/익절 기준을 몇 %로/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "익절 10%" })).toBeInTheDocument();
    }, { timeout: 5000 });
  });
});
