import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { loadStockList } from "@/lib/krx-stocks";
import { scoreSmartMatch, normalizeSearchText } from "@/lib/smart-search";
import type {
  QuickSearchStockItem,
  QuickSearchResponse,
  StrategyQuickSearchItem,
  VirtualAccountQuickSearchItem,
} from "@/types/quick-search";

function parseUniverse(settings: string) {
  try {
    const parsed = JSON.parse(settings);
    const universeValue = parsed?.universe?.id ?? parsed?.universe ?? "";

    if (typeof universeValue !== "string") {
      return "기타";
    }

    if (universeValue.toUpperCase().includes("KOSPI") || universeValue === "KOSPI200") {
      return "KOSPI";
    }

    if (universeValue.toUpperCase().includes("KOSDAQ")) {
      return "KOSDAQ";
    }

    if (
      universeValue.includes("US") ||
      universeValue.includes("미국") ||
      universeValue.includes("NYSE") ||
      universeValue.includes("NASDAQ")
    ) {
      return "미국주식";
    }

    return universeValue || "기타";
  } catch {
    return "기타";
  }
}

export async function GET(request: NextRequest) {
  const query = normalizeSearchText(request.nextUrl.searchParams.get("q"));

  if (!query) {
    return NextResponse.json({
      stocks: [],
      strategies: [],
      virtualAccounts: [],
    } satisfies QuickSearchResponse);
  }

  try {
    const [stocks, strategies, accounts] = await Promise.all([
      loadStockList(),
      prisma.strategy.findMany({
        orderBy: { createdAt: "desc" },
      }),
      prisma.virtualAccount.findMany({
        orderBy: { createdAt: "desc" },
      }),
    ]);

    const matchedStocks: QuickSearchStockItem[] = stocks
      .map((stock) => {
        const score =
          scoreSmartMatch(query, [stock.symbol]) * 5 +
          scoreSmartMatch(query, [stock.name]) * 4 +
          scoreSmartMatch(query, [stock.market, stock.sector, stock.industry]);

        return {
          score,
          item: {
            symbol: stock.symbol,
            name: stock.name,
            type: stock.market,
            region: "KR",
            currency: "KRW",
            matchScore: score,
            sector: stock.sector,
            industry: stock.industry,
          },
        };
      })
      .filter((entry) => entry.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 6)
      .map((entry) => entry.item);

    const matchedStrategies: StrategyQuickSearchItem[] = strategies
      .map((strategy) => {
        const universe = parseUniverse(strategy.settings);
        const score =
          scoreSmartMatch(query, [strategy.name]) * 4 +
          scoreSmartMatch(query, [strategy.description]) * 2 +
          scoreSmartMatch(query, [strategy.strategyType, universe]);

        return {
          score,
          item: {
            id: strategy.id,
            name: strategy.name,
            description: strategy.description ?? null,
            strategyType: strategy.strategyType || "기타",
            universe,
          },
        };
      })
      .filter((entry) => entry.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 6)
      .map((entry) => entry.item);

    const matchedAccounts: VirtualAccountQuickSearchItem[] = accounts
      .map((account) => {
        const score =
          scoreSmartMatch(query, [account.name]) * 4 +
          scoreSmartMatch(query, [account.strategyName]) * 2 +
          scoreSmartMatch(query, [
            account.tradingMode === "auto" ? "자동매매" : "수동매매",
          ]);

        return {
          score,
          item: {
            id: account.id,
            name: account.name,
            strategyName: account.strategyName ?? null,
            tradingMode: account.tradingMode === "auto" ? "auto" : "manual",
          },
        };
      })
      .filter((entry) => entry.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 6)
      .map((entry) => entry.item);

    return NextResponse.json({
      stocks: matchedStocks,
      strategies: matchedStrategies,
      virtualAccounts: matchedAccounts,
    } satisfies QuickSearchResponse);
  } catch (error) {
    console.error("Quick search API error:", error);
    return NextResponse.json(
      { error: "Failed to search quick items" },
      { status: 500 }
    );
  }
}
