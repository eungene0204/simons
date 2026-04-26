import { NextRequest, NextResponse } from "next/server";
import { loadStockList } from "@/lib/krx-stocks";
import {
  fetchStockInfoProfileFromSource,
  hasStoredInfoProfile,
  persistStockInfoProfile,
  readStoredStockInfoProfile,
  type StockMetadataSeed,
} from "@/app/api/stocks/profile-store";

interface SyncRequestBody {
  symbols?: string[];
  limit?: number;
  force?: boolean;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({})) as SyncRequestBody;
    const allStocks = await loadStockList();
    const requestedSymbols = Array.isArray(body.symbols) && body.symbols.length > 0
      ? new Set(body.symbols)
      : null;
    const limit = typeof body.limit === "number" && body.limit > 0 ? body.limit : null;
    const force = body.force === true;

    const seeds = allStocks
      .filter((stock) => !requestedSymbols || requestedSymbols.has(stock.symbol))
      .slice(0, limit ?? undefined)
      .map<StockMetadataSeed>((stock) => ({
        symbol: stock.symbol,
        name: stock.name,
        market: stock.market,
        sector: stock.sector || undefined,
      }));

    let success = 0;
    let failed = 0;
    let skipped = 0;
    const failedSymbols: string[] = [];

    for (const seed of seeds) {
      try {
        if (!force) {
          const storedProfile = await readStoredStockInfoProfile(seed.symbol);

          if (hasStoredInfoProfile(storedProfile)) {
            skipped += 1;
            continue;
          }
        }

        const profile = await fetchStockInfoProfileFromSource(seed);
        await persistStockInfoProfile(seed, profile);
        success += 1;
      } catch (error) {
        failed += 1;
        failedSymbols.push(seed.symbol);
        console.error(`Failed to sync stock info profile for ${seed.symbol}:`, error);
      }
    }

    return NextResponse.json({
      success: true,
      requested: seeds.length,
      synced: success,
      skipped,
      failed,
      failedSymbols,
    });
  } catch (error) {
    console.error("Failed to sync stock info profiles:", error);
    return NextResponse.json(
      {
        error: "종목정보 프로필 동기화 실패",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 },
    );
  }
}
