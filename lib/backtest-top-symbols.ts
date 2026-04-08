export type BacktestAssetStat = {
  symbol: string;
  totalReturn: number;
  trades: number;
  profit?: number;
  winRate?: number;
};

export function getTopAssetStats(
  perAssetStats: Record<string, BacktestAssetStat> | undefined | null,
  limit = 10
): BacktestAssetStat[] {
  if (!perAssetStats) return [];

  return Object.values(perAssetStats)
    .filter((stat) => stat && typeof stat.symbol === "string" && (stat.trades ?? 0) > 0)
    .sort((a, b) => (b.totalReturn ?? 0) - (a.totalReturn ?? 0))
    .slice(0, limit)
    .map((stat) => ({
      symbol: stat.symbol,
      totalReturn: stat.totalReturn ?? 0,
      trades: stat.trades ?? 0,
      profit: stat.profit ?? 0,
      winRate: stat.winRate ?? 0,
    }));
}

export function getTopSymbolsFromSummary(
  summary: Record<string, unknown> | null | undefined,
  limit = 10
): string[] {
  if (!summary) return [];

  const topSymbols = summary.topSymbols;
  if (Array.isArray(topSymbols)) {
    return topSymbols
      .filter((symbol): symbol is string => typeof symbol === "string" && symbol.trim().length > 0)
      .slice(0, limit);
  }

  const topAssetStats = summary.topAssetStats;
  if (Array.isArray(topAssetStats)) {
    return topAssetStats
      .map((item) => (item && typeof item === "object" ? (item as { symbol?: unknown }).symbol : null))
      .filter((symbol): symbol is string => typeof symbol === "string" && symbol.trim().length > 0)
      .slice(0, limit);
  }

  const perAssetStats = summary.perAssetStats as Record<string, BacktestAssetStat> | undefined;
  return getTopAssetStats(perAssetStats, limit).map((stat) => stat.symbol);
}
