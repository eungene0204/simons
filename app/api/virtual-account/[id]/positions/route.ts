import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

function mapPosition(p: any) {
  return {
    symbol: p.symbol,
    name: p.name,
    quantity: p.quantity,
    averagePrice: p.avgPrice,
    currentPrice: p.avgPrice, // 프론트에서 실시간 가격으로 덮어씀
    totalValue: p.quantity * p.avgPrice,
    profit: 0,
    profitPercent: 0,
  };
}

// GET: 보유 포지션 목록
export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const positions = await prisma.virtualPosition.findMany({
      where: { accountId: params.id },
      orderBy: { openedAt: 'asc' },
    });
    return NextResponse.json(positions.map(mapPosition));
  } catch (error) {
    console.error('Failed to fetch positions:', error);
    return NextResponse.json({ error: 'Failed to fetch positions' }, { status: 500 });
  }
}
