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
