// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, {
    get: () => ({ children, layoutId: _layoutId, ...props }: any) => <div {...props}>{children}</div>,
  }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));

import BacktestDashboard from "./BacktestDashboard";

const baseResult = {
  executionId: "exec-trade-stats",
  strategyId: "strat-trade-stats",
  symbols: ["005930"],
  totalReturn: 14.2,
  cagr: 9.1,
  buyAndHoldReturn: 6.8,
  maxDrawdown: -8.4,
  winRate: 57.1,
  profitFactor: 1.53,
  sharpe: 1.24,
  sortino: 1.41,
  trades: 101,
  avgProfit: 3.21,
  avgLoss: 1.76,
  maxConsecutiveWins: 6,
  maxConsecutiveLosses: 3,
  finalEquity: 11_420_000,
  initialCapital: 10_000_000,
  equity: [10_000_000, 10_650_000, 11_420_000],
  dates: ["2024-01-02", "2024-06-03", "2024-12-30"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

describe("BacktestDashboard 매매 통계", () => {
  beforeEach(() => {
    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }))
    );
  });

  it("중복된 총 매매 횟수 카드를 표시하지 않는다", async () => {
    await act(async () => {
      render(
        <BacktestDashboard
          result={baseResult}
          onRestart={() => {}}
          disableHistorySave
        />
      );
    });

    expect(screen.queryByText("총 매매 횟수")).not.toBeInTheDocument();
    expect(screen.getByText("평균 수익")).toBeInTheDocument();
    expect(screen.getByText("평균 손실")).toBeInTheDocument();
    expect(screen.getByText("최대 연속 수익")).toBeInTheDocument();
    expect(screen.getByText("최대 연속 손실")).toBeInTheDocument();
  });
});
