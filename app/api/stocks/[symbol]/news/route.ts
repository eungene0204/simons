import { NextRequest, NextResponse } from "next/server";

import type { NewsResponseV2 } from "@/types/news-v2";

const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";
const TIMEOUT_MS = 1500;

export const dynamic = "force-dynamic";

async function fetchWithTimeout(
  url: string,
  timeoutMs: number,
  init?: RequestInit
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { cache: "no-store", ...init, signal: controller.signal });
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
  const limit = searchParams.get("limit") ?? "30";

  const url = new URL(`${BACKEND}/v2/news/${encodeURIComponent(symbol)}`);
  url.searchParams.set("limit", limit);
  const companyName = searchParams.get("company_name");
  if (companyName) url.searchParams.set("company_name", companyName);

  try {
    const res = await fetchWithTimeout(url.toString(), TIMEOUT_MS);
    if (!res.ok) {
      const isTransientBackendError = res.status >= 500;
      const fallback: NewsResponseV2 = {
        symbol,
        items: [],
        lastUpdatedAt: null,
        isStale: false,
        status: isTransientBackendError ? "COLLECTING" : "FAILED",
        source: "queue",
        message: isTransientBackendError
          ? "뉴스 서비스가 일시적으로 응답하지 않아 다시 시도하고 있습니다."
          : "뉴스를 불러오지 못했습니다.",
      };
      return NextResponse.json(fallback, { status: 200 });
    }
    const data = (await res.json()) as NewsResponseV2;
    return NextResponse.json(data);
  } catch (err: unknown) {
    const fallback: NewsResponseV2 = {
      symbol,
      items: [],
      lastUpdatedAt: null,
      isStale: false,
      status: "COLLECTING",
      source: "queue",
      message: "뉴스 서비스에 연결할 수 없습니다.",
    };
    return NextResponse.json(fallback, { status: 200 });
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: { symbol: string } }
) {
  const { symbol } = params;
  let body: Record<string, unknown> = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  const payload = {
    ...body,
    symbol,
    eventType: body.eventType ?? "current_view",
    metadata: {
      ...(typeof body.metadata === "object" && body.metadata !== null ? body.metadata : {}),
      proxy: "stock_news_route",
    },
  };

  try {
    const res = await fetchWithTimeout(
      `${BACKEND}/v2/news/priority/events`,
      TIMEOUT_MS,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (res.ok) {
      return NextResponse.json(await res.json());
    }
  } catch {
    // Priority events are best-effort and must not affect stock detail rendering.
  }

  return NextResponse.json(
    { accepted: false, symbol, eventType: payload.eventType },
    { status: 202 }
  );
}
