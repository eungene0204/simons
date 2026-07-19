import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { BacktestResult } from "@/types/strategy";
import BacktestStatsSummary from "./BacktestStatsSummary";

const result = {
  totalReturn: 30,
  cagr: 10,
  buyAndHoldReturn: 5,
  finalEquity: 13_000_000,
  initialCapital: 10_000_000,
  volatility: 12,
  sharpe: 1.2,
  sortino: 1.5,
  calmar: 0.5,
  maxDrawdown: -15,
  kelly: 0.2,
  trades: 71,
  winRate: 33.8,
  profitFactor: 1.5,
  avgProfit: 24.8,
  avgLoss: 5.31,
  maxConsecutiveWins: 3,
  maxConsecutiveLosses: 4,
} as unknown as BacktestResult;

describe("BacktestStatsSummary responsive layout", () => {
  it("stacks groups on mobile and restores the desktop grid at lg", () => {
    render(<BacktestStatsSummary result={result} />);

    expect(screen.getByTestId("backtest-stats-summary")).toHaveClass(
      "px-3",
      "sm:px-4",
      "lg:px-5"
    );
    expect(screen.getByTestId("backtest-stats-summary-grid")).toHaveClass(
      "grid-cols-1",
      "divide-y",
      "lg:grid-cols-3",
      "lg:divide-x",
      "lg:divide-y-0"
    );
    expect(screen.getAllByTestId("backtest-stats-summary-group")).toHaveLength(3);
    expect(screen.getAllByTestId("backtest-stats-summary-group")[1]).toHaveClass(
      "py-4",
      "lg:py-0",
      "lg:pl-5"
    );
  });
});
