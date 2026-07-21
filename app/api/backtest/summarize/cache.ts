export type RoadmapItem = {
  title: string;
  reason: string;
  priority: number;
};

export type SummaryCachePayload = {
  score: number;
  summary: string;
  strengths: string[];
  weaknesses: string[];
  improvements: string[];
  advisorScore?: number | null;
  riskScore?: number | null;
  overfitRisk?: string | null;
  // 전략 검증 전문가 리포트(10섹션) 확장 필드 — 구 저장 리포트엔 없을 수 있어 모두 선택적.
  executiveSummary?: string;
  topInsights?: string[];
  hiddenRisks?: string[];
  overfittingAnalysis?: string;
  strategyProfile?: string[];
  strategyProfileNote?: string;
  validationRoadmap?: RoadmapItem[];
  finalVerdict?: string;
  degraded?: boolean;
};

const SUMMARY_CACHE_MAX = 200;
const summaryMemoryCache = new Map<string, SummaryCachePayload>();
const summaryInFlight = new Map<string, Promise<SummaryCachePayload>>();

export function getSummaryMemoryCache(key: string) {
  return summaryMemoryCache.get(key);
}

export function rememberSummary(key: string, payload: SummaryCachePayload) {
  if (summaryMemoryCache.has(key)) {
    summaryMemoryCache.delete(key);
  }
  summaryMemoryCache.set(key, payload);
  if (summaryMemoryCache.size > SUMMARY_CACHE_MAX) {
    const oldestKey = summaryMemoryCache.keys().next().value;
    if (oldestKey) summaryMemoryCache.delete(oldestKey);
  }
}

export function getSummaryInFlight(key: string) {
  return summaryInFlight.get(key);
}

export function setSummaryInFlight(key: string, value: Promise<SummaryCachePayload>) {
  summaryInFlight.set(key, value);
}

export function deleteSummaryInFlight(key: string) {
  summaryInFlight.delete(key);
}

export function __resetSummaryCacheForTests() {
  summaryMemoryCache.clear();
  summaryInFlight.clear();
}
