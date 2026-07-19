import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VirtualTradingDashboard from "@/components/dashboard/VirtualTradingDashboard";
import type { DashboardStats } from "@/app/api/virtual-account/[id]/dashboard/route";

const fetchMock = vi.fn();

const zeroStats: DashboardStats = {
  totalRealizedPnl: 0,
  totalReturn: 0,
  totalTrades: 0,
  winCount: 0,
  lossCount: 0,
  winRate: 0,
  avgWin: 0,
  avgLoss: 0,
  profitFactor: 0,
  totalFees: 0,
  totalTax: 0,
  dailyPnl: [],
  monthlyPnl: [],
  bySymbol: [],
};

function mockStats(stats: DashboardStats) {
  fetchMock.mockResolvedValue({
    json: async () => stats,
  });
}

function getMetricValue(label: string, value: string) {
  const cell = screen.getByText(label).parentElement;
  if (!cell) throw new Error(`Metric cell not found: ${label}`);
  return within(cell).getByText(value);
}

describe("VirtualTradingDashboard metric formatting", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("renders zero monetary values without a sign and in white", async () => {
    mockStats(zeroStats);

    render(<VirtualTradingDashboard accountId="account-123" initialAmount={9_000_000} />);

    const realizedPnl = await screen.findByText("총 실현 손익");
    expect(realizedPnl).toBeInTheDocument();

    for (const label of ["총 실현 손익", "평균 수익", "평균 손실", "총 수수료", "총 증권거래세"]) {
      expect(getMetricValue(label, "0원")).toHaveClass("text-white");
    }
    expect(getMetricValue("실현 수익률", "0.00%")).toHaveClass("text-white");
    expect(screen.queryByText("+0원")).not.toBeInTheDocument();
    expect(screen.queryByText("-0원")).not.toBeInTheDocument();
  });

  it("renders positive values in red and negative values in blue", async () => {
    mockStats({
      ...zeroStats,
      totalRealizedPnl: 125_000,
      totalReturn: -1.25,
      totalFees: 804,
    });

    render(<VirtualTradingDashboard accountId="account-123" initialAmount={9_000_000} />);

    expect(await screen.findByText("+125,000원")).toHaveClass(
      "text-[var(--main-red)]"
    );
    expect(getMetricValue("실현 수익률", "-1.25%")).toHaveClass(
      "text-[var(--main-blue)]"
    );
    expect(getMetricValue("총 수수료", "-804원")).toHaveClass(
      "text-[var(--main-blue)]"
    );
  });

  it("uses compact metric spacing on mobile and restores desktop sizing", async () => {
    mockStats(zeroStats);

    render(<VirtualTradingDashboard accountId="account-123" initialAmount={9_000_000} />);

    await screen.findByText("총 실현 손익");
    expect(screen.getAllByTestId("dashboard-metric-cell")[0]).toHaveClass(
      "p-3",
      "sm:p-4",
      "lg:p-5"
    );
    expect(screen.getAllByTestId("dashboard-metric-value")[0]).toHaveClass(
      "text-lg",
      "sm:text-xl",
      "lg:text-2xl"
    );
  });

  it("keeps symbol columns readable with mobile-only internal scrolling", async () => {
    mockStats({
      ...zeroStats,
      totalTrades: 2,
      winCount: 1,
      lossCount: 1,
      bySymbol: [
        {
          symbol: "005930",
          name: "삼성전자",
          trades: 2,
          winRate: 50,
          pnl: 125_000,
        },
      ],
    });

    render(<VirtualTradingDashboard accountId="account-123" initialAmount={9_000_000} />);

    expect(await screen.findByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByTestId("symbol-list-scroll")).toHaveClass(
      "overflow-x-auto",
      "lg:overflow-x-visible"
    );
    expect(screen.getByTestId("symbol-list-table")).toHaveClass(
      "min-w-[440px]",
      "lg:min-w-0"
    );
  });
});
