import { NextRequest, NextResponse } from "next/server";
import { loadStockList, loadStockMasterNameMap } from "@/lib/krx-stocks";
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

    const [stocks, masterNames] = await Promise.all([
      loadStockList(),
      loadStockMasterNameMap(),
    ]);
    const metadataMap: Record<string, { name: string, sector: string }> = {};

    // 상폐 종목 이름을 먼저 깔고(코드 대신 이름 표시), 현재 상장분으로 덮어쓴다
    // (현재 상장분이 sector 등 더 풍부한 메타를 가짐).
    Object.entries(masterNames).forEach(([symbol, name]) => {
      metadataMap[symbol] = { name, sector: "-" };
    });

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
