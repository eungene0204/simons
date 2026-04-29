import { mkdir, writeFile } from "fs/promises";
import path from "path";
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { createStrategyId } from "./hash";

type PromptCategory =
  | "technical_momentum"
  | "technical_mean_reversion"
  | "value_fundamental"
  | "hybrid_value_technical"
  | "breakout_volume"
  | "ai_hybrid"
  | "risk_management_variants"
  | "ambiguous_beginner_prompts";

type CandidateStatus =
  | "waiting"
  | "running"
  | "parsed"
  | "cache_hit"
  | "computed"
  | "failed"
  | "skipped";

type ErrorType =
  | "parse_error"
  | "conversion_error"
  | "backtest_error"
  | "data_error"
  | "timeout"
  | "zero_trade"
  | "invalid_strategy"
  | "unknown_error";

type PromptSeed = {
  id: string;
  text: string;
  category: PromptCategory;
  complexity: "beginner" | "intermediate" | "advanced";
  risk_profile: "conservative" | "moderate" | "aggressive";
  expected_blocks: string[];
  notes: string;
};

type CandidatePayload = PromptSeed & {
  prompt_id: string;
  prompt: string;
  risk_profile: "conservative" | "moderate" | "aggressive";
  expected_blocks: string[];
  parsed_strategy?: any;
  strategy_dsl?: any;
  strategy_id?: string | null;
  status: CandidateStatus;
  error_type?: ErrorType | null;
  error_message?: string | null;
  metrics?: Record<string, number> | null;
  quality_score?: number | null;
  extracted_blocks?: string[];
  extracted_parameters?: Record<string, any>;
  coach_learning_tags?: string[];
};

type ExperimentJob = {
  experimentId: string;
  origin: string;
  concurrency: number;
  timeoutMs: number;
  candidates: CandidatePayload[];
  canceled: boolean;
};

type ExecutionState = {
  queue: ExperimentJob[];
  activeJobs: Map<string, ExperimentJob>;
  canceledIds: Set<string>;
};

const DEFAULT_CATEGORY_COUNTS: Record<PromptCategory, number> = {
  technical_momentum: 45,
  technical_mean_reversion: 45,
  value_fundamental: 45,
  hybrid_value_technical: 60,
  breakout_volume: 35,
  ai_hybrid: 25,
  risk_management_variants: 30,
  ambiguous_beginner_prompts: 15,
};

const RESULT_FILE_PATH = "data/advisor-learning/strategy_prompt_experiment_result.json";
const SUMMARY_FILE_PATH = "data/advisor-learning/strategy_prompt_experiment_summary.json";
const DATASET_FILE_PATH = "data/advisor-learning/strategy_advisor_learning_dataset.jsonl";
const RULES_FILE_PATH = "data/advisor-learning/strategy_advisor_rules.json";
const PATTERNS_FILE_PATH = "data/advisor-learning/strategy_advisor_patterns.csv";
const ADVISOR_LEARNING_DIR = path.join(process.cwd(), "data", "advisor-learning");
const MAX_ACTIVE_EXPERIMENTS = 1;
const DEFAULT_CONCURRENCY = 2;
const MAX_CONCURRENCY = 4;
const DEFAULT_TIMEOUT_MS = 120_000;
function database() {
  return prisma as any;
}

function getExecutionState(): ExecutionState {
  const globalScope = globalThis as typeof globalThis & {
    __strategyPromptExperimentState?: ExecutionState;
  };

  if (!globalScope.__strategyPromptExperimentState) {
    globalScope.__strategyPromptExperimentState = {
      queue: [],
      activeJobs: new Map<string, ExperimentJob>(),
      canceledIds: new Set<string>(),
    };
  }

  return globalScope.__strategyPromptExperimentState;
}

