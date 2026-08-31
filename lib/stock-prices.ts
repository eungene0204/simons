export interface StockPriceSnapshot {
  price: number;
  changePercent: number;
  volume: number;
  source?: string;
  open?: number;
  high?: number;
  low?: number;
  previousClose?: number;
  date?: string;
}

// 한국 심볼은 6자리·숫자 시작(005930), 미국 티커는 영문 시작(AAPL, BRK-B)
// — backend/engine/providers/toss_us.py의 _US_SYMBOL_RE와 동일 규약
const US_SYMBOL_RE = /^[A-Z][A-Z0-9.\-]{0,9}$/;

export function isUsSymbol(symbol: string): boolean {
  return US_SYMBOL_RE.test(symbol);
}

export function normalizeSymbols(symbols: string[]): string[] {
  return Array.from(
    new Set(
      symbols
        .map((symbol) => symbol.trim())
        .filter(Boolean)
    )
  ).sort();
}

export function emptyStockPriceSnapshot(): StockPriceSnapshot {
  return { price: 0, changePercent: 0, volume: 0 };
}
