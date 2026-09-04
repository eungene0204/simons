// [회귀] 2026-09-04 사용자 지적 — /us 전략 요약 카드에 '진입 신호'·'분기 rebalancing'·'5년'이
// 한글로 남았다. 사전(en.ts)에는 영어 문구가 다 있었는데, 카드가 라벨 상수·리밸런싱 주기·
// 상대 기간을 t()로 감싸지 않고 그대로 찍었기 때문이다. 카드의 모든 문구가 사전을 타야 한다.
import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { __resetLanguageForTests, setLanguage } from "@/lib/i18n";
import StrategyLabPage from "./page";

const push = vi.fn();
const fetchMock = vi.fn();

// 되묻기 없이 한 번에 완성되는 US 전략 — 요약 카드가 파스 직후 바로 그려진다.
const parsedComplete = {
  description: "S&P 500 momentum strategy",
  universe: ["SP500"],
  fundamental_filters: [],
  entry_signals: [{ type: "ranking", params: { metric: "return", period: 180, top_n: 10 } }],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "quarterly",
  rebalance_method: "reconstitute",
  stop_loss_pct: 10,
  take_profit_pct: 30,
  trailing_stop_pct: null,
  backtest_period: "5y",
  initial_capital: 30000,
};

const backtestRequest = {
  symbols: ["AAPL", "MSFT"],
  universe_id: "sp500",
  entry: { conditions: [] },
  exit: { conditions: [] },
  risk: { max_positions: 10, init_cash: 30000, stop_loss_pct: 10, take_profit_pct: 30, rebalancing_period: "quarterly" },
  period: "5y",
  options: { fee_rate: 0.015, slippage_rate: 0.05 },
};

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/us/analytics/chat",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/components/strategy/StrategyExampleTabs", () => ({ StrategyExampleTabs: () => <div>예시 전략</div> }));
vi.mock("@/components/strategy/StrategyWaveBackground", () => ({ StrategyWaveBackground: () => <div>배경</div> }));
vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: { signInWithOAuth: vi.fn(), getSession: vi.fn().mockResolvedValue({ data: { session: null } }) },
  }),
}));

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

function parseStream() {
  const payload = [
    `data: ${JSON.stringify({
      type: "parsed_final",
      parsed: parsedComplete,
      explicit_fields: ["universe", "max_positions", "rebalancing", "rebalance_method", "backtest_period", "initial_capital"],
    })}\n\n`,
    `data: ${JSON.stringify({ type: "dsl_ready", backtest_request: backtestRequest, symbol_count: 2 })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(payload));
        controller.close();
      },
    }),
    { status: 200 },
  );
}

describe("/us 전략 요약 카드는 모든 문구를 영어 사전으로 그린다", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    // jsdom의 window.location은 "/"라 경로 mock만으로는 en으로 넘어가지 않는다 —
    // LanguageProvider가 하는 일을 명시로 대신한다.
    setLanguage("en");
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => { cb(0); return 1; });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.stubGlobal("scrollTo", vi.fn());
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/model/status") return Promise.resolve(json({ status: "ready", error: null }));
      if (url === "/api/user") return Promise.resolve(json({ user: { name: "Tester" } }));
      if (url === "/api/query/classify") return Promise.resolve(json({ intent: "STRATEGY_ADVICE", symbols: [] }));
      if (url === "/api/strategy/parse/stream") return Promise.resolve(parseStream());
      return Promise.resolve(json({}));
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    __resetLanguageForTests();
  });

  it("진입 신호 라벨·리밸런싱 주기·상대 기간이 한글로 새지 않는다", async () => {
    render(<StrategyLabPage />);
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "Top 10 S&P 500 stocks by 180-day return, quarterly rebalancing, 5 years, $30,000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate strategy" }));

    const card = (await screen.findByText("Strategy summary", undefined, { timeout: 5000 })).closest("div.space-y-3");
    expect(card).not.toBeNull();
    const text = card!.textContent ?? "";

    expect(text).toContain("Entry signal");
    expect(text).toContain("Quarterly rebalancing");
    expect(text).toContain("5 years");

    expect(text).not.toContain("진입 신호");
    expect(text).not.toContain("분기");
    expect(text).not.toContain("5년");
  });
});
