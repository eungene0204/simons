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

type LegacyStrategySummaryFields = {
  universe?: string | string[] | { id?: string; filters?: Record<string, unknown> };
  fundamental_filters?: Array<{ metric: string; operator: string; value: number }>;
  entry_signals?: Array<{ indicator: string; signal_type?: string | null }>;
  exit_signals?: Array<{ indicator: string; signal_type?: string | null }>;
  max_positions?: number | null;
  hold_period_days?: number | null;
  rebalancing_period?: string | null;
  stop_loss_pct?: number | null;
  take_profit_pct?: number | null;
  trailing_stop_pct?: number | null;
};

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

const KO_NUMBER_FORMAT = new Intl.NumberFormat("ko-KR");

// 시총처럼 원 단위 큰 금액(>=1억)을 '100억' / '1조' / '1조 5,000억' 형태로 표시한다.
// 1억 미만이거나 숫자가 아니면 원본을 그대로 둔다(단위가 모호한 값 오변환 방지).
function formatMarketCapValue(value: number): string {
  if (!Number.isFinite(value) || value < 100_000_000) return String(value);

  const roundedEok = Math.round(value / 100_000_000);
  if (roundedEok < 10_000) {
    return `${KO_NUMBER_FORMAT.format(roundedEok)}억`;
  }

  const jo = Math.floor(roundedEok / 10_000);
  const remainderEok = roundedEok % 10_000;
  return remainderEok === 0
    ? `${KO_NUMBER_FORMAT.format(jo)}조`
    : `${KO_NUMBER_FORMAT.format(jo)}조 ${KO_NUMBER_FORMAT.format(remainderEok)}억`;
}

// 펀더멘털 필터 배지 문자열을 만든다. 시총은 한글 단위로, 거래대금은 억 단위 표시, 나머지는 원본 숫자로 표시.
export function formatFundamentalFilter(filter: {
  metric: string;
  operator: string;
  value: number;
}): string {
  const label = METRIC_LABELS[filter.metric] ?? filter.metric;
  let value: string;
  if (filter.metric === "market_cap") {
    value = formatMarketCapValue(filter.value);
  } else if (filter.metric === "trading_value") {
    value = `${KO_NUMBER_FORMAT.format(filter.value)}억`;
  } else {
    value = String(filter.value);
  }
  return `${label} ${filter.operator} ${value}`;
}

// 초기자금 배지 문자열을 만든다. 1억 이상이면 '50억원'처럼 한글 단위로, 미만이면 콤마 포함 원 단위로 표시.
export function formatInitialCapital(value: number): string {
  if (Number.isFinite(value) && value >= 100_000_000) {
    return `${formatMarketCapValue(value)}원`;
  }
  return `${KO_NUMBER_FORMAT.format(value)}원`;
}

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
      ...parsed.fundamental_filters.map(formatFundamentalFilter),
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

export interface StrategySummaryDisplay {
  universeName?: string | null;
  entryBlocks?: string[] | null;
  exitBlocks?: string[] | null;
  positionText?: string | null;
  rebalancingText?: string | null;
  riskText?: string | null;
}

function isRawSymbolUniverseName(value: string): boolean {
  const tokens = value.split(/[,\s]+/).map((token) => token.trim()).filter(Boolean);
  return tokens.length > 0 && tokens.every((token) => /^\d{6}$/.test(token));
}

export function buildStrategySummaryChips(
  summary: StrategySummaryDisplay | null | undefined
): string[] {
  if (!summary) return [];

  const chips: Array<string | undefined | null> = [];
  const universeName = summary.universeName?.trim();
  if (universeName && universeName !== "미정" && !isRawSymbolUniverseName(universeName)) {
    chips.push(`유니버스 ${universeName}`);
  }

  chips.push(
    ...(summary.entryBlocks ?? []),
    ...(summary.exitBlocks ?? []),
    summary.positionText,
    summary.rebalancingText,
    summary.riskText ? `리스크 관리 ${summary.riskText}` : undefined
  );

  return chips.filter((value): value is string => Boolean(value));
}

