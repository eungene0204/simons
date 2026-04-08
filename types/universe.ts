export interface UniverseStockChange {
  symbol: string;
  name: string;
  market: string;
  sector?: string;
  industry?: string;
}

export interface UniverseHistoryEntry {
  date: string;
  syncedAt: string;
  totalCount: number;
  kospiCount: number;
  kosdaqCount: number;
  addedCount: number;
  delistedCount: number;
  added: UniverseStockChange[];
  delisted: UniverseStockChange[];
}

export interface UniverseHistoryStore {
  updatedAt: string | null;
  entries: UniverseHistoryEntry[];
}

export interface UniverseOverview {
  currentTotal: number;
  currentKospi: number;
  currentKosdaq: number;
  latest: UniverseHistoryEntry | null;
  recent: UniverseHistoryEntry[];
}
