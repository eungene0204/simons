// @ts-nocheck
import { Prisma } from "@prisma/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockFetchStockPriceSnapshots = vi.hoisted(() => vi.fn());

vi.mock("@/lib/server/stock-prices", () => ({
  fetchStockPriceSnapshots: mockFetchStockPriceSnapshots,
}));

import {
  calculateAccountValue,
  closeAccountWithSettlement,
  createFundedAccount,
  fetchSettlementPriceMap,
  getAccountSettlementValues,
  moneyToNumber,
  resolveAccountTotalValue,
} from "@/lib/server/assetService";

function createTx(overrides: Record<string, any> = {}) {
  return {
    assetLedger: {
      create: vi.fn(),
      findFirst: vi.fn(),
    },
    virtualAccount: {
      create: vi.fn(),
      findMany: vi.fn(),
      findFirst: vi.fn(),
      update: vi.fn(),
    },
    virtualPosition: {
      deleteMany: vi.fn(),
    },
    virtualMarketState: {
      updateMany: vi.fn(),
    },
    virtualOrder: {
      create: vi.fn(),
      updateMany: vi.fn(),
    },
    ...overrides,
  };
}

const activeAccount = {
  id: "account-1",
  userId: 1,
  name: "계좌 A",
  initialCash: 3_000_000,
  currentCash: 200_000,
  status: "ACTIVE",
  strategyId: null,
  strategyName: null,
  tradingMode: "manual",
  createdAt: new Date("2026-01-01"),
  updatedAt: new Date("2026-01-01"),
  VirtualPosition: [
    {
      symbol: "005930",
      name: "삼성전자",
      quantity: 10,
      avgPrice: 300_000,
      currentPrice: 350_000,
    },
  ],
};

