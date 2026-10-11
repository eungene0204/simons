import { NextRequest, NextResponse } from "next/server";
import { backendPathSegment } from "@/lib/server/backend";

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
    const symbolSegment = backendPathSegment(symbol);
    if (!symbolSegment) return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
    const res = await fetch(`${BACKEND_URL}/market/orderbook/${symbolSegment}`, {
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
