import { beforeEach, describe, expect, it, vi } from "vitest";

import { prisma } from "@/lib/prisma";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";
import { GET } from "./route";

vi.mock("@/lib/prisma", () => ({
  prisma: { virtualAccount: { findMany: vi.fn() } },
}));

vi.mock("@/lib/server/stock-prices", () => ({
  fetchStockPriceSnapshots: vi.fn(),
}));

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: vi.fn().mockResolvedValue({ userId: 7 }),
  isUnauthorizedAccessError: vi.fn().mockReturnValue(false),
  withOwnership: vi.fn((where) => ({ ...where, userId: 7 })),
}));

const findMany = vi.mocked(prisma.virtualAccount.findMany);
const fetchPrices = vi.mocked(fetchStockPriceSnapshots);

const account = {
  id: "account-1",
  name: "가상계좌",
  initialCash: 100_000,
  contributedCash: 10_000,
  currentCash: 50_000,
  status: "ACTIVE",
  strategyId: null,
  strategyName: null,
  tradingMode: "manual",
  createdAt: new Date("2026-01-01"),
  updatedAt: new Date("2026-01-01"),
  VirtualPosition: [
    { symbol: "005930", quantity: 10, avgPrice: 5_000, currentPrice: 5_000 },
  ],
};

describe("GET /api/virtual-account", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    findMany.mockResolvedValue([account] as any);
  });

  it("values unsold holdings at the current quote, including contributions in the return basis", async () => {
    fetchPrices.mockResolvedValue({ "005930": { price: 7_000 } } as any);

    const response = await GET();
    const [result] = await response.json();

    expect(fetchPrices).toHaveBeenCalledWith(["005930"], {
      mode: "realtime",
      subscribe: false,
    });
    expect(result).toMatchObject({
      currentBalance: 50_000,
      totalContributed: 110_000,
      totalValue: 120_000,
    });
  });

  it("uses the stored position price if a quote is unavailable", async () => {
    fetchPrices.mockResolvedValue({ "005930": { price: 0 } } as any);

    const response = await GET();
    const [result] = await response.json();

    expect(result.totalValue).toBe(100_000);
  });

  it("does not request quotes for an account with no positions", async () => {
    findMany.mockResolvedValue([{ ...account, VirtualPosition: [] }] as any);

    const response = await GET();
    const [result] = await response.json();

    expect(fetchPrices).not.toHaveBeenCalled();
    expect(result.totalValue).toBe(50_000);
  });
});
