import { NextRequest, NextResponse } from "next/server";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";

export type { StockPriceSnapshot } from "@/lib/stock-prices";

export async function POST(request: NextRequest) {
  const { symbols }: { symbols: string[] } = await request.json();
  const snapshots = await fetchStockPriceSnapshots(symbols, {
    subscribe: true,
    mode: "realtime",
  });
  return NextResponse.json(snapshots);
}
