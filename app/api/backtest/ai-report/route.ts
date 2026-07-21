import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

/**
 * PATCH /api/backtest/ai-report
 * AI 리포트(summary, score, strengths, weaknesses, improvements + advisor 진단)를
 * BacktestHistory.metrics에 저장. 같은 전략 캐시 히트 시 재생성 없이 반환하기 위함.
 */
export async function PATCH(req: Request) {
  try {
    const {
      cacheKey,
      aiSummary,
      aiScore,
      aiStrengths,
      aiWeaknesses,
      aiImprovements,
      advisorScore,
      riskScore,
      overfitRisk,
      aiExecutiveSummary,
      aiTopInsights,
      aiHiddenRisks,
      aiOverfittingAnalysis,
      aiStrategyProfile,
      aiStrategyProfileNote,
      aiValidationRoadmap,
      aiFinalVerdict,
    } = await req.json();

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
      aiWeaknesses: aiWeaknesses ?? currentMetrics.aiWeaknesses,
      aiImprovements: aiImprovements ?? currentMetrics.aiImprovements,
      advisorScore: advisorScore ?? currentMetrics.advisorScore,
      riskScore: riskScore ?? currentMetrics.riskScore,
      overfitRisk: overfitRisk ?? currentMetrics.overfitRisk,
      aiExecutiveSummary: aiExecutiveSummary ?? currentMetrics.aiExecutiveSummary,
      aiTopInsights: aiTopInsights ?? currentMetrics.aiTopInsights,
      aiHiddenRisks: aiHiddenRisks ?? currentMetrics.aiHiddenRisks,
      aiOverfittingAnalysis: aiOverfittingAnalysis ?? currentMetrics.aiOverfittingAnalysis,
      aiStrategyProfile: aiStrategyProfile ?? currentMetrics.aiStrategyProfile,
      aiStrategyProfileNote: aiStrategyProfileNote ?? currentMetrics.aiStrategyProfileNote,
      aiValidationRoadmap: aiValidationRoadmap ?? currentMetrics.aiValidationRoadmap,
      aiFinalVerdict: aiFinalVerdict ?? currentMetrics.aiFinalVerdict,
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
