import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import RecentBacktestList from "./RecentBacktestList";
import type { DashboardBacktestRecord } from "@/types/dashboard";

function makeRecord(overrides: Partial<DashboardBacktestRecord> = {}): DashboardBacktestRecord {
  return {
    id: "1",
    timestamp: Date.now(),
    strategyName: "모멘텀 전략",
    universe: "KOSPI",
    metrics: { totalReturn: 12.4, cagr: 8.2, mdd: -8.3 },
    ...overrides,
  };
}

describe("RecentBacktestList", () => {
  it("contains the fixed-width table inside a mobile scroll region", () => {
    render(<RecentBacktestList initialRecords={[makeRecord()]} />);

    const scrollRegion = screen.getByTestId("recent-backtest-table-scroll");
    expect(scrollRegion).toHaveClass(
      "overflow-x-auto",
      "lg:overflow-x-visible"
    );
    expect(scrollRegion.firstElementChild).toHaveClass(
      "min-w-[520px]",
      "lg:min-w-0"
    );
  });

  it("renders CAGR and MDD columns from stored metrics", () => {
    render(<RecentBacktestList initialRecords={[makeRecord()]} />);

    expect(screen.getByText("CAGR")).toBeInTheDocument();
    expect(screen.getByText("MDD")).toBeInTheDocument();
    expect(screen.getByText("+12.4%")).toBeInTheDocument();
    expect(screen.getByText("+8.2%")).toBeInTheDocument();
    expect(screen.getByText("-8.3%")).toBeInTheDocument();
  });

  it("shows a dash when cagr/mdd are missing in older records", () => {
    render(
      <RecentBacktestList
        initialRecords={[makeRecord({ metrics: { totalReturn: 5.0 } })]}
      />
    );

    expect(screen.getAllByText("–")).toHaveLength(2);
  });

  it("falls back to the raw universe label when it is not in the known mapping", () => {
    render(<RecentBacktestList initialRecords={[makeRecord({ universe: "반도체" })]} />);

    expect(screen.getByText("반도체")).toBeInTheDocument();
  });
});
