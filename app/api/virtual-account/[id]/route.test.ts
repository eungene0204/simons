import { beforeEach, describe, expect, it, vi } from "vitest";

import { prisma } from "@/lib/prisma";
import { GET, PATCH } from "./route";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualAccount: { findFirst: vi.fn(), update: vi.fn() },
    strategy: { findFirst: vi.fn() },
    stock: { findMany: vi.fn().mockResolvedValue([]) },
  },
}));

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: vi.fn().mockResolvedValue({ userId: 7 }),
  isUnauthorizedAccessError: vi.fn().mockReturnValue(false),
  withOwnership: vi.fn((where) => ({ ...where, userId: 7 })),
}));

vi.mock("@/lib/krx-stocks", () => ({
  getStockNameMap: vi.fn().mockResolvedValue({}),
  loadEtfMasterNameMap: vi.fn().mockResolvedValue({}),
}));

vi.mock("@/lib/strategy-tracked-symbols", () => ({
  resolveTrackedSymbolsForStrategy: vi.fn().mockResolvedValue({ symbols: [], source: "universe" }),
}));

vi.mock("@/lib/server/assetService", () => ({
  moneyToNumber: vi.fn((value) => Number(value)),
  getAccountSettlementValues: vi.fn().mockResolvedValue({}),
}));

const findFirst = vi.mocked(prisma.virtualAccount.findFirst);

describe("GET /api/virtual-account/[id] cash events", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns dated contributions only for the owned account", async () => {
    findFirst.mockResolvedValue({
      id: "account-1",
      name: "적립 계좌",
      initialCash: 10_000_000,
      contributedCash: 500_000,
      currentCash: 10_500_000,
      createdAt: new Date("2026-01-05T00:00:00Z"),
      updatedAt: new Date("2026-02-01T00:00:00Z"),
      VirtualPosition: [],
      VirtualCashEvent: [
        { date: "2026-01-05", type: "CONTRIBUTION_START", amount: 0 },
        { date: "2026-02-01", type: "CONTRIBUTION", amount: 500_000 },
      ],
    } as any);

    const response = await GET(new Request("http://localhost/api/virtual-account/account-1"), {
      params: { id: "account-1" },
    });

    expect(response.status).toBe(200);
    expect(findFirst).toHaveBeenCalledWith({
      where: { id: "account-1", userId: 7 },
      include: { VirtualPosition: true, VirtualCashEvent: { orderBy: { date: "asc" } } },
    });
    expect(await response.json()).toMatchObject({
      totalContributed: 10_500_000,
      cashEvents: [
        { date: "2026-01-05", type: "CONTRIBUTION_START", amount: 0 },
        { date: "2026-02-01", type: "CONTRIBUTION", amount: 500_000 },
      ],
    });
  });
});

describe("PATCH /api/virtual-account/[id] isPublic", () => {
  const update = vi.mocked(prisma.virtualAccount.update);
  const patch = (body: unknown) =>
    PATCH(
      new Request("http://localhost/api/virtual-account/a1", { method: "PATCH", body: JSON.stringify(body) }),
      { params: { id: "a1" } }
    );
  const row = {
    id: "a1", name: "n", initialCash: 1, contributedCash: 0, currentCash: 1, isPublic: true,
    createdAt: new Date(), updatedAt: new Date(), VirtualPosition: [],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    findFirst.mockResolvedValue({ id: "a1", status: "ACTIVE" } as any);
    update.mockResolvedValue(row as any);
  });

  it("boolean isPublic만 저장하고 응답에 싣는다", async () => {
    const res = await patch({ isPublic: true });
    expect(update.mock.calls[0][0].data).toMatchObject({ isPublic: true });
    expect((await res.json()).isPublic).toBe(true);
  });

  it("boolean이 아닌 isPublic은 무시한다", async () => {
    await patch({ isPublic: "true" });
    expect(update.mock.calls[0][0].data).not.toHaveProperty("isPublic");
  });

  it("소유 계좌가 아니면 404이고 쓰지 않는다", async () => {
    findFirst.mockResolvedValue(null);
    const res = await patch({ isPublic: true });
    expect(res.status).toBe(404);
    expect(update).not.toHaveBeenCalled();
  });
});

// 2026-11-17: 소유 확인 전에 strategyId를 저장해, 남의 전략 id로 자동매매가 돌 수 있었다.
describe("PATCH /api/virtual-account/[id] strategy link", () => {
  const update = vi.mocked(prisma.virtualAccount.update);
  const strategyFindFirst = vi.mocked(prisma.strategy.findFirst);
  const patch = (body: unknown) =>
    PATCH(
      new Request("http://localhost/api/virtual-account/a1", { method: "PATCH", body: JSON.stringify(body) }),
      { params: { id: "a1" } }
    );

  beforeEach(() => {
    vi.clearAllMocks();
    findFirst.mockResolvedValue({ id: "a1", status: "ACTIVE" } as any);
    update.mockResolvedValue({
      id: "a1", name: "n", initialCash: 1, contributedCash: 0, currentCash: 1,
      createdAt: new Date(), updatedAt: new Date(), VirtualPosition: [],
    } as any);
  });

  it("내 전략이 아니면 404이고 계좌를 쓰지 않는다", async () => {
    strategyFindFirst.mockResolvedValue(null);
    const res = await patch({ strategyId: "2:someone-else" });
    expect(res.status).toBe(404);
    expect(strategyFindFirst).toHaveBeenCalledWith({ where: { id: "2:someone-else", userId: 7 } });
    expect(update).not.toHaveBeenCalled();
  });

  it("내 전략이면 그 id를 저장한다", async () => {
    strategyFindFirst.mockResolvedValue({ id: "7:mine", name: "s", settings: "{}" } as any);
    const res = await patch({ strategyId: "7:mine" });
    expect(res.status).toBe(200);
    expect(update.mock.calls[0][0].data).toMatchObject({ strategyId: "7:mine" });
  });

  it("빈 strategyId는 연결 해제(null)로 저장한다", async () => {
    await patch({ strategyId: "" });
    expect(strategyFindFirst).not.toHaveBeenCalled();
    expect(update.mock.calls[0][0].data).toMatchObject({ strategyId: null });
  });
});
