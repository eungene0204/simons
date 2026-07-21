import { NextResponse } from "next/server";
import { fetchBackend } from "@/lib/server/backend";
import { prisma } from "@/lib/prisma";
import {
  deleteSummaryInFlight,
  getSummaryInFlight,
  getSummaryMemoryCache,
  rememberSummary,
  setSummaryInFlight,
  type SummaryCachePayload,
} from "./cache";

type SummaryPayload = SummaryCachePayload & {
  cached: boolean;
};

const SUMMARY_CACHE_GENERATION = "ai-report-expert-v5";

class SummarizeBackendError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }

  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
    .join(",")}}`;
}

async function sha256(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function summaryPayloadKey(
  metrics: unknown,
  strategySummary: unknown,
  parsedStrategy: unknown,
  userPrompt: unknown
): Promise<string> {
  return sha256(stableStringify({
    generation: SUMMARY_CACHE_GENERATION,
    metrics,
    strategySummary,
    parsedStrategy,
    userPrompt,
  }));
}

function hasReportFormattingArtifact(summary: unknown): boolean {
  if (typeof summary !== "string") return false;
  const value = summary.trim();
  if (!value) return false;

  return (
    (/^'?\s*\{/.test(value) && /["'](?:total_summary|totalSummary|executive_summary|executiveSummary|strengths|weaknesses|improvements|top_insights)["']\s*:/.test(value)) ||
    /<\/?think>/i.test(value) ||
    /```(?:json)?/i.test(value) ||
    // 프롬프트 지시문 복창(에코)이 요약으로 저장된 오염 레코드 — 서빙하지 않고 재생성한다.
    /\[중요\]|작성 규칙|출력 형식|advisor 진단 근거|JSON만 출력/.test(value)
  );
}

