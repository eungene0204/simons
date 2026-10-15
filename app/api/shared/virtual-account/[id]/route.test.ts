import { beforeEach, describe, expect, it, vi } from "vitest";

import { prisma } from "@/lib/prisma";
import { GET } from "./route";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualAccount: { findFirst: vi.fn() },
    virtualOrder: { findMany: vi.fn() },
    virtualMarketState: { findUnique: vi.fn() },
    virtualMarketLog: { findMany: vi.fn() },
    stock: { findMany: vi.fn().mockResolvedValue([]) },
  },
}));
vi.mock("@/lib/krx-stocks", () => ({
  getStockNameMap: vi.fn().mockResolvedValue({ "005930": "삼성전자" }),
  loadEtfMasterNameMap: vi.fn().mockResolvedValue({}),
}));
vi.mock("@/lib/server/assetService", () => ({
  moneyToNumber: vi.fn((value) => Number(value)),
  getAccountSettlementValues: vi.fn().mockResolvedValue({}),
}));

const findFirst = vi.mocked(prisma.virtualAccount.findFirst);

describe("GET /api/shared/virtual-account/[id]", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("공개 계좌만 조회하고 비공개·없는 계좌는 404", async () => {
    findFirst.mockResolvedValue(null);
    const res = await GET(new Request("http://localhost/x"), { params: { id: "a1" } });
    expect(res.status).toBe(404);
    expect(findFirst.mock.calls[0][0]).toMatchObject({ where: { id: "a1", isPublic: true } });
  });

  it("로그인 없이 계좌 화면 데이터를 주되 소유자·전략 ID는 싣지 않는다", async () => {
    findFirst.mockResolvedValue({
      id: "a1", userId: 7, name: "반도체etf", strategyId: "s1", strategyName: "전략A", isPublic: true,
      initialCash: 1_000_000, contributedCash: 0, currentCash: 500_000, currency: "KRW",
      createdAt: new Date("2026-01-01T00:00:00Z"), updatedAt: new Date("2026-01-02T00:00:00Z"),
      VirtualPosition: [{ symbol: "005930", name: null, quantity: 10, avgPrice: 50_000, currentPrice: 60_000 }],
      VirtualCashEvent: [],
    } as any);
    vi.mocked(prisma.virtualOrder.findMany).mockResolvedValue([]);
    vi.mocked(prisma.virtualMarketState.findUnique).mockResolvedValue({ symbols: '["005930"]' } as any);
    vi.mocked(prisma.virtualMarketLog.findMany).mockResolvedValue([]);

    const res = await GET(new Request("http://localhost/x"), { params: { id: "a1" } });
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.account).toMatchObject({ id: "a1", name: "반도체etf", strategyName: "전략A", isPublic: true });
    expect(body.account.strategyId).toBeUndefined();
    expect(body.account).not.toHaveProperty("userId");
    expect(body.holdings[0]).toMatchObject({ name: "삼성전자", quantity: 10 });
    expect(body.trackedSymbols).toEqual([{ symbol: "005930", name: "삼성전자" }]);
  });
});
