import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";

// 독립 스크리너(엔진 v16.33) — 저장된 전략의 조건을 오늘 데이터에 적용한다.
// 유니버스 전체를 훑으므로 백테스트만큼 오래 걸릴 수 있다(타임아웃을 넉넉히 둔다).
export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  try {
    const res = await fetchBackend("/screener/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      timeoutMs: 180_000,
      signal: req.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return NextResponse.json({ detail: err.detail ?? res.statusText }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (e: any) {
    return NextResponse.json({ detail: `Screener proxy error: ${e.message}` }, { status: 500 });
  }
}
