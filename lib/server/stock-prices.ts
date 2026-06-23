import { cache } from "@/lib/cache";
import {
  emptyStockPriceSnapshot,
  normalizeSymbols,
  type StockPriceSnapshot,
} from "@/lib/stock-prices";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

interface BackendQuote {
  close?: number;
  open?: number;
  high?: number;
  low?: number;
  volume?: number;
  source?: string;
  prev_close?: number;
  change_rate?: number;
  date?: string;
}

export type StockPriceFetchMode = "stream" | "realtime" | "standard";

interface FetchStockPriceSnapshotOptions {
  subscribe?: boolean;
  mode?: StockPriceFetchMode;
}

const FETCH_MODE_CONFIG: Record<
  StockPriceFetchMode,
  { ttlSeconds: number; useCache: boolean }
> = {
  stream: { ttlSeconds: 0, useCache: false },
  realtime: { ttlSeconds: 1, useCache: true },
  standard: { ttlSeconds: 2, useCache: true },
};

/**
 * 로컬 개발 전용: KIS WebSocket은 appkey당 동시 세션이 1개뿐이라,
 * 프로덕션이 그 세션을 점유하면 로컬 백엔드 WS는 접속이 거절돼 실시간 시세를 못 받는다.
 * STOCK_REALTIME_PROXY_URL(예: https://www.nullstock.im)이 설정되면,
 * 로컬은 프로덕션의 공개 가격 API를 통해 진짜 KIS 실시간 시세를 프록시한다.
 * 프로덕션에서는 이 변수를 설정하지 않는다(자기 WS를 직접 사용).
 */
interface ProxyPriceResponse {
  price?: number;
  change?: number;
  changePercent?: number;
  previousClose?: number;
  open?: number;
  high?: number;
  low?: number;
  volume?: number;
}

async function fetchSnapshotFromProxy(
  symbol: string,
  proxyBase: string
): Promise<StockPriceSnapshot> {
  try {
    const res = await fetch(`${proxyBase}/api/stock/${symbol}/price`, {
      signal: AbortSignal.timeout(8000),
      cache: "no-store",
    });
    if (!res.ok) {
      return emptyStockPriceSnapshot();
    }
    const data: ProxyPriceResponse = await res.json();
    if (!data.price || data.price <= 0) {
      return emptyStockPriceSnapshot();
    }
    // 프로덕션 응답에 previousClose가 없으면(구버전) price - change로 역산한다.
    const previousClose =
      typeof data.previousClose === "number" && data.previousClose > 0
        ? data.previousClose
        : typeof data.change === "number"
          ? data.price - data.change
          : undefined;
    return {
      price: data.price,
      changePercent: data.changePercent ?? 0,
      volume: data.volume ?? 0,
      source: "prod_proxy",
      open: data.open,
      high: data.high,
      low: data.low,
      previousClose,
    };
  } catch {
    return emptyStockPriceSnapshot();
  }
}

function toSnapshot(quote?: BackendQuote | null): StockPriceSnapshot {
  if (!quote?.close || quote.close <= 0) {
    return emptyStockPriceSnapshot();
  }

  let changePercent = 0;
  if (quote.change_rate !== undefined && quote.change_rate !== 0) {
    changePercent = quote.change_rate;
  } else {
    const base =
      quote.prev_close && quote.prev_close > 0 ? quote.prev_close : quote.open;
    changePercent =
      base && base > 0
        ? Math.round(((quote.close - base) / base) * 10000) / 100
        : 0;
  }

  return {
    price: quote.close,
    changePercent,
    volume: quote.volume ?? 0,
    source: quote.source,
    open: quote.open,
    high: quote.high,
    low: quote.low,
    previousClose: quote.prev_close,
    date: quote.date,
  };
}

export async function fetchStockPriceSnapshots(
  symbols: string[],
  options?: FetchStockPriceSnapshotOptions
): Promise<Record<string, StockPriceSnapshot>> {
  const normalizedSymbols = normalizeSymbols(symbols);
  if (normalizedSymbols.length === 0) {
    return {};
  }

  const mode = options?.mode ?? "standard";
  const config = FETCH_MODE_CONFIG[mode];
  const cacheKey = `stock:prices:${mode}:${normalizedSymbols.join(",")}`;

  if (config.useCache) {
    const cached = cache.get<Record<string, StockPriceSnapshot>>(cacheKey);
    if (cached) {
      return cached;
    }
  }

  // 로컬 개발 전용: 프로덕션 공개 API로 진짜 KIS 실시간 시세를 프록시한다.
  const proxyBase = process.env.STOCK_REALTIME_PROXY_URL?.replace(/\/+$/, "");
  if (proxyBase) {
    const entries = await Promise.all(
      normalizedSymbols.map(
        async (symbol) =>
          [symbol, await fetchSnapshotFromProxy(symbol, proxyBase)] as const
      )
    );
    const result = Object.fromEntries(entries);
    if (config.useCache && config.ttlSeconds > 0) {
      cache.set(cacheKey, result, config.ttlSeconds);
    }
    return result;
  }

  const subscribe = options?.subscribe ?? true;

  try {
    if (subscribe) {
      // fire-and-forget: prices 조회를 block하지 않도록 병렬 실행
      fetch(`${BACKEND_URL}/market/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: normalizedSymbols }),
        signal: AbortSignal.timeout(3000),
        cache: "no-store",
      }).catch(() => {
        // 구독 실패 시에도 현재가 조회는 진행한다.
      });
    }

    const response = await fetch(`${BACKEND_URL}/market/prices`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols: normalizedSymbols }),
      signal: AbortSignal.timeout(8000),
      cache: "no-store",
    });

    if (!response.ok) {
      return Object.fromEntries(
        normalizedSymbols.map((symbol) => [symbol, emptyStockPriceSnapshot()])
      );
    }

    const data: Record<string, BackendQuote> = await response.json();
    const result = Object.fromEntries(
      normalizedSymbols.map((symbol) => [symbol, toSnapshot(data[symbol])])
    );

    if (config.useCache && config.ttlSeconds > 0) {
      cache.set(cacheKey, result, config.ttlSeconds);
    }

    return result;
  } catch {
    return Object.fromEntries(
      normalizedSymbols.map((symbol) => [symbol, emptyStockPriceSnapshot()])
    );
  }
}
