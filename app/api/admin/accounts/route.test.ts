// @ts-nocheck
import { describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const accountFindMany = vi.fn();
const ledgerFindMany = vi.fn();
const fetchStockPriceSnapshots = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualAccount: { count: vi.fn().mockResolvedValue(2), findMany: accountFindMany },
    assetLedger: { findMany: ledgerFindMany },
  },
}));
vi.mock("@/lib/server/adminAuth", () => ({
  requireAdmin: vi.fn().mockResolvedValue({ id: 1 }),
  writeAuditLog: vi.fn(),
}));
vi.mock("@/lib/server/stock-prices", () => ({ fetchStockPriceSnapshots }));

const { GET } = await import("./route");

function makeAccount(overrides = {}) {
  return {
    id: "acc-active",
    name: "계좌",
    status: "ACTIVE",
    initialCash: 1_000_000,
    contributedCash: 0,
    currentCash: 500_000,
    strategyName: null,
    createdAt: new Date("2026-01-01T00:00:00Z"),
    User: { id: 1, email: "a@example.com" },
    VirtualPosition: [],
    _count: { VirtualOrder: 0 },
    ...overrides,
  };
}

describe("GET /api/admin/accounts", () => {
  it("닫은 계좌는 정산금, 보유 종목은 실시간 시세로 평가한다", async () => {
    // 2026-10-30: 닫은 계좌가 현금 0·포지션 없음으로 계산돼 -100%로 보였다.
    accountFindMany.mockResolvedValue([
      makeAccount({
        VirtualPosition: [{ symbol: "005930", quantity: 10, avgPrice: 50_000, currentPrice: 40_000 }],
      }),
      makeAccount({ id: "acc-closed", status: "CLOSED", currentCash: 0 }),
    ]);
    ledgerFindMany.mockResolvedValue([
      { accountId: "acc-closed", amount: 1_100_000, createdAt: new Date("2026-06-01T00:00:00Z") },
    ]);
    fetchStockPriceSnapshots.mockResolvedValue({ "005930": { price: 60_000 } });

    const response = await GET(new NextRequest("http://localhost/api/admin/accounts"));
    const { accounts } = await response.json();

    expect(accounts[0]).toMatchObject({ totalValue: 1_100_000, returnPct: 10 });
    expect(accounts[1]).toMatchObject({ totalValue: 1_100_000, returnPct: 10 });
  });
});
