import { NextRequest, NextResponse } from "next/server";
import { loadStockList, loadStockMasterNameMap, loadEtfMasterNameMap } from "@/lib/krx-stocks";
import { cache } from "@/lib/cache";

// 런타임에 볼륨 마운트되는 data/stock-master.json(상폐 종목명)을 읽으므로 정적 prerender 금지.
// 정적 생성 시 빌드 컨테이너엔 stock-master.json이 없어(.dockerignore) 상폐 이름이 누락된 응답이 고정된다.
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const cacheKey = "stocks:metadata-map";
    /*
    const cached = cache.get(cacheKey);
    
    if (cached) {
      return NextResponse.json(cached);
    }
    */

    const [stocks, masterNames, etfNames] = await Promise.all([
      loadStockList(),
      loadStockMasterNameMap(),
      loadEtfMasterNameMap(),
    ]);
    const metadataMap: Record<string, { name: string, sector: string }> = {};

    // 상폐 종목·ETF 이름을 먼저 깔고(코드 대신 이름 표시), 현재 상장분으로 덮어쓴다
    // (현재 상장분이 sector 등 더 풍부한 메타를 가짐). ETF 코드는 주식과 겹치지 않는다.
    Object.entries(masterNames).forEach(([symbol, name]) => {
      metadataMap[symbol] = { name, sector: "-" };
    });
    Object.entries(etfNames).forEach(([symbol, name]) => {
      metadataMap[symbol] = { name, sector: "ETF" };
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
