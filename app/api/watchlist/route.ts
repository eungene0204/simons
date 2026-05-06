import { NextRequest, NextResponse } from 'next/server'
import { cache } from '@/lib/cache'
import { loadStockList } from '@/lib/krx-stocks'
import { fetchStockPriceSnapshots } from '@/lib/server/stock-prices'

export const dynamic = "force-dynamic";

interface WatchlistItem {
  symbol: string;
  name: string;
  logo?: string;
  currentPrice: number;
  changePercent: number;
  change: number;
  volume: number;
}

export async function GET(request: NextRequest) {
  try {
    // Get symbols from query parameter (sent from client's localStorage)
    const { searchParams } = new URL(request.url);
    const symbolsParam = searchParams.get('symbols');
    
    let symbols: string[] = [];
    let names: Record<string, string> = {};

    if (symbolsParam) {
      // Parse symbols from query parameter
      try {
        const parsed = JSON.parse(symbolsParam);
        if (Array.isArray(parsed)) {
          symbols = parsed;
          // Get names from KRX stock list
          try {
            const koreaStocks = await loadStockList();
            parsed.forEach((symbol: string) => {
              const stock = koreaStocks.find((s) => s.symbol === symbol);
              if (stock) {
                names[symbol] = stock.name;
              }
            });
          } catch (error) {
            console.error("Failed to load stock list:", error);
          }
        }
      } catch (error) {
        console.error("Failed to parse symbols:", error);
      }
    }

    // If no symbols provided, use default mock data
    if (symbols.length === 0) {
      symbols = [
        "005930", "000660", "035420", "035720", "005380", "051910",
        "006400", "028260", "034730", "003670", "018260", "032830"
      ];

      names = {
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "035420": "NAVER",
        "035720": "카카오",
        "005380": "현대차",
        "051910": "LG화학",
        "006400": "삼성SDI",
        "028260": "삼성물산",
        "034730": "SK",
        "003670": "포스코홀딩스",
        "018260": "삼성에스디에스",
        "032830": "삼성생명",
      };
    }

    // Check cache first
    const cacheKey = `watchlist:items:${symbols.join(',')}`;
    const cached = cache.get(cacheKey);
    if (cached) {
      console.log('Returning cached watchlist data');
      return NextResponse.json(cached);
    }

    console.log('Generating watchlist data for symbols:', symbols);

    const snapshots = await fetchStockPriceSnapshots(symbols, {
      subscribe: true,
      mode: 'realtime',
    });

    const watchlistItems: WatchlistItem[] = symbols.map((symbol) => {
      const snapshot = snapshots[symbol];
      const currentPrice = snapshot?.price ?? 0;
      const previousClose = snapshot?.previousClose ?? 0;
      return {
        symbol,
        name: names[symbol] || symbol,
        logo: undefined,
        currentPrice,
        changePercent: snapshot?.changePercent ?? 0,
        change: previousClose > 0 ? currentPrice - previousClose : 0,
        volume: snapshot?.volume ?? 0,
      };
    });

    const response = {
      items: watchlistItems,
    };

    // Cache for 2 seconds (for real-time updates)
    cache.set(cacheKey, response, 2);
    return NextResponse.json(response);
  } catch (error) {
    console.error('Watchlist API error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch watchlist data', items: [] },
      { status: 500 }
    );
  }
}
