import { NextRequest, NextResponse } from "next/server";
import { cache } from "@/lib/cache";
import { generateOrderBook, getBasePrice, generateStockPriceData } from "@/lib/mock-stock-data";

/**
 * 호가창 데이터를 제공하는 API
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ symbol: string }> | { symbol: string } }
) {
  try {
    const resolvedParams = await Promise.resolve(params);
    const symbol = resolvedParams.symbol;

    if (!symbol) {
      return NextResponse.json(
        { error: "Symbol parameter is required" },
        { status: 400 }
      );
    }

    // Check cache first
    const cacheKey = `stock:orderbook:${symbol}`;
    const cached = cache.get(cacheKey);
    if (cached) {
      return NextResponse.json(cached);
    }

    // 현재가 가져오기 (또는 기본 가격 사용)
    const basePrice = getBasePrice(symbol);
    const priceData = generateStockPriceData(symbol, basePrice);
    const currentPrice = priceData.currentPrice;

    // 호가 데이터 생성
    const orderBookData = generateOrderBook(symbol, currentPrice, 10);

    const response = {
      symbol,
      currentPrice,
      ...orderBookData,
      timestamp: new Date().toISOString(),
    };

    // Cache for 1 second (for real-time updates)
    cache.set(cacheKey, response, 1);
    return NextResponse.json(response);
  } catch (error) {
    console.error("Order book API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch order book", detail: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}

