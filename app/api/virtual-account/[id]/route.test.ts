import { beforeEach, describe, expect, it, vi } from "vitest";

import { prisma } from "@/lib/prisma";
import { GET } from "./route";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualAccount: { findFirst: vi.fn() },
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
