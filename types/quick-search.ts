import type { StockSearchResult } from "@/types/stock";

export interface QuickSearchStockItem extends StockSearchResult {}

export interface StrategyQuickSearchItem {
  id: string;
  name: string;
  description: string | null;
  strategyType: string;
  universe: string;
}

export interface VirtualAccountQuickSearchItem {
  id: string;
  name: string;
  strategyName: string | null;
  tradingMode: "auto" | "manual";
}

export interface QuickSearchResponse {
  stocks: QuickSearchStockItem[];
  strategies: StrategyQuickSearchItem[];
  virtualAccounts: VirtualAccountQuickSearchItem[];
}
