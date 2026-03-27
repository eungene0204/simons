import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// GET: 보유 포지션 목록 (항상 실시간 시세 조회)
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

    // 실시간 시세 조회 (장중/장외 모두 — Naver 캐시 TTL 내 최신 가격)
    const symbols = positions.map((p) => p.symbol);
    let livePrices: Record<string, number> = {};
    try {
      const res = await fetch(`${BACKEND_URL}/market/prices`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols }),
        cache: 'no-store',
      });
      if (res.ok) {
        const data: Record<string, { close: number }> = await res.json();
        for (const [sym, q] of Object.entries(data)) {
          if (q.close) livePrices[sym] = q.close;
        }
      }
    } catch {
      // 시세 조회 실패 시 DB 값으로 폴백
    }

    const result = positions.map((p) => {
      const currentPrice = livePrices[p.symbol] ?? p.currentPrice ?? p.avgPrice;
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
