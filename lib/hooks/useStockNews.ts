"use client";

import { useQuery } from "@tanstack/react-query";

import type { NewsResponseV2, NewsStatus } from "@/types/news-v2";

export const STOCK_NEWS_LIMIT = 30;
const STOCK_NEWS_PENDING_REFETCH_MS = 3000;
const STOCK_NEWS_PENDING_STATUSES: NewsStatus[] = ["COLLECTING", "NOT_COLLECTED"];

export type StockNewsPriorityEventType =
  | "current_view"
  | "stock_view"
  | "stock_detail_view";

export function stockNewsQueryKey(symbol: string) {
  return ["stock-news", symbol] as const;
}

interface UseStockNewsOptions {
  /** Items per request. Default 30. */
  limit?: number;
}

interface UseStockNewsResult {
  data: NewsResponseV2 | null;
  status: NewsStatus | null;
  isLoading: boolean;
  isRevalidating: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
}

const emptyResponse = (symbol: string): NewsResponseV2 => ({
  symbol,
  items: [],
  lastUpdatedAt: null,
  isStale: false,
  status: "NOT_COLLECTED",
  source: "queue",
  message: null,
});

export async function fetchStockNews(symbol: string, limit: number): Promise<NewsResponseV2> {
  const res = await fetch(
    `/api/stocks/${encodeURIComponent(symbol)}/news?limit=${limit}`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as NewsResponseV2;
}

export async function recordStockNewsPriorityEvent(
  symbol: string,
  eventType: StockNewsPriorityEventType,
  metadata: Record<string, unknown> = {}
): Promise<void> {
  const res = await fetch(`/api/stocks/${encodeURIComponent(symbol)}/news`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ eventType, metadata }),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export function useStockNews(
  symbol: string | null | undefined,
  opts: UseStockNewsOptions = {}
): UseStockNewsResult {
  const limit = opts.limit ?? STOCK_NEWS_LIMIT;
  const enabled = Boolean(symbol);
  const query = useQuery({
    queryKey: enabled ? stockNewsQueryKey(symbol as string) : ["stock-news", symbol],
    queryFn: () => fetchStockNews(symbol as string, limit),
    staleTime: 60_000,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!enabled || !data) return false;
      if (data.items.length > 0) return false;
      return STOCK_NEWS_PENDING_STATUSES.includes(data.status)
        ? STOCK_NEWS_PENDING_REFETCH_MS
        : false;
    },
    refetchOnWindowFocus: false,
    enabled,
    placeholderData: enabled ? emptyResponse(symbol as string) : undefined,
  });

  return {
    data: query.data ?? null,
    status: query.data?.status ?? null,
    isLoading: query.isLoading,
    isRevalidating: query.isFetching && !query.isLoading,
    error: query.error instanceof Error ? query.error : null,
    refresh: async () => {
      await query.refetch();
    },
  };
}
