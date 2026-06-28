import { describe, expect, it, vi, beforeEach } from "vitest";

// refreshVirtualMarket 은 표시 전용이다 — 자동매매 체결의 정본은 백엔드 VirtualTrader 이고,
// 이 함수는 가격/포지션 표시만 갱신하고 매매(주문 생성/현금 변동/지정가 체결)는 하지 않는다.
vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualMarketState: { findUnique: vi.fn(), update: vi.fn() },
    virtualAccount: { findUnique: vi.fn() },
    virtualPosition: { update: vi.fn() },
    virtualOrder: { create: vi.fn(), update: vi.fn(), findMany: vi.fn() },
  },
}));
vi.mock("@/lib/server/stock-prices", () => ({
  fetchStockPriceSnapshots: vi.fn(),
}));
vi.mock("@/data/korea-stocks.json", () => ({ default: [] }));

import { refreshVirtualMarket } from "@/lib/server/virtual-market-refresh";
import { prisma } from "@/lib/prisma";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";

const mockStateFind = vi.mocked(prisma.virtualMarketState.findUnique);
const mockAccountFind = vi.mocked(prisma.virtualAccount.findUnique);
const mockPositionUpdate = vi.mocked(prisma.virtualPosition.update);
const mockSnapshots = vi.mocked(fetchStockPriceSnapshots);

describe("refreshVirtualMarket — 표시 전용", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("running 이 아니면 새로고침하지 않는다", async () => {
    mockStateFind.mockResolvedValue({ status: "paused" } as any);
    const result = await refreshVirtualMarket("acc-1");
    expect(result).toEqual({ refreshed: false, reason: "not running" });
  });

  it("가격으로 포지션 현재가/최고가만 갱신하고 매매(주문/현금)는 하지 않는다", async () => {
    mockStateFind.mockResolvedValue({
      status: "running",
      symbols: JSON.stringify(["005930"]),
    } as any);
    mockAccountFind.mockResolvedValue({
      id: "acc-1",
      VirtualPosition: [
        { symbol: "005930", avgPrice: 70000, peakPrice: 72000, quantity: 10 },
      ],
    } as any);
    mockSnapshots.mockResolvedValue({
      "005930": { price: 80000, open: 79000, high: 81000, low: 78000, volume: 100 },
    } as any);

    const result = await refreshVirtualMarket("acc-1");

    expect(result).toMatchObject({ refreshed: true, signals: [], logs: [] });
    // 포지션 표시는 갱신
    expect(mockPositionUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { accountId_symbol: { accountId: "acc-1", symbol: "005930" } },
      })
    );
    // 매매 경로는 일절 타지 않는다 (주문 생성/조회·시그널 평가 없음)
    expect(prisma.virtualOrder.create).not.toHaveBeenCalled();
    expect(prisma.virtualOrder.findMany).not.toHaveBeenCalled();
    // /market/signals 호출 없음 — 구독(/market/subscribe)만 fire-and-forget
    const fetchMock = vi.mocked(global.fetch);
    const signalCalls = fetchMock.mock.calls.filter(([url]) =>
      String(url).includes("/market/signals")
    );
    expect(signalCalls).toHaveLength(0);
  });
});
