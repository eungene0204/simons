import { NextRequest, NextResponse } from "next/server";
import { computeCacheKey, findCachedResult, saveCachedResult } from "@/lib/server/backtestCache";

export async function POST(req: NextRequest) {
  let body: any;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const cacheKey = computeCacheKey(body);

  // 동일 전략 기존 실행 결과 조회 (isVisible 무관)
  const cached = await findCachedResult(cacheKey);
  if (cached) {
    return NextResponse.json(cached);
  }

  // 미저장 전략: Python 엔진 실행
  let pythonRes: Response;
  try {
    pythonRes = await fetch("http://localhost:8000/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch (err: any) {
    return NextResponse.json(
      { detail: `백엔드 연결 실패: ${err.message}` },
      { status: 502 }
    );
  }

  if (!pythonRes.ok) {
    const errData = await pythonRes.json().catch(() => ({ detail: "Unknown error" }));
    return NextResponse.json(errData, { status: pythonRes.status });
  }

  const result = await pythonRes.json();

  // BacktestHistory에 isVisible=false 로 저장 (중복 실행 방지용, 목록 비노출)
  await saveCachedResult(cacheKey, body, result);

  return NextResponse.json({ ...result, fromCache: false, cacheKey });
}
