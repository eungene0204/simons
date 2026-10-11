import { NextResponse } from "next/server";
import { backendPathSegment, fetchBackend } from "@/lib/server/backend";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> | { symbol: string } }
) {
  const resolvedParams = await Promise.resolve(params);
  const symbol = resolvedParams.symbol;

  if (!symbol) {
    return NextResponse.json(
      { detail: "Symbol parameter is required" },
      { status: 400 }
    );
  }

  try {
    const symbolSegment = backendPathSegment(symbol);
    if (!symbolSegment) return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
    const res = await fetchBackend(`/market/orderbook-stream/${symbolSegment}`, {
      method: "GET",
      cache: "no-store",
      timeoutMs: 600_000,
      headers: {
        Accept: "text/event-stream",
      },
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return NextResponse.json(err, { status: res.status });
    }

    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("Content-Type") || "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch (e: any) {
    return NextResponse.json(
      { detail: `Orderbook stream proxy error: ${e.message}` },
      { status: 500 }
    );
  }
}
