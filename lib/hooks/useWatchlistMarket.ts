"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getWatchlistSymbols } from "@/lib/watchlist";
import { useStockPrices } from "@/lib/hooks/useStockPrices";

export interface WatchlistMarketItem {
  symbol: string;
  name: string;
  logo?: string;
  currentPrice: number;
  changePercent: number;
  change: number;
  volume: number;
  groupId?: string;
}

export function useWatchlistMarket(refetchInterval = 3000) {
  const symbolsQuery = useQuery({
    queryKey: ["watchlist-symbols"],
    queryFn: getWatchlistSymbols,
    refetchInterval,
    refetchIntervalInBackground: true,
  });

  const symbols = useMemo(
    () => (symbolsQuery.data ?? []).map((item) => item.symbol),
    [symbolsQuery.data]
  );

  const pricesQuery = useStockPrices(symbols, {
    enabled: symbols.length > 0,
    refetchInterval,
  });

  const items = useMemo<WatchlistMarketItem[]>(() => {
    const symbolEntries = symbolsQuery.data ?? [];
    const prices = pricesQuery.data ?? {};

    return symbolEntries.map((item) => {
      const quote = prices[item.symbol];
      const currentPrice = quote?.price ?? 0;
      const previousClose = quote?.previousClose ?? 0;

      return {
        symbol: item.symbol,
        name: item.name,
        currentPrice,
        changePercent: quote?.changePercent ?? 0,
        change: previousClose > 0 ? currentPrice - previousClose : 0,
        volume: quote?.volume ?? 0,
        groupId: item.groupId,
      };
    });
  }, [symbolsQuery.data, pricesQuery.data]);

  return {
    items,
    loading: symbolsQuery.isLoading || pricesQuery.isLoading,
    refetch: async () => {
      await symbolsQuery.refetch();
      await pricesQuery.refetch();
    },
  };
}