describe("asset service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchStockPriceSnapshots.mockResolvedValue({});
  });

  it("계좌는 전달된 초기 투자금으로 생성되며 공유 자산 풀에서 차감하지 않는다", async () => {
    const tx = createTx();
    tx.virtualAccount.create.mockResolvedValue({ ...activeAccount, VirtualPosition: [] });

    await createFundedAccount(tx, {
      userId: 1,
      name: "계좌 A",
      initialAmount: 50_000_000,
    });

    expect(tx.virtualAccount.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        userId: 1,
        name: "계좌 A",
        initialCash: new Prisma.Decimal(50_000_000),
        currentCash: new Prisma.Decimal(50_000_000),
        status: "ACTIVE",
      }),
      include: { VirtualPosition: true },
    });
    // 자산 풀 차감/배정 원장이 없어야 한다
    expect(tx.assetLedger.create).not.toHaveBeenCalled();
  });

  it("음수 금액 입력은 거부된다", async () => {
    const tx = createTx();

    await expect(
      createFundedAccount(tx, {
        userId: 1,
        name: "계좌 A",
        initialAmount: -1,
      })
    ).rejects.toThrow("INVALID_AMOUNT");
    expect(tx.virtualAccount.create).not.toHaveBeenCalled();
  });

  it("계좌 가치는 현금과 보유 종목 평가금액으로 계산한다", () => {
    expect(calculateAccountValue(activeAccount).toNumber()).toBe(3_700_000);
  });

  it("계좌 해지 시 정산금을 다른 곳으로 이전하지 않고 정산값만 기록한다", async () => {
    const tx = createTx();
    tx.virtualAccount.findFirst.mockResolvedValue(activeAccount);
    tx.virtualAccount.update.mockResolvedValue({
      ...activeAccount,
      currentCash: 0,
      status: "CLOSED",
      VirtualPosition: [],
    });

    const result = await closeAccountWithSettlement(tx, {
      userId: 1,
      accountId: "account-1",
      priceMap: { "005930": new Prisma.Decimal(350_000) },
    });

    // 남은 현금 + 강제 매도 대금
    expect(result.returnedAmount.toNumber()).toBe(3_692_475);
    // 정산값은 ACCOUNT_LIQUIDATION_RETURN 원장에만 기록된다(사용자 자산으로 이전하지 않음)
    expect(tx.assetLedger.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        accountId: "account-1",
        type: "ACCOUNT_LIQUIDATION_RETURN",
        amount: expect.any(Prisma.Decimal),
        balanceAfter: expect.any(Prisma.Decimal),
      }),
    });
    expect(tx.virtualPosition.deleteMany).toHaveBeenCalledWith({
      where: { accountId: "account-1" },
    });
    const updateArg = tx.virtualAccount.update.mock.calls[0][0];
    expect(moneyToNumber(updateArg.data.currentCash)).toBe(0);
    expect(updateArg.data.status).toBe("CLOSED");
  });

  it("계좌 해지 시 모니터링 종목 이력(VirtualMarketState)을 지우지 않고 추적만 멈춘다", async () => {
    const tx = createTx();
    tx.virtualAccount.findFirst.mockResolvedValue(activeAccount);
    tx.virtualAccount.update.mockResolvedValue({
      ...activeAccount,
      status: "CLOSED",
      VirtualPosition: [],
    });

    await closeAccountWithSettlement(tx, {
      userId: 1,
      accountId: "account-1",
      priceMap: { "005930": new Prisma.Decimal(350_000) },
    });

    expect(tx.virtualMarketState.updateMany).toHaveBeenCalledWith({
      where: { accountId: "account-1" },
      data: expect.objectContaining({ status: "stopped" }),
    });
  });

  it("포지션 강제 청산 중 오류가 나면 이후 쓰기를 실행하지 않는다", async () => {
    const tx = createTx();
    tx.virtualAccount.findFirst.mockResolvedValue(activeAccount);

    await expect(
      closeAccountWithSettlement(tx, {
        userId: 1,
        accountId: "account-1",
        priceMap: {},
      })
    ).rejects.toThrow("PRICE_UNAVAILABLE");

    expect(tx.virtualPosition.deleteMany).not.toHaveBeenCalled();
    expect(tx.virtualAccount.update).not.toHaveBeenCalled();
  });

  it("실시간 정산 시세 조회가 실패하면 저장된 현재가로 정산 가격을 만든다", async () => {
    mockFetchStockPriceSnapshots.mockRejectedValue(new Error("quote provider down"));

    const priceMap = await fetchSettlementPriceMap([
      {
        symbol: "005930",
        avgPrice: new Prisma.Decimal(300_000),
        currentPrice: new Prisma.Decimal(350_000),
      },
    ]);

    expect(priceMap["005930"].toNumber()).toBe(350_000);
  });

  it("실시간 정산 시세와 저장된 현재가가 모두 없으면 평단가로 정산 가격을 만든다", async () => {
    mockFetchStockPriceSnapshots.mockResolvedValue({});

    const priceMap = await fetchSettlementPriceMap([
      {
        symbol: "005930",
        avgPrice: new Prisma.Decimal(300_000),
        currentPrice: null,
      },
    ]);

    expect(priceMap["005930"].toNumber()).toBe(300_000);
  });

  it("CLOSED 계좌는 다시 해지할 수 없다", async () => {
    const tx = createTx();
    tx.virtualAccount.findFirst.mockResolvedValue({
      ...activeAccount,
      status: "CLOSED",
    });

    await expect(
      closeAccountWithSettlement(tx, {
        userId: 1,
        accountId: "account-1",
        priceMap: { "005930": new Prisma.Decimal(350_000) },
      })
    ).rejects.toThrow("ACCOUNT_CLOSED");
  });

  it("거래가 없던 계좌(0% 수익률)를 닫아도 정산금이 그대로 totalValue가 되어 -100%로 계산되지 않는다", () => {
    const settlementValues = { "account-1": 5_000_000 };
    const totalValue = resolveAccountTotalValue(
      { id: "account-1", status: "CLOSED" },
      0, // 정산 후 currentCash=0, 포지션 없음
      settlementValues
    );

    expect(totalValue).toBe(5_000_000);
  });

  it("ACTIVE 계좌는 정산금 맵과 무관하게 현재 평가금액(liveValue)을 그대로 쓴다", () => {
    const totalValue = resolveAccountTotalValue(
      { id: "account-1", status: "ACTIVE" },
      3_700_000,
      { "account-1": 5_000_000 }
    );

    expect(totalValue).toBe(3_700_000);
  });

  it("getAccountSettlementValues는 ACCOUNT_LIQUIDATION_RETURN 원장에서 계좌별 정산금을 가져온다", async () => {
    const client = {
      assetLedger: {
        findMany: vi.fn().mockResolvedValue([
          { accountId: "account-1", amount: new Prisma.Decimal(5_000_000) },
          { accountId: "account-2", amount: new Prisma.Decimal(8_568_751) },
        ]),
      },
    };

    const result = await getAccountSettlementValues(client, ["account-1", "account-2"]);

    expect(result).toEqual({ "account-1": 5_000_000, "account-2": 8_568_751 });
    expect(client.assetLedger.findMany).toHaveBeenCalledWith({
      where: { accountId: { in: ["account-1", "account-2"] }, type: "ACCOUNT_LIQUIDATION_RETURN" },
      orderBy: { createdAt: "desc" },
    });
  });
});
