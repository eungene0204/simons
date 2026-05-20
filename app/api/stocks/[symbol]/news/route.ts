import { NextRequest, NextResponse } from "next/server";

import type { NewsResponseV2 } from "@/types/news-v2";

const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";
const TIMEOUT_MS = 1500;

export const dynamic = "force-dynamic";

async function fetchWithTimeout(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { cache: "no-store", signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { symbol: string } }
) {
  const { symbol } = params;
  const { searchParams } = request.nextUrl;
  const limit = searchParams.get("limit") ?? "20";

  const url = new URL(`${BACKEND}/v2/news/${encodeURIComponent(symbol)}`);
  url.searchParams.set("limit", limit);
  const companyName = searchParams.get("company_name");
  if (companyName) url.searchParams.set("company_name", companyName);

  try {
    const res = await fetchWithTimeout(url.toString(), TIMEOUT_MS);
    if (!res.ok) {
      const fallback: NewsResponseV2 = {
        status: "FAILED",
        source: "queue",
        stale: false,
        items: [],
        fetched_at: null,
        message: `백엔드 응답 오류 (${res.status})`,
      };
      return NextResponse.json(fallback, { status: 200 });
    }
    const data = (await res.json()) as NewsResponseV2;
    return NextResponse.json(data);
  } catch (err: unknown) {
    const fallback: NewsResponseV2 = {
      status: "COLLECTING",
      source: "queue",
      stale: false,
      items: [],
      fetched_at: null,
      message: "뉴스 서비스에 연결할 수 없습니다.",
    };
    return NextResponse.json(fallback, { status: 200 });
  }
}
