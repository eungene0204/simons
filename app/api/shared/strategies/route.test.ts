import { beforeEach, describe, expect, it, vi } from "vitest";

import { prisma } from "@/lib/prisma";
import { GET } from "./route";

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: async () => ({ userId: 1 }),
  isUnauthorizedAccessError: () => false,
}));
vi.mock("@/lib/prisma", () => ({
  prisma: {
    strategy: { findMany: vi.fn() },
    virtualAccount: { findMany: vi.fn() },
  },
}));
vi.mock("@/lib/krx-stocks", () => ({
  getStockNameMap: vi.fn().mockResolvedValue({}),
  loadEtfMasterNameMap: vi.fn().mockResolvedValue({}),
}));
vi.mock("@/lib/server/assetService", () => ({
  moneyToNumber: vi.fn((value) => Number(value)),
  getAccountSettlementValues: vi.fn().mockResolvedValue({}),
}));

const updatedAt = new Date("2026-10-20T00:00:00Z");
const strategy = (id: string, userId: number, name: string) => ({
  id, userId, name, description: `${name} 설명`, updatedAt,
});
const account = (id: string, strategyId: string, userId: number, currentCash: number) => ({
  id, userId, strategyId, name: `계좌 ${id}`, isPublic: true, status: "ACTIVE", currency: "KRW",
  initialCash: 1_000_000, contributedCash: 0, currentCash,
  createdAt: updatedAt, updatedAt, VirtualPosition: [],
});

describe("GET /api/shared/strategies", () => {
  beforeEach(() => vi.clearAllMocks());

  it("공개·저장·미삭제 전략과 공개 계좌만 조회한다", async () => {
    vi.mocked(prisma.strategy.findMany).mockResolvedValue([strategy("s1", 7, "A")] as any);
    vi.mocked(prisma.virtualAccount.findMany).mockResolvedValue([]);

    await GET();

    expect(vi.mocked(prisma.strategy.findMany).mock.calls[0][0]).toMatchObject({
      where: { isPublic: true, isSaved: true, deletedAt: null },
    });
    expect(vi.mocked(prisma.virtualAccount.findMany).mock.calls[0][0]).toMatchObject({
      where: { isPublic: true, strategyId: { in: ["s1"] } },
    });
  });

  it("공개 계좌 수익률 높은 순으로 정렬하고, 공개 계좌 없는 전략은 뒤로 보낸다", async () => {
    vi.mocked(prisma.strategy.findMany).mockResolvedValue([
      strategy("none", 7, "계좌없음"),
      strategy("low", 7, "낮음"),
      strategy("high", 8, "높음"),
    ] as any);
    vi.mocked(prisma.virtualAccount.findMany).mockResolvedValue([
      account("a1", "low", 7, 900_000), // -10%
      account("a2", "high", 8, 1_200_000), // +20%
      account("a3", "high", 8, 1_000_000), // 0%
    ] as any);

    const body = await (await GET()).json();

    expect(body.strategies.map((s: any) => s.name)).toEqual(["높음", "낮음", "계좌없음"]);
    expect(body.strategies[0].avgReturnPct).toBeCloseTo(10);
    expect(body.strategies[0].accounts.map((a: any) => a.returnPct)).toEqual([20, 0]);
    expect(body.strategies[2].avgReturnPct).toBeNull();
  });

  it("다른 사용자 계좌는 같은 전략 ID여도 섞지 않고, 소유자·전략 ID를 내보내지 않는다", async () => {
    vi.mocked(prisma.strategy.findMany).mockResolvedValue([strategy("s1", 7, "A")] as any);
    vi.mocked(prisma.virtualAccount.findMany).mockResolvedValue([
      account("mine", "s1", 7, 1_100_000),
      account("other", "s1", 9, 500_000),
    ] as any);

    const body = await (await GET()).json();
    const [card] = body.strategies;

    expect(card.accounts.map((a: any) => a.id)).toEqual(["mine"]);
    expect(JSON.stringify(body)).not.toContain('"s1"');
    expect(card).not.toHaveProperty("userId");
    expect(card.accounts[0]).not.toHaveProperty("userId");
  });
});
