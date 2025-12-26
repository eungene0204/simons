import { StrategyDSL, Condition, ConditionGroup } from "@/types/strategy";

export type FusionMode = "logic_merge" | "signal_voting" | "portfolio_blending";
export type StrategyRole = "signal" | "filter" | "distribution";
export type ConflictResolution = "conservative" | "aggressive" | "neutral";

export interface StrategyWeight {
  strategyId: string;
  weight: number; // 0-100
  role: StrategyRole;
}

export interface FusionConfig {
  mode: FusionMode;
  weights: StrategyWeight[];
  conflictResolution: ConflictResolution;
  priorityStrategyId?: string; // For filter role
}

export interface FusionResult {
  combinedStrategy: StrategyDSL;
  conflicts: string[];
  contributions: Record<string, number>; // Strategy ID -> contribution percentage
  aiComment: string;
}

/**
 * Analyze strategy type based on conditions
 */
export function analyzeStrategyType(strategy: StrategyDSL): {
  type: "trend" | "momentum" | "factor" | "mean_reversion" | "mixed";
  confidence: number;
} {
  const entryIds = strategy.entry.conditions.map((c) => c.id);
  const exitIds = strategy.exit.conditions.map((c) => c.id);

  // Simple heuristic-based classification
  const trendIndicators = ["ma_crossover", "ema_crossover", "macd", "donchian_breakout"];
  const momentumIndicators = ["rsi", "momentum", "absolute_momentum"];
  const meanReversionIndicators = ["bollinger_bands", "rsi_mean_reversion"];

  let trendScore = 0;
  let momentumScore = 0;
  let meanReversionScore = 0;

  [...entryIds, ...exitIds].forEach((id) => {
    if (trendIndicators.some((ti) => id.includes(ti))) trendScore++;
    if (momentumIndicators.some((mi) => id.includes(mi))) momentumScore++;
    if (meanReversionIndicators.some((mri) => id.includes(mri))) meanReversionScore++;
  });

  const maxScore = Math.max(trendScore, momentumScore, meanReversionScore);
  if (maxScore === 0) return { type: "mixed", confidence: 0.5 };

  if (trendScore === maxScore) return { type: "trend", confidence: trendScore / (entryIds.length + exitIds.length) };
  if (momentumScore === maxScore) return { type: "momentum", confidence: momentumScore / (entryIds.length + exitIds.length) };
  if (meanReversionScore === maxScore) return { type: "mean_reversion", confidence: meanReversionScore / (entryIds.length + exitIds.length) };

  return { type: "mixed", confidence: 0.5 };
}

/**
 * Extract all blocks/rules from strategies
 */
export function extractStrategyBlocks(strategies: StrategyDSL[]): {
  entryConditions: Condition[];
  exitConditions: Condition[];
  riskSettings: Record<string, any>;
} {
  const entryConditions: Condition[] = [];
  const exitConditions: Condition[] = [];
  const riskSettings: Record<string, any> = {};

  strategies.forEach((strategy) => {
    entryConditions.push(...strategy.entry.conditions);
    exitConditions.push(...strategy.exit.conditions);
    Object.assign(riskSettings, strategy.risk);
  });

  return { entryConditions, exitConditions, riskSettings };
}

/**
 * Merge strategies using Logic Merge mode
 */
