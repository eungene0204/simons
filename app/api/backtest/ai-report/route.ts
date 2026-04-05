import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

/**
 * PATCH /api/backtest/ai-report
 * AI 리포트(summary, score, strengths, risks)를 BacktestHistory.metrics에 저장.
 * 같은 전략 캐시 히트 시 재생성 없이 저장된 리포트를 반환하기 위함.
 */
export async function PATCH(req: Request) {
  try {
    const { cacheKey, aiSummary, aiScore, aiStrengths, aiRisks } = await req.json();

    if (!cacheKey) {
      return NextResponse.json({ error: "cacheKey is required" }, { status: 400 });
    }

    const existing = await prisma.backtestHistory.findUnique({ where: { cacheKey } });
    if (!existing) {
      return NextResponse.json({ error: "Record not found" }, { status: 404 });
    }

    const currentMetrics = existing.metrics ? JSON.parse(existing.metrics) : {};
    const updatedMetrics = {
      ...currentMetrics,
      aiSummary: aiSummary ?? currentMetrics.aiSummary,
      aiScore: aiScore ?? currentMetrics.aiScore,
      aiStrengths: aiStrengths ?? currentMetrics.aiStrengths,
      aiRisks: aiRisks ?? currentMetrics.aiRisks,
    };

    await prisma.backtestHistory.update({
      where: { cacheKey },
      data: { metrics: JSON.stringify(updatedMetrics) },
    });

    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("[ai-report] 저장 실패:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
