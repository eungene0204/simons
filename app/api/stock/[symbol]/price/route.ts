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

    // 실시간 가격·등락률은 KIS 값을 그대로 사용한다.
    // 전일종가가 빠진 경우에만 KIS 등락률로 역산한다(로컬 OHLCV와 섞지 않는다).
    const changePercent = quote.changePercent ?? 0;
    const kisPrevClose =
      typeof quote.previousClose === "number" && quote.previousClose > 0
        ? quote.previousClose
        : null;
    const previousClose =
      kisPrevClose ??
      (changePercent !== 0
        ? Math.round(quote.price / (1 + changePercent / 100))
        : quote.price);
    const change = quote.price - previousClose;

    return NextResponse.json(
      {
        price: quote.price,
        change,
        changePercent,
        previousClose,
        open: quote.open,
        high: quote.high,
        low: quote.low,
        volume: quote.volume,
      },
      { headers: { "Cache-Control": "no-store, must-revalidate" } }
    );
  } catch {
    return NextResponse.json({ error: "Failed to fetch price" }, { status: 500 });
  }
}
