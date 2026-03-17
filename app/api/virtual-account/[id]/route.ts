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
    (a.positions ?? []).reduce((sum: number, p: any) => {
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

// GET: 계좌 상세 조회
export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const account = await prisma.virtualAccount.findUnique({
      where: { id: params.id },
      include: { positions: true },
    });
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }

    // 보유 종목 현재가 병렬 조회
    const symbols = account.positions.map((p) => p.symbol);
    const prices = await Promise.all(symbols.map(fetchLastClose));
    const priceMap: Record<string, number> = {};
    symbols.forEach((s, i) => { if (prices[i] !== null) priceMap[s] = prices[i]!; });

    return NextResponse.json(mapAccount(account, priceMap));
  } catch (error) {
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
    const body = await request.json();
    const account = await prisma.virtualAccount.update({
      where: { id: params.id },
      data: {
        ...(body.currentBalance !== undefined && { currentCash: body.currentBalance }),
        ...(body.tradingMode !== undefined && { tradingMode: body.tradingMode }),
      },
      include: { positions: true },
    });
    const symbols2 = account.positions.map((p) => p.symbol);
    const prices2 = await Promise.all(symbols2.map(fetchLastClose));
    const priceMap2: Record<string, number> = {};
    symbols2.forEach((s, i) => { if (prices2[i] !== null) priceMap2[s] = prices2[i]!; });

    return NextResponse.json(mapAccount(account, priceMap2));
  } catch (error) {
    console.error('Failed to update virtual account:', error);
    return NextResponse.json({ error: 'Failed to update account' }, { status: 500 });
  }
}

// DELETE: 계좌 삭제 (positions, orders cascade)
export async function DELETE(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    await prisma.virtualAccount.delete({ where: { id: params.id } });
    return NextResponse.json({ message: 'Account deleted' });
  } catch (error) {
    console.error('Failed to delete virtual account:', error);
    return NextResponse.json({ error: 'Failed to delete account' }, { status: 500 });
  }
}