function mergeLogic(
  strategies: StrategyDSL[],
  config: FusionConfig
): { entry: ConditionGroup; exit: ConditionGroup; conflicts: string[] } {
  const { entryConditions, exitConditions } = extractStrategyBlocks(strategies);
  const conflicts: string[] = [];

  // Deduplicate conditions
  const uniqueEntryConditions: Condition[] = [];
  const seenEntry = new Set<string>();

  entryConditions.forEach((cond) => {
    const key = `${cond.type}-${cond.id}-${JSON.stringify(cond.params)}`;
    if (!seenEntry.has(key)) {
      seenEntry.add(key);
      uniqueEntryConditions.push(cond);
    } else {
      conflicts.push(`중복된 엔트리 조건: ${cond.id}`);
    }
  });

  const uniqueExitConditions: Condition[] = [];
  const seenExit = new Set<string>();

  exitConditions.forEach((cond) => {
    const key = `${cond.type}-${cond.id}-${JSON.stringify(cond.params)}`;
    if (!seenExit.has(key)) {
      seenExit.add(key);
      uniqueExitConditions.push(cond);
    } else {
      conflicts.push(`중복된 엑시트 조건: ${cond.id}`);
    }
  });

  // Apply conflict resolution
  let finalEntryConditions = uniqueEntryConditions;
  let finalExitConditions = uniqueExitConditions;

  if (config.conflictResolution === "conservative") {
    // Keep only conditions that appear in multiple strategies
    const entryCounts = new Map<string, number>();
    entryConditions.forEach((cond) => {
      const key = `${cond.type}-${cond.id}`;
      entryCounts.set(key, (entryCounts.get(key) || 0) + 1);
    });
    finalEntryConditions = uniqueEntryConditions.filter((cond) => {
      const key = `${cond.type}-${cond.id}`;
      return (entryCounts.get(key) || 0) > 1;
    });

    const exitCounts = new Map<string, number>();
    exitConditions.forEach((cond) => {
      const key = `${cond.type}-${cond.id}`;
      exitCounts.set(key, (exitCounts.get(key) || 0) + 1);
    });
    finalExitConditions = uniqueExitConditions.filter((cond) => {
      const key = `${cond.type}-${cond.id}`;
      return (exitCounts.get(key) || 0) > 1;
    });
  } else if (config.conflictResolution === "aggressive") {
    // Keep all conditions
    // Already done above
  }

  // Apply filter role if specified
  if (config.priorityStrategyId) {
    const priorityStrategy = strategies.find((s) => s.id === config.priorityStrategyId);
    if (priorityStrategy) {
      // Filter conditions based on priority strategy
      const priorityEntryIds = new Set(priorityStrategy.entry.conditions.map((c) => c.id));
      const priorityExitIds = new Set(priorityStrategy.exit.conditions.map((c) => c.id));

      finalEntryConditions = finalEntryConditions.filter((c) => priorityEntryIds.has(c.id));
      finalExitConditions = finalExitConditions.filter((c) => priorityExitIds.has(c.id));
    }
  }

  return {
    entry: {
      logic: "AND",
      conditions: finalEntryConditions,
    },
    exit: {
      logic: "OR",
      conditions: finalExitConditions,
    },
    conflicts,
  };
}

/**
 * Merge strategies using Signal Voting mode
 */
function mergeVoting(
  strategies: StrategyDSL[],
  config: FusionConfig
): { entry: ConditionGroup; exit: ConditionGroup; conflicts: string[] } {
  const conflicts: string[] = [];
  
  // For voting, we create weighted conditions
  // Each strategy's conditions get a weight based on config
  const weightedEntryConditions: Condition[] = [];
  const weightedExitConditions: Condition[] = [];

  strategies.forEach((strategy, idx) => {
    const weightConfig = config.weights.find((w) => w.strategyId === strategy.id);
    const weight = weightConfig?.weight || 50;

    strategy.entry.conditions.forEach((cond) => {
      weightedEntryConditions.push({
        ...cond,
        weight: (cond.weight || 1) * (weight / 100),
      });
    });

    strategy.exit.conditions.forEach((cond) => {
      weightedExitConditions.push({
        ...cond,
        weight: (cond.weight || 1) * (weight / 100),
      });
    });
  });

  return {
    entry: {
      logic: "WEIGHTED_SUM",
      conditions: weightedEntryConditions,
    },
    exit: {
      logic: "OR",
      conditions: weightedExitConditions,
    },
    conflicts,
  };
}

/**
 * Merge strategies using Portfolio Blending mode
 */
function mergeBlending(
  strategies: StrategyDSL[],
  config: FusionConfig
): { entry: ConditionGroup; exit: ConditionGroup; conflicts: string[] } {
  // Portfolio blending keeps all conditions but adjusts risk management
  const { entryConditions, exitConditions } = extractStrategyBlocks(strategies);
  const conflicts: string[] = [];

  // Average risk settings
  const avgRisk = {
    position_size_pct: 0,
    max_positions: 0,
    max_daily_loss_pct: 0,
    max_total_exposure_pct: 0,
  };

  let totalWeight = 0;
  strategies.forEach((strategy) => {
    const weightConfig = config.weights.find((w) => w.strategyId === strategy.id);
    const weight = weightConfig?.weight || 50;
    totalWeight += weight;

    avgRisk.position_size_pct += strategy.risk.position_size_pct * weight;
    avgRisk.max_positions += strategy.risk.max_positions * weight;
    if (strategy.risk.max_daily_loss_pct) {
      avgRisk.max_daily_loss_pct += strategy.risk.max_daily_loss_pct * weight;
    }
    if (strategy.risk.max_total_exposure_pct) {
      avgRisk.max_total_exposure_pct += strategy.risk.max_total_exposure_pct * weight;
    }
  });

  if (totalWeight > 0) {
    avgRisk.position_size_pct /= totalWeight;
    avgRisk.max_positions = Math.round(avgRisk.max_positions / totalWeight);
    avgRisk.max_daily_loss_pct /= totalWeight;
    avgRisk.max_total_exposure_pct /= totalWeight;
  }

  return {
    entry: {
      logic: "OR", // Portfolio blending uses OR to allow any strategy to trigger
      conditions: entryConditions,
    },
    exit: {
      logic: "OR",
      conditions: exitConditions,
    },
    conflicts,
  };
}

/**
 * Generate AI comment explaining the combination
 */
