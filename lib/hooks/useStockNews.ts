"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { NewsResponseV2, NewsStatus } from "@/types/news-v2";

interface UseStockNewsOptions {
  /** Polling interval in ms while status === "COLLECTING". Default 3000. */
  collectingPollMs?: number;
  /** Polling interval in ms when data is READY/STALE. Default 60000. */
  steadyPollMs?: number;
  /** Items per page. Default 20. */
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

const INITIAL: NewsResponseV2 = {
  status: "NOT_COLLECTED",
  source: "queue",
  stale: false,
  items: [],
  fetched_at: null,
  message: null,
};

export function useStockNews(
  symbol: string | null | undefined,
  opts: UseStockNewsOptions = {}
): UseStockNewsResult {
  const { collectingPollMs = 3000, steadyPollMs = 60_000, limit = 20 } = opts;

  const [data, setData] = useState<NewsResponseV2 | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRevalidating, setIsRevalidating] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const fetchOnce = useCallback(
    async (silent: boolean): Promise<NewsResponseV2 | null> => {
      if (!symbol) return null;
      if (silent) setIsRevalidating(true);
      else setIsLoading(true);
      try {
        const res = await fetch(
          `/api/stocks/${encodeURIComponent(symbol)}/news?limit=${limit}`,
          { cache: "no-store" }
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as NewsResponseV2;
        if (!mountedRef.current) return null;
        setData(json);
        setError(null);
        return json;
      } catch (err) {
        if (mountedRef.current) {
          setError(err instanceof Error ? err : new Error(String(err)));
        }
        return null;
      } finally {
        if (mountedRef.current) {
          if (silent) setIsRevalidating(false);
          else setIsLoading(false);
        }
      }
    },
    [symbol, limit]
  );

  const scheduleNext = useCallback(
    (status: NewsStatus | null) => {
      clearTimer();
      if (!status || !mountedRef.current || !symbol) return;
      const interval =
        status === "COLLECTING" ? collectingPollMs :
        status === "FAILED" ? steadyPollMs * 5 :
        steadyPollMs;
      timerRef.current = setTimeout(async () => {
        const next = await fetchOnce(true);
        scheduleNext(next?.status ?? status);
      }, interval);
    },
    [collectingPollMs, steadyPollMs, symbol, fetchOnce]
  );

  useEffect(() => {
    mountedRef.current = true;
    if (!symbol) {
      setData(null);
      return () => {
        mountedRef.current = false;
        clearTimer();
      };
    }
    setData(INITIAL);
    (async () => {
      const first = await fetchOnce(false);
      scheduleNext(first?.status ?? null);
    })();
    return () => {
      mountedRef.current = false;
      clearTimer();
    };
  }, [symbol, fetchOnce, scheduleNext]);

  const refresh = useCallback(async () => {
    await fetchOnce(true);
  }, [fetchOnce]);

  return {
    data,
    status: data?.status ?? null,
    isLoading,
    isRevalidating,
    error,
    refresh,
  };
}
