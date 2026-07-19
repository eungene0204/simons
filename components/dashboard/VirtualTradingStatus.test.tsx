import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import VirtualTradingStatus from "./VirtualTradingStatus";
import type { TradingStatusData } from "@/app/api/dashboard/trading-status/route";

const data: TradingStatusData = {
  totalAccounts: 4,
  runningAccounts: 2,
  autoAccounts: 3,
  todayFilledOrders: 5,
  totalPositions: 8,
  dailyPnl: 84_000,
  totalEvaluation: 29_320_000,
};

describe("VirtualTradingStatus", () => {
  it("uses two mobile columns and restores the desktop status row", () => {
    render(<VirtualTradingStatus initialData={data} />);

    expect(screen.getByTestId("virtual-trading-status-grid")).toHaveClass(
      "grid-cols-2",
      "lg:flex",
      "lg:divide-x"
    );
  });

  it("focuses on trading status and omits stats duplicated in the summary bar", () => {
    render(<VirtualTradingStatus initialData={data} />);

    // PortfolioSummaryBar와 중복되는 항목은 표시하지 않는다.
    expect(screen.queryByText("총 평가금")).not.toBeInTheDocument();
    expect(screen.queryByText("전체 계좌")).not.toBeInTheDocument();

    expect(screen.getByText("실행중인 계좌 수")).toBeInTheDocument();
    expect(screen.getByText("자동매매 계좌")).toBeInTheDocument();
    expect(screen.getByText("보유 종목")).toBeInTheDocument();
    expect(screen.getByText("오늘 체결")).toBeInTheDocument();
    expect(screen.getByText("3개")).toBeInTheDocument();
  });
});
