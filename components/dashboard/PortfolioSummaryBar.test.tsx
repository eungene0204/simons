import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PortfolioSummaryBar from "./PortfolioSummaryBar";
import type { PortfolioStats } from "@/lib/dashboard-data";

function makeStats(overrides: Partial<PortfolioStats> = {}): PortfolioStats {
  return {
    totalInvested: 1000000,
    totalValue: 1000000,
    totalProfit: 0,
    totalReturnPct: 0,
    accountCount: 1,
    dailyPnl: 0,
    ...overrides,
  };
}

describe("PortfolioSummaryBar", () => {
  it("renders zero profit values in white", () => {
    render(<PortfolioSummaryBar initialStats={makeStats()} />);

    expect(screen.getByText("0.00%").className).toContain("text-white");

    const zeroWonValues = screen.getAllByText("0원");
    expect(zeroWonValues).toHaveLength(2);
    for (const value of zeroWonValues) {
      expect(value.className).toContain("text-white");
    }
  });

  it("renders the total evaluation value card", () => {
    render(
      <PortfolioSummaryBar initialStats={makeStats({ totalValue: 29_320_000 })} />
    );

    expect(screen.getByText("총 평가금액")).toBeInTheDocument();
    expect(screen.getByText("2,932만원")).toBeInTheDocument();
  });

  it("renders positive profit in red and negative profit in blue", () => {
    render(
      <PortfolioSummaryBar
        initialStats={makeStats({
          totalProfit: -100,
          totalReturnPct: -0.01,
          dailyPnl: 50,
        })}
      />
    );

    expect(screen.getByText("-0.01%").className).toContain("text-[var(--main-blue)]");
    expect(screen.getByText("-100원").className).toContain("text-[var(--main-blue)]");
    expect(screen.getByText("+50원").className).toContain("text-[var(--main-red)]");
  });
});
