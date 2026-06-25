import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { resolveTrackedSymbolsForStrategy } from '@/lib/strategy-tracked-symbols';
import { getStockNameMap } from '@/lib/krx-stocks';
import {
  closeAccountWithSettlement,
  fetchSettlementPriceMap,
  getAccountSettlementValues,
  moneyToNumber,
  toMoney,
} from '@/lib/server/assetService';
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

function resolvePositionName(
  symbol: string,
  storedName: string | null | undefined,
  stockNameMap: Record<string, string>
) {
  if (stockNameMap[symbol]) return stockNameMap[symbol];
  if (storedName && storedName.trim().length > 0 && storedName !== symbol) return storedName;
  return symbol;
}

function mapAccount(
  a: any,
  priceMap: Record<string, number>,
  stockNameMap: Record<string, string>,
  settlementValue?: number
) {
  const positions = a.VirtualPosition ?? [];
  const currentCash = moneyToNumber(a.currentCash);
  const liveValue =
    currentCash +
    positions.reduce((sum: number, p: any) => {
      const currentPrice = priceMap[p.symbol] ?? moneyToNumber(p.currentPrice ?? p.avgPrice);
      return sum + p.quantity * currentPrice;
    }, 0);
  // CLOSED 계좌는 강제 정산 후 currentCash/포지션이 0/삭제되므로, 정산 시점 금액을 그대로 보여준다.
  const totalValue = a.status === "CLOSED" && settlementValue != null ? settlementValue : liveValue;
  const holdings = positions.map((p: any) => {
    const avgPrice = moneyToNumber(p.avgPrice);
    const currentPrice = priceMap[p.symbol] ?? moneyToNumber(p.currentPrice ?? p.avgPrice);
    const cost = p.quantity * avgPrice;
    const totalVal = p.quantity * currentPrice;
    const profit = totalVal - cost;
    return {
      symbol: p.symbol,
      name: resolvePositionName(p.symbol, p.name, stockNameMap),
      quantity: p.quantity,
      averagePrice: avgPrice,
      currentPrice,
      totalValue: totalVal,
      profit,
      profitPercent: cost > 0 ? (profit / cost) * 100 : 0,
    };
  });
  return {
    id: a.id,
    name: a.name,
    initialAmount: moneyToNumber(a.initialCash),
    currentBalance: currentCash,
    totalValue,
    status: a.status ?? "ACTIVE",
    strategyId: a.strategyId ?? undefined,
    strategyName: a.strategyName ?? undefined,
    tradingMode: (a.tradingMode ?? "manual") as "auto" | "manual",
    createdAt: a.createdAt.toISOString(),
    updatedAt: a.updatedAt.toISOString(),
    closedAt: a.closedAt ? a.closedAt.toISOString() : undefined,
    holdings,
  };
}

async function buildNameMap(symbols: string[]): Promise<Record<string, string>> {
  const [stockNameMap, dbStocks] = await Promise.all([
    getStockNameMap(),
    symbols.length > 0
      ? prisma.stock.findMany({ where: { symbol: { in: symbols }, name: { not: null } }, select: { symbol: true, name: true } })
      : Promise.resolve([]),
  ]);
  const merged: Record<string, string> = {};
  for (const s of dbStocks) if (s.name) merged[s.symbol] = s.name;
  return { ...merged, ...stockNameMap };
}

async function findOwnedAccountById(
  id: string,
  userId: number | null,
  options: Record<string, unknown> = {}
) {
  if (userId == null) {
    return prisma.virtualAccount.findUnique({
      where: { id },
      ...options,
    });
  }

  return prisma.virtualAccount.findFirst({
    where: withOwnership({ id }, userId),
    ...options,
  });
}

async function findOwnedStrategyById(
  id: string,
  userId: number | null
) {
  if (userId == null) {
    return prisma.strategy.findUnique({
      where: { id },
    });
  }

  return prisma.strategy.findFirst({
    where: withOwnership({ id }, userId),
  });
}

// GET: 계좌 상세 조회
export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext();
    const account = await findOwnedAccountById(params.id, userId, {
      include: { VirtualPosition: true },
    });
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }

    const symbols = (account as any).VirtualPosition.map((p: any) => p.symbol);
    const nameMap = await buildNameMap(symbols);
    const settlementValues = await getAccountSettlementValues(prisma, [account.id]);
    return NextResponse.json(mapAccount(account, {}, nameMap, settlementValues[account.id]));
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to fetch virtual account:', error);
    return NextResponse.json({ error: 'Failed to fetch account' }, { status: 500 });
  }
}

