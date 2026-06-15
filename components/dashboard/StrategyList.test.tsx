import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyList from "./StrategyList";
import type { StrategyListData } from "@/app/api/dashboard/strategy-list/route";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

function makeData(): StrategyListData {
  return {
    strategies: [
      {
        id: "strategy-1",
        name: "골드 크로스",
        description: null,
        type: "모멘텀",
        universe: "KOSPI",
        aiScore: null,
        avgReturnPct: 3.2,
        totalProfit: 1952,
        accountCount: 1,
        autoTradingCount: 1,
        createdAt: "2026-06-15T00:00:00.000Z",
      },
    ],
  };
}

describe("StrategyList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens the latest matching backtest result when a strategy row is clicked", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          { id: "backtest-new", strategyName: "골드 크로스", timestamp: 2 },
          { id: "backtest-old", strategyName: "골드 크로스", timestamp: 1 },
        ],
      })
    );

    render(<StrategyList initialData={makeData()} />);

    fireEvent.click(screen.getByRole("button", { name: /골드 크로스/i }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/backtest/backtest-new");
    });
  });

  it("falls back to the backtest list when no result matches the strategy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [{ id: "backtest-other", strategyName: "다른 전략" }],
      })
    );

    render(<StrategyList initialData={makeData()} />);

    fireEvent.click(screen.getByRole("button", { name: /골드 크로스/i }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/backtest");
    });
  });

  it("opens the full backtest list from the header action", () => {
    render(<StrategyList initialData={makeData()} />);

    fireEvent.click(screen.getByRole("button", { name: "전체 보기" }));

    expect(pushMock).toHaveBeenCalledWith("/backtest");
  });
});
