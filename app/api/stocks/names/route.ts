import { NextRequest, NextResponse } from "next/server";
import { loadStockList } from "@/lib/krx-stocks";
import { cache } from "@/lib/cache";

export async function GET(request: NextRequest) {
  try {
    const cacheKey = "stocks:metadata-map";
    /*
    const cached = cache.get(cacheKey);
    
    if (cached) {
      return NextResponse.json(cached);
    }
    */

    const stocks = await loadStockList();
    const metadataMap: Record<string, { name: string, sector: string }> = {};
    
    stocks.forEach(stock => {
      metadataMap[stock.symbol] = {
        name: stock.name,
        sector: stock.sector || stock.industry || "-"
      };
    });

    // Cache for 1 hour
    cache.set(cacheKey, metadataMap, 3600);
    
    return NextResponse.json(metadataMap);
  } catch (error) {
    console.error("Failed to fetch stock metadata map:", error);
    return NextResponse.json({ error: "Failed to load stock metadata" }, { status: 500 });
  }
}
