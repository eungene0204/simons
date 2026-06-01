import { NextRequest, NextResponse } from "next/server";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";

export const dynamic = "force-dynamic";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ symbol: string }> | { symbol: string } }
) {
  try {
    const { symbol } = await Promise.resolve(params);
    const snapshots = await fetchStockPriceSnapshots([symbol], {
      subscribe: true,
      mode: "stream",
    });
    const quote = snapshots[symbol];

    if (!quote || quote.price <= 0) {
      return NextResponse.json({ error: "Price unavailable" }, { status: 404 });
    }

    return NextResponse.json({
      price: quote.price,
      change: quote.price - (quote.previousClose ?? quote.price),
      changePercent: quote.changePercent,
      open: quote.open,
      high: quote.high,
      low: quote.low,
      volume: quote.volume,
    });
  } catch {
    return NextResponse.json({ error: "Failed to fetch price" }, { status: 500 });
  }
}
