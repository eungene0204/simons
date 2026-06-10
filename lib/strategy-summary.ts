import type { StrategyDSL } from "@/types/strategy";

export interface ParsedSummary {
  description: string;
  universe: string[];
  fundamental_filters: Array<{ metric: string; operator: string; value: number }>;
  entry_signals: Array<{ indicator: string; signal_type?: string | null }>;
  exit_signals: Array<{ indicator: string; signal_type?: string | null }>;
  ranking_metric?: "return" | null;
  ranking_lookback_days?: number | null;
  max_positions: number;
  hold_period_days: number | null;
  rebalancing_period: string;
  stop_loss_pct: number | null;
  take_profit_pct: number | null;
  trailing_stop_pct?: number | null;
  backtest_period: string;
  initial_capital: number;
}

interface BacktestRequestLike {
  symbols?: string[];
}

export const UNIVERSE_LABELS: Record<string, string> = {
  kospi: "KOSPI",
  kosdaq: "KOSDAQ",
  kospi200: "KOSPI 200",
  KOR_KOSPI200: "KOSPI 200",
  KOR_KOSDAQ150: "KOSDAQ 150",
  US_TECH_TOP10: "미국 테크 Top 10",
  CRYPTO_TOP10: "크립토 Top 10",
};

export const METRIC_LABELS: Record<string, string> = {
  per: "PER",
  pbr: "PBR",
  roe_or_gpa: "ROE",
  debt_ratio: "부채비율",
  market_cap: "시총",
  trading_value: "거래대금",
};

export const PERIOD_LABELS: Record<string, string> = {
  "1y": "1년",
  "3y": "3년",
  "5y": "5년",
  full: "전체",
};

export const REBAL_LABELS: Record<string, string> = {
  none: "없음",
  daily: "매일",
  weekly: "매주",
  monthly: "매월",
  bimonthly: "격월",
  quarterly: "분기",
  yearly: "매년",
};

export const FUNDAMENTAL_FILTER_SECTION_LABEL = "진입 신호";

export const INDICATOR_LABELS: Record<string, string> = {
  ma_crossover: "MA 크로스",
  rsi: "RSI",
  ema: "EMA 크로스",
  macd: "MACD",
  bollinger_bands: "볼린저밴드",
  breakout: "브레이크아웃",
  volume_spike: "거래량 급증",
  stochastic: "스토캐스틱",
  cci: "CCI",
  adx: "ADX",
  ai_model: "AI 매수 예측",
  ai_drop_model: "AI 하락 예측",
};

function getSignalLabel(
  signal: { indicator: string; signal_type?: string | null },
  context: "entry" | "exit"
): string {
  if (signal.indicator === "ai_drop_model") {
    return INDICATOR_LABELS.ai_drop_model;
  }

  if (signal.indicator === "ai_model" && (context === "exit" || signal.signal_type === "sell")) {
    return INDICATOR_LABELS.ai_drop_model;
  }

  return INDICATOR_LABELS[signal.indicator] ?? signal.indicator;
}

function normalizeUniverseId(universe: string): string {
  const normalized = universe.trim();
  if (!normalized) return normalized;

  switch (normalized.toUpperCase()) {
    case "KOSPI":
      return "kospi";
    case "KOSDAQ":
      return "kosdaq";
    case "KOSPI200":
      return "kospi200";
    default:
      return normalized;
  }
}

function formatPercent(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  return Number.isInteger(value) ? value.toFixed(0) : value.toString();
}

export function getDisplayUniverseLabels(
  parsed: ParsedSummary,
  backtestRequest?: BacktestRequestLike | null
): string[] {
  const normalizedUniverses = parsed.universe.map(normalizeUniverseId);

  if (
    normalizedUniverses.length === 1 &&
    normalizedUniverses[0] === "kospi200" &&
    (backtestRequest?.symbols?.length ?? 0) > 220
  ) {
    return ["KOSPI"];
  }

  return normalizedUniverses.map((universe) => UNIVERSE_LABELS[universe] ?? universe);
}

export function getRankingLabel(parsed: ParsedSummary): string | null {
  if (parsed.ranking_metric === "return") {
    const days = parsed.ranking_lookback_days ?? 60;
    return `${days}일 수익률 상위`;
  }
  return null;
}

export function getDisplayExitLabels(parsed: ParsedSummary): string[] {
  const labels: string[] = [];

  for (const signal of parsed.exit_signals) {
    labels.push(getSignalLabel(signal, "exit"));
  }

  const takeProfitPct = formatPercent(parsed.take_profit_pct);
  const stopLossPct = formatPercent(parsed.stop_loss_pct);
  const trailingStopPct = formatPercent(parsed.trailing_stop_pct);

  if (stopLossPct) {
    labels.push(`손절 -${stopLossPct}% 하락시 매도`);
  }
  if (takeProfitPct) {
    labels.push(`익절 ${takeProfitPct}% 이상 수익시 매도`);
  }
  if (trailingStopPct) {
    labels.push(`트레일링 스탑 -${trailingStopPct}% 하락시 매도`);
  }
  if (parsed.hold_period_days) {
    labels.push(`최대 ${parsed.hold_period_days}일 보유 후 매도`);
  }

  return labels;
}

