import { NextRequest, NextResponse } from "next/server";

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

    const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
    const res = await fetch(`${BACKEND_URL}/market/orderbook/${symbol}`, {
      cache: "no-store",
    });
    if (!res.ok) {
      return NextResponse.json(
        { error: "Failed to fetch orderbook" },
        { status: res.status }
      );
    }

    const response = await res.json();
    return NextResponse.json(response);
  } catch (error) {
    console.error("Order book API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch order book", detail: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}
