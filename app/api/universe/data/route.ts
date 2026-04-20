import { NextResponse } from "next/server";
import { loadStockList } from "@/lib/krx-stocks";
import { getUniverseOverview } from "@/lib/universe-history";
import fs from "fs/promises";
import path from "path";

async function loadKospi200Symbols(): Promise<string[]> {
  try {
    const cachePath = path.join(process.cwd(), "data", "kospi200-cache.json");
    const raw = await fs.readFile(cachePath, "utf-8");
    const parsed = JSON.parse(raw) as { symbols?: string[] };
    if (Array.isArray(parsed.symbols) && parsed.symbols.length >= 150) {
      return parsed.symbols;
    }
  } catch {
    // fallback handled below
  }
  return [];
}

export async function GET() {
  try {
    const [stocks, overview, kospi200Symbols] = await Promise.all([
      loadStockList(),
      getUniverseOverview(),
      loadKospi200Symbols(),
    ]);

    const symbolToSector: Record<string, string> = {};
    const universes: Record<string, string[]> = {
      kospi: [],
      kosdaq: [],
      kospi200: kospi200Symbols,
    };

    stocks.forEach(stock => {
      if (stock.sector) {
        symbolToSector[stock.symbol] = stock.sector;
      }

      if (stock.market === "KOSPI") {
        universes.kospi.push(stock.symbol);
      } else if (stock.market === "KOSDAQ") {
        universes.kosdaq.push(stock.symbol);
      }
    });

    return NextResponse.json({
      symbolToSector,
      universes,
      counts: {
        total: stocks.length,
        kospi: universes.kospi.length,
        kosdaq: universes.kosdaq.length,
        kospi200: universes.kospi200.length,
      },
      latestSync: overview.latest,
    });
  } catch (error) {
    console.error("Failed to load universe data:", error);
    return NextResponse.json({ error: "Failed to load universe data" }, { status: 500 });
  }
}
