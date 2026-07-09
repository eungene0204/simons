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
    (/^'?\s*\{/.test(value) && /["'](?:total_summary|totalSummary|strengths|weaknesses|improvements)["']\s*:/.test(value)) ||
    /<\/?think>/i.test(value) ||
    /```(?:json)?/i.test(value) ||
    /\[중요\]|작성 규칙|출력 형식|advisor 진단 근거|JSON만 출력/.test(value)
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
  };
}
