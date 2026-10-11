import { NextRequest, NextResponse } from 'next/server';
import { backendPathSegment } from '@/lib/server/backend';
import { cache } from "@/lib/cache";

export const dynamic = "force-dynamic";

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const CACHE_TTL_SECONDS = 30;

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ symbol: string }> | { symbol: string } }
) {
  const { symbol } = await Promise.resolve(params);
  const limit = request.nextUrl.searchParams.get('limit') || '1260';

  const cacheKey = `stock:ohlcv:${symbol}:${limit}`;
  const cached = cache.get(cacheKey);
  if (cached) {
    return NextResponse.json(cached);
  }

  try {
    const symbolSegment = backendPathSegment(symbol);
    if (!symbolSegment) return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
    const res = await fetch(`${BACKEND_URL}/stock/${symbolSegment}/ohlcv?limit=${limit}`, {
      cache: "no-store",
    });
    if (!res.ok) {
      return NextResponse.json({ error: 'Not found' }, { status: res.status });
    }
    const data = await res.json();
    cache.set(cacheKey, data, CACHE_TTL_SECONDS);
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: 'Backend unavailable' }, { status: 503 });
  }
}
