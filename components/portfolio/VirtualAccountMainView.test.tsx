import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import VirtualAccountMainView from "./VirtualAccountMainView";

const refreshAccountValueMock = vi.hoisted(() => vi.fn());

vi.mock("@/contexts/OrderAccountContext", () => ({
  useOrderAccount: () => ({ selectedAccountId: "account-1" }),
}));

vi.mock("@/lib/portfolio", () => ({
  refreshAccountValue: refreshAccountValueMock,
}));

vi.mock("@/components/stock/CandlestickChart", () => ({
  default: () => <div data-testid="candlestick-chart" />,
}));

describe("VirtualAccountMainView", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ candles: [] }),
    }));
    refreshAccountValueMock.mockResolvedValue({
      account: {
        id: "account-1",
        name: "장기 가상계좌 이름",
        initialAmount: 10_000_000,
        currentBalance: 5_000_000,
        totalValue: 11_000_000,
        createdAt: "2026-07-01T00:00:00.000Z",
        updatedAt: "2026-07-20T00:00:00.000Z",
      },
      holdings: [
        {
          symbol: "005930",
          name: "삼성전자",
          quantity: 10,
          averagePrice: 70_000,
          currentPrice: 72_000,
          totalValue: 720_000,
          profit: 20_000,
          profitPercent: 2.86,
        },
      ],
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("stacks account and holding details on mobile and restores desktop rows", async () => {
    render(<VirtualAccountMainView />);

    expect(await screen.findByText("장기 가상계좌 이름")).toBeInTheDocument();
    expect(screen.getByTestId("account-summary-card")).toHaveClass(
      "p-3",
      "sm:p-4",
      "lg:p-5"
    );
    expect(screen.getByTestId("account-summary-header")).toHaveClass(
      "flex-col",
      "lg:flex-row"
    );
    expect(screen.getByTestId("account-chart-container")).toHaveClass(
      "h-72",
      "sm:h-80",
      "lg:h-96"
    );
    expect(screen.getByTestId("account-holding-row")).toHaveClass(
      "flex-col",
      "lg:flex-row"
    );
    expect(screen.getByTestId("account-holding-value")).toHaveClass(
      "text-left",
      "lg:text-right"
    );
  });
});
