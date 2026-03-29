import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

async function fetchPriceChange(symbol: string): Promise<{ price: number; prevClose: number } | null> {
  try {
    const res = await fetch(`${BACKEND_URL}/stock/${symbol}/ohlcv?limit=2`, { cache: 'no-store' });
    if (!res.ok) return null;
    const data = await res.json();
    const candles: { close: number }[] = data.candles ?? [];
    if (candles.length === 0) return null;
    const price = candles[candles.length - 1].close;
    const prevClose = candles.length >= 2 ? candles[candles.length - 2].close : price;
    return { price, prevClose };
  } catch {
    return null;
  }
}

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

    const quotes = await Promise.all(symbols.map((s) => fetchPriceChange(s.symbol)));

    const items: WatchlistSnapshotItem[] = symbols.map((s, i) => {
      const q = quotes[i];
      if (!q || q.price === 0) {
        return { symbol: s.symbol, name: s.name, price: 0, change: 0, changePercent: 0 };
      }
      const change = q.price - q.prevClose;
      const changePercent = q.prevClose > 0 ? (change / q.prevClose) * 100 : 0;
      return { symbol: s.symbol, name: s.name, price: q.price, change, changePercent };
    });

    return NextResponse.json(items);
  } catch (error) {
    console.error('Failed to fetch watchlist snapshot:', error);
    return NextResponse.json({ error: 'Failed to fetch watchlist snapshot' }, { status: 500 });
  }
}