export function buildStrategySummary(
  parsed: ParsedSummary | null,
  backtestRequest?: BacktestRequestLike | null
) {
  if (!parsed) return undefined;

  const exitLabels = getDisplayExitLabels(parsed);
  const stopLossPct = formatPercent(parsed.stop_loss_pct);
  const takeProfitPct = formatPercent(parsed.take_profit_pct);
  const trailingStopPct = formatPercent(parsed.trailing_stop_pct);

  return {
    strategyName: parsed.description,
    universeName: getDisplayUniverseLabels(parsed, backtestRequest).join(", "),
    blockNames: [
      ...parsed.fundamental_filters.map(
        (filter) => `${METRIC_LABELS[filter.metric] ?? filter.metric} ${filter.operator} ${filter.value}`
      ),
      ...parsed.entry_signals.map(
        (signal) => getSignalLabel(signal, "entry")
      ),
      ...exitLabels,
    ],
    entryBlocks: parsed.entry_signals.map(
      (signal) => getSignalLabel(signal, "entry")
    ),
    exitBlocks: exitLabels,
    positionText: `최대 ${parsed.max_positions}종목${parsed.hold_period_days ? ` · ${parsed.hold_period_days}일 보유` : ""}`,
    riskText: [
      stopLossPct ? `손절 ${stopLossPct}%` : "",
      takeProfitPct ? `익절 ${takeProfitPct}%` : "",
      trailingStopPct ? `트레일링 스탑 ${trailingStopPct}%` : "",
    ].filter(Boolean).join(", ") || undefined,
  };
}

function getIndicatorLabel(indicator: string): string {
  return INDICATOR_LABELS[indicator] ?? indicator;
}

function inferUniverseFromLegacyStrategy(strategy: StrategyDSL | null | undefined): string {
  if (!strategy) return "미정";

  const legacyStrategy = strategy as StrategyDSL & {
    symbols?: string[];
  };
  const description = strategy.description ?? "";
  const normalizedDescription = description.toUpperCase().replace(/\s+/g, "");
  const symbolCount = legacyStrategy.symbols?.length ?? 0;

  if (normalizedDescription.includes("KOSPI200")) {
    return "KOSPI 200";
  }
  if (normalizedDescription.includes("KOSDAQ150")) {
    return "KOSDAQ 150";
  }
  if (normalizedDescription.includes("KOSDAQ")) {
    return "KOSDAQ";
  }
  if (normalizedDescription.includes("KOSPI")) {
    return "KOSPI";
  }
  if (symbolCount >= 180 && symbolCount <= 260) {
    return "KOSPI 200";
  }
  if (symbolCount >= 130 && symbolCount <= 170) {
    return "KOSDAQ 150";
  }
  if (symbolCount > 260) {
    return "KOSPI";
  }

  return "미정";
}

export function buildStrategySummaryFromDsl(strategy: StrategyDSL | null | undefined) {
  if (!strategy) return undefined;

  const rawUniverse =
    typeof strategy.universe === "string"
      ? strategy.universe
      : strategy.universe?.id;
  const normalizedUniverse =
    (rawUniverse ? UNIVERSE_LABELS[rawUniverse] : undefined) ??
    UNIVERSE_LABELS[normalizeUniverseId(rawUniverse ?? "")];
  const universeName =
    normalizedUniverse ??
    (rawUniverse || undefined) ??
    inferUniverseFromLegacyStrategy(strategy);
  const stopLossPct = formatPercent(strategy.risk?.stop_loss_pct);
  const takeProfitPct = formatPercent(strategy.risk?.take_profit_pct);
  const trailingStopPct = formatPercent(strategy.risk?.trailing_stop_pct);
  const maxHoldingDays = strategy.risk?.max_holding_days;
  const maxPositions = strategy.risk?.max_positions;
  const rebalancingPeriod = strategy.risk?.rebalancing_period;
  const exitSignalBlocks =
    strategy.exit?.conditions?.map((condition) => getIndicatorLabel(condition.id)) ?? [];
  const exitBlocks = getDisplayExitLabels({
    description: strategy.description,
    universe: [rawUniverse ?? ""],
    fundamental_filters: [],
    entry_signals: [],
    exit_signals: exitSignalBlocks.map((indicator) => ({ indicator })),
    max_positions: maxPositions ?? 0,
    hold_period_days: maxHoldingDays ?? null,
    rebalancing_period: rebalancingPeriod ?? "none",
    stop_loss_pct: strategy.risk?.stop_loss_pct ?? null,
    take_profit_pct: strategy.risk?.take_profit_pct ?? null,
    trailing_stop_pct: strategy.risk?.trailing_stop_pct ?? null,
    backtest_period: "full",
    initial_capital: 0,
  });
  const rebalancingText =
    rebalancingPeriod && rebalancingPeriod !== "none"
      ? `${REBAL_LABELS[rebalancingPeriod] ?? rebalancingPeriod} 리밸런싱`
      : undefined;

  return {
    strategyName: strategy.name,
    universeName,
    exitBlocks,
    positionText: maxPositions
      ? `포지션/비중 최대 ${maxPositions}종목${maxHoldingDays ? ` · ${maxHoldingDays}일 보유` : ""}`
      : undefined,
    riskText: [
      stopLossPct ? `손절 ${stopLossPct}%` : "",
      takeProfitPct ? `익절 ${takeProfitPct}%` : "",
      trailingStopPct ? `트레일링 스탑 ${trailingStopPct}%` : "",
    ].filter(Boolean).join(", ") || undefined,
    rebalancingText,
  };
}
