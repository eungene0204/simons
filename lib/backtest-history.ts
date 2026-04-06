import type { BacktestResult } from "@/types/strategy";

export interface BacktestStrategySummary {
  universeName: string;
  strategyName: string;
  entryLogic?: string;
  exitLogic?: string;
  entryBlocks?: string[];
  exitBlocks?: string[];
  positionText?: string;
  riskText?: string;
}

export function buildAutoSaveHistoryPayload(
  result: BacktestResult,
  strategySummary: BacktestStrategySummary
) {
  return {
    strategyName: strategySummary.strategyName || "이름 없는 전략",
    universe: strategySummary.universeName,
    conditions: {
      entry: { logic: strategySummary.entryLogic || "AND", names: strategySummary.entryBlocks || [] },
      exit: { logic: strategySummary.exitLogic || "AND", names: strategySummary.exitBlocks || [] },
      position: strategySummary.positionText,
      risk: strategySummary.riskText,
    },
    metrics: {
      totalReturn: result.totalReturn || 0,
      cagr: result.cagr || 0,
      mdd: result.maxDrawdown || 0,
      winRate: result.winRate || 0,
      profitFactor: result.profitFactor || 0,
      buyHold: result.buyAndHoldReturn || 0,
      trades: result.trades || 0,
      executionTime: result.executionTime ?? 0,
      score: calculateHistoryScore(result),
    },
    cacheKey: result.cacheKey,
    isAutoSave: true,
    // cacheKey 기반 source-of-truth 레코드가 없으면 상세 결과도 같이 저장해야 한다.
    result: result.cacheKey ? undefined : result,
  };
}

function calculateHistoryScore(r: {
  cagr?: number;
  maxDrawdown?: number;
  sharpe?: number;
  profitFactor?: number;
  winRate?: number;
}): number {
  const scoreCagr = (v?: number) => {
    if (v == null) return 50;
    if (v >= 20) return 100;
    if (v >= 10) return 70;
    return Math.max(0, Math.round((v / 10) * 70));
  };
  const scoreMdd = (v?: number) => {
    if (v == null) return 50;
    const a = Math.abs(v);
    if (a <= 10) return 100;
    if (a <= 20) return 70;
    if (a <= 30) return 40;
    return Math.max(0, Math.round(100 - a * 2));
  };
  const scoreSharpe = (v?: number) => {
    if (v == null) return 50;
    if (v >= 1.5) return 100;
    if (v >= 1.0) return 70;
    if (v >= 0.5) return 40;
    return Math.max(0, Math.round((v / 1.5) * 100));
  };
  const scorePf = (v?: number) => {
    if (v == null) return 50;
    if (v >= 2.0) return 100;
    if (v >= 1.5) return 70;
    if (v >= 1.0) return 40;
    return Math.max(0, Math.round((v / 2.0) * 100));
  };
  const scoreWr = (v?: number) => {
    if (v == null) return 50;
    if (v >= 55) return 100;
    if (v >= 50) return 70;
    if (v >= 45) return 40;
    return Math.max(0, Math.round((v / 55) * 100));
  };

  return Math.round(
    scoreCagr(r.cagr) * 0.3 +
    scoreMdd(r.maxDrawdown) * 0.25 +
    scoreSharpe(r.sharpe) * 0.2 +
    scorePf(r.profitFactor) * 0.15 +
    scoreWr(r.winRate) * 0.1
  );
}
