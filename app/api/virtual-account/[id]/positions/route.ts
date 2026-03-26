import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

// GET: 보유 포지션 목록 (가상시장 현재가 포함)
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

    const result = positions.map((p) => {
      const currentPrice = p.currentPrice ?? p.avgPrice;
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
