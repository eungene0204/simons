// @ts-nocheck
import { describe, expect, it, vi } from "vitest";

const virtualAccountFindMany = vi.fn();
const marketStateCount = vi.fn();
const orderCount = vi.fn();
const orderAggregate = vi.fn();
const orderFindMany = vi.fn();
const userBacktestFindMany = vi.fn();
const assetLedgerFindMany = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualAccount: { findMany: virtualAccountFindMany },
    virtualMarketState: { count: marketStateCount },
    virtualOrder: {
      count: orderCount,
      aggregate: orderAggregate,
      findMany: orderFindMany,
    },
    userBacktestHistory: { findMany: userBacktestFindMany },
    backtestHistory: { findMany: vi.fn() },
    assetLedger: { findMany: assetLedgerFindMany },
  },
}));

vi.mock("@/lib/get-user", () => ({
  withOwnership: (where, userId) => ({ ...where, userId }),
}));

// unstable_cache 캐싱을 우회해 매 호출이 DB(mock)로 가게 한다.
vi.mock("next/cache", () => ({
  unstable_cache: (fn) => fn,
}));

const { getDashboardInitialData } = await import("@/lib/dashboard-data");

function makeAccount(overrides = {}) {
  return {
    id: "acc-active",
    userId: 1,
    name: "운용 계좌",
    status: "ACTIVE",
    initialCash: 10_000_000,
    currentCash: 12_000_000,
    strategyId: null,
    strategyName: null,
    tradingMode: "manual",
    createdAt: new Date("2026-01-01T00:00:00Z"),
    updatedAt: new Date("2026-01-01T00:00:00Z"),
    closedAt: null,
    VirtualPosition: [],
    ...overrides,
  };
}

describe("getDashboardInitialData portfolio stats", () => {
  it("삭제(CLOSED)된 계좌는 요약 통계에서 제외하고 운용중 계좌만 집계한다", async () => {
    virtualAccountFindMany.mockResolvedValue([
      makeAccount(),
      makeAccount({
        id: "acc-closed",
        name: "삭제 계좌",
        status: "CLOSED",
        initialCash: 5_000_000,
        currentCash: 0,
        closedAt: new Date("2026-06-01T00:00:00Z"),
      }),
    ]);
    marketStateCount.mockResolvedValue(0);
    orderCount.mockResolvedValue(0);
    orderAggregate.mockResolvedValue({ _sum: { realizedPnl: null } });
    orderFindMany.mockResolvedValue([]);
    userBacktestFindMany.mockResolvedValue([]);
    // CLOSED 계좌의 정산금 — 요약 통계엔 포함되면 안 되고 계좌 목록에만 반영된다.
    assetLedgerFindMany.mockResolvedValue([
      {
        accountId: "acc-closed",
        type: "ACCOUNT_LIQUIDATION_RETURN",
        amount: 5_500_000,
        createdAt: new Date("2026-06-01T00:00:00Z"),
      },
    ]);

    const data = await getDashboardInitialData(1);

    // 운용중 계좌(초기 1천만, 평가 1,200만)만 반영 — CLOSED의 500만/정산 550만은 제외
    expect(data.portfolioStats.totalInvested).toBe(10_000_000);
    expect(data.portfolioStats.totalValue).toBe(12_000_000);
    expect(data.portfolioStats.totalProfit).toBe(2_000_000);
    expect(data.portfolioStats.totalReturnPct).toBeCloseTo(20);
    expect(data.portfolioStats.accountCount).toBe(1);

    // 가상계좌 목록에는 삭제된 계좌도 정산금 기준으로 계속 표시된다.
    const closedItem = data.accountList.accounts.find((a) => a.id === "acc-closed");
    expect(closedItem?.status).toBe("CLOSED");
    expect(closedItem?.totalValue).toBe(5_500_000);
  });
});

describe("getDashboardInitialData 조회 왕복 묶기", () => {
  it("정산금 조회는 집계 조회가 끝나기를 기다리지 않고 같은 왕복에 띄운다", async () => {
    virtualAccountFindMany.mockResolvedValue([makeAccount()]);
    // 집계 조회 하나를 영원히 대기시켜, 정산금 조회가 그 결과에 직렬로 묶여 있으면 호출조차 안 되게 한다.
    marketStateCount.mockReturnValue(new Promise(() => {}));
    orderCount.mockResolvedValue(0);
    orderAggregate.mockResolvedValue({ _sum: { realizedPnl: null } });
    orderFindMany.mockResolvedValue([]);
    userBacktestFindMany.mockResolvedValue([]);
    assetLedgerFindMany.mockClear();
    assetLedgerFindMany.mockResolvedValue([]);

    void getDashboardInitialData(1);
    // 계좌 조회 resolve → 후속 조회 발행까지 마이크로태스크를 몇 번 흘린다.
    for (let i = 0; i < 5; i++) await Promise.resolve();

    expect(assetLedgerFindMany).toHaveBeenCalledTimes(1);
  });
});
