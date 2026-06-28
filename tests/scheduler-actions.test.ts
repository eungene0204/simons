import { describe, expect, it, vi, beforeEach } from "vitest";

// 자동매매 체결은 FastAPI 백엔드의 VirtualTrader 로 일원화됐다.
// 따라서 TS 스케줄러의 market-refresh 액션은 더 이상 매매를 실행하면 안 되고,
// running 계좌를 조회하지도 않는(no-op) 상태여야 한다.
vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualMarketState: { findMany: vi.fn(), updateMany: vi.fn() },
    virtualAccount: { findMany: vi.fn() },
  },
}));
vi.mock("@/lib/server/stock-prices", () => ({
  fetchStockPriceSnapshots: vi.fn(),
}));
vi.mock("@/lib/server/strategy-start", () => ({
  startAccountStrategy: vi.fn(),
}));

import { runSchedulerAction } from "@/lib/server/scheduler-actions";
import { prisma } from "@/lib/prisma";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";

describe("runSchedulerAction — market-refresh 일원화", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "log").mockImplementation(() => {});
  });

  it("market-refresh 는 매매를 실행하지 않고 no-op 으로 건너뛴다 (정본=VirtualTrader)", async () => {
    const result = await runSchedulerAction("market-refresh");

    expect(result).toMatchObject({
      action: "market-refresh",
      skipped: true,
    });
    // 매매 경로(running 계좌 조회)를 일절 타지 않는다 → VirtualTrader 와 이중 체결 불가
    expect(prisma.virtualMarketState.findMany).not.toHaveBeenCalled();
    expect(fetchStockPriceSnapshots).not.toHaveBeenCalled();
  });
});
