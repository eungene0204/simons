import { describe, expect, it, vi, beforeEach } from "vitest";

// 자동매매 체결은 FastAPI 백엔드의 VirtualTrader 로 일원화됐다.
// 따라서 TS 스케줄러의 market-refresh 액션은 더 이상 매매를 실행하면 안 되고,
// running 계좌를 조회하지도 않는(no-op) 상태여야 한다.
vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualMarketState: {
      findMany: vi.fn(),
      updateMany: vi.fn(),
      findUnique: vi.fn(),
      update: vi.fn(),
    },
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

// USD 계좌를 한국장 생명주기가 건드리면 미국 정규장(KST 밤)에 항상 paused 상태가 되어
// VirtualTrader(running 계좌만 처리)가 한 번도 돌지 않는다 — 통화별 분리 회귀 방지.
describe("runSchedulerAction — 생명주기 통화 분리 (KRW/USD)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "log").mockImplementation(() => {});
  });

  it("market-open 은 USD 계좌를 제외하고 조회한다", async () => {
    vi.mocked(prisma.virtualAccount.findMany).mockResolvedValue([]);

    await runSchedulerAction("market-open");

    expect(prisma.virtualAccount.findMany).toHaveBeenCalledWith({
      where: {
        tradingMode: "auto",
        strategyId: { not: null },
        currency: { not: "USD" },
      },
    });
  });

  it("us-market-open 은 USD 계좌만 조회해 paused 를 running 으로 되돌린다", async () => {
    vi.mocked(prisma.virtualAccount.findMany).mockResolvedValue([
      { id: "acc-usd", userId: "user-1" } as never,
    ]);
    vi.mocked(prisma.virtualMarketState.findUnique).mockResolvedValue({
      status: "paused",
    } as never);
    vi.mocked(prisma.virtualMarketState.update).mockResolvedValue({} as never);

    const result = await runSchedulerAction("us-market-open");

    expect(prisma.virtualAccount.findMany).toHaveBeenCalledWith({
      where: {
        tradingMode: "auto",
        strategyId: { not: null },
        currency: "USD",
      },
    });
    expect(prisma.virtualMarketState.update).toHaveBeenCalledWith({
      where: { accountId: "acc-usd" },
      data: expect.objectContaining({ status: "running" }),
    });
    expect(result.results).toEqual([{ accountId: "acc-usd", result: "resumed" }]);
  });

  it("market-close 는 USD 계좌를 제외하고 일시정지한다", async () => {
    vi.mocked(prisma.virtualMarketState.updateMany).mockResolvedValue({ count: 2 } as never);

    const result = await runSchedulerAction("market-close");

    expect(prisma.virtualMarketState.updateMany).toHaveBeenCalledWith({
      where: { status: "running", VirtualAccount: { currency: { not: "USD" } } },
      data: expect.objectContaining({ status: "paused" }),
    });
    expect(result.paused).toBe(2);
  });

  it("us-market-close 는 USD 계좌만 일시정지한다", async () => {
    vi.mocked(prisma.virtualMarketState.updateMany).mockResolvedValue({ count: 1 } as never);

    const result = await runSchedulerAction("us-market-close");

    expect(prisma.virtualMarketState.updateMany).toHaveBeenCalledWith({
      where: { status: "running", VirtualAccount: { currency: "USD" } },
      data: expect.objectContaining({ status: "paused" }),
    });
    expect(result.paused).toBe(1);
  });
});
