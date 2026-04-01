import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

async function fetchBatchPrices(symbols: string[]): Promise<Record<string, number>> {
  if (symbols.length === 0) return {};
  try {
    const res = await fetch(`${BACKEND_URL}/market/prices`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbols }),
      cache: 'no-store',
    });
    if (!res.ok) return {};
    const data: Record<string, { close: number }> = await res.json();
    return Object.fromEntries(
      Object.entries(data).filter(([, v]) => v?.close).map(([k, v]) => [k, v.close])
    );
  } catch {
    return {};
  }
}

function mapAccount(a: any, priceMap: Record<string, number>) {
  const positions = a.VirtualPosition ?? [];
  const totalValue =
    a.currentCash +
    positions.reduce((sum: number, p: any) => {
      const currentPrice = priceMap[p.symbol] ?? p.currentPrice ?? p.avgPrice;
      return sum + p.quantity * currentPrice;
    }, 0);
  const holdings = positions.map((p: any) => {
    const currentPrice = priceMap[p.symbol] ?? p.currentPrice ?? p.avgPrice;
    const cost = p.quantity * p.avgPrice;
    const totalVal = p.quantity * currentPrice;
    const profit = totalVal - cost;
    return {
      symbol: p.symbol,
      name: p.name,
      quantity: p.quantity,
      averagePrice: p.avgPrice,
      currentPrice,
      totalValue: totalVal,
      profit,
      profitPercent: cost > 0 ? (profit / cost) * 100 : 0,
    };
  });
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
    holdings,
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
      include: { VirtualPosition: true },
    });
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }

    // 보유 종목 현재가 배치 조회 (1회 요청)
    const symbols = account.VirtualPosition.map((p) => p.symbol);
    const priceMap = await fetchBatchPrices(symbols);

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
        updatedAt: new Date(),
      },
      include: { VirtualPosition: true },
    });
    const symbols2 = account.VirtualPosition.map((p) => p.symbol);
    const priceMap2 = await fetchBatchPrices(symbols2);

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
