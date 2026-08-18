import { BacktestResult } from "@/types/strategy";

/**
 * 백테스트 SSE `result` 이벤트의 raw payload를 프론트엔드 BacktestResult로 매핑한다.
 * 인라인 매핑이 필드를 누락하면(예: avgHoldingDays) 대시보드가 0으로 표시되는 버그를
 * 막기 위해 순수 함수로 분리해 단위 테스트로 검증한다.
 */
export function mapRawBacktestResult(
  raw: any,
  executionId: string,
  cacheKey?: string
): BacktestResult {
  const equity: number[] = raw.equity ?? [];
  return {
    executionId,
    strategyId: "nl_strategy",
    // 히스토리 dedup 키. 없으면 자동저장(프롬프트명)과 명시저장(전략명)이
    // 별도 행으로 분리되어 같은 백테스트가 두 번 기록된다.
    cacheKey: cacheKey ?? raw.cacheKey ?? undefined,
    symbols: raw.symbols,
    totalReturn: raw.totalReturn ?? 0,
    cagr: raw.cagr ?? 0,
    buyAndHoldReturn: raw.buyAndHoldReturn ?? 0,
    maxDrawdown: raw.maxDrawdown ?? 0,
    winRate: raw.winRate ?? 0,
    // 손실 거래 0건이면 엔진이 null(=∞)을 내려보낸다 — 0으로 뭉개면 전승 전략이
    // 손익비 0(최악)으로 표시된다. 켈리도 마찬가지로 미정의를 0으로 바꾸지 않는다.
    profitFactor: raw.profitFactor ?? null,
    sharpe: raw.sharpe ?? 0,
    sortino: raw.sortino ?? 0,
    kelly: raw.kelly ?? null,
    volatility: raw.volatility ?? 0,
    avgHoldingDays: raw.avgHoldingDays ?? 0,
    exposure: raw.exposure ?? 0,
    maxDrawdownDuration: raw.maxDrawdownDuration ?? 0,
    expectancy: raw.expectancy ?? 0,
    recoveryFactor: raw.recoveryFactor ?? 0,
    trades: raw.trades ?? 0,
    avgProfit: raw.avgProfit ?? 0,
    avgLoss: raw.avgLoss ?? 0,
    maxConsecutiveWins: raw.maxConsecutiveWins ?? 0,
    maxConsecutiveLosses: raw.maxConsecutiveLosses ?? 0,
    finalEquity: equity[equity.length - 1] ?? 0,
    initialCapital: equity[0] ?? 0,
    equity,
    benchmarkEquity: raw.benchmark_equity,
    benchmarkLabel: raw.benchmark_label,
    benchmarkPartial: raw.benchmark_partial,
    dates: raw.dates ?? [],
    tradesList: (raw.signals ?? []).map((s: any) => ({
      date: s.date,
      symbol: s.symbol,
      type: s.type as "buy" | "sell",
      price: s.price,
      quantity: s.quantity ?? 0,
      amount: s.amount ?? 0,
      reason: s.condition,
    })),
    monthlyReturns: {},
    yearlyReturns: {},
    signals: (raw.signals ?? []).map((s: any) => ({
      date: s.date,
      symbol: s.symbol,
      type: s.type === "buy" ? "entry" : "exit",
      condition: s.condition,
      price: Number(s.price),
      quantity: Number(s.quantity),
      amount: Number(s.amount),
    })),
    perAssetStats: raw.perAssetStats,
    universeId: raw.universe_id,
    warnings: raw.warnings,
    executionTime: raw.executionTime,
    vbtResult: raw.vbtResult ?? undefined,
    // 분위 그룹 비교(FR-BT-060) — 누락하면 그룹 비교 섹션이 조용히 사라진다.
    quantileGroups: raw.quantileGroups ?? undefined,
    rebalanceComparison: raw.rebalanceComparison ?? undefined,
  };
}
