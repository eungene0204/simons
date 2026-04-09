import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { fetchStockPriceSnapshots } from '@/lib/server/stock-prices';

export interface WatchlistSnapshotItem {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
}

export async function GET() {
  try {
    const symbols = await prisma.watchlistSymbol.findMany({
      take: 12,
      orderBy: { addedAt: 'desc' },
    });

    if (symbols.length === 0) {
      return NextResponse.json([]);
    }

    const snapshots = await fetchStockPriceSnapshots(
      symbols.map((symbol) => symbol.symbol),
      {
        subscribe: true,
        mode: 'realtime',
      }
    );

    const items: WatchlistSnapshotItem[] = symbols.map((s, i) => {
      const q = snapshots[s.symbol];
      if (!q || q.price === 0) {
        return { symbol: s.symbol, name: s.name, price: 0, change: 0, changePercent: 0 };
      }
      const prevClose = q.previousClose ?? q.price;
      const change = q.price - prevClose;
      const changePercent = prevClose > 0 ? (change / prevClose) * 100 : 0;
      return { symbol: s.symbol, name: s.name, price: q.price, change, changePercent };
    });

    return NextResponse.json(items);
  } catch (error) {
    console.error('Failed to fetch watchlist snapshot:', error);
    return NextResponse.json({ error: 'Failed to fetch watchlist snapshot' }, { status: 500 });
  }
}
