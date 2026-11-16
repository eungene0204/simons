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
  creditCash,
  debitCash,
  fetchSettlementPriceMap,
  getAccountSettlementValues,
  moneyToNumber,
  resolveAccountTotalValue,
} from "@/lib/server/assetService";

function createTx(overrides: Record<string, any> = {}) {
  return {
    $queryRaw: vi.fn(),
    assetLedger: {
      create: vi.fn(),
      findFirst: vi.fn(),
    },
    virtualAccount: {
      create: vi.fn(),
      findMany: vi.fn(),
      findFirst: vi.fn(),
      update: vi.fn(),
      updateMany: vi.fn(),
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

    // 남은 현금 + 강제 매도 대금 (350만원 매도 − 수수료 525 − 거래세 0.15% 5,250)
    expect(result.returnedAmount.toNumber()).toBe(3_694_225);
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

  // 2026-11-17 lost update: 읽어 둔 잔고로 절대값을 쓰면 파이썬 자동매매의 동시 차감이 지워졌다.
  it("debitCash는 잔고 조건부 상대 차감이고, 잔고가 모자라면 INSUFFICIENT_BALANCE", async () => {
    const tx = createTx();
    tx.virtualAccount.updateMany.mockResolvedValueOnce({ count: 1 });
    await debitCash(tx, "account-1", 1_000);
    const call = tx.virtualAccount.updateMany.mock.calls[0][0];
    expect(call.where.id).toBe("account-1");
    expect(call.where.currentCash.gte.toNumber()).toBe(1_000);
    expect(call.data.currentCash.decrement.toNumber()).toBe(1_000);
    expect(call.data.currentCash).not.toHaveProperty("set");

    tx.virtualAccount.updateMany.mockResolvedValueOnce({ count: 0 });
    await expect(debitCash(tx, "account-1", 1_000)).rejects.toThrow("INSUFFICIENT_BALANCE");
  });

  it("creditCash는 읽은 잔고 없이 increment로 더한다", async () => {
    const tx = createTx();
    await creditCash(tx, "account-1", 2_500);
    const call = tx.virtualAccount.update.mock.calls[0][0];
    expect(call.where).toEqual({ id: "account-1" });
    expect(call.data.currentCash.increment.toNumber()).toBe(2_500);
  });

  it("계좌 정산은 현금을 읽기 전에 계좌 행을 잠근다(FOR UPDATE)", async () => {
    const tx = createTx();
    tx.virtualAccount.findFirst.mockResolvedValue({ ...activeAccount, VirtualPosition: [] });
    tx.virtualAccount.update.mockResolvedValue({ ...activeAccount, status: "CLOSED", VirtualPosition: [] });

    await closeAccountWithSettlement(tx, { userId: 1, accountId: "account-1", priceMap: {} });

    const [strings, accountId] = tx.$queryRaw.mock.calls[0];
    expect(strings.join("?")).toMatch(/FOR UPDATE/);
    expect(accountId).toBe("account-1");
    expect(tx.$queryRaw.mock.invocationCallOrder[0]).toBeLessThan(
      tx.virtualAccount.findFirst.mock.invocationCallOrder[0]
    );
  });
});