function parseJsonField<T>(value: string | null | undefined, fallback: T): T {
  if (!value) return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function clampConcurrency(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return DEFAULT_CONCURRENCY;
  return Math.max(1, Math.min(MAX_CONCURRENCY, Math.floor(numeric)));
}

function makeRng(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function pick<T>(items: T[], index: number, rng: () => number) {
  return items[(index + Math.floor(rng() * items.length)) % items.length];
}

function toPromptId(index: number) {
  return `prompt_${String(index + 1).padStart(3, "0")}`;
}

function normalizeCategoryCounts(input: any): Record<PromptCategory, number> {
  const counts = { ...DEFAULT_CATEGORY_COUNTS };
  for (const key of Object.keys(counts) as PromptCategory[]) {
    const value = Number(input?.[key]);
    if (Number.isFinite(value) && value >= 0) {
      counts[key] = Math.floor(value);
    }
  }
  return counts;
}

function categoryBlocks(category: PromptCategory, index: number) {
  const blocks: Record<PromptCategory, string[][]> = {
    technical_momentum: [
      ["ma_crossover", "adx", "stop_loss"],
      ["macd", "rsi", "take_profit"],
      ["ema", "volume_spike", "trailing_stop"],
      ["breakout_52w", "adx", "max_holding_days"],
    ],
    technical_mean_reversion: [
      ["rsi", "bollinger_band", "take_profit"],
      ["stochastic", "cci", "stop_loss"],
      ["bollinger_band", "rsi", "max_holding_days"],
      ["rsi"],
    ],
    value_fundamental: [
      ["per", "pbr", "roe", "max_positions"],
      ["debt_ratio", "market_cap", "dividend_yield"],
      ["revenue_growth", "operating_margin", "trading_value"],
      ["pbr", "per"],
    ],
    hybrid_value_technical: [
      ["rsi", "pbr", "stop_loss", "take_profit"],
      ["per", "roe", "ma_crossover", "max_holding_days"],
      ["pbr", "rsi", "volume_spike", "trailing_stop"],
      ["debt_ratio", "macd", "take_profit"],
    ],
    breakout_volume: [
      ["breakout_52w", "volume_spike", "trailing_stop"],
      ["breakout", "adx", "stop_loss"],
      ["volume_spike", "ema", "take_profit"],
      ["breakout_52w", "max_holding_days"],
    ],
    ai_hybrid: [
      ["ai_prediction", "rsi", "stop_loss"],
      ["ai_prediction", "pbr", "roe", "max_positions"],
      ["ai_prediction", "macd", "volume_spike"],
      ["ai_prediction", "per", "take_profit"],
    ],
    risk_management_variants: [
      ["rsi", "stop_loss", "take_profit", "max_holding_days"],
      ["ma_crossover", "trailing_stop", "max_positions"],
      ["pbr", "stop_loss", "max_positions"],
      ["breakout_52w", "take_profit", "trailing_stop"],
    ],
    ambiguous_beginner_prompts: [
      ["rsi", "take_profit"],
      ["pbr", "stop_loss"],
      ["volume_spike", "max_holding_days"],
      ["ma_crossover"],
    ],
  };
  return blocks[category][index % blocks[category].length];
}

function buildPromptText(category: PromptCategory, index: number, rng: () => number) {
  const universes = ["KOSPI200", "KOSPI", "KOSDAQ"];
  const universe = pick(universes, index, rng);
  const rsi = pick([20, 25, 30, 35], index, rng);
  const stop = pick([3, 5, 8, 10, 15], index, rng);
  const profit = pick([5, 10, 15, 20, 30], index, rng);
  const trailing = pick([5, 8, 10, 15], index, rng);
  const holding = pick([5, 10, 20, 60, 120], index, rng);
  const positions = pick([3, 5, 10, 20], index, rng);
  const ma = pick([[5, 20], [10, 20], [20, 60], [50, 120]], index, rng);
  const pbr = pick([0.7, 0.8, 1.0, 1.2], index, rng);
  const per = pick([8, 10, 12, 15], index, rng);
  const roe = pick([8, 10, 12, 15], index, rng);
  const tradingValue = pick([10, 20, 30, 50], index, rng);

  switch (category) {
    case "technical_momentum":
      return `${universe}에서 ${ma[0]}일 이동평균이 ${ma[1]}일 이동평균을 상향 돌파하고 ADX가 25 이상이면 매수, 손절 ${stop}%와 최대 보유기간 ${holding}일을 적용해줘.`;
    case "technical_mean_reversion":
      return `${universe} 종목 중 RSI가 ${rsi} 이하이고 볼린저밴드 하단 근처까지 내려온 종목을 매수하고 ${profit}% 수익 또는 ${holding}일 보유 후 매도해줘.`;
    case "value_fundamental":
      return `${universe}에서 PER ${per} 이하, PBR ${pbr} 이하, ROE ${roe}% 이상이고 일평균 거래대금 ${tradingValue}억 이상인 종목을 최대 ${positions}개만 보유해줘.`;
    case "hybrid_value_technical":
      return `${universe}에서 PBR ${pbr} 이하인 저평가 종목 중 RSI가 ${rsi} 이하에서 반등하면 매수하고 손절 ${stop}%, 익절 ${profit}%를 적용해줘.`;
    case "breakout_volume":
      return `${universe}에서 52주 신고가를 돌파하고 거래량이 20일 평균의 2배 이상인 종목을 매수, 트레일링 스탑 ${trailing}%와 최대 보유 ${holding}일로 관리해줘.`;
    case "ai_hybrid":
      return `AI 상승 예측 점수가 높은 ${universe} 종목 중 MACD 골든크로스와 일평균 거래대금 ${tradingValue}억 이상 조건을 만족하면 매수하고 손절 ${stop}%를 넣어줘.`;
    case "risk_management_variants":
      return `${universe}에서 RSI ${rsi} 이하 조건으로 진입하되 손절 ${stop}%, 익절 ${profit}%, 트레일링 스탑 ${trailing}%, 최대 보유 종목 ${positions}개로 리스크를 제한해줘.`;
    case "ambiguous_beginner_prompts":
      return `${universe}에서 너무 비싸지 않고 최근 힘이 좋아지는 종목을 찾되 RSI ${rsi} 이하나 거래량 증가 같은 조건은 넣고, 손실은 ${stop}% 정도에서 제한해줘.`;
    default:
      return `${universe}에서 RSI ${rsi} 이하 조건을 테스트해줘.`;
  }
}

function promptMeta(category: PromptCategory, index: number) {
  const complexity = category === "ambiguous_beginner_prompts"
    ? "beginner"
    : index % 3 === 0
      ? "advanced"
      : "intermediate";
  const risk_profile = index % 5 === 0 ? "aggressive" : index % 2 === 0 ? "moderate" : "conservative";
  const notes: Record<PromptCategory, string> = {
    technical_momentum: "momentum and trend validation",
    technical_mean_reversion: "mean reversion validation",
    value_fundamental: "fundamental factor validation",
    hybrid_value_technical: "value filter with technical entry",
    breakout_volume: "breakout and liquidity validation",
    ai_hybrid: "AI signal with filter validation",
    risk_management_variants: "risk setting sensitivity",
    ambiguous_beginner_prompts: "beginner expression parser coverage",
  };

  return {
    complexity: complexity as PromptSeed["complexity"],
    risk_profile: risk_profile as PromptSeed["risk_profile"],
    notes: notes[category],
  };
}

function generatePromptDataset(config: { seed?: number; categoryCounts?: Partial<Record<PromptCategory, number>> } = {}) {
  const rng = makeRng(Number(config.seed ?? 42));
  const counts = normalizeCategoryCounts(config.categoryCounts);
  const prompts: PromptSeed[] = [];
  const seen = new Set<string>();

  for (const category of Object.keys(counts) as PromptCategory[]) {
    for (let index = 0; index < counts[category]; index += 1) {
      let text = buildPromptText(category, index + prompts.length, rng);
      if (seen.has(text)) {
        text = `${text} 검증 기간은 최근 3년으로 해줘.`;
      }
      seen.add(text);
      const meta = promptMeta(category, index);
      prompts.push({
        id: toPromptId(prompts.length),
        text,
        category,
        complexity: meta.complexity,
        risk_profile: meta.risk_profile,
        expected_blocks: categoryBlocks(category, index),
        notes: meta.notes,
      });
    }
  }

  return prompts;
}

function numberValue(value: unknown, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function normalizeMetrics(raw: any): Record<string, number> {
  const totalReturn = numberValue(raw?.total_return ?? raw?.totalReturn ?? raw?.return);
  const maxDrawdown = numberValue(raw?.max_drawdown ?? raw?.maxDrawdown);
  const buyAndHoldReturn = numberValue(raw?.buy_and_hold_return ?? raw?.buyAndHoldReturn);
  return {
    cagr: numberValue(raw?.cagr),
    total_return: totalReturn,
    sharpe: numberValue(raw?.sharpe ?? raw?.sharpe_ratio),
    sortino: numberValue(raw?.sortino ?? raw?.sortino_ratio),
    max_drawdown: maxDrawdown,
    profit_factor: numberValue(raw?.profit_factor ?? raw?.profitFactor),
    win_rate: numberValue(raw?.win_rate ?? raw?.winRate),
    trades: numberValue(raw?.trades),
    volatility: numberValue(raw?.volatility),
    calmar: numberValue(raw?.calmar ?? raw?.calmar_ratio),
    buy_and_hold_return: buyAndHoldReturn,
    excess_return: numberValue(raw?.excess_return ?? totalReturn - buyAndHoldReturn),
  };
}

function clamp01(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function calculateQualityScore(metrics: Record<string, number>) {
  const trades = numberValue(metrics.trades);
  const normalizedCagr = clamp01((numberValue(metrics.cagr) + 20) / 60);
  const normalizedSharpe = clamp01((numberValue(metrics.sharpe) + 1) / 4);
  const normalizedProfitFactor = clamp01(numberValue(metrics.profit_factor) / 3);
  const normalizedWinRate = clamp01(numberValue(metrics.win_rate) / 100);
  const normalizedMdd = clamp01(Math.abs(numberValue(metrics.max_drawdown)) / 50);
  const tradeCountHealth = trades < 10 ? 0.1 : trades < 30 ? 0.45 : trades < 100 ? 0.8 : 1;
  const consistencyScore = normalizedSharpe * 0.6 + clamp01(numberValue(metrics.calmar) / 3) * 0.4;
  return Number(
    (
      normalizedCagr * 0.2 +
      normalizedSharpe * 0.2 +
      normalizedProfitFactor * 0.15 +
      normalizedWinRate * 0.1 -
      normalizedMdd * 0.2 +
      tradeCountHealth * 0.1 +
      consistencyScore * 0.05
    ).toFixed(4)
  );
}

function extractParameters(strategyDsl: any, prompt: string) {
  const source = `${JSON.stringify(strategyDsl ?? {})} ${prompt}`;
  const grab = (pattern: RegExp) => {
    const match = source.match(pattern);
    return match ? Number(match[1]) : undefined;
  };
  const params: Record<string, any> = {};
  const values: Array<[string, number | undefined]> = [
    ["rsi_threshold", grab(/RSI[^0-9]*(\d+)/i)],
    ["take_profit_pct", grab(/(?:익절|수익)[^0-9]*(\d+)/)],
    ["stop_loss_pct", grab(/(?:손절|손실)[^0-9]*(\d+)/)],
    ["trailing_stop_pct", grab(/트레일링[^0-9]*(\d+)/)],
    ["max_holding_days", grab(/(?:보유|기간)[^0-9]*(\d+)일/)],
    ["max_positions", grab(/(?:종목|보유 종목)[^0-9]*(\d+)개/)],
  ];
  for (const [key, value] of values) {
    if (value !== undefined && Number.isFinite(value)) params[key] = value;
  }
  return params;
}

function extractBlocks(strategyDsl: any, expectedBlocks: string[]) {
  const source = JSON.stringify(strategyDsl ?? {}).toLowerCase();
  const found = expectedBlocks.filter((block) => source.includes(block.toLowerCase()));
  return Array.from(new Set([...found, ...expectedBlocks]));
}

function median(values: number[]) {
  const filtered = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (filtered.length === 0) return 0;
  const middle = Math.floor(filtered.length / 2);
  return filtered.length % 2 ? filtered[middle] : (filtered[middle - 1] + filtered[middle]) / 2;
}

function confidence(sampleCount: number, medianTrades: number, failureRate = 0) {
  if (sampleCount >= 20 && medianTrades >= 30 && failureRate <= 0.2) return "high";
  if (sampleCount >= 10 && medianTrades >= 20 && failureRate <= 0.4) return "medium";
  return "low";
}

function aggregateRows(rows: CandidatePayload[]) {
  const successes = rows.filter((row) => row.metrics);
  const failureRate = rows.length ? (rows.length - successes.length) / rows.length : 0;
  const medianTrades = median(successes.map((row) => numberValue(row.metrics?.trades)));
  return {
    count: rows.length,
    success_count: successes.length,
    failure_count: rows.length - successes.length,
    median_cagr: median(successes.map((row) => numberValue(row.metrics?.cagr))),
    mean_cagr: successes.length
      ? successes.reduce((sum, row) => sum + numberValue(row.metrics?.cagr), 0) / successes.length
      : 0,
    median_sharpe: median(successes.map((row) => numberValue(row.metrics?.sharpe))),
    median_mdd: median(successes.map((row) => numberValue(row.metrics?.max_drawdown))),
    median_profit_factor: median(successes.map((row) => numberValue(row.metrics?.profit_factor))),
    median_trades: medianTrades,
    median_quality_score: median(successes.map((row) => numberValue(row.quality_score))),
    confidence: confidence(rows.length, medianTrades, failureRate),
  };
}

function analyzeExperimentCandidates(candidates: CandidatePayload[]) {
  const byBlock = new Map<string, CandidatePayload[]>();
  const byCombination = new Map<string, CandidatePayload[]>();
  const failures = new Map<string, CandidatePayload[]>();

  for (const candidate of candidates) {
    for (const block of candidate.extracted_blocks ?? candidate.expected_blocks ?? []) {
      byBlock.set(block, [...(byBlock.get(block) ?? []), candidate]);
    }
    const combination = [...(candidate.extracted_blocks ?? candidate.expected_blocks ?? [])].sort().join("+");
    byCombination.set(combination, [...(byCombination.get(combination) ?? []), candidate]);
    if (candidate.error_type) {
      failures.set(candidate.error_type, [...(failures.get(candidate.error_type) ?? []), candidate]);
    }
  }

  const blockStats = Object.fromEntries(
    Array.from(byBlock.entries()).map(([block, rows]) => [block, aggregateRows(rows)])
  );
  const combinationStats = Object.fromEntries(
    Array.from(byCombination.entries()).map(([combination, rows]) => {
      const stats = aggregateRows(rows);
      const sorted = rows
        .filter((row: CandidatePayload) => row.metrics)
        .sort((a: CandidatePayload, b: CandidatePayload) => numberValue(b.quality_score) - numberValue(a.quality_score));
      return [
        combination,
        {
          combination_count: rows.length,
          ...stats,
          best_strategy_id: sorted[0]?.strategy_id ?? null,
          worst_strategy_id: sorted[sorted.length - 1]?.strategy_id ?? null,
          recommended_guidance: `${combination} 조합은 백테스트 기반 경향으로만 검증하고 리스크 설정을 함께 확인하세요.`,
          warnings: stats.confidence === "low" ? ["실험 샘플 또는 거래 횟수가 부족합니다."] : [],
        },
      ];
    })
  );
  const parserFailurePatterns = Object.fromEntries(
    Array.from(failures.entries()).map(([errorType, rows]) => [
      errorType,
      {
        count: rows.length,
        sample_prompts: rows.slice(0, 3).map((row: CandidatePayload) => row.prompt),
        likely_cause: errorType === "parse_error" ? "자연어 조건이 파서가 지원하는 블록으로 충분히 매핑되지 않았습니다." : "실행 단계에서 후보가 실패했습니다.",
        parser_improvement_suggestion: "자주 실패한 표현을 rule-first parser 예제로 추가하세요.",
      },
    ])
  );

  const weakPatterns = [
    {
      pattern: "missing_exit_rule",
      condition: "exit_signals empty and no stop_loss/take_profit/max_holding_days",
      coach_message: "청산 조건이 없어 MDD가 커질 가능성이 있습니다. 손절, 익절, 최대 보유기간 중 하나를 추가하는 것이 좋습니다.",
      suggestion_buttons: ["손절 8% 추가", "익절 15% 추가", "최대 보유기간 20일 추가"],
    },
  ];

  return {
    best_overall_patterns: Object.entries(combinationStats)
      .sort(([, left]: any, [, right]: any) => numberValue(right.median_quality_score) - numberValue(left.median_quality_score))
      .slice(0, 10),
    best_single_indicators: blockStats,
    best_indicator_combinations: combinationStats,
    best_parameter_ranges: {},
    weak_patterns: weakPatterns,
    high_risk_patterns: candidates
      .filter((row) => numberValue(row.metrics?.max_drawdown) <= -40)
      .slice(0, 10)
      .map((row) => ({ prompt_id: row.prompt_id, strategy_id: row.strategy_id, max_drawdown: row.metrics?.max_drawdown })),
    low_confidence_patterns: candidates
      .filter((row) => numberValue(row.metrics?.trades) < 30)
      .slice(0, 10)
      .map((row) => ({ prompt_id: row.prompt_id, strategy_id: row.strategy_id, trades: row.metrics?.trades })),
    parser_failure_patterns: parserFailurePatterns,
  };
}

function buildLearningArtifacts(experiment: any, candidates: CandidatePayload[]) {
  const summary = analyzeExperimentCandidates(candidates);
  const completed = candidates.filter((row) => row.status === "computed" || row.status === "cache_hit");
  const resultPayload = {
    experiment_id: experiment.id,
    created_at: experiment.createdAt?.toISOString?.() ?? new Date().toISOString(),
    total_prompts: candidates.length,
    completed_count: completed.length,
    cache_hit_count: candidates.filter((row) => row.status === "cache_hit").length,
    failed_count: candidates.filter((row) => row.status === "failed").length,
    skipped_count: candidates.filter((row) => row.status === "skipped").length,
    candidates,
  };
  const summaryPayload = {
    experiment_id: experiment.id,
    summary,
    advisor_guidance: {
      recommended_default_rules: ["전략 검증 조언에는 유사 실험 수, median Sharpe, median MDD를 함께 포함합니다."],
      risk_warning_rules: ["MDD가 -25%보다 낮거나 거래 횟수가 30회 미만이면 리스크 관리 또는 신뢰도 경고를 우선합니다."],
      parameter_suggestion_rules: ["손절, 익절, 최대 보유기간은 동일 블록 조합 내 중앙값 품질 점수로 비교합니다."],
      prompt_clarification_rules: ["파싱 실패 표현은 매수 조건, 청산 조건, 유니버스를 분리해 되묻습니다."],
    },
  };
  const datasetLines = candidates.map((row) =>
    JSON.stringify({
      input: {
        user_prompt: row.prompt,
        parsed_blocks: row.extracted_blocks ?? row.expected_blocks,
        risk_profile: row.risk_profile,
        category: row.category,
        extracted_parameters: row.extracted_parameters ?? {},
      },
      output: {
        analysis: row.metrics
          ? "유사 실험 근거를 기반으로 전략 검증과 리스크 관리 관점에서 평가합니다."
          : "실패 후보는 파서 개선과 조건 명확화 근거로 사용합니다.",
        evidence: {
          similar_strategy_count: completed.length,
          median_cagr: median(completed.map((item) => numberValue(item.metrics?.cagr))),
          median_sharpe: median(completed.map((item) => numberValue(item.metrics?.sharpe))),
          median_mdd: median(completed.map((item) => numberValue(item.metrics?.max_drawdown))),
          confidence: confidence(completed.length, median(completed.map((item) => numberValue(item.metrics?.trades)))),
        },
        recommended_advice: row.metrics
          ? "백테스트 기반 경향으로만 해석하고 손절, 익절, 최대 보유기간의 유무를 함께 검증하세요."
          : "비슷한 실험 데이터가 부족하거나 실행이 실패했으므로 조건을 더 명확히 해야 합니다.",
        suggested_actions: row.metrics ? ["MDD 확인", "거래 횟수 확인", "청산 조건 비교"] : ["조건 명확화", "지원 지표로 재작성"],
      },
    })
  );
  const rules = {
    rules: [
      {
        id: "rule_missing_exit_rule",
        condition: "missing stop_loss_pct, take_profit_pct, trailing_stop_pct, and max_holding_days",
        evidence: { source: SUMMARY_FILE_PATH, confidence: "medium" },
        advice: "청산 조건이 부족하면 실험 근거와 함께 MDD 확대 가능성을 먼저 설명합니다.",
        suggested_actions: ["손절 8% 추가", "익절 15% 추가", "최대 보유기간 20일 추가"],
        confidence: "medium",
      },
    ],
  };
  const csvHeader = "pattern_key,pattern_type,blocks,parameter_range,sample_count,median_cagr,median_sharpe,median_mdd,median_profit_factor,median_trades,quality_score,confidence,coach_guidance";
  const csvRows = Object.entries(summary.best_single_indicators).map(([block, stats]: any) =>
    [
      block,
      "single_indicator",
      block,
      "",
      stats.count,
      stats.median_cagr,
      stats.median_sharpe,
      stats.median_mdd,
      stats.median_profit_factor,
      stats.median_trades,
      stats.median_quality_score,
      stats.confidence,
      "전략 검증 근거로만 사용하고 리스크 설정을 함께 확인하세요.",
    ].join(",")
  );

  return {
    resultJson: JSON.stringify(resultPayload, null, 2),
    summaryJson: JSON.stringify(summaryPayload, null, 2),
    datasetJsonl: datasetLines.join("\n"),
    rulesJson: JSON.stringify(rules, null, 2),
    patternsCsv: [csvHeader, ...csvRows].join("\n"),
    summary: summaryPayload,
  };
}

async function writeLearningFiles(artifacts: ReturnType<typeof buildLearningArtifacts>) {
  if (process.env.NODE_ENV === "test") return;

  await mkdir(ADVISOR_LEARNING_DIR, { recursive: true });
  await Promise.all([
    writeFile(path.join(process.cwd(), RESULT_FILE_PATH), artifacts.resultJson, "utf8"),
    writeFile(path.join(process.cwd(), SUMMARY_FILE_PATH), artifacts.summaryJson, "utf8"),
    writeFile(path.join(process.cwd(), DATASET_FILE_PATH), artifacts.datasetJsonl, "utf8"),
    writeFile(path.join(process.cwd(), RULES_FILE_PATH), artifacts.rulesJson, "utf8"),
    writeFile(path.join(process.cwd(), PATTERNS_FILE_PATH), artifacts.patternsCsv, "utf8"),
  ]);
}

function candidateFromRow(row: any): CandidatePayload {
  return {
    id: row.promptId,
    prompt_id: row.promptId,
    text: row.prompt,
    prompt: row.prompt,
    category: row.category,
    complexity: row.complexity,
    risk_profile: row.riskProfile,
    expected_blocks: parseJsonField(row.expectedBlocks, []),
    notes: "",
    parsed_strategy: parseJsonField(row.parsedStrategy, null),
    strategy_dsl: parseJsonField(row.strategyDsl, null),
    strategy_id: row.strategyId,
    status: row.status,
    error_type: row.errorType,
    error_message: row.errorMessage,
    metrics: parseJsonField(row.metrics, null),
    quality_score: row.qualityScore,
    extracted_blocks: parseJsonField(row.extractedBlocks, []),
    extracted_parameters: parseJsonField(row.extractedParameters, {}),
    coach_learning_tags: parseJsonField(row.coachLearningTags, []),
  };
}

function classifyError(error: any, fallback: ErrorType): ErrorType {
  const message = String(error?.message ?? "");
  if (message.includes("timeout")) return "timeout";
  if (message.includes("data") || message.includes("데이터")) return "data_error";
  if (message.includes("trade") || message.includes("거래")) return "zero_trade";
  return fallback;
}

async function fetchJsonFromApp(origin: string, path: string, body: Record<string, any>, timeoutMs: number) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${origin}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload?.detail ?? payload?.error ?? "요청 처리에 실패했습니다.");
    }
    return payload;
  } catch (error: any) {
    if (error?.name === "AbortError") throw new Error("timeout");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function runBacktestViaApp(origin: string, body: Record<string, any>, timeoutMs: number) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${origin}/api/strategy/backtest-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload?.detail ?? payload?.error ?? "백테스트 실행에 실패했습니다.");
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("백테스트 스트림을 읽을 수 없습니다.");

    const decoder = new TextDecoder();
    let buffer = "";
    let result: any = null;
    let sawCacheHit = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (!payload || payload === "[DONE]") continue;
        const event = JSON.parse(payload);
        if (event.type === "status" && String(event.message ?? "").includes("캐시")) sawCacheHit = true;
        if (event.type === "result" && event.data) {
          result = event.data;
          sawCacheHit = sawCacheHit || !!event.data.fromCache;
        }
        if (event.type === "error") throw new Error(event.message ?? "백테스트 실행 중 오류가 발생했습니다.");
      }
    }

    if (!result) throw new Error("백테스트 결과를 받지 못했습니다.");
    return { result, status: (sawCacheHit ? "cache_hit" : "computed") as CandidateStatus };
  } catch (error: any) {
    if (error?.name === "AbortError") throw new Error("timeout");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function loadCachedMetrics(strategyId: string) {
  const db = database();
  const result = await db.backtestResult.findFirst({
    where: { strategyId },
    orderBy: { createdAt: "desc" },
  });
  if (result) return normalizeMetrics(parseJsonField(result.summary, {}));

  const history = await db.backtestHistory.findFirst({
    where: { OR: [{ strategyId }, { cacheKey: strategyId }] },
    orderBy: { createdAt: "desc" },
  });
  if (!history) return null;

  return normalizeMetrics(parseJsonField(history.metrics, parseJsonField(history.result, {})));
}

async function saveCandidate(experimentId: string, candidate: CandidatePayload) {
  await database().strategyPromptExperimentCandidate.update({
    where: {
      experimentId_promptId: {
        experimentId,
        promptId: candidate.prompt_id,
      },
    },
    data: {
      parsedStrategy: candidate.parsed_strategy ? JSON.stringify(candidate.parsed_strategy) : null,
      strategyDsl: candidate.strategy_dsl ? JSON.stringify(candidate.strategy_dsl) : null,
      strategyId: candidate.strategy_id ?? null,
      status: candidate.status,
      errorType: candidate.error_type ?? null,
      errorMessage: candidate.error_message ?? null,
      metrics: candidate.metrics ? JSON.stringify(candidate.metrics) : null,
      qualityScore: candidate.quality_score ?? null,
      extractedBlocks: JSON.stringify(candidate.extracted_blocks ?? []),
      extractedParameters: JSON.stringify(candidate.extracted_parameters ?? {}),
      coachLearningTags: JSON.stringify(candidate.coach_learning_tags ?? []),
      updatedAt: new Date(),
    },
  });
}

async function updateExperimentCounts(experimentId: string) {
  const rows = await database().strategyPromptExperimentCandidate.findMany({
    where: { experimentId },
  });
  const completedCount = rows.filter((row: any) => row.status === "computed" || row.status === "cache_hit").length;
  const failedCount = rows.filter((row: any) => row.status === "failed").length;
  const skippedCount = rows.filter((row: any) => row.status === "skipped").length;
  const runningCount = rows.filter((row: any) => row.status === "running" || row.status === "parsed").length;
  const status = completedCount + failedCount + skippedCount >= rows.length
    ? "completed"
    : runningCount > 0
      ? "running"
      : "queued";

  await database().strategyPromptExperiment.update({
    where: { id: experimentId },
    data: {
      status,
      summary: status === "completed"
        ? JSON.stringify(analyzeExperimentCandidates(rows.map(candidateFromRow)))
        : undefined,
      updatedAt: new Date(),
    },
  });
}

async function finalizeExperiment(experimentId: string) {
  const db = database();
  const experiment = await db.strategyPromptExperiment.findUnique({
    where: { id: experimentId },
    include: { candidates: { orderBy: { createdAt: "asc" } } },
  });
  if (!experiment) return;

  const candidates = experiment.candidates.map(candidateFromRow);
  const artifacts = buildLearningArtifacts(experiment, candidates);
  await writeLearningFiles(artifacts);
  await db.strategyPromptExperiment.update({
    where: { id: experimentId },
    data: {
      status: "completed",
      summary: JSON.stringify(artifacts.summary),
      resultFilePath: RESULT_FILE_PATH,
      summaryFilePath: SUMMARY_FILE_PATH,
      datasetFilePath: DATASET_FILE_PATH,
      rulesFilePath: RULES_FILE_PATH,
      patternsFilePath: PATTERNS_FILE_PATH,
      updatedAt: new Date(),
    },
  });

  await db.strategyAdvisorLearningInsight.deleteMany({ where: { experimentId } });
  const insights = Object.entries(artifacts.summary.summary.best_single_indicators).slice(0, 25).map(([key, payload]: any) => ({
    experimentId,
    insightType: "single_indicator",
    key,
    payload: JSON.stringify(payload),
    confidence: payload.confidence ?? "low",
  }));
  if (insights.length > 0) {
    await db.strategyAdvisorLearningInsight.createMany({ data: insights });
  }
}

async function executeCandidate(job: ExperimentJob, candidate: CandidatePayload) {
  candidate.status = "running";
  await saveCandidate(job.experimentId, candidate);
  await updateExperimentCounts(job.experimentId);

  try {
    const parsedPayload = await fetchJsonFromApp(job.origin, "/api/strategy/parse", {
      prompt: candidate.prompt,
      backend: "mlx",
    }, job.timeoutMs);
    const strategyDsl = parsedPayload?.backtest_request;
    if (!strategyDsl) throw new Error(parsedPayload?.clarification_question ?? "백테스트 가능한 Strategy DSL을 만들지 못했습니다.");

    candidate.parsed_strategy = parsedPayload?.parsed ?? null;
    candidate.strategy_dsl = strategyDsl;
    candidate.strategy_id = createStrategyId(strategyDsl);
    candidate.extracted_blocks = extractBlocks(strategyDsl, candidate.expected_blocks);
    candidate.extracted_parameters = extractParameters(strategyDsl, candidate.prompt);
    candidate.status = "parsed";
    await saveCandidate(job.experimentId, candidate);

    const cached = await loadCachedMetrics(candidate.strategy_id);
    if (cached) {
      candidate.metrics = cached;
      candidate.quality_score = calculateQualityScore(cached);
      candidate.status = "cache_hit";
      candidate.coach_learning_tags = ["cache_hit", "strategy_validation"];
      await saveCandidate(job.experimentId, candidate);
      return;
    }

    const backtestPayload = await runBacktestViaApp(job.origin, {
      ...strategyDsl,
      strategy_id: candidate.strategy_id,
    }, job.timeoutMs);
    const metrics = normalizeMetrics(backtestPayload.result);
    if (numberValue(metrics.trades) <= 0) throw new Error("zero_trade");

    candidate.metrics = metrics;
    candidate.quality_score = calculateQualityScore(metrics);
    candidate.status = backtestPayload.status;
    candidate.coach_learning_tags = ["strategy_validation", "risk_management", candidate.category];
    await saveCandidate(job.experimentId, candidate);
  } catch (error: any) {
    const message = error?.message ?? "실행 실패";
    candidate.status = "failed";
    candidate.error_type = classifyError(error, candidate.parsed_strategy ? "backtest_error" : "parse_error");
    candidate.error_message = message;
    await saveCandidate(job.experimentId, candidate);
  } finally {
    await updateExperimentCounts(job.experimentId);
  }
}

async function executeExperiment(job: ExperimentJob) {
  let cursor = 0;
  const worker = async () => {
    while (cursor < job.candidates.length) {
      const index = cursor;
      cursor += 1;
      if (job.canceled || getExecutionState().canceledIds.has(job.experimentId)) {
        const candidate = job.candidates[index];
        candidate.status = "skipped";
        candidate.error_message = "사용자 요청으로 스킵됨";
        await saveCandidate(job.experimentId, candidate);
        continue;
      }
      await executeCandidate(job, job.candidates[index]);
    }
  };

  await Promise.all(Array.from({ length: Math.min(job.concurrency, job.candidates.length) }, () => worker()));
  await updateExperimentCounts(job.experimentId);
  if (!getExecutionState().canceledIds.has(job.experimentId)) {
    await finalizeExperiment(job.experimentId);
  } else {
    await database().strategyPromptExperiment.update({
      where: { id: job.experimentId },
      data: { status: "canceled", updatedAt: new Date() },
    });
  }
  getExecutionState().canceledIds.delete(job.experimentId);
}

function pumpQueue() {
  const state = getExecutionState();
  while (state.activeJobs.size < MAX_ACTIVE_EXPERIMENTS && state.queue.length > 0) {
    const job = state.queue.shift();
    if (!job) break;
    state.activeJobs.set(job.experimentId, job);
    void executeExperiment(job)
      .catch((error) => console.error("Failed to execute prompt experiment:", error))
      .finally(() => {
        state.activeJobs.delete(job.experimentId);
        pumpQueue();
      });
  }
}

function formatExperiment(row: any) {
  const candidates = (row.candidates ?? row.Candidate ?? []).map(candidateFromRow);
  const completedCount = candidates.filter((candidate: CandidatePayload) => candidate.status === "computed" || candidate.status === "cache_hit").length;
  const failedCount = candidates.filter((candidate: CandidatePayload) => candidate.status === "failed").length;
  const skippedCount = candidates.filter((candidate: CandidatePayload) => candidate.status === "skipped").length;
  return {
    id: row.id,
    name: row.name,
    seed: row.seed,
    totalPrompts: row.totalPrompts,
    status: row.status,
    config: parseJsonField(row.config, {}),
    summary: parseJsonField(row.summary, null),
    resultFilePath: row.resultFilePath,
    summaryFilePath: row.summaryFilePath,
    datasetFilePath: row.datasetFilePath,
    rulesFilePath: row.rulesFilePath,
    patternsFilePath: row.patternsFilePath,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
    completedCount,
    cacheHitCount: candidates.filter((candidate: CandidatePayload) => candidate.status === "cache_hit").length,
    failedCount,
    skippedCount,
    candidates,
  };
}

async function loadExperiment(id: string) {
  return database().strategyPromptExperiment.findUnique({
    where: { id },
    include: { candidates: { orderBy: { createdAt: "asc" } } },
  });
}

function buildExperimentId(seed: number) {
  return `prompt_exp_${Date.now()}_${seed}_${Math.random().toString(36).slice(2, 8)}`;
}

async function enqueueStoredExperiment(experimentId: string, origin: string) {
  const state = getExecutionState();
  if (state.activeJobs.has(experimentId) || state.queue.some((job) => job.experimentId === experimentId)) {
    return { queued: false, reason: "already_queued" };
  }

  const experiment = await loadExperiment(experimentId);
  if (!experiment) {
    return { queued: false, reason: "not_found" };
  }

  const storedCandidates = (experiment.candidates ?? []).map(candidateFromRow);
  const runnableCandidates = storedCandidates
    .filter((candidate: CandidatePayload) => candidate.status !== "computed" && candidate.status !== "cache_hit")
    .map((candidate: CandidatePayload) => ({
      ...candidate,
      status: "waiting" as CandidateStatus,
      error_type: null,
      error_message: null,
    }));

  if (runnableCandidates.length === 0) {
    return { queued: false, reason: "nothing_to_run" };
  }

  const config = parseJsonField<Record<string, any>>(experiment.config, {});
  await database().strategyPromptExperiment.update({
    where: { id: experimentId },
    data: { status: "queued", updatedAt: new Date() },
  });
  await database().strategyPromptExperimentCandidate.updateMany({
    where: { experimentId, status: { in: ["waiting", "running", "parsed", "failed", "skipped"] } },
    data: { status: "waiting", errorType: null, errorMessage: null, updatedAt: new Date() },
  });

  state.queue.push({
    experimentId,
    origin,
    concurrency: clampConcurrency(config?.concurrency),
    timeoutMs: Number(config?.timeoutMs ?? DEFAULT_TIMEOUT_MS),
    canceled: false,
    candidates: runnableCandidates,
  });
  pumpQueue();
  return { queued: true, reason: "queued" };
}

export async function GET(req: NextRequest) {
  try {
    const id = req.nextUrl.searchParams.get("id")?.trim();
    if (id) {
      const experiment = await loadExperiment(id);
      if (!experiment) return NextResponse.json({ error: "Experiment not found" }, { status: 404 });
      const formatted = formatExperiment(experiment);
      const exportFormat = req.nextUrl.searchParams.get("export");
      if (exportFormat) {
        const artifacts = buildLearningArtifacts(experiment, formatted.candidates);
        if (exportFormat === "csv") {
          return new NextResponse(artifacts.patternsCsv, {
            headers: { "Content-Type": "text/csv; charset=utf-8" },
          });
        }
        return NextResponse.json(JSON.parse(artifacts.resultJson));
      }
      const analysis = req.nextUrl.searchParams.get("analysis");
      if (analysis === "true") {
        return NextResponse.json(analyzeExperimentCandidates(formatted.candidates));
      }
      return NextResponse.json(formatted);
    }

    const rows = await database().strategyPromptExperiment.findMany({
      orderBy: { createdAt: "desc" },
      take: 20,
    });
    return NextResponse.json({ experiments: rows.map(formatExperiment) });
  } catch (error) {
    console.error("Failed to fetch prompt experiments:", error);
    return NextResponse.json({ error: "Failed to fetch prompt experiments" }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    if (body?.action === "start") {
      const experimentId = String(body.experimentId ?? body.id ?? "").trim();
      if (!experimentId) return NextResponse.json({ error: "experimentId is required" }, { status: 400 });
      const result = await enqueueStoredExperiment(experimentId, req.nextUrl.origin);
      if (result.reason === "not_found") {
        return NextResponse.json({ error: "Experiment not found" }, { status: 404 });
      }
      if (result.reason === "nothing_to_run") {
        return NextResponse.json({ ok: true, experimentId, status: "completed" });
      }
      return NextResponse.json({ ok: true, experimentId, status: "queued", reason: result.reason }, { status: 202 });
    }

    if (body?.action === "generate") {
      const prompts = generatePromptDataset({
        seed: Number(body.seed ?? 42),
        categoryCounts: body.categoryCounts,
      });
      return NextResponse.json({ prompts, totalPrompts: prompts.length });
    }

    if (body?.action === "cancel") {
      const experimentId = String(body.experimentId ?? body.id ?? "").trim();
      if (!experimentId) return NextResponse.json({ error: "experimentId is required" }, { status: 400 });
      const state = getExecutionState();
      state.canceledIds.add(experimentId);
      const active = state.activeJobs.get(experimentId);
      if (active) active.canceled = true;
      state.queue = state.queue.filter((job) => job.experimentId !== experimentId);
      await database().strategyPromptExperiment.update({
        where: { id: experimentId },
        data: { status: "canceled", updatedAt: new Date() },
      });
      await database().strategyPromptExperimentCandidate.updateMany({
        where: { experimentId, status: "waiting" },
        data: { status: "skipped", errorMessage: "사용자 요청으로 실행 전에 취소됨", updatedAt: new Date() },
      });
      return NextResponse.json({ ok: true, experimentId, status: "cancel_requested" }, { status: 202 });
    }

    const seed = Number(body?.seed ?? 42);
    const prompts = Array.isArray(body?.prompts)
      ? body.prompts.map((prompt: PromptSeed, index: number) => ({
          ...prompt,
          id: prompt.id ?? toPromptId(index),
        }))
      : generatePromptDataset({ seed, categoryCounts: body?.categoryCounts });
    if (prompts.length === 0) return NextResponse.json({ error: "prompts are required" }, { status: 400 });

    const experimentId = typeof body?.experimentId === "string" && body.experimentId.trim()
      ? body.experimentId.trim()
      : buildExperimentId(seed);
    const now = new Date();
    const config = {
      categoryCounts: normalizeCategoryCounts(body?.categoryCounts),
      seed,
      timeoutMs: Number(body?.timeoutMs ?? DEFAULT_TIMEOUT_MS),
      concurrency: clampConcurrency(body?.concurrency),
    };

    await database().strategyPromptExperiment.create({
      data: {
        id: experimentId,
        name: String(body?.name ?? "Strategy Prompt Experiment"),
        seed,
        totalPrompts: prompts.length,
        status: body?.start === false ? "waiting" : "queued",
        config: JSON.stringify(config),
        resultFilePath: RESULT_FILE_PATH,
        summaryFilePath: SUMMARY_FILE_PATH,
        datasetFilePath: DATASET_FILE_PATH,
        rulesFilePath: RULES_FILE_PATH,
        patternsFilePath: PATTERNS_FILE_PATH,
        createdAt: now,
        updatedAt: now,
      },
    });
    await database().strategyPromptExperimentCandidate.createMany({
      data: prompts.map((prompt: PromptSeed) => ({
        experimentId,
        promptId: prompt.id,
        prompt: prompt.text,
        category: prompt.category,
        complexity: prompt.complexity,
        riskProfile: prompt.risk_profile,
        expectedBlocks: JSON.stringify(prompt.expected_blocks),
        status: "waiting",
        extractedBlocks: JSON.stringify([]),
        extractedParameters: JSON.stringify({}),
        coachLearningTags: JSON.stringify([]),
        createdAt: now,
        updatedAt: now,
      })),
    });

    if (body?.start !== false) {
      getExecutionState().queue.push({
        experimentId,
        origin: req.nextUrl.origin,
        concurrency: config.concurrency,
        timeoutMs: config.timeoutMs,
        canceled: false,
        candidates: prompts.map((prompt: PromptSeed) => ({
          ...prompt,
          prompt_id: prompt.id,
          prompt: prompt.text,
          risk_profile: prompt.risk_profile,
          expected_blocks: prompt.expected_blocks,
          status: "waiting",
        })),
      });
      pumpQueue();
    }

    return NextResponse.json({
      ok: true,
      experimentId,
      status: body?.start === false ? "waiting" : "queued",
      totalPrompts: prompts.length,
      filePaths: {
        result: RESULT_FILE_PATH,
        summary: SUMMARY_FILE_PATH,
        dataset: DATASET_FILE_PATH,
        rules: RULES_FILE_PATH,
        patterns: PATTERNS_FILE_PATH,
      },
    }, { status: 202 });
  } catch (error: any) {
    if (String(error?.code ?? "") === "P2002") {
      return NextResponse.json({ error: "Experiment already exists" }, { status: 409 });
    }
    console.error("Failed to create prompt experiment:", error);
    return NextResponse.json({ error: "Failed to create prompt experiment" }, { status: 500 });
  }
}
