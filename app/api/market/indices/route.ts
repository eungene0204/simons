import { NextResponse } from "next/server";
import { cache } from "@/lib/cache";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET() {
  try {
    const cacheKey = "market:indices:all";
    const cached = cache.get(cacheKey);
    if (cached) {
      return NextResponse.json(cached);
    }

    const res = await fetch(`${BACKEND_URL}/market/indices`, {
      next: { revalidate: 0 },
    });
    if (!res.ok) {
      throw new Error(`Backend responded ${res.status}`);
    }
    const data = await res.json();

    // 30초 캐시
    cache.set(cacheKey, data, 30);
    return NextResponse.json(data);
  } catch (error) {
    console.error("Market indices API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch market indices" },
      { status: 500 }
    );
  }
}
