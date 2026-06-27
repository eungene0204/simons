import { Prisma, PrismaClient } from "@prisma/client";
import { calcFee, calcRealizedPnl, calcSellProceeds, calcTransactionTax } from "@/lib/order-engine";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";
import type { StockPriceSnapshot } from "@/lib/stock-prices";

type AssetTx = Prisma.TransactionClient;
type AssetLedgerReader = Pick<PrismaClient, "assetLedger"> | Pick<AssetTx, "assetLedger">;

type AccountWithPositions = {
  id: string;
  userId: number | null;
  name: string;
  initialCash: Prisma.Decimal.Value;
  currentCash: Prisma.Decimal.Value;
  status?: string;
  strategyId: string | null;
  strategyName: string | null;
  tradingMode: string;
  createdAt: Date;
  updatedAt: Date;
  closedAt?: Date | null;
  VirtualPosition?: Array<{
    symbol: string;
    name: string;
    quantity: number;
    avgPrice: Prisma.Decimal.Value;
    currentPrice?: Prisma.Decimal.Value | null;
  }>;
};

export function toMoney(value: Prisma.Decimal.Value) {
  return new Prisma.Decimal(value);
}

export function moneyToNumber(value: Prisma.Decimal.Value | null | undefined) {
  if (value == null) return 0;
  return new Prisma.Decimal(value).toNumber();
}

function assertPositiveAmount(amount: Prisma.Decimal, errorCode = "INVALID_AMOUNT") {
  if (!amount.isFinite() || amount.lte(0)) {
    throw new Error(errorCode);
  }
}

function positionPrice(
  position: NonNullable<AccountWithPositions["VirtualPosition"]>[number],
  priceMap: Record<string, Prisma.Decimal>
) {
  return (
    priceMap[position.symbol] ??
    (position.currentPrice && toMoney(position.currentPrice).gt(0)
      ? toMoney(position.currentPrice)
      : toMoney(position.avgPrice))
  );
}

export function calculateAccountValue(
  account: AccountWithPositions,
  priceMap: Record<string, Prisma.Decimal> = {}
) {
  return (account.VirtualPosition ?? []).reduce(
    (sum, position) =>
      sum.plus(positionPrice(position, priceMap).mul(position.quantity)),
    toMoney(account.currentCash)
  );
}

// CLOSED 계좌는 강제 정산 후 currentCash/VirtualPosition이 0/삭제되므로,
// 그 값을 그대로 totalValue로 쓰면 -100% 수익률처럼 보인다.
// 닫힌 시점에 실제로 자산으로 돌아간 정산금(ACCOUNT_LIQUIDATION_RETURN)을 대신 사용해야 한다.
export async function getAccountSettlementValues(
  client: AssetLedgerReader,
  accountIds: string[]
): Promise<Record<string, number>> {
  if (accountIds.length === 0) return {};
  const entries = await client.assetLedger.findMany({
    where: { accountId: { in: accountIds }, type: "ACCOUNT_LIQUIDATION_RETURN" },
    orderBy: { createdAt: "desc" },
  });
  const result: Record<string, number> = {};
  for (const entry of entries) {
    if (entry.accountId && !(entry.accountId in result)) {
      result[entry.accountId] = moneyToNumber(entry.amount);
    }
  }
  return result;
}

// CLOSED 계좌면 정산금(settlementValues)을, 아니면 currentCash+포지션 평가금(liveValue)을 totalValue로 쓴다.
export function resolveAccountTotalValue(
  account: { id: string; status?: string | null },
  liveValue: number,
  settlementValues: Record<string, number>
): number {
  if (account.status === "CLOSED" && account.id in settlementValues) {
    return settlementValues[account.id];
  }
  return liveValue;
}

// 가상계좌를 플랜의 초기 투자금(initialAmount)으로 독립 생성한다.
// 공유 자산 풀에서 차감하지 않으며, 계좌마다 정해진 초기 투자금만 부여한다.
export async function createFundedAccount(
  tx: AssetTx,
  params: {
    userId: number;
    name: string;
    initialAmount: Prisma.Decimal.Value;
    strategyId?: string | null;
    strategyName?: string | null;
    tradingMode?: string | null;
  }
) {
  const allocation = toMoney(params.initialAmount);
  assertPositiveAmount(allocation);

  return tx.virtualAccount.create({
    data: {
      id: crypto.randomUUID(),
      userId: params.userId,
      name: params.name,
      initialCash: allocation,
      currentCash: allocation,
      status: "ACTIVE",
      strategyId: params.strategyId || null,
      strategyName: params.strategyName || null,
      tradingMode: params.tradingMode || "manual",
      updatedAt: new Date(),
    },
    include: { VirtualPosition: true },
  });
}

