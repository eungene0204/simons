// @ts-nocheck
/**
 * Strategy-graph entry point on the result screen. The dashboard renders the snapshot it is
 * given (executed request) and never substitutes anything: no input -> no entry point, no
 * snapshot -> an explicit "not saved" state.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/" }));

import BacktestDashboard from "./BacktestDashboard";
import { executedInput, META } from "@/lib/strategy-graph/fixtures";
import { resetGraphMetaForTests } from "@/lib/strategy-graph/meta";

const result = {
  executionId: "exec-1", strategyId: "strat-1", symbols: [], totalReturn: 10, cagr: 5, buyAndHoldReturn: 8,
  maxDrawdown: -10, winRate: 50, profitFactor: 1.5, sharpe: 1, sortino: 1, trades: 3, finalEquity: 110,
  initialCapital: 100, totalProfit: 10, equity: [100, 110], dates: ["2024-01-02", "2024-06-01"],
  tradesList: [], monthlyReturns: {}, yearlyReturns: {}, signals: [],
} as any;

const fetchMock = vi.fn();

beforeEach(() => {
  cleanup();
  resetGraphMetaForTests();
  fetchMock.mockReset();
  fetchMock.mockImplementation((url: string) =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(String(url).includes("graph-meta") ? META : {}) }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

describe("BacktestDashboard strategy graph entry", () => {
  it("renders no graph entry when no snapshot input is provided", () => {
    render(<BacktestDashboard result={result} onRestart={vi.fn()} disableHistorySave />);
    expect(screen.queryByRole("button", { name: "전략 그래프" })).not.toBeInTheDocument();
  });

  it("opens the executed-strategy graph from the provided snapshot", async () => {
    render(<BacktestDashboard result={result} onRestart={vi.fn()} disableHistorySave strategyGraphInput={executedInput("goldenCrossRsiAnd")} />);
    expect(screen.queryByTestId("backtest-strategy-graph")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "전략 그래프" }));
    const panel = await screen.findByTestId("backtest-strategy-graph");
    expect(within(panel).getByRole("heading", { name: "실행된 전략" })).toBeInTheDocument();
    await within(panel).findByTestId("strategy-graph-canvas");
    expect(within(panel).getByText("RSI(14) < 70")).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes("graph"))).toEqual(["/api/strategy/graph-meta"]);
  });

  it("shows an explicit no-snapshot state instead of the current strategy", async () => {
    render(
      <BacktestDashboard
        result={result}
        onRestart={vi.fn()}
        disableHistorySave
        strategyGraphInput={{ origin: "none", schema: "none", sourceRef: "history:x" }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "전략 그래프" }));
    expect(await screen.findByTestId("graph-no-snapshot")).toHaveTextContent("이 실행의 전략 스냅샷이 저장되어 있지 않습니다.");
    await waitFor(() => expect(document.querySelector("[data-node-id]")).toBeNull());
  });
});
