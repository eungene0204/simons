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

export interface HistorySummary {
  strategyName?: string;
  universeName?: string;
  entryLogic: string;
  exitLogic: string;
  entryBlocks: string[];
  exitBlocks: string[];
  blockNames: string[];
  positionText?: string;
  riskText?: string;
}

// BacktestHistory.conditions(표시용 names 스키마)를 화면 배지용 요약으로 변환하는 단일 빌더.
// /backtest/[id]와 /api/strategy/[id]가 같은 경로·같은 로직으로 SOT를 공유하도록 통일한다.
// 레거시 평면 스키마(conditions가 string[] 또는 { logic, names })도 함께 처리한다.
export function buildHistorySummary(args: {
  conditions: unknown;
  universeName?: string | null;
  strategyName?: string | null;
}): HistorySummary {
  const conds = (args.conditions ?? {}) as Record<string, any>;
  const entry =
    conds.entry ??
    (Array.isArray(args.conditions)
      ? { logic: "AND", names: args.conditions }
      : { logic: conds.logic ?? "AND", names: conds.names ?? [] });
  const exit = conds.exit ?? { logic: "AND", names: [] };
  const entryBlocks: string[] = Array.isArray(entry.names) ? entry.names : [];
  const exitBlocks: string[] = Array.isArray(exit.names) ? exit.names : [];

  return {
    strategyName: args.strategyName ?? undefined,
    universeName: args.universeName ?? undefined,
    entryLogic: entry.logic ?? "AND",
    exitLogic: exit.logic ?? "AND",
    entryBlocks,
    exitBlocks,
    blockNames: [...entryBlocks, ...exitBlocks],
    positionText: conds.position,
    riskText: conds.risk,
  };
}

// 요약이 유니버스 외 실제 배지(진입/청산/포지션/리스크)를 담고 있는지.
// 표시용 names가 없는 행(예: save-with-backtest의 raw DSL conditions만 가진 행)은
// 빈 요약이 되므로 SOT로 채택하지 않고 다음 후보로 넘기기 위한 판정.
export function historySummaryHasContent(summary: HistorySummary): boolean {
  return (
    summary.entryBlocks.length > 0 ||
    summary.exitBlocks.length > 0 ||
    Boolean(summary.positionText) ||
    Boolean(summary.riskText)
  );
}

export function buildAutoSaveHistoryPayload(
  result: BacktestResult,
  strategySummary: BacktestStrategySummary,
  prompt?: string
) {
  return {
    // 저장된 전략이면 전략명, 아니면 사용자 프롬프트를 이름으로 사용한다.
    // (실행된 요청 기반 요약은 strategyName이 비어 있으므로 프롬프트가 폴백이다.)
    strategyName: strategySummary.strategyName || prompt?.trim() || "이름 없는 전략",
    prompt: prompt?.trim() || undefined,
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