// PATCH: 계좌 업데이트 (현금 잔액 등)
export async function PATCH(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext();
    const ownedAccount = await findOwnedAccountById(params.id, userId, {
      select: { id: true, status: true },
    });
    if (!ownedAccount) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }
    if ((ownedAccount as any).status === "CLOSED") {
      return NextResponse.json({ error: 'Account is closed' }, { status: 400 });
    }

    const body = await request.json();
    const strategyChanged = typeof body.strategyId === "string" && body.strategyId.trim().length > 0;
    const account = await prisma.virtualAccount.update({
      where: { id: params.id },
      data: {
        ...(body.currentBalance !== undefined && { currentCash: toMoney(body.currentBalance) }),
        ...(body.tradingMode !== undefined && { tradingMode: body.tradingMode }),
        ...(body.strategyId !== undefined && { strategyId: body.strategyId }),
        ...(body.strategyName !== undefined && { strategyName: body.strategyName }),
        updatedAt: new Date(),
      },
      include: { VirtualPosition: true },
    });

    const posSymbols = account.VirtualPosition.map((p: any) => p.symbol);
    const nameMap = await buildNameMap(posSymbols);

    if (strategyChanged) {
      const strategy = await findOwnedStrategyById(body.strategyId, userId);

      const resolved = strategy
        ? await resolveTrackedSymbolsForStrategy({
            strategyId: body.strategyId,
            strategyName: strategy.name,
            strategySettings: strategy.settings,
          })
        : { symbols: [], source: "universe" as const };
      const topSymbols = resolved.symbols;

      if (topSymbols.length > 0) {
        const existingState = await prisma.virtualMarketState.findUnique({
          where: { accountId: params.id },
        });
        const today = new Date().toISOString().split("T")[0];
        const state = await prisma.virtualMarketState.upsert({
          where: { accountId: params.id },
          create: {
            id: crypto.randomUUID(),
            accountId: params.id,
            startDate: today,
            status: existingState?.status ?? "running",
            symbols: JSON.stringify(topSymbols),
            updatedAt: new Date(),
          },
          update: {
            symbols: JSON.stringify(topSymbols),
            updatedAt: new Date(),
          },
        });

        // fire-and-forget: route 응답을 block하지 않도록 timeout 없이 병렬 실행
        fetch(`${BACKEND_URL}/market/subscribe`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbols: topSymbols }),
          signal: AbortSignal.timeout(3000),
        }).catch((error) => {
          console.warn("Failed to subscribe top strategy symbols:", error);
        });

        return NextResponse.json({
          ...mapAccount(account, {}, nameMap),
          trackedSymbols: topSymbols,
          symbolSource: resolved.source,
          virtualMarketState: {
            ...state,
            symbols: topSymbols,
          },
        });
      }
    }

    return NextResponse.json(mapAccount(account, {}, nameMap));
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to update virtual account:', error);
    return NextResponse.json({ error: 'Failed to update account' }, { status: 500 });
  }
}

// DELETE: 계좌 삭제/정산
export async function DELETE(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext();
    if (userId == null) {
      await prisma.virtualAccount.delete({
        where: { id: params.id },
      });
      return NextResponse.json({ message: 'Account deleted' });
    }

    const account = await prisma.virtualAccount.findFirst({
      where: withOwnership({ id: params.id }, userId),
      include: { VirtualPosition: true },
    });
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }
    if (account.status === "CLOSED") {
      return NextResponse.json({ error: 'Account is closed' }, { status: 400 });
    }

    const priceMap = await fetchSettlementPriceMap(account.VirtualPosition);
    const result = await prisma.$transaction((tx) =>
      closeAccountWithSettlement(tx, {
        userId,
        accountId: params.id,
        priceMap,
      })
    );

    return NextResponse.json({
      message: 'Account closed',
      returnedAmount: result.returnedAmount.toNumber(),
      availableCash: result.availableCash.toNumber(),
      account: mapAccount(result.account, {}, {}, result.returnedAmount.toNumber()),
    });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    if (error instanceof Error && error.message === "ACCOUNT_CLOSED") {
      return NextResponse.json({ error: 'Account is closed' }, { status: 400 });
    }
    if (error instanceof Error && error.message === "PRICE_UNAVAILABLE") {
      return NextResponse.json({ error: 'Settlement price unavailable' }, { status: 502 });
    }
    if (error instanceof Error && error.message === "ACCOUNT_NOT_FOUND") {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }
    console.error('Failed to delete virtual account:', error);
    return NextResponse.json({ error: 'Failed to delete account' }, { status: 500 });
  }
}
