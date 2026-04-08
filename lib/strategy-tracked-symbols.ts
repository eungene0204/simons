import { prisma } from "@/lib/prisma";
import { loadStockList } from "@/lib/krx-stocks";
import { getTopSymbolsFromSummary } from "@/lib/backtest-top-symbols";

const KOSPI200_TOP = [
  "005930", "000660", "373220", "207940", "005380",
  "000270", "068270", "005490", "051910", "003670",
  "035420", "035720", "105560", "055550", "034730",
  "017670", "011200", "010130", "009150", "012330",
];

const MAX_SYMBOLS = 20;
const BACKTEST_TOP_SYMBOLS = 10;
const MIN_BACKTEST_SYMBOLS = 3;

export type TrackedSymbolSource = "backtest" | "universe";

export async function resolveUniverseSymbols(
  universeId: string,
  filters: Record<string, any>
): Promise<string[]> {
  if (universeId === "kospi200") {
    return KOSPI200_TOP.slice(0, MAX_SYMBOLS);
  }

  const stocks = await loadStockList();
  let filtered = stocks;

  if (universeId === "kospi") {
    filtered = stocks.filter((s) => s.market === "KOSPI");
  } else if (universeId === "kosdaq") {
    filtered = stocks.filter((s) => s.market === "KOSDAQ");
  }

  if (filters?.selectedSectors?.length > 0) {
    filtered = filtered.filter(
      (s) => s.sector && filters.selectedSectors.includes(s.sector)
    );
  }

  return filtered.slice(0, MAX_SYMBOLS).map((s) => s.symbol);
}

export async function getBestBacktestSymbols(
  strategyId: string,
  strategyName: string
): Promise<{ symbols: string[]; source: "backtest" } | null> {
  const savedResult = await prisma.backtestResult.findFirst({
    where: { strategyId },
    orderBy: { createdAt: "desc" },
  });

  if (savedResult) {
    try {
      const summary = JSON.parse(savedResult.summary);
      const ranked = (summary.topSymbols as string[] | undefined)?.slice(0, BACKTEST_TOP_SYMBOLS)
        ?? getTopSymbolsFromSummary(summary, BACKTEST_TOP_SYMBOLS);
      const perAssetStats = summary.perAssetStats as Record<string, { totalReturn: number; trades: number }> | undefined;
      if (
        ranked.length >= MIN_BACKTEST_SYMBOLS ||
        (perAssetStats && Object.keys(perAssetStats).length >= MIN_BACKTEST_SYMBOLS)
      ) {
        return { symbols: ranked, source: "backtest" };
      }
    } catch {
      // Ignore malformed summary and continue to history fallback.
    }
  }

  const latestHistory = await prisma.backtestHistory.findFirst({
    where: { strategyName },
    orderBy: { createdAt: "desc" },
  });
  if (!latestHistory) return null;

  try {
    const metrics = JSON.parse(latestHistory.metrics);
    const ranked = getTopSymbolsFromSummary(metrics, BACKTEST_TOP_SYMBOLS);
    const perAssetStats = metrics.perAssetStats as Record<string, { totalReturn: number; trades: number }> | undefined;
    if (
      ranked.length < MIN_BACKTEST_SYMBOLS &&
      (!perAssetStats || Object.keys(perAssetStats).length < MIN_BACKTEST_SYMBOLS)
    ) {
      return null;
    }

    return { symbols: ranked, source: "backtest" };
  } catch {
    return null;
  }
}

export async function resolveTrackedSymbolsForStrategy(params: {
  strategyId: string;
  strategyName: string;
  strategySettings?: string | null;
}): Promise<{ symbols: string[]; source: TrackedSymbolSource }> {
  const backtestBest = await getBestBacktestSymbols(params.strategyId, params.strategyName);
  if (backtestBest) {
    return backtestBest;
  }

  let settings: any = null;
  if (params.strategySettings) {
    try {
      settings = JSON.parse(params.strategySettings);
    } catch {
      settings = null;
    }
  }

  const universe = settings?.universe || { id: "kospi200", filters: {} };
  const symbols = await resolveUniverseSymbols(
    universe.id || "kospi200",
    universe.filters || {}
  );

  return {
    symbols,
    source: "universe",
  };
}
