/**
 * AI 백테스트 리포트(전략 검증 전문가 리포트) 공유 타입 + 매핑 헬퍼.
 * BacktestDashboard(생성·저장)와 BacktestSummaryCard(표시)가 같은 형태를 공유한다.
 */

export type RoadmapItem = {
  title: string;
  reason: string;
  priority: number;
};

export interface AiReportData {
  // summary == executiveSummary (기존 저장/캐시 키 하위호환)
  summary: string;
  score: number;
  strengths: string[];
  weaknesses: string[];
  improvements: string[];
  advisorScore: number | null;
  riskScore: number | null;
  overfitRisk: string | null;
  // 전략 검증 전문가 리포트(10섹션) 확장 — 구 저장 리포트엔 없을 수 있어 모두 선택적.
  topInsights?: string[];
  hiddenRisks?: string[];
  overfittingAnalysis?: string;
  strategyProfile?: string[];
  strategyProfileNote?: string;
  validationRoadmap?: RoadmapItem[];
  finalVerdict?: string;
}

/**
 * /api/backtest/summarize 응답 → AiReportData. 파싱 실패(degraded)·필수 필드 누락 시 null.
 */
export function reportFromSummaryResponse(data: any): AiReportData | null {
  if (!data || !data.summary || data.score == null || data.degraded) return null;
  return {
    summary: data.summary,
    score: data.score,
    strengths: data.strengths ?? [],
    weaknesses: data.weaknesses ?? [],
    improvements: data.improvements ?? [],
    advisorScore: data.advisorScore ?? null,
    riskScore: data.riskScore ?? null,
    overfitRisk: data.overfitRisk ?? null,
    topInsights: data.topInsights ?? undefined,
    hiddenRisks: data.hiddenRisks ?? undefined,
    overfittingAnalysis: data.overfittingAnalysis ?? undefined,
    strategyProfile: data.strategyProfile ?? undefined,
    strategyProfileNote: data.strategyProfileNote ?? undefined,
    validationRoadmap: data.validationRoadmap ?? undefined,
    finalVerdict: data.finalVerdict ?? undefined,
  };
}

/**
 * 저장/캐시(BacktestHistory.metrics blob)용 평탄화 필드. summarize POST·ai-report PATCH·
 * save-with-backtest·history 가 동일 키를 쓰도록 한 곳에서 만든다.
 */
export function reportToPersistedFields(report: AiReportData) {
  return {
    aiSummary: report.summary,
    aiScore: report.score,
    aiStrengths: report.strengths,
    aiWeaknesses: report.weaknesses,
    aiImprovements: report.improvements,
    advisorScore: report.advisorScore,
    riskScore: report.riskScore,
    overfitRisk: report.overfitRisk,
    aiExecutiveSummary: report.summary,
    aiTopInsights: report.topInsights,
    aiHiddenRisks: report.hiddenRisks,
    aiOverfittingAnalysis: report.overfittingAnalysis,
    aiStrategyProfile: report.strategyProfile,
    aiStrategyProfileNote: report.strategyProfileNote,
    aiValidationRoadmap: report.validationRoadmap,
    aiFinalVerdict: report.finalVerdict,
  };
}
