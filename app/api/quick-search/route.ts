import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { loadStockList } from "@/lib/krx-stocks";
import { loadUsStockList } from "@/lib/us-stocks";
import { scoreSmartMatch, normalizeSearchText } from "@/lib/smart-search";
import { matchStocks } from "./stock-search";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from "@/lib/get-user";
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
    const { userId } = await getOwnershipContext();
    const [stocks, usStocks, strategies, accounts] = await Promise.all([
      loadStockList(),
      loadUsStockList(),
      prisma.strategy.findMany({
        where: withOwnership({ isSaved: true }, userId),
        orderBy: { createdAt: "desc" },
      }),
      prisma.virtualAccount.findMany({
        where: withOwnership({}, userId),
        orderBy: { createdAt: "desc" },
      }),
    ]);

    const matchedStocks: QuickSearchStockItem[] = matchStocks(query, stocks, usStocks);

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
            tradingMode: account.tradingMode === "auto" ? ("auto" as const) : ("manual" as const),
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
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }
    console.error("Quick search API error:", error);
    return NextResponse.json(
      { error: "Failed to search quick items" },
      { status: 500 }
    );
  }
}
