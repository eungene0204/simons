import { BacktestResult } from "@/types/strategy";

/**
 * 저장된 AI 총평이 LLM 내부 추론(<think>)이나 프롬프트 지시문 복창으로 오염됐는지 검사.
 * 서버 라우트의 hasReportFormattingArtifact와 같은 기준 — 오염 레코드는 표시하지 않고
 * 재생성을 트리거한다.
 */
export function hasAiReportArtifact(summary: unknown): boolean {
  if (typeof summary !== "string") return false;
  const value = summary.trim();
  if (!value) return false;

  return (
    (/^'?\s*\{/.test(value) && /["'](?:total_summary|totalSummary|executive_summary|executiveSummary|strengths|weaknesses|improvements|top_insights)["']\s*:/.test(value)) ||
    /<\/?think>/i.test(value) ||
    /```(?:json)?/i.test(value) ||
    /\[중요\]|작성 규칙|출력 형식|advisor 진단 근거|JSON만 출력/.test(value)
  );
}

// 한글·ASCII 외 문자(가나·한자·키릴 등) — 어느 UI 언어에서도 리포트에 있으면 안 된다.
const FOREIGN_LETTER = /(?!\p{Script=Hangul})[^\x00-\x7F\P{L}]/u;
// 영어 '문장' — 소문자 낱말을 포함한 4단어 이상 연속(지표 약어·고유 명칭은 통과). 한국어 UI 전용.
const ENGLISH_RUN = /[A-Za-z][A-Za-z'’-]*(?:\s+[A-Za-z][A-Za-z'’-]*){3,}/g;

/**
 * 저장된 AI 리포트 서술(LLM 출력)에 표시 언어가 아닌 텍스트가 섞였는지 검사한다.
 * 백엔드 `find_non_korean_fragments`와 같은 기준 — 2026-10-02 이전에 저장된 '가능성があります'
 * 같은 혼입 레코드는 표시하지 않고 재생성을 트리거한다.
 */
export function hasForeignLanguageReportText(fields: readonly unknown[], language: "ko" | "en"): boolean {
  const texts = fields.flatMap((field) => (Array.isArray(field) ? field : [field]))
    .filter((value): value is string => typeof value === "string");
  return texts.some((text) =>
    FOREIGN_LETTER.test(text) ||
    (language === "ko" && [...text.matchAll(ENGLISH_RUN)].some((m) => /\b[a-z]{2,}\b/.test(m[0])))
  );
}

/**
 * AI 리포트 생성에 쓰는 metrics 페이로드. 대시보드(백그라운드 생성)와
 * BacktestSummaryCard('다시 생성')가 반드시 같은 형태를 보내야
 * 서버의 in-flight 중복 제거·메모리 캐시가 동작한다.
 */
export function buildAiReportMetrics(result: BacktestResult) {
  // 엔진 응답에 initialCapital/finalEquity가 비어 있는 경우 equity 배열 양끝값으로 보완
  const initialCapital = result.initialCapital || result.equity?.[0] || 0;
  const finalEquity = result.finalEquity || result.equity?.[result.equity.length - 1] || 0;
  return {
    totalReturn: result.totalReturn,
    cagr: result.cagr,
    buyAndHoldReturn: result.buyAndHoldReturn,
    maxDrawdown: result.maxDrawdown,
    sharpe: result.sharpe,
    sortino: result.sortino,
    profitFactor: result.profitFactor,
    winRate: result.winRate,
    trades: result.trades,
    volatility: result.volatility,
    kelly: result.kelly,
    initialCapital,
    finalEquity,
    // 백테스트 기간 — LLM이 기간을 추측(환각)하지 않고 실제 기간을 인용하게 한다
    periodStart: result.dates?.[0],
    periodEnd: result.dates?.[result.dates.length - 1],
    // 전략 검증 전문가 리포트의 결정론 근거(집중도·수중기간·기대값·회전율·종목집중)용 확장 지표.
    // 엔진이 이미 계산해 내려주는 값을 전달만 한다.
    calmar: result.calmar,
    maxDrawdownDuration: result.maxDrawdownDuration,
    expectancy: result.expectancy,
    recoveryFactor: result.recoveryFactor,
    avgHoldingDays: result.avgHoldingDays,
    exposure: result.exposure,
    maxConsecutiveWins: result.maxConsecutiveWins,
    maxConsecutiveLosses: result.maxConsecutiveLosses,
    avgProfit: result.avgProfit,
    avgLoss: result.avgLoss,
    monthlyReturns: result.monthlyReturns,
    yearlyReturns: result.yearlyReturns,
    perAssetStats: result.perAssetStats,
  };
}
