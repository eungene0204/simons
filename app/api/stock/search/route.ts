import { NextRequest, NextResponse } from "next/server";
import { getStockAPIProvider } from "@/lib/stock-api";
import { cache, cacheKeys, cacheTTL } from "@/lib/cache";
import { StockAPIError } from "@/lib/stock-api/base";
import { loadStockList } from "@/lib/krx-stocks";
import { scoreSmartMatch, normalizeSearchText } from "@/lib/smart-search";
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
      const normalizedQuery = normalizeSearchText(query);
      
      // 한국 종목 검색: 종목 코드, 이름, 초성, 순서 기반 부분 일치까지 반영
      const koreaResults: Array<StockSearchResult & { _score: number }> = koreaStocks
        .map((stock) => {
          const score =
            scoreSmartMatch(normalizedQuery, [stock.symbol]) * 5 +
            scoreSmartMatch(normalizedQuery, [stock.name]) * 4 +
            scoreSmartMatch(normalizedQuery, [stock.market, stock.sector, stock.industry]);

          return {
            symbol: stock.symbol,
            name: stock.name,
            type: stock.market,
            region: "KR",
            currency: "KRW",
            matchScore: score,
            sector: stock.sector,
            industry: stock.industry,
            _score: score,
          };
        })
        .filter((stock) => stock._score > 0);

      // 한국 종목이 있으면 반환
      if (koreaResults.length > 0) {
        const sortedResults = koreaResults.sort((a, b) => {
          if (b._score !== a._score) {
            return b._score - a._score;
          }

          return a.name.localeCompare(b.name, "ko");
        }).map(({ _score, ...stock }) => stock);

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
