import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import BacktestConfig, { type StrategySummaryData } from "./BacktestConfig";

const summary: StrategySummaryData = {
  strategyName: "테스트 전략",
  universeName: "KOSPI",
  universeSettings: {
    marketCapRange: [0, 100],
    minTradingVolume: 0,
    selectedSectors: [],
    excludeLossMaking: false,
    excludeCapitalImpaired: false,
    excludeAdministrative: false,
    excludePreferred: false,
    excludeETF_ETN: false,
    excludeSPAC: false,
    excludeREITs: false,
    excludeInvestmentWarning: false,
    excludeDelistingPending: false,
    excludeForeignStock: false,
    excludePennyStocks: false,
    excludeNewListings: false,
    excludeHighVolatility: false,
  },
  universeFiltersCount: 0,
  blockNames: [],
  riskSettings: {
    maxPositions: 10,
    allocationType: "equal",
    executionTiming: "close",
    rebalancingPeriod: "none",
  },
  riskManagement: {},
};

describe("BacktestConfig responsive layout", () => {
  it("stacks input steps on mobile and restores the desktop columns", () => {
    render(
      <BacktestConfig
        onRun={vi.fn()}
        isRunning={false}
        summary={summary}
      />
    );

    expect(screen.getByTestId("backtest-config-input-columns")).toHaveClass(
      "flex-col",
      "divide-y",
      "lg:flex-row",
      "lg:divide-x",
      "lg:divide-y-0"
    );
    expect(screen.getByTestId("backtest-config-input-panel")).toHaveClass(
      "lg:border-r"
    );
    expect(screen.getByTestId("backtest-config-summary-panel")).toHaveClass(
      "border-t",
      "lg:border-l",
      "lg:border-t-0"
    );
  });

  it("stacks custom dates on mobile and restores the row from sm", () => {
    render(
      <BacktestConfig
        onRun={vi.fn()}
        isRunning={false}
        summary={summary}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "직접 입력" }));

    expect(screen.getByTestId("backtest-config-custom-dates")).toHaveClass(
      "flex-col",
      "sm:flex-row"
    );
  });
});
