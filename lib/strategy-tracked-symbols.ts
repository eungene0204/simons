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

/** 미국 유니버스 id → 지수 명부 키(data/us-index-membership.json). 'us'·'us_etf'는 명부가 없다. */
const US_INDEX_ROSTERS: Record<string, string> = {
  sp500: "SP500",
  nasdaq100: "NASDAQ100",
  dow30: "DOW30",
};

/** 미국 유니버스의 추적 종목 — 지수 명부(시총 상위 대신 명부 순서) 상위 N.
 *
 *  [2026-08-26] 종전에는 US 유니버스 id가 아래 한국 분기 어디에도 걸리지 않아
 *  한국 종목 목록이 그대로 반환됐다 — 미국 전략 계좌가 한국 종목을 추적·자동매매하는
 *  교차 시장 오염. 명부가 없는 id('us' 전체·'us_etf')는 빈 배열을 돌려 상위 호출이
 *  백테스트 상위 종목/기존 폴백을 쓰게 한다(한국 종목으로 채우지 않는다). */
async function resolveUsUniverseSymbols(universeId: string): Promise<string[]> {
  const rosterKey = US_INDEX_ROSTERS[universeId];
  if (!rosterKey) return [];
  try {
    const fs = await import("fs/promises");
    const path = await import("path");
    const raw = await fs.readFile(
      path.join(process.cwd(), "data", "us-index-membership.json"),
      "utf-8"
    );
    const members = JSON.parse(raw)?.indices?.[rosterKey];
    if (!Array.isArray(members)) return [];
    return members
      .map((m: { symbol?: string }) => m?.symbol)
      .filter((s: unknown): s is string => typeof s === "string" && s.length > 0)
      .slice(0, MAX_SYMBOLS);
  } catch (error) {
    console.warn("Failed to load US index roster:", error);
    return [];
  }
}

export function isUsUniverseIdForTracking(universeId: string): boolean {
  const id = (universeId || "").toLowerCase();
  return id === "us" || id === "us_etf" || id in US_INDEX_ROSTERS;
}

export async function resolveUniverseSymbols(
  universeId: string,
  filters: Record<string, any>
): Promise<string[]> {
  // 미국 유니버스는 한국 목록으로 흘려보내지 않는다(교차 시장 오염 차단).
  if (isUsUniverseIdForTracking(universeId)) {
    return resolveUsUniverseSymbols(universeId.toLowerCase());
  }
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
