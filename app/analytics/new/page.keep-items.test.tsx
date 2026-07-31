// [FR-SA-020] "조건을 바꾸고 싶어"처럼 무엇을 바꿀지 말하지 않은 요청에는, 지금 설정된
// 항목을 값과 함께 체크박스로 보여주고 그대로 둘 것을 고르게 한다. 고르지 않은 항목은
// 전략에서 비우고 진행 골격 순서대로 다시 묻는다 — 진행률 언체크는 같은 술어로 자동 성립.
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

// 스크린샷의 전략: KOSPI · ROE 10% 이상 · 골든크로스 매수 · 데드크로스 매도 · 8종목 · 손절 -8%
const PARSED = {
  description: "KOSPI ROE 골든크로스 전략",
  universe: ["KOSPI"],
  sector: null,
  target_symbols: [],
  fundamental_filters: [{ metric: "roe_or_gpa", operator: ">=", value: 10 }],
  entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
  exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
  max_positions: 8,
  rebalancing_period: "monthly",
  backtest_period: "5y",
  initial_capital: 10000000,
  stop_loss_pct: 8,
  take_profit_pct: 15,
  hold_period_days: null,
  trailing_stop_pct: null,
};

function progressComplete(label: string): boolean {
  const item = document
    .querySelector('[data-testid="strategy-progress-list"]')
    ?.querySelector(`[data-progress-label="${label}"]`);
  return item?.getAttribute("data-complete") === "true";
}

describe("유지/변경 체크박스 선택", () => {
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

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
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
        const query = JSON.parse((init?.body as string) ?? "{}").query ?? "";
        return Promise.resolve(createJsonResponse({
          intent: "STRATEGY_ADVICE",
          symbols: [],
          ...(query === "조건을 바꾸고 싶어" ? { clarify_target: "condition" } : {}),
        }));
      }
      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(sseResultResponse({
          parsed: PARSED,
          clarification_question: null,
          clarification_suggestions: null,
          clarification_priority: null,
          pending_ask: null,
          explicit_fields: [
            "universe", "max_positions", "rebalancing", "backtest_period", "initial_capital",
          ],
          notices: [],
        }));
      }
      if (url === "/api/strategy/coach") {
        return Promise.resolve(createJsonResponse({ message: "전략 정의가 완료되었습니다." }));
      }
      return Promise.resolve(createJsonResponse({}));
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function openSelector() {
    render(<StrategyLabPage />);
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "KOSPI에서 ROE 10% 이상 골든크로스 매수" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
    await screen.findByText("전략 요약", undefined, { timeout: 5000 });

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "조건을 바꾸고 싶어" },
    });
    fireEvent.click(screen.getByRole("button", { name: /전략 생성|전송/ }));
    return await screen.findByTestId("keep-items-selector", undefined, { timeout: 5000 });
  }

  it("지금 설정된 항목을 값과 함께 체크박스로 보여준다", async () => {
    const selector = await openSelector();
    // 값이 보여야 사용자가 무엇을 바꿀지 판단할 수 있다.
    expect(within(selector).getByText("KOSPI")).toBeInTheDocument();
    expect(within(selector).getByText(/ROE/)).toBeInTheDocument();
    expect(within(selector).getByText("8종목")).toBeInTheDocument();
    expect(within(selector).getByText("-8%")).toBeInTheDocument();
    // 기본은 전부 체크(현 상태 유지) — 아무것도 안 건드리고 제출하면 전략이 그대로다.
    for (const box of within(selector).getAllByRole("checkbox")) {
      expect(box).toBeChecked();
    }
  });

  it("체크 해제한 항목을 비우고 다시 물으며 진행률도 언체크된다", async () => {
    const selector = await openSelector();
    expect(progressComplete("리스크 관리")).toBe(true);

    // 손절만 체크 해제한다.
    const stopLossRow = within(selector).getByText("-8%").closest("label")!;
    fireEvent.click(within(stopLossRow).getByRole("checkbox"));
    fireEvent.click(within(selector).getByRole("button", { name: "선택 완료" }));

    await waitFor(() => {
      // 비운 항목을 다시 묻는다.
      expect(screen.getByText(/손절 기준을 몇 %로/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "손절 -10%" })).toBeInTheDocument();
    }, { timeout: 5000 });

    // 진행률이 같은 술어로 언체크된다(싱크).
    expect(progressComplete("리스크 관리")).toBe(false);
    // 체크를 유지한 항목은 그대로다.
    expect(progressComplete("유니버스")).toBe(true);
    expect(progressComplete("최대 보유")).toBe(true);

    // 백엔드 재파싱 없이 처리된다(화면의 값을 사용자가 고른 것이라 재해석할 것이 없다).
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input) === "/api/strategy/parse/stream"),
    ).toHaveLength(1);
  });

  it("모두 체크된 채 제출하면 전략이 그대로 남는다", async () => {
    const selector = await openSelector();
    fireEvent.click(within(selector).getByRole("button", { name: "선택 완료" }));

    await screen.findByText(/현재 조건을 그대로 두었어요/, undefined, { timeout: 5000 });
    expect(progressComplete("리스크 관리")).toBe(true);
    expect(progressComplete("유니버스")).toBe(true);
  });
});
