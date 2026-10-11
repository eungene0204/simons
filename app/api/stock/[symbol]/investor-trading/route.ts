import { NextRequest, NextResponse } from "next/server";
import { backendPathSegment } from "@/lib/server/backend";
import { cache } from "@/lib/cache";

const CACHE_TTL_SECONDS = 60;

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ symbol: string }> | { symbol: string } }
) {
  try {
    const resolvedParams = await Promise.resolve(params);
    const symbol = resolvedParams.symbol;

    if (!symbol) {
      return NextResponse.json({ error: "Symbol parameter is required" }, { status: 400 });
    }

    const cacheKey = `stock:investor-trading:${symbol}`;
    const cached = cache.get(cacheKey);
    if (cached) {
      return NextResponse.json(cached);
    }

    const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
    const symbolSegment = backendPathSegment(symbol);
    if (!symbolSegment) return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
    const res = await fetch(`${BACKEND_URL}/market/investor-trading/${symbolSegment}`, {
      cache: "no-store",
    });

    if (!res.ok) {
      const body = await res.json().catch(() => null);
      return NextResponse.json(
        { error: body?.detail || "투자자 매매동향 데이터를 가져올 수 없습니다" },
        { status: res.status }
      );
    }

    const data = await res.json();
    cache.set(cacheKey, data, CACHE_TTL_SECONDS);
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: "서버 오류", detail: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}
