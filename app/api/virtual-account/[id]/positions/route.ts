import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { fetchStockPriceSnapshots } from '@/lib/server/stock-prices';
import { getStockNameMap } from '@/lib/krx-stocks';
import { isZeroValuation } from '@/lib/listing-status';
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user';
import { moneyToNumber } from '@/lib/server/assetService';

function resolvePositionName(
  symbol: string,
  storedName: string | null | undefined,
  stockNameMap: Record<string, string>
) {
  if (stockNameMap[symbol]) return stockNameMap[symbol];
  if (storedName && storedName.trim().length > 0 && storedName !== symbol) return storedName;
  return symbol;
}

// GET: 보유 포지션 목록 (항상 실시간 시세 조회)
export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext();
    const account = await prisma.virtualAccount.findFirst({
      where: withOwnership({ id: params.id }, userId),
      select: { id: true },
    });
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }

    const positions = await prisma.virtualPosition.findMany({
      where: { accountId: params.id },
      orderBy: { openedAt: 'asc' },
    });

    if (positions.length === 0) {
      return NextResponse.json([]);
    }

    // 상장 상태 + 이름 조회 (DELISTED → 0원 평가)
    const symbols = positions.map((p) => p.symbol);
    const [stockNameMap, stockRecords] = await Promise.all([
      getStockNameMap(),
      prisma.stock.findMany({
        where: { symbol: { in: symbols } },
        select: { symbol: true, name: true, listingStatus: true, lastTradableDate: true, delistingDate: true },
      }),
    ]);
    // DB Stock 이름을 우선 적용 (korea-stocks.json에 없는 상장폐지 종목 대응)
    const dbNameMap = Object.fromEntries(stockRecords.filter((s) => s.name).map((s) => [s.symbol, s.name!]));
    const mergedNameMap = { ...dbNameMap, ...stockNameMap };
    const statusMap = Object.fromEntries(stockRecords.map((s) => [s.symbol, s as { symbol: string; listingStatus: string; lastTradableDate: string | null; delistingDate: string | null }]));
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
      const stockInfo = statusMap[p.symbol];
      const listingStatus = stockInfo?.listingStatus ?? 'NORMAL';

      // DELISTED: 평가금액 0원
      let currentPrice: number;
      if (isZeroValuation(listingStatus)) {
        currentPrice = 0;
      } else {
        currentPrice = livePrices[p.symbol] ?? moneyToNumber(p.currentPrice ?? p.avgPrice);
      }

      const averagePrice = moneyToNumber(p.avgPrice);
      const cost = p.quantity * averagePrice;
      const totalValue = p.quantity * currentPrice;
      const profit = totalValue - cost;
      const profitPercent = cost > 0 ? (profit / cost) * 100 : 0;
      return {
        symbol: p.symbol,
        name: resolvePositionName(p.symbol, p.name, mergedNameMap),
        quantity: p.quantity,
        averagePrice,
        currentPrice,
        totalValue,
        profit,
        profitPercent,
        listingStatus,
        lastTradableDate: stockInfo?.lastTradableDate ?? null,
        delistingDate: stockInfo?.delistingDate ?? null,
      };
    });

    return NextResponse.json(result);
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to fetch positions:', error);
    return NextResponse.json({ error: 'Failed to fetch positions' }, { status: 500 });
  }
}
