import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

async function fetchLastClose(symbol: string): Promise<number | null> {
  try {
    const res = await fetch(`${BACKEND_URL}/stock/${symbol}/ohlcv?limit=1`, {
      cache: 'no-store',
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.lastClose ?? null;
  } catch {
    return null;
  }
}

// GET: 보유 포지션 목록 (실시간 현재가 포함)
export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const positions = await prisma.virtualPosition.findMany({
      where: { accountId: params.id },
      orderBy: { openedAt: 'asc' },
    });

    if (positions.length === 0) {
      return NextResponse.json([]);
    }

    // 모든 종목 현재가 병렬 조회
    const prices = await Promise.all(positions.map((p) => fetchLastClose(p.symbol)));

    const result = positions.map((p, i) => {
      const currentPrice = prices[i] ?? p.avgPrice;
      const cost = p.quantity * p.avgPrice;
      const totalValue = p.quantity * currentPrice;
      const profit = totalValue - cost;
      const profitPercent = cost > 0 ? (profit / cost) * 100 : 0;
      return {
        symbol: p.symbol,
        name: p.name,
        quantity: p.quantity,
        averagePrice: p.avgPrice,
        currentPrice,
        totalValue,
        profit,
        profitPercent,
      };
    });

    return NextResponse.json(result);
  } catch (error) {
    console.error('Failed to fetch positions:', error);
    return NextResponse.json({ error: 'Failed to fetch positions' }, { status: 500 });
  }
}
