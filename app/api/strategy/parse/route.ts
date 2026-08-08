import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";

export async function POST(req: NextRequest) {
  let body: unknown;

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  try {
    const res = await fetchBackend("/strategy/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      // 스트리밍 경로와 같은 백엔드 파스를 부른다 — 예산도 같이 간다(stream/route.ts 주석 참조).
      timeoutMs: 240_000,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return NextResponse.json(err, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json(
      { detail: `Strategy parse proxy error: ${e.message}` },
      { status: 500 }
    );
  }
}
