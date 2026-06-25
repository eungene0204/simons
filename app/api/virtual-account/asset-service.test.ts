// @ts-nocheck
import { Prisma } from "@prisma/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  calculateAccountValue,
  closeAccountWithSettlement,
  createFundedAccount,
  ensureUserAsset,
  getAccountSettlementValues,
  INITIAL_GRANT_AMOUNT,
  moneyToNumber,
  resolveAccountTotalValue,
} from "@/lib/server/assetService";

function createTx(overrides: Record<string, any> = {}) {
  return {
    userAsset: {
      findUnique: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
    },
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
  });

  it("신규 가입 시 10,000,000원 자산과 INITIAL_GRANT 원장을 생성한다", async () => {
    const tx = createTx();
    tx.userAsset.findUnique.mockResolvedValue(null);
    tx.virtualAccount.findMany.mockResolvedValue([]);
    tx.userAsset.create.mockResolvedValue({
      userId: 1,
      availableCash: INITIAL_GRANT_AMOUNT,
      initialGrantAmount: INITIAL_GRANT_AMOUNT,
    });

    await ensureUserAsset(tx, 1);

    expect(tx.userAsset.create).toHaveBeenCalledWith({
      data: {
        userId: 1,
        availableCash: INITIAL_GRANT_AMOUNT,
        initialGrantAmount: INITIAL_GRANT_AMOUNT,
      },
    });
    expect(tx.assetLedger.create).toHaveBeenCalledWith({
      data: {
        userId: 1,
        type: "INITIAL_GRANT",
        amount: INITIAL_GRANT_AMOUNT,
        balanceAfter: INITIAL_GRANT_AMOUNT,
      },
    });
  });

  it("기존 ACTIVE 계좌가 있는데 배정 원장이 없으면 availableCash에서 초기 투자금을 차감한다", async () => {
    const tx = createTx();
    tx.userAsset.findUnique.mockResolvedValue({
      userId: 1,
      availableCash: new Prisma.Decimal(10_000_000),
      initialGrantAmount: new Prisma.Decimal(10_000_000),
    });
    tx.virtualAccount.findMany.mockResolvedValue([
      {
        id: "legacy-account",
        initialCash: new Prisma.Decimal(10_000_000),
      },
    ]);
    tx.assetLedger.findFirst.mockResolvedValue(null);
    tx.userAsset.update.mockResolvedValue({
      userId: 1,
      availableCash: new Prisma.Decimal(0),
      initialGrantAmount: new Prisma.Decimal(10_000_000),
    });

    const asset = await ensureUserAsset(tx, 1);

    expect(tx.assetLedger.create).toHaveBeenCalledWith({
      data: {
        userId: 1,
        accountId: "legacy-account",
        type: "ACCOUNT_ALLOCATION",
        amount: new Prisma.Decimal(-10_000_000),
        balanceAfter: new Prisma.Decimal(0),
      },
    });
    expect(tx.userAsset.update).toHaveBeenCalledWith({
      where: { userId: 1 },
      data: { availableCash: new Prisma.Decimal(0) },
    });
    expect(asset.availableCash.toNumber()).toBe(0);
  });

  it("3,000,000원 계좌 생성 시 availableCash를 7,000,000원으로 차감한다", async () => {
    const tx = createTx();
    tx.userAsset.findUnique.mockResolvedValue({
      userId: 1,
      availableCash: new Prisma.Decimal(10_000_000),
    });
    tx.virtualAccount.findMany.mockResolvedValue([]);
    tx.virtualAccount.create.mockResolvedValue({ ...activeAccount, VirtualPosition: [] });

    await createFundedAccount(tx, {
      userId: 1,
      name: "계좌 A",
      initialAmount: 3_000_000,
    });

    expect(tx.userAsset.update).toHaveBeenCalledWith({
      where: { userId: 1 },
      data: { availableCash: new Prisma.Decimal(7_000_000) },
    });
    expect(tx.assetLedger.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        type: "ACCOUNT_ALLOCATION",
        amount: new Prisma.Decimal(-3_000_000),
        balanceAfter: new Prisma.Decimal(7_000_000),
      }),
    });
  });

  it("사용 가능 자산보다 큰 금액으로 계좌를 생성하면 실패한다", async () => {
    const tx = createTx();
    tx.userAsset.findUnique.mockResolvedValue({
      userId: 1,
      availableCash: new Prisma.Decimal(1_000_000),
    });
    tx.virtualAccount.findMany.mockResolvedValue([]);

    await expect(
      createFundedAccount(tx, {
        userId: 1,
        name: "계좌 A",
        initialAmount: 3_000_000,
      })
    ).rejects.toThrow("INSUFFICIENT_ASSET_CASH");
    expect(tx.virtualAccount.create).not.toHaveBeenCalled();
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
  });

  it("계좌 가치는 현금과 보유 종목 평가금액으로 계산한다", () => {
    expect(calculateAccountValue(activeAccount).toNumber()).toBe(3_700_000);
  });

  it("계좌 삭제 시 남은 현금과 강제 매도 금액을 사용자 자산으로 반환한다", async () => {
    const tx = createTx();
    tx.userAsset.findUnique.mockResolvedValue({
      userId: 1,
      availableCash: new Prisma.Decimal(7_000_000),
    });
    tx.virtualAccount.findMany.mockResolvedValue([]);
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

    expect(result.returnedAmount.toNumber()).toBe(3_692_475);
    expect(result.availableCash.toNumber()).toBe(10_692_475);
    expect(tx.virtualPosition.deleteMany).toHaveBeenCalledWith({
      where: { accountId: "account-1" },
    });
    expect(tx.virtualAccount.update).toHaveBeenCalledWith({
      where: { id: "account-1" },
      data: expect.objectContaining({
        currentCash: expect.any(Prisma.Decimal),
        status: "CLOSED",
      }),
      include: { VirtualPosition: true },
    });
    const updateArg = tx.virtualAccount.update.mock.calls[0][0];
    expect(moneyToNumber(updateArg.data.currentCash)).toBe(0);
  });

  it("계좌 삭제 시 모니터링 종목 이력(VirtualMarketState)을 지우지 않고 추적만 멈춘다", async () => {
    const tx = createTx();
    tx.userAsset.findUnique.mockResolvedValue({
      userId: 1,
      availableCash: new Prisma.Decimal(7_000_000),
    });
    tx.virtualAccount.findMany.mockResolvedValue([]);
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

  it("수익이 난 계좌 삭제 후 사용자 총 자산이 증가한다", async () => {
    const tx = createTx();
    tx.userAsset.findUnique.mockResolvedValue({
      userId: 1,
      availableCash: new Prisma.Decimal(7_000_000),
    });
    tx.virtualAccount.findMany.mockResolvedValue([]);
    tx.virtualAccount.findFirst.mockResolvedValue(activeAccount);
    tx.virtualAccount.update.mockResolvedValue({
      ...activeAccount,
      status: "CLOSED",
      VirtualPosition: [],
    });

    const result = await closeAccountWithSettlement(tx, {
      userId: 1,
      accountId: "account-1",
      priceMap: { "005930": new Prisma.Decimal(350_000) },
    });

    expect(result.availableCash.gt(10_000_000)).toBe(true);
  });

  it("손실이 난 계좌 삭제 후 사용자 총 자산이 감소한다", async () => {
    const tx = createTx();
    tx.userAsset.findUnique.mockResolvedValue({
      userId: 1,
      availableCash: new Prisma.Decimal(7_000_000),
    });
    tx.virtualAccount.findMany.mockResolvedValue([]);
    tx.virtualAccount.findFirst.mockResolvedValue(activeAccount);
    tx.virtualAccount.update.mockResolvedValue({
      ...activeAccount,
      status: "CLOSED",
      VirtualPosition: [],
    });

    const result = await closeAccountWithSettlement(tx, {
      userId: 1,
      accountId: "account-1",
      priceMap: { "005930": new Prisma.Decimal(250_000) },
    });

    expect(result.availableCash.lt(10_000_000)).toBe(true);
  });

  it("포지션 강제 청산 중 오류가 나면 이후 쓰기를 실행하지 않는다", async () => {
    const tx = createTx();
    tx.userAsset.findUnique.mockResolvedValue({
      userId: 1,
      availableCash: new Prisma.Decimal(7_000_000),
    });
    tx.virtualAccount.findMany.mockResolvedValue([]);
    tx.virtualAccount.findFirst.mockResolvedValue(activeAccount);

    await expect(
      closeAccountWithSettlement(tx, {
        userId: 1,
        accountId: "account-1",
        priceMap: {},
      })
    ).rejects.toThrow("PRICE_UNAVAILABLE");

    expect(tx.virtualPosition.deleteMany).not.toHaveBeenCalled();
    expect(tx.userAsset.update).not.toHaveBeenCalled();
  });

  it("CLOSED 계좌는 다시 삭제할 수 없다", async () => {
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
