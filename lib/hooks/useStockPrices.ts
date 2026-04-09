"use client";

import { useQuery } from "@tanstack/react-query";
import {
  normalizeSymbols,
  type StockPriceSnapshot,
} from "@/lib/stock-prices";

async function fetchStockPrices(
  symbols: string[]
): Promise<Record<string, StockPriceSnapshot>> {
  const response = await fetch("/api/stock/prices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols }),
  });

  if (!response.ok) {
    throw new Error("Failed to fetch stock prices");
  }

  return response.json();
}

export function useStockPrices(
  symbols: string[],
  options?: {
    enabled?: boolean;
    refetchInterval?: number | false;
  }
) {
  const normalizedSymbols = normalizeSymbols(symbols);

  return useQuery({
    queryKey: ["stock-prices", normalizedSymbols],
    queryFn: () => fetchStockPrices(normalizedSymbols),
    enabled: (options?.enabled ?? true) && normalizedSymbols.length > 0,
    refetchInterval: options?.refetchInterval,
    refetchIntervalInBackground: true,
    placeholderData: (previousData) => previousData,
  });
}
