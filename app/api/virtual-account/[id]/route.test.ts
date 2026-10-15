import { beforeEach, describe, expect, it, vi } from "vitest";

import { prisma } from "@/lib/prisma";
import { GET, PATCH } from "./route";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualAccount: { findFirst: vi.fn(), update: vi.fn() },
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