export async function closeAccountWithSettlement(
  tx: AssetTx,
  params: {
    userId: number;
    accountId: string;
    priceMap: Record<string, Prisma.Decimal>;
  }
) {
  const account = await tx.virtualAccount.findFirst({
    where: { id: params.accountId, userId: params.userId },
    include: { VirtualPosition: true },
  });
  if (!account) throw new Error("ACCOUNT_NOT_FOUND");
  if (account.status !== "ACTIVE") throw new Error("ACCOUNT_CLOSED");

  let settlementCash = toMoney(account.currentCash);

  for (const position of account.VirtualPosition) {
    const executionPrice = params.priceMap[position.symbol];
    if (!executionPrice || executionPrice.lte(0)) {
      throw new Error("PRICE_UNAVAILABLE");
    }

    const priceNumber = executionPrice.toNumber();
    const fee = calcFee(priceNumber, position.quantity);
    const tax = calcTransactionTax(priceNumber, position.quantity);
    const proceeds = toMoney(calcSellProceeds(priceNumber, position.quantity));
    const realizedPnl = calcRealizedPnl(
      priceNumber,
      moneyToNumber(position.avgPrice),
      position.quantity,
      fee,
      tax
    );

    settlementCash = settlementCash.plus(proceeds);

    await tx.virtualOrder.create({
      data: {
        id: crypto.randomUUID(),
        accountId: account.id,
        symbol: position.symbol,
        name: position.name,
        side: "SELL",
        type: "MARKET",
        quantity: position.quantity,
        price: toMoney(priceNumber),
        filledPrice: toMoney(priceNumber),
        fee: toMoney(fee),
        tax: toMoney(tax),
        avgBuyPrice: toMoney(position.avgPrice),
        realizedPnl: toMoney(realizedPnl),
        status: "FILLED",
        filledAt: new Date(),
      },
    });

    await tx.assetLedger.create({
      data: {
        userId: params.userId,
        accountId: account.id,
        type: "FORCE_SELL",
        amount: proceeds,
        balanceAfter: settlementCash,
      },
    });
  }

  await tx.virtualPosition.deleteMany({ where: { accountId: account.id } });
  // symbols 추적 이력은 보존하고 추적만 멈춘다 (계좌 닫기 후에도 모니터링 종목 목록을 조회할 수 있어야 함)
  await tx.virtualMarketState.updateMany({
    where: { accountId: account.id },
    data: { status: "stopped", updatedAt: new Date() },
  });
  await tx.virtualOrder.updateMany({
    where: { accountId: account.id, status: "PENDING" },
    data: { status: "CANCELLED" },
  });
  const closedAccount = await tx.virtualAccount.update({
    where: { id: account.id },
    data: {
      currentCash: toMoney(0),
      status: "CLOSED",
      closedAt: new Date(),
      updatedAt: new Date(),
    },
    include: { VirtualPosition: true },
  });
  // 계좌 정산값을 기록한다(닫힌 계좌의 최종 평가금액/수익률 조회용).
  // 남은 현금·평가금액은 다른 계좌나 사용자 자산으로 이전하지 않는다.
  await tx.assetLedger.create({
    data: {
      userId: params.userId,
      accountId: account.id,
      type: "ACCOUNT_LIQUIDATION_RETURN",
      amount: settlementCash,
      balanceAfter: settlementCash,
    },
  });

  return {
    account: closedAccount,
    returnedAmount: settlementCash,
  };
}

export async function fetchSettlementPriceMap(
  positions: Array<{ symbol: string; avgPrice: Prisma.Decimal.Value; currentPrice?: Prisma.Decimal.Value | null }>
) {
  const symbols = [...new Set(positions.map((position) => position.symbol))];
  if (symbols.length === 0) return {};

  const snapshots = await fetchStockPriceSnapshots(symbols, {
    mode: "realtime",
    subscribe: false,
  }).catch((): Record<string, StockPriceSnapshot> => ({}));

  return Object.fromEntries(
    positions.map((position) => {
      const snapshotPrice = snapshots[position.symbol]?.price;
      const storedPrice = moneyToNumber(position.currentPrice ?? position.avgPrice);
      const price = snapshotPrice && snapshotPrice > 0 ? snapshotPrice : storedPrice;
      if (!price || price <= 0) {
        throw new Error("PRICE_UNAVAILABLE");
      }
      return [position.symbol, toMoney(price)];
    })
  );
}
