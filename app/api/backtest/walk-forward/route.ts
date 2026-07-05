import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(req: NextRequest) {
  // Walk-forward can take a long time (multiple optimization windows).
  // 클라이언트가 취소하면(req.signal) 백엔드로 가는 프록시 fetch도 함께 중단한다.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 600_000);
  req.signal?.addEventListener("abort", () => controller.abort());

  try {
    const body = await req.json();
    const res = await fetch(`${BACKEND_URL}/walk-forward`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return NextResponse.json(err, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json(
      { detail: `Walk-forward proxy error: ${e.message}` },
      { status: 500 }
    );
  } finally {
    clearTimeout(timeoutId);
  }
}
