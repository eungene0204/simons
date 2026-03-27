import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

async function fetchLastClose(symbol: string): Promise<number | null> {
  try {
    const res = await fetch(`${BACKEND_URL}/stock/${symbol}/ohlcv?limit=1`, { cache: 'no-store' });
    if (!res.ok) return null;
    const data = await res.json();
    return data.lastClose ?? null;
  } catch {
    return null;
  }
}

function mapAccount(a: any, priceMap: Record<string, number>) {
  const totalValue =
    a.currentCash +
    (a.VirtualPosition ?? []).reduce((sum: number, p: any) => {
      const currentPrice = priceMap[p.symbol] ?? p.avgPrice;
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
    const accounts = await prisma.virtualAccount.findMany({
      include: { VirtualPosition: true },
      orderBy: { createdAt: 'desc' },
    });

    // 전체 계좌의 고유 종목 코드 수집 후 병렬로 현재가 조회
    const symbols = [...new Set(accounts.flatMap((a) => a.VirtualPosition.map((p) => p.symbol)))];
    const prices = await Promise.all(symbols.map(fetchLastClose));
    const priceMap: Record<string, number> = {};
    symbols.forEach((s, i) => { if (prices[i] !== null) priceMap[s] = prices[i]!; });

    return NextResponse.json(accounts.map((a) => mapAccount(a, priceMap)));
  } catch (error) {
    console.error('Failed to fetch virtual accounts:', error);
    return NextResponse.json({ error: 'Failed to fetch accounts' }, { status: 500 });
  }
}

// POST: 가상계좌 생성
export async function POST(request: Request) {
  try {
    const { name, initialAmount, strategyId, strategyName, tradingMode } = await request.json();

    if (!name || !initialAmount) {
      return NextResponse.json(
        { error: 'name and initialAmount are required' },
        { status: 400 }
      );
    }

    if (!strategyId) {
      return NextResponse.json(
        { error: '전략을 선택해야 계좌를 생성할 수 있습니다.' },
        { status: 400 }
      );
    }

    const account = await prisma.virtualAccount.create({
      data: {
        id: crypto.randomUUID(),
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

    return NextResponse.json(mapAccount(account, {}));
  } catch (error) {
    console.error('Failed to create virtual account:', error);
    return NextResponse.json({ error: 'Failed to create account' }, { status: 500 });
  }
}
