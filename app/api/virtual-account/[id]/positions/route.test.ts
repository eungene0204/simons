import { beforeEach, describe, expect, it, vi } from "vitest";

import { prisma } from "@/lib/prisma";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";
import { GET } from "./route";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    stock: {
      findMany: vi.fn(),
    },
    virtualAccount: {
      findFirst: vi.fn(),
    },
    virtualPosition: {
      findMany: vi.fn(),
    },
  },
}));

vi.mock("@/lib/krx-stocks", () => ({
  getStockNameMap: vi.fn().mockResolvedValue({}),
  loadEtfMasterNameMap: vi.fn().mockResolvedValue({
    "488080": "TIGER 반도체TOP10레버리지",
  }),
}));

vi.mock("@/lib/server/stock-prices", () => ({
  fetchStockPriceSnapshots: vi.fn(),
}));

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: vi.fn().mockResolvedValue({ userId: 1 }),
  isUnauthorizedAccessError: vi.fn().mockReturnValue(false),
  withOwnership: vi.fn((where) => ({ ...where, userId: 1 })),
}));

vi.mock("@/lib/server/assetService", () => ({
  moneyToNumber: vi.fn((value) => Number(value)),
}));

const mockStockFindMany = vi.mocked(prisma.stock.findMany);
const mockAccountFindFirst = vi.mocked(prisma.virtualAccount.findFirst);
const mockPositionFindMany = vi.mocked(prisma.virtualPosition.findMany);
const mockFetchStockPriceSnapshots = vi.mocked(fetchStockPriceSnapshots);

describe("/api/virtual-account/[id]/positions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAccountFindFirst.mockResolvedValue({ id: "account-1" } as any);
    mockStockFindMany.mockResolvedValue([]);
    mockPositionFindMany.mockResolvedValue([
      {
        id: "position-1",
        accountId: "account-1",
        symbol: "488080",
        name: "488080",
        quantity: 2,
        avgPrice: 40000,
        currentPrice: 40605,
        openedAt: new Date("2026-07-21"),
      },
    ] as any);
    mockFetchStockPriceSnapshots.mockResolvedValue({
      "488080": { price: 40605 },
    } as any);
  });

  it("ETF 코드로 저장된 보유종목의 이름을 ETF 마스터에서 채운다", async () => {
    const response = await GET(
      new Request("http://localhost/api/virtual-account/account-1/positions"),
      { params: { id: "account-1" } }
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual([
      expect.objectContaining({
        symbol: "488080",
        name: "TIGER 반도체TOP10레버리지",
      }),
    ]);
  });
});