async function fetchSummary(
  metrics: unknown,
  strategySummary: unknown,
  parsedStrategy: unknown,
  userPrompt: unknown
): Promise<SummaryCachePayload> {
  const res = await fetchBackend("/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      metrics,
      strategySummary,
      parsed_strategy: parsedStrategy,
      user_prompt: userPrompt,
    }),
    cache: "no-store",
    // Modal 콜드스타트(웜업 ~200s + 첫 추론)까지 커버해야 한다 — 백엔드 summarize가
    // warmup+재시도 예산을 갖게 되었으므로 프록시가 먼저 끊지 않도록 여유를 둔다.
    timeoutMs: 360_000,
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new SummarizeBackendError(errData.detail ?? "Summarize failed", res.status);
  }

  const result = await res.json();
  const payload: SummaryCachePayload = {
    score: result.score,
    summary: result.summary,
    strengths: result.strengths ?? [],
    weaknesses: result.weaknesses ?? [],
    improvements: result.improvements ?? [],
  };
  // advisor 진단이 수행된 경우에만 부가 필드를 포함한다(LLM 단독 폴백 경로와 응답 형태 동일 유지).
  if (result.advisorScore != null) payload.advisorScore = result.advisorScore;
  if (result.riskScore != null) payload.riskScore = result.riskScore;
  if (result.overfitRisk != null) payload.overfitRisk = result.overfitRisk;
  // 전략 검증 전문가 리포트(10섹션) 확장 필드.
  if (result.executiveSummary != null) payload.executiveSummary = result.executiveSummary;
  if (result.topInsights != null) payload.topInsights = result.topInsights;
  if (result.hiddenRisks != null) payload.hiddenRisks = result.hiddenRisks;
  if (result.overfittingAnalysis != null) payload.overfittingAnalysis = result.overfittingAnalysis;
  if (result.strategyProfile != null) payload.strategyProfile = result.strategyProfile;
  if (result.strategyProfileNote != null) payload.strategyProfileNote = result.strategyProfileNote;
  if (result.validationRoadmap != null) payload.validationRoadmap = result.validationRoadmap;
  if (result.finalVerdict != null) payload.finalVerdict = result.finalVerdict;
  // 백엔드가 LLM 출력 파싱에 실패해 폴백 문구를 반환한 경우 — 캐시/저장 금지 신호.
  if (result.degraded) payload.degraded = true;
  return payload;
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { metrics, strategySummary, parsedStrategy, userPrompt, cacheKey, force } = body;

    if (!metrics) {
      return NextResponse.json({ error: "Missing metrics" }, { status: 400 });
    }

    // force=true('다시 생성' 버튼)는 저장된 리포트를 무시하고 새로 생성한다.
    if (cacheKey && !force) {
      const existing = await prisma.backtestHistory.findUnique({ where: { cacheKey } });
      const existingMetrics = existing?.metrics ? JSON.parse(existing.metrics) : null;

      if (
        existingMetrics?.aiSummary &&
        existingMetrics?.aiScore != null &&
        !hasReportFormattingArtifact(existingMetrics.aiSummary)
      ) {
        return NextResponse.json({
          score: existingMetrics.aiScore,
          summary: existingMetrics.aiSummary,
          strengths: existingMetrics.aiStrengths ?? [],
          weaknesses: existingMetrics.aiWeaknesses ?? [],
          improvements: existingMetrics.aiImprovements ?? [],
          // advisor 진단이 함께 저장된 경우 그대로 복원한다(누락 시 리스크 진단 카드가 사라짐).
          advisorScore: existingMetrics.advisorScore ?? undefined,
          riskScore: existingMetrics.riskScore ?? undefined,
          overfitRisk: existingMetrics.overfitRisk ?? undefined,
          // 전략 검증 전문가 리포트 확장 필드 복원(구 저장 리포트엔 없어 undefined 폴백).
          executiveSummary: existingMetrics.aiExecutiveSummary ?? undefined,
          topInsights: existingMetrics.aiTopInsights ?? undefined,
          hiddenRisks: existingMetrics.aiHiddenRisks ?? undefined,
          overfittingAnalysis: existingMetrics.aiOverfittingAnalysis ?? undefined,
          strategyProfile: existingMetrics.aiStrategyProfile ?? undefined,
          strategyProfileNote: existingMetrics.aiStrategyProfileNote ?? undefined,
          validationRoadmap: existingMetrics.aiValidationRoadmap ?? undefined,
          finalVerdict: existingMetrics.aiFinalVerdict ?? undefined,
          cached: true,
        });
      }
    }

    const payloadKey = await summaryPayloadKey(metrics, strategySummary, parsedStrategy, userPrompt);
    if (!force) {
      const memoryHit = getSummaryMemoryCache(payloadKey);
      if (memoryHit) {
        return NextResponse.json({ ...memoryHit, cached: true });
      }
    }

    let pending = getSummaryInFlight(payloadKey);
    if (!pending) {
      pending = fetchSummary(metrics, strategySummary, parsedStrategy, userPrompt).finally(() => {
        deleteSummaryInFlight(payloadKey);
      });
      setSummaryInFlight(payloadKey, pending);
    }

    const generated = await pending;
    // 파싱 실패 폴백(degraded)은 캐시·DB에 남기지 않는다 — 남기면 실패 문구가
    // 캐시 히트로 계속 서빙되고 '다시 생성' 외엔 복구 수단이 없어진다.
    if (!generated.degraded) {
      rememberSummary(payloadKey, generated);
    }

    const payload: SummaryPayload = {
      ...generated,
      cached: false,
    };

    if (cacheKey && !generated.degraded) {
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
              aiWeaknesses: payload.weaknesses,
              aiImprovements: payload.improvements,
              // advisor 진단 필드도 함께 저장 — 클라이언트 PATCH가 누락돼도 캐시 히트에서 복원 가능.
              advisorScore: payload.advisorScore ?? currentMetrics.advisorScore,
              riskScore: payload.riskScore ?? currentMetrics.riskScore,
              overfitRisk: payload.overfitRisk ?? currentMetrics.overfitRisk,
              // 전략 검증 전문가 리포트(10섹션) 확장 필드.
              aiExecutiveSummary: payload.executiveSummary ?? currentMetrics.aiExecutiveSummary,
              aiTopInsights: payload.topInsights ?? currentMetrics.aiTopInsights,
              aiHiddenRisks: payload.hiddenRisks ?? currentMetrics.aiHiddenRisks,
              aiOverfittingAnalysis: payload.overfittingAnalysis ?? currentMetrics.aiOverfittingAnalysis,
              aiStrategyProfile: payload.strategyProfile ?? currentMetrics.aiStrategyProfile,
              aiStrategyProfileNote: payload.strategyProfileNote ?? currentMetrics.aiStrategyProfileNote,
              aiValidationRoadmap: payload.validationRoadmap ?? currentMetrics.aiValidationRoadmap,
              aiFinalVerdict: payload.finalVerdict ?? currentMetrics.aiFinalVerdict,
            }),
          },
        });
      }
    }

    return NextResponse.json({
      ...payload,
    });
  } catch (error: any) {
    if (error instanceof SummarizeBackendError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }

    console.error("Summarize error:", error);
    return NextResponse.json(
      { error: `Summarize proxy error: ${error?.message ?? "Internal server error"}` },
      { status: 500 }
    );
  }
}