function getIndicatorLabel(indicator: string): string {
  return INDICATOR_LABELS[indicator] ?? indicator;
}

function uniqueLabels(labels: string[]): string[] {
  return Array.from(new Set(labels.filter(Boolean)));
}

function conditionToEntryLabel(condition: {
  id?: string;
  type?: string;
  params?: Record<string, unknown>;
}): string | null {
  if (!condition.id) return null;

  const metric = condition.id;
  const rawValue = condition.params?.value;
  const value = typeof rawValue === "number" ? rawValue : Number(rawValue);
  if ((condition.type === "filter" || METRIC_LABELS[metric]) && Number.isFinite(value)) {
    return formatFundamentalFilter({
      metric,
      operator: String(condition.params?.operator ?? "<="),
      value,
    });
  }

  return getIndicatorLabel(metric);
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

  const legacyStrategy = strategy as StrategyDSL & LegacyStrategySummaryFields;
  const rawUniverse =
    Array.isArray(legacyStrategy.universe)
      ? legacyStrategy.universe[0]
      : typeof legacyStrategy.universe === "string"
        ? legacyStrategy.universe
        : legacyStrategy.universe?.id;
  const normalizedUniverse =
    (rawUniverse ? UNIVERSE_LABELS[rawUniverse] : undefined) ??
    UNIVERSE_LABELS[normalizeUniverseId(rawUniverse ?? "")];
  const universeName =
    normalizedUniverse ??
    (rawUniverse || undefined) ??
    inferUniverseFromLegacyStrategy(strategy);
  const stopLossValue = strategy.risk?.stop_loss_pct ?? legacyStrategy.stop_loss_pct;
  const takeProfitValue = strategy.risk?.take_profit_pct ?? legacyStrategy.take_profit_pct;
  const trailingStopValue = strategy.risk?.trailing_stop_pct ?? legacyStrategy.trailing_stop_pct;
  const maxHoldingDays = strategy.risk?.max_holding_days ?? legacyStrategy.hold_period_days;
  const maxPositions = strategy.risk?.max_positions ?? legacyStrategy.max_positions;
  const rebalancingPeriod = strategy.risk?.rebalancing_period ?? legacyStrategy.rebalancing_period;
  const stopLossPct = formatPercent(stopLossValue);
  const takeProfitPct = formatPercent(takeProfitValue);
  const trailingStopPct = formatPercent(trailingStopValue);
  const conditionEntryBlocks =
    strategy.entry?.conditions?.map(conditionToEntryLabel).filter((label): label is string => Boolean(label)) ?? [];
  const legacyFundamentalBlocks =
    legacyStrategy.fundamental_filters?.map(formatFundamentalFilter) ?? [];
  const legacyEntryBlocks =
    legacyStrategy.entry_signals?.map((signal) => getSignalLabel(signal, "entry")) ?? [];
  const entryBlocks = uniqueLabels([
    ...conditionEntryBlocks,
    ...legacyFundamentalBlocks,
    ...legacyEntryBlocks,
  ]);
  const exitSignalBlocks = [
    ...(strategy.exit?.conditions?.map((condition) => ({ indicator: getIndicatorLabel(condition.id) })) ?? []),
    ...(legacyStrategy.exit_signals ?? []),
  ];
  const exitBlocks = getDisplayExitLabels({
    description: strategy.description,
    universe: [rawUniverse ?? ""],
    fundamental_filters: [],
    entry_signals: [],
    exit_signals: exitSignalBlocks,
    max_positions: maxPositions ?? 0,
    hold_period_days: maxHoldingDays ?? null,
    rebalancing_period: rebalancingPeriod ?? "none",
    stop_loss_pct: stopLossValue ?? null,
    take_profit_pct: takeProfitValue ?? null,
    trailing_stop_pct: trailingStopValue ?? null,
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
    blockNames: [...entryBlocks, ...exitBlocks],
    entryBlocks,
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
