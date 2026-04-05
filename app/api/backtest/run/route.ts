import { NextRequest, NextResponse } from "next/server";
import { createHash } from "crypto";
import { prisma } from "@/lib/prisma";

/** 객체/배열을 재귀적으로 키 정렬해 JSON.stringify 결과를 결정적으로 만든다 */
function sortDeep(val: any): any {
  if (Array.isArray(val)) return val.map(sortDeep);
  if (val !== null && typeof val === "object") {
    return Object.fromEntries(
      Object.keys(val)
        .sort()
        .map((k) => [k, sortDeep(val[k])])
    );
  }
  return val;
}

function computeCacheKey(body: any): string {
  const normalized = sortDeep({
    symbols: [...(body.symbols ?? [])].sort(),
    entry: {
      conditions: [...(body.entry?.conditions ?? [])].sort((a: any, b: any) =>
        (a.id ?? "").localeCompare(b.id ?? "")
      ),
    },
    exit: {
      conditions: [...(body.exit?.conditions ?? [])].sort((a: any, b: any) =>
        (a.id ?? "").localeCompare(b.id ?? "")
      ),
    },
    risk: body.risk ?? {},
    period: (body.period ?? "5Y").toUpperCase(),
    options: body.options ?? {},
  });
  return createHash("sha256")
    .update(JSON.stringify(normalized))
    .digest("hex");
}

export async function POST(req: NextRequest) {
  let body: any;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const cacheKey = computeCacheKey(body);

  // 동일 전략 기존 실행 결과 조회 (isVisible 무관)
  const existing = await prisma.backtestHistory.findUnique({
    where: { cacheKey },
  });

  if (existing?.result) {
    const result = JSON.parse(existing.result);
    const metrics = existing.metrics ? JSON.parse(existing.metrics) : {};
    await prisma.backtestHistory.update({
      where: { cacheKey },
      data: { hitCount: { increment: 1 } },
    });
    return NextResponse.json({
      ...result,
      fromCache: true,
      cacheKey,
      cachedAt: existing.createdAt,
      // 저장된 AI 리포트가 있으면 캐시 응답에 포함 (재생성 불필요)
      aiSummary: metrics.aiSummary ?? null,
      aiScore: metrics.aiScore ?? null,
      aiStrengths: metrics.aiStrengths ?? null,
      aiRisks: metrics.aiRisks ?? null,
    });
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
  try {
    const metrics = {
      totalReturn: result.totalReturn ?? 0,
      cagr: result.cagr ?? 0,
      mdd: result.maxDrawdown ?? 0,
      winRate: result.winRate ?? 0,
      profitFactor: result.profitFactor ?? 0,
      buyHold: result.buyAndHoldReturn ?? 0,
      trades: result.trades ?? 0,
      executionTime: result.executionTime ?? 0,
    };

    await prisma.backtestHistory.create({
      data: {
        strategyName: "",
        universe: (body.symbols ?? []).slice(0, 3).join(","),
        conditions: JSON.stringify({ entry: body.entry, exit: body.exit }),
        metrics: JSON.stringify(metrics),
        result: JSON.stringify(result),
        cacheKey,
        isVisible: false,
      },
    });
  } catch (err) {
    console.error("[BacktestHistory] 자동 저장 실패:", err);
  }

  return NextResponse.json({ ...result, fromCache: false, cacheKey });
}
