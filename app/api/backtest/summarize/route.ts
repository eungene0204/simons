import { NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";
import { prisma } from "@/lib/prisma";

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { metrics, strategySummary, cacheKey } = body;

    if (!metrics) {
      return NextResponse.json({ error: "Missing metrics" }, { status: 400 });
    }

    if (cacheKey) {
      const existing = await prisma.backtestHistory.findUnique({ where: { cacheKey } });
      const existingMetrics = existing?.metrics ? JSON.parse(existing.metrics) : null;

      if (existingMetrics?.aiSummary && existingMetrics?.aiScore != null) {
        return NextResponse.json({
          score: existingMetrics.aiScore,
          summary: existingMetrics.aiSummary,
          strengths: existingMetrics.aiStrengths ?? [],
          risks: existingMetrics.aiRisks ?? [],
          cached: true,
        });
      }
    }

    const res = await fetchBackend("/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metrics, strategySummary }),
      cache: "no-store",
      timeoutMs: 120_000,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: "Unknown error" }));
      return NextResponse.json(
        { error: errData.detail ?? "Summarize failed" },
        { status: res.status }
      );
    }

    const result = await res.json();
    const payload = {
      score: result.score,
      summary: result.summary,
      strengths: result.strengths ?? [],
      risks: result.risks ?? [],
      cached: false,
    };

    if (cacheKey) {
      const existing = await prisma.backtestHistory.findUnique({ where: { cacheKey } });
      if (existing) {
        const currentMetrics = existing.metrics ? JSON.parse(existing.metrics) : {};
        await prisma.backtestHistory.update({
          where: { cacheKey },
          data: {
            metrics: JSON.stringify({
              ...currentMetrics,
              aiSummary: payload.summary ?? currentMetrics.aiSummary,
              aiScore: payload.score ?? currentMetrics.aiScore,
              aiStrengths: payload.strengths,
              aiRisks: payload.risks,
            }),
          },
        });
      }
    }

    return NextResponse.json({
      ...payload,
    });
  } catch (error: any) {
    console.error("Summarize error:", error);
    return NextResponse.json(
      { error: `Summarize proxy error: ${error?.message ?? "Internal server error"}` },
      { status: 500 }
    );
  }
}
