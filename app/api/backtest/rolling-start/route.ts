import { NextRequest, NextResponse } from "next/server";
import { rejectWalkForwardIfNotAllowed } from "../walk-forward/access";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

// 검증 도구(v16.30, 'rolling-start')는 워크포워드와 같은 프리미엄 게이트를 지난다 — 화면 잠금만으로는
// API 직접 호출을 막지 못하므로 백엔드로 넘기기 전에 로그인·플랜을 재검증한다.
export async function POST(req: NextRequest) {
  const rejected = await rejectWalkForwardIfNotAllowed();
  if (rejected) return rejected;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 600_000);
  req.signal?.addEventListener("abort", () => controller.abort());

  try {
    const body = await req.json();
    const res = await fetch(`${BACKEND_URL}/rolling-start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return NextResponse.json(err, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (e: any) {
    return NextResponse.json({ detail: `rolling-start proxy error: ${e.message}` }, { status: 500 });
  } finally {
    clearTimeout(timeoutId);
  }
}
