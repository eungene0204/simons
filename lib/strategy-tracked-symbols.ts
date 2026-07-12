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
const LOCAL_DELISTED_SYMBOLS = new Set([
  "001570", "001840", "002420", "016600", "016790",
  "018620", "023790", "027040", "032680", "032790",
  "032980", "041590", "042040", "043220", "043590",
  "046390", "052420", "061040", "064090", "065150",
  "065570", "065770", "068940", "072770", "078590",
  "079970", "080720", "088290", "091970", "101390",
  "106520", "109960", "115530", "131760", "137940",
  "140430", "140910", "148780", "152550", "193250",
  "198940", "203690", "204210", "222160", "225590",
  "226340", "227100", "227610", "227950", "230980",
  "234100", "258790", "258830", "266350", "288330",
  "309930", "322780", "352770", "368970", "373200",
  "380540", "419540", "464680", "477760", "900100",
  "900250", "900300",
]);

export type TrackedSymbolSource = "backtest" | "universe";

function normalizeUniqueSymbols(symbols: string[]): string[] {
  const seen = new Set<string>();
  return symbols
    .map((symbol) => String(symbol).trim())
    .filter((symbol) => {
      if (!symbol || seen.has(symbol)) return false;
      seen.add(symbol);
      return true;
    });
}

export async function filterMonitorableSymbols(symbols: string[]): Promise<string[]> {
  const normalized = normalizeUniqueSymbols(symbols);
  if (normalized.length === 0) return [];

  const blocked = new Set<string>();
  normalized.forEach((symbol) => {
    if (LOCAL_DELISTED_SYMBOLS.has(symbol)) blocked.add(symbol);
  });

  try {
    const dbBlocked = await prisma.stock.findMany({
      where: {
        symbol: { in: normalized },
        listingStatus: { in: ["DELISTED", "TRADING_SUSPENDED"] },
      },
      select: { symbol: true },
    });
    dbBlocked.forEach((stock) => blocked.add(stock.symbol));
  } catch (error) {
    console.warn("Failed to filter DB blocked symbols:", error);
  }

  return normalized.filter((symbol) => !blocked.has(symbol));
}

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
    where: { strategyId },
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
    return {
      symbols: await filterMonitorableSymbols(backtestBest.symbols),
      source: backtestBest.source,
    };
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
    symbols: await filterMonitorableSymbols(symbols),
    source: "universe",
  };
}
