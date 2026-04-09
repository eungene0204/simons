type StockInfoLike = {
  currentPrice?: number;
  changePercent?: number;
  volume?: number;
  marketCap?: number;
  open?: number;
  high?: number;
  low?: number;
  previousClose?: number;
  [key: string]: unknown;
} | null | undefined;

export function pickPositiveNumber(
  ...values: Array<number | null | undefined>
): number | undefined {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      return value;
    }
  }
  return undefined;
}

export function pickStockName(
  symbol: string,
  ...values: Array<string | null | undefined>
): string | undefined {
  const normalizedSymbol = symbol.trim();

  for (const value of values) {
    if (typeof value !== "string") {
      continue;
    }

    const normalizedValue = value.trim();
    if (!normalizedValue || normalizedValue === normalizedSymbol) {
      continue;
    }

    return normalizedValue;
  }

  return undefined;
}

export function mergeStockInfo(
  previous: StockInfoLike,
  next: StockInfoLike
): Record<string, unknown> | null {
  if (!next && !previous) {
    return null;
  }

  return {
    ...(previous ?? {}),
    ...(next ?? {}),
    volume: pickPositiveNumber(next?.volume, previous?.volume),
    marketCap: pickPositiveNumber(next?.marketCap, previous?.marketCap),
    open: pickPositiveNumber(next?.open, previous?.open),
    high: pickPositiveNumber(next?.high, previous?.high),
    low: pickPositiveNumber(next?.low, previous?.low),
    previousClose: pickPositiveNumber(next?.previousClose, previous?.previousClose),
  };
}

type StoredMarketCapSnapshot = {
  marketCap: number;
  price?: number;
  updatedAt: number;
};

const MARKET_CAP_STORAGE_PREFIX = "stock-order:market-cap";
const MARKET_CAP_RATIO_TOLERANCE = 0.15;

function getMarketCapStorageKey(symbol: string): string {
  return `${MARKET_CAP_STORAGE_PREFIX}:${symbol.trim()}`;
}

function readStoredMarketCapSnapshot(symbol: string): StoredMarketCapSnapshot | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.sessionStorage.getItem(getMarketCapStorageKey(symbol));
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as Partial<StoredMarketCapSnapshot>;
    const marketCap = pickPositiveNumber(parsed.marketCap);
    if (!marketCap) {
      return null;
    }

    return {
      marketCap,
      price: pickPositiveNumber(parsed.price),
      updatedAt:
        typeof parsed.updatedAt === "number" && Number.isFinite(parsed.updatedAt)
          ? parsed.updatedAt
          : Date.now(),
    };
  } catch {
    return null;
  }
}

function writeStoredMarketCapSnapshot(
  symbol: string,
  marketCap: number,
  price?: number
): void {
  if (typeof window === "undefined" || !pickPositiveNumber(marketCap)) {
    return;
  }

  try {
    const payload: StoredMarketCapSnapshot = {
      marketCap,
      price: pickPositiveNumber(price),
      updatedAt: Date.now(),
    };
    window.sessionStorage.setItem(getMarketCapStorageKey(symbol), JSON.stringify(payload));
  } catch {
    // Ignore storage failures and continue with in-memory state.
  }
}

export function sanitizeMarketCap(
  symbol: string,
  marketCap?: number | null,
  currentPrice?: number | null
): number | undefined {
  const nextMarketCap = pickPositiveNumber(marketCap ?? undefined);
  const nextPrice = pickPositiveNumber(currentPrice ?? undefined);
  const stored = readStoredMarketCapSnapshot(symbol);
  const storedMarketCap = pickPositiveNumber(stored?.marketCap);
  const storedPrice = pickPositiveNumber(stored?.price);

  if (!nextMarketCap) {
    return storedMarketCap;
  }

  if (storedMarketCap && storedMarketCap !== nextMarketCap) {
    const marketCapRatio = nextMarketCap / storedMarketCap;

    if (storedPrice && nextPrice) {
      const priceRatio = nextPrice / storedPrice;
      const divergence = Math.abs(marketCapRatio / priceRatio - 1);

      if (divergence > MARKET_CAP_RATIO_TOLERANCE) {
        return storedMarketCap;
      }
    } else if (marketCapRatio < 0.7 || marketCapRatio > 1.3) {
      return storedMarketCap;
    }
  }

  writeStoredMarketCapSnapshot(symbol, nextMarketCap, nextPrice);
  return nextMarketCap;
}
