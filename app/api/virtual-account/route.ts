import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { resolveTrackedSymbolsForStrategy } from '@/lib/strategy-tracked-symbols';
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user';

function mapAccount(a: any, priceMap: Record<string, number>) {
  const totalValue =
    a.currentCash +
    (a.VirtualPosition ?? []).reduce((sum: number, p: any) => {
      const currentPrice = priceMap[p.symbol] ?? p.currentPrice ?? p.avgPrice;
      return sum + p.quantity * currentPrice;
    }, 0);
  return {
    id: a.id,
    name: a.name,
    initialAmount: a.initialCash,
    currentBalance: a.currentCash,
    totalValue,
    strategyId: a.strategyId ?? undefined,
    strategyName: a.strategyName ?? undefined,
    tradingMode: (a.tradingMode ?? "manual") as "auto" | "manual",
    createdAt: a.createdAt.toISOString(),
    updatedAt: a.updatedAt.toISOString(),
  };
}

// GET: 모든 가상계좌 목록
export async function GET() {
  try {
    const { userId } = await getOwnershipContext();
    const accounts = await prisma.virtualAccount.findMany({
      where: withOwnership({}, userId),
      include: { VirtualPosition: true },
      orderBy: { createdAt: 'desc' },
    });

    return NextResponse.json(accounts.map((a) => mapAccount(a, {})));
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to fetch virtual accounts:', error);
    return NextResponse.json({ error: 'Failed to fetch accounts' }, { status: 500 });
  }
}

// POST: 가상계좌 생성
export async function POST(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    const { name, initialAmount, strategyId, strategyName, tradingMode } = await request.json();

    if (!name || !initialAmount) {
      return NextResponse.json(
        { error: 'name and initialAmount are required' },
        { status: 400 }
      );
    }

    const strategy = strategyId
      ? userId == null
        ? await prisma.strategy.findUnique({
            where: { id: strategyId },
          })
        : await prisma.strategy.findFirst({
            where: withOwnership({ id: strategyId }, userId),
          })
      : null;

    const account = await prisma.virtualAccount.create({
      data: {
        id: crypto.randomUUID(),
        ...(userId != null && { userId }),
        name,
        initialCash: initialAmount,
        currentCash: initialAmount,
        strategyId: strategyId || null,
        strategyName: strategyName || null,
        tradingMode: tradingMode || "manual",
        updatedAt: new Date(),
      },
      include: { VirtualPosition: true },
    });

    if (strategy) {
      const resolved = await resolveTrackedSymbolsForStrategy({
        strategyId,
        strategyName: strategy.name,
        strategySettings: strategy.settings,
      });

      if (resolved.symbols.length > 0) {
        const today = new Date().toISOString().split("T")[0];
        await prisma.virtualMarketState.upsert({
          where: { accountId: account.id },
          create: {
            id: crypto.randomUUID(),
            accountId: account.id,
            startDate: today,
            status: tradingMode === "auto" ? "running" : "paused",
            symbols: JSON.stringify(resolved.symbols),
            updatedAt: new Date(),
          },
          update: {
            startDate: today,
            status: tradingMode === "auto" ? "running" : "paused",
            symbols: JSON.stringify(resolved.symbols),
            updatedAt: new Date(),
          },
        });
      }
    }

    return NextResponse.json(mapAccount(account, {}));
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to create virtual account:', error);
    return NextResponse.json({ error: 'Failed to create account' }, { status: 500 });
  }
}
