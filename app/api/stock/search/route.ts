import { NextRequest, NextResponse } from "next/server";
import { getStockAPIProvider } from "@/lib/stock-api";
import { cache, cacheKeys, cacheTTL } from "@/lib/cache";
import { StockAPIError } from "@/lib/stock-api/base";
import { loadStockList } from "@/lib/krx-stocks";
import type { StockSearchResult } from "@/types/stock";

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const query = searchParams.get("q");

    if (!query || query.length < 1) {
      return NextResponse.json(
        { error: "Search query parameter is required" },
        { status: 400 }
      );
    }

    // Check cache first
    const cacheKey = cacheKeys.search(query);
    const cached = cache.get(cacheKey);
    if (cached) {
      return NextResponse.json(cached);
    }

    // 먼저 저장된 한국 종목 목록에서 검색
    try {
      const koreaStocks = await loadStockList();
      const lowerQuery = query.toLowerCase();
      
      // 한국 종목 검색 (종목 코드 또는 종목명으로 검색)
      const koreaResults: StockSearchResult[] = koreaStocks
        .filter((stock) => {
          const symbolMatch = stock.symbol.includes(query);
          const nameMatch = stock.name.toLowerCase().includes(lowerQuery);
          return symbolMatch || nameMatch;
        })
        .map((stock) => ({
          symbol: stock.symbol,
          name: stock.name,
          type: stock.market,
          region: "KR",
          currency: "KRW",
          matchScore: 1.0,
          sector: stock.sector,
          industry: stock.industry,
        }));

      // 한국 종목이 있으면 반환
      if (koreaResults.length > 0) {
        // 관련도 순으로 정렬 (정확한 일치 우선)
        const sortedResults = koreaResults.sort((a, b) => {
          const aExactSymbol = a.symbol === query;
          const bExactSymbol = b.symbol === query;
          const aExactName = a.name.toLowerCase() === lowerQuery;
          const bExactName = b.name.toLowerCase() === lowerQuery;
          
          if (aExactSymbol && !bExactSymbol) return -1;
          if (!aExactSymbol && bExactSymbol) return 1;
          if (aExactName && !bExactName) return -1;
          if (!aExactName && bExactName) return 1;
          
          return a.name.localeCompare(b.name, "ko");
        });

        // Cache the result
        cache.set(cacheKey, sortedResults, cacheTTL.search);
        return NextResponse.json(sortedResults);
      }
    } catch (error) {
      console.error("Failed to search Korea stocks:", error);
      // 한국 종목 검색 실패 시 기존 API로 계속 진행
    }

    // 한국 종목이 없으면 기존 API 사용 (해외 종목 검색)
    const provider = getStockAPIProvider();
    const results = await provider.searchStock(query);

    // Cache the result
    cache.set(cacheKey, results, cacheTTL.search);

    return NextResponse.json(results);
  } catch (error) {
    console.error("Stock search API error:", error);

    if (error instanceof StockAPIError) {
      return NextResponse.json(
        { error: error.message, code: error.code },
        { status: error.statusCode || 500 }
      );
    }

    return NextResponse.json(
      { error: "Failed to search stocks" },
      { status: 500 }
    );
  }
}
