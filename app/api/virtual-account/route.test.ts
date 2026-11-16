import { beforeEach, describe, expect, it, vi } from "vitest";

import { prisma } from "@/lib/prisma";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";
import { GET, POST } from "./route";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualAccount: { findMany: vi.fn(), create: vi.fn() },
    strategy: { findFirst: vi.fn() },
    $transaction: vi.fn(),
  },
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

  it("returns the current holdings valuation and cost separately from contributed capital", async () => {
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
      holdingsCost: 50_000,
      holdingsProfit: 20_000,
    });
  });

  it("uses the stored position price if a quote is unavailable", async () => {
    fetchPrices.mockResolvedValue({ "005930": { price: 0 } } as any);

    const response = await GET();
    const [result] = await response.json();

    expect(result).toMatchObject({ totalValue: 100_000, holdingsCost: 50_000, holdingsProfit: 0 });
  });

  it("does not request quotes for an account with no positions", async () => {
    findMany.mockResolvedValue([{ ...account, VirtualPosition: [] }] as any);

    const response = await GET();
    const [result] = await response.json();

    expect(fetchPrices).not.toHaveBeenCalled();
    expect(result).toMatchObject({ totalValue: 50_000, holdingsCost: 0, holdingsProfit: 0 });
  });
});

// 2026-11-17: 찾지 못한(남의·없는) 전략 id도 그대로 계좌에 저장했다.
describe("POST /api/virtual-account strategy link", () => {
  beforeEach(() => vi.clearAllMocks());

  it("내 전략이 아니면 404이고 계좌를 만들지 않는다", async () => {
    vi.mocked(prisma.strategy.findFirst).mockResolvedValue(null);
    const res = await POST(
      new Request("http://localhost/api/virtual-account", {
        method: "POST",
        body: JSON.stringify({ name: "계좌", strategyId: "2:someone-else" }),
      })
    );
    expect(res.status).toBe(404);
    expect(prisma.strategy.findFirst).toHaveBeenCalledWith({ where: { id: "2:someone-else", userId: 7 } });
    expect(prisma.$transaction).not.toHaveBeenCalled();
    expect(prisma.virtualAccount.create).not.toHaveBeenCalled();
  });
});
