import { describe, expect, it, vi, beforeEach } from "vitest";

import type { BacktestHistoryItem } from "@/types/strategy";

class FakeUnauthorizedAccessError extends Error {}

let currentUserId: number | null = 7;
const fetchUserBacktestHistory = vi.fn();

vi.mock("@/lib/get-user", () => ({
  getSessionUserId: () => Promise.resolve(currentUserId),
  isUnauthorizedAccessError: (error: unknown) => error instanceof FakeUnauthorizedAccessError,
}));

vi.mock("@/lib/server/backtest-history-list", () => ({
  fetchUserBacktestHistory: (...args: unknown[]) => fetchUserBacktestHistory(...args),
}));

vi.mock("./BacktestHistoryView", () => ({
  default: () => null,
}));

const BacktestHistoryPage = (await import("./page")).default;

function makeHistoryItem(): BacktestHistoryItem {
  return {
    id: "history-1",
    timestamp: 1750000000000,
    strategyName: "모멘텀 전략",
    universe: "KOSPI",
    conditions: { entry: { names: ["20일 신고가"] } },
    metrics: {
      totalReturn: 12.3,
      cagr: 9.8,
      mdd: -4.5,
      winRate: 55,
      profitFactor: 1.4,
      buyHold: 3.2,
      trades: 18,
    },
  };
}

describe("/backtest 서버 렌더", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentUserId = 7;
  });

  it("서버에서 조회한 목록을 뷰에 넘긴다", async () => {
    const items = [makeHistoryItem()];
    fetchUserBacktestHistory.mockResolvedValue(items);

    const element = await BacktestHistoryPage();

    expect(fetchUserBacktestHistory).toHaveBeenCalledWith(7);
    expect(element.props.initialHistory).toBe(items);
  });

  it("비로그인이면 조회 없이 빈 목록으로 렌더한다", async () => {
    currentUserId = null;

    const element = await BacktestHistoryPage();

    expect(fetchUserBacktestHistory).not.toHaveBeenCalled();
    expect(element.props.initialHistory).toEqual([]);
  });

  it("비활성 계정이면 빈 목록으로 렌더한다", async () => {
    fetchUserBacktestHistory.mockRejectedValue(new FakeUnauthorizedAccessError());

    const element = await BacktestHistoryPage();

    expect(element.props.initialHistory).toEqual([]);
  });

  it("조회 자체가 실패하면 감추지 않고 던진다", async () => {
    fetchUserBacktestHistory.mockRejectedValue(new Error("DB down"));

    await expect(BacktestHistoryPage()).rejects.toThrow("DB down");
  });
});
