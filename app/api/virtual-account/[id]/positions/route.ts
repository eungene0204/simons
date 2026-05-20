import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { fetchStockPriceSnapshots } from '@/lib/server/stock-prices';
import { getStockNameMap } from '@/lib/krx-stocks';

function resolvePositionName(
  symbol: string,
  storedName: string | null | undefined,
  stockNameMap: Record<string, string>
) {
  if (stockNameMap[symbol]) return stockNameMap[symbol];
  return storedName && storedName.trim().length > 0 ? storedName : symbol;
}

// GET: 보유 포지션 목록 (항상 실시간 시세 조회)
export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const stockNameMap = await getStockNameMap();
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
      const snapshots = await fetchStockPriceSnapshots(symbols, {
        subscribe: true,
        mode: 'realtime',
      });
      for (const [sym, quote] of Object.entries(snapshots)) {
        if (quote.price > 0) {
          livePrices[sym] = quote.price;
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
        name: resolvePositionName(p.symbol, p.name, stockNameMap),
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