function generateAIComment(
  strategies: StrategyDSL[],
  config: FusionConfig,
  conflicts: string[]
): string {
  const types = strategies.map((s) => analyzeStrategyType(s));
  const typeCounts = types.reduce((acc, t) => {
    acc[t.type] = (acc[t.type] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const modeNames = {
    logic_merge: "룰 병합",
    signal_voting: "시그널 투표",
    portfolio_blending: "포트폴리오 혼합",
  };

  let comment = `${modeNames[config.mode]} 모드로 ${strategies.length}개 전략을 결합했습니다. `;

  if (typeCounts.trend) {
    comment += `추세 추종 전략 ${typeCounts.trend}개, `;
  }
  if (typeCounts.momentum) {
    comment += `모멘텀 전략 ${typeCounts.momentum}개, `;
  }
  if (typeCounts.mean_reversion) {
    comment += `평균회귀 전략 ${typeCounts.mean_reversion}개를 포함합니다. `;
  }

  if (config.priorityStrategyId) {
    const priority = strategies.find((s) => s.id === config.priorityStrategyId);
    if (priority) {
      comment += `필터 역할로 "${priority.name}" 전략이 적용되었습니다. `;
    }
  }

  if (conflicts.length > 0) {
    comment += `${conflicts.length}개의 충돌이 감지되었으며, ${config.conflictResolution === "conservative" ? "보수적" : config.conflictResolution === "aggressive" ? "공격적" : "중립"} 방식으로 해결했습니다.`;
  } else {
    comment += "충돌이 없어 모든 조건이 포함되었습니다.";
  }

  return comment;
}

/**
 * Main fusion function
 */
export function fuseStrategies(
  strategies: StrategyDSL[],
  config: FusionConfig
): FusionResult {
  if (strategies.length === 0) {
    throw new Error("최소 1개 이상의 전략이 필요합니다.");
  }

  if (strategies.length === 1) {
    return {
      combinedStrategy: strategies[0],
      conflicts: [],
      contributions: { [strategies[0].id]: 100 },
      aiComment: "단일 전략입니다.",
    };
  }

  let merged: { entry: ConditionGroup; exit: ConditionGroup; conflicts: string[] };

  switch (config.mode) {
    case "logic_merge":
      merged = mergeLogic(strategies, config);
      break;
    case "signal_voting":
      merged = mergeVoting(strategies, config);
      break;
    case "portfolio_blending":
      merged = mergeBlending(strategies, config);
      break;
    default:
      merged = mergeLogic(strategies, config);
  }

  // Calculate contributions
  const totalWeight = config.weights.reduce((sum, w) => sum + w.weight, 0);
  const contributions: Record<string, number> = {};
  config.weights.forEach((w) => {
    contributions[w.strategyId] = totalWeight > 0 ? (w.weight / totalWeight) * 100 : 0;
  });

  // Calculate average risk management
  const avgRisk = {
    position_size_pct: 0,
    max_positions: 0,
    max_daily_loss_pct: 0,
    max_total_exposure_pct: 0,
  };

  let riskTotalWeight = 0;
  strategies.forEach((strategy) => {
    const weightConfig = config.weights.find((w) => w.strategyId === strategy.id);
    const weight = weightConfig?.weight || 50;
    riskTotalWeight += weight;

    avgRisk.position_size_pct += strategy.risk.position_size_pct * weight;
    avgRisk.max_positions += strategy.risk.max_positions * weight;
    if (strategy.risk.max_daily_loss_pct) {
      avgRisk.max_daily_loss_pct += strategy.risk.max_daily_loss_pct * weight;
    }
    if (strategy.risk.max_total_exposure_pct) {
      avgRisk.max_total_exposure_pct += strategy.risk.max_total_exposure_pct * weight;
    }
  });

  if (riskTotalWeight > 0) {
    avgRisk.position_size_pct = Math.round(avgRisk.position_size_pct / riskTotalWeight);
    avgRisk.max_positions = Math.round(avgRisk.max_positions / riskTotalWeight);
    avgRisk.max_daily_loss_pct = Math.round((avgRisk.max_daily_loss_pct / riskTotalWeight) * 10) / 10;
    avgRisk.max_total_exposure_pct = Math.round((avgRisk.max_total_exposure_pct / riskTotalWeight) * 10) / 10;
  }

  const combinedStrategy: StrategyDSL = {
    id: `fused_${Date.now()}`,
    name: `조합 전략: ${strategies.map((s) => s.name).join(" + ")}`,
    description: `${strategies.length}개 전략을 ${config.mode === "logic_merge" ? "병합" : config.mode === "signal_voting" ? "투표" : "혼합"}한 전략`,
    version: "1.0.0",
    entry: merged.entry,
    exit: merged.exit,
    risk: avgRisk,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  const aiComment = generateAIComment(strategies, config, merged.conflicts);

  return {
    combinedStrategy,
    conflicts: merged.conflicts,
    contributions,
    aiComment,
  };
}

