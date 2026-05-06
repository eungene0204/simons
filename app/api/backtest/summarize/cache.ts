export type SummaryCachePayload = {
  score: number;
  summary: string;
  strengths: string[];
  weaknesses: string[];
  improvements: string[];
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
