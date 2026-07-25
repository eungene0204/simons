import {
  formatFundamentalFilter,
  formatInitialCapital,
  getDisplayExitLabels,
  getDisplayUniverseLabels,
  getRankingLabel,
  getSignalLabel,
  PERIOD_LABELS,
  type ParsedSummary,
} from "./strategySummary";
import {
  hasExplicitBacktestPeriod,
  hasExplicitInitialCapital,
  hasExplicitMaxPositions,
  hasExplicitRebalancing,
  hasExplicitUniverse,
} from "./backtestReadiness";

export type BuilderSummaryItem = {
  label: string;
  value: string;
};

export type BuilderProgressItem = {
  label: string;
  complete: boolean;
};

export type BuilderTurnPresentation = {
  summaryItems: BuilderSummaryItem[];
  progressItems: BuilderProgressItem[];
  question: string;
};

export function getDisplayBuilderProgressItems(
  items: BuilderProgressItem[],
): BuilderProgressItem[] {
  const normalizedItems = items.map((item) => ({
    ...item,
    label: item.label === "투자 대상" ? "유니버스" : item.label,
  }));

  return [
    ...normalizedItems.filter((item) => item.complete),
    ...normalizedItems.filter((item) => !item.complete),
  ];
}

const UNIVERSE_LABELS: Record<string, string> = {
  KOSPI: "KOSPI",
  KOSDAQ: "KOSDAQ",
  KOSPI200: "KOSPI 200",
  KOSPI_KOSDAQ: "KOSPI·KOSDAQ 전체",
  ETF: "ETF",
};

const STRATEGY_LABELS: Record<string, string> = {
  momentum: "모멘텀",
  golden_cross: "골든크로스",
  macd: "MACD",
  bollinger: "볼린저 밴드",
  breakout: "돌파",
  volume_spike: "거래량 급증",
  stochastic: "스토캐스틱",
  cci: "CCI",
  rsi: "RSI",
  mean_reversion: "과매도 반등",
  value: "저평가 가치주",
  custom: "직접 설계",
};

const REBALANCE_LABELS: Record<string, string> = {
  daily: "매일",
  weekly: "매주",
  monthly: "매월",
  quarterly: "분기",
  yearly: "매년",
  none: "설정 안 함",
};

const PAIRED_EXIT_STRATEGIES = new Set([
  "golden_cross",
  "macd",
  "bollinger",
  "stochastic",
  "cci",
  "rsi",
  "mean_reversion",
]);

function hasValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "" && value !== false;
}

function isEntryComplete(state: Record<string, any>, parsed?: ParsedSummary | null): boolean {
  const parsedHasEntry = Boolean(
    parsed?.fundamental_filters?.length ||
    parsed?.entry_signals?.length ||
    parsed?.ranking_metric,
  );
  if (parsedHasEntry) return true;

  const strategyType = state.strategy_type;
  if (!strategyType) return false;
  if (strategyType === "custom") return hasValue(state.entry_rule);
  if (strategyType === "momentum" || strategyType === "breakout") {
    return hasValue(state.lookback_days);
  }
  if (strategyType === "rsi") {
    return hasValue(state.rsi_period) &&
      hasValue(state.rsi_oversold) &&
      hasValue(state.rsi_overbought) &&
      state.filters_asked === true;
  }
  if (strategyType === "golden_cross") {
    return hasValue(state.ma_kind) &&
      hasValue(state.ma_short) &&
      hasValue(state.ma_long) &&
      state.filters_asked === true;
  }
  if (strategyType === "macd") {
    return hasValue(state.macd_mode) && state.filters_asked === true;
  }
  if (strategyType === "cci") {
    return hasValue(state.cci_period) &&
      hasValue(state.cci_threshold) &&
      state.filters_asked === true;
  }
  if (strategyType === "volume_spike") {
    return hasValue(state.volume_period) && state.filters_asked === true;
  }
  if (strategyType === "value") {
    return hasValue(state.value_pbr) && hasValue(state.value_roe);
  }
  return state.filters_asked === true;
}

function buildEntryLabel(
  state: Record<string, any>,
  parsed?: ParsedSummary | null,
): string | null {
  const parsedLabels = [
    ...(parsed?.fundamental_filters ?? []).map(formatFundamentalFilter),
    ...(parsed?.entry_signals ?? []).map((signal) => getSignalLabel(signal, "entry")),
    ...(parsed && getRankingLabel(parsed) ? [getRankingLabel(parsed)!] : []),
  ];
  if (parsedLabels.length > 0) return parsedLabels.join(" · ");

  if (state.entry_rule) return String(state.entry_rule);
  const strategyLabel = STRATEGY_LABELS[state.strategy_type];
  return strategyLabel ? `${strategyLabel} 조건` : null;
}

function buildRiskLabel(state: Record<string, any>, parsed?: ParsedSummary | null): string | null {
  const labels: string[] = [];
  const stopLoss = state.stop_loss_pct ?? parsed?.stop_loss_pct;
  const takeProfit = state.take_profit_pct ?? parsed?.take_profit_pct;
  const trailingStop = state.trailing_stop_pct ?? parsed?.trailing_stop_pct;
  const holdPeriod = state.hold_period_days ?? parsed?.hold_period_days;
  if (hasValue(stopLoss)) labels.push(`손절 ${stopLoss}%`);
  if (hasValue(takeProfit)) labels.push(`익절 ${takeProfit}%`);
  if (hasValue(trailingStop)) labels.push(`트레일링 스탑 ${trailingStop}%`);
  if (hasValue(holdPeriod)) labels.push(`${holdPeriod}일 보유`);
  return labels.length > 0 ? labels.join(" · ") : null;
}

export function makeBuilderQuestionFriendly(reply: string): string {
  return reply
    .replace(
      "대상 시장·종목이 빠져 있습니다. 어떤 시장·종목을 대상으로 할까요?",
      "먼저 어떤 시장·종목을 대상으로 할지 정해볼까요?",
    )
    .replace(
      "매수 조건이 빠져 있습니다. 어떤 조건에서 매수할까요?",
      "다음으로 어떤 조건에서 매수할지 정해볼까요?",
    )
    .replace(
      "청산 조건이 빠져 있습니다. 어떤 조건에서 청산할까요?",
      "이제 언제 매도할지 정해볼까요?",
    )
    .replace(
      "리밸런싱 주기가 빠져 있습니다. 포트폴리오를 얼마나 자주 다시 구성할까요?",
      "다음으로 포트폴리오를 얼마나 자주 다시 구성할지 정해볼까요?",
    )
    .replace(
      "손절 기준이 빠져 있습니다. 손절 기준을 몇 %로 설정할까요?",
      "이제 손절 기준을 몇 %로 정할까요?",
    )
    .replace(
      "익절 기준이 빠져 있습니다. 익절 기준을 몇 %로 설정할까요?",
      "이제 익절 기준을 몇 %로 정할까요?",
    )
    .replace(/^세부 조건이 빠져 있습니다\.\s*/, "")
    .replace(/^[^.\n]+(?:빠져 있습니다|빠졌습니다)\.\s*/, "")
    .replace("과매도·과매수 기준을 정해 주세요.", "과매도·과매수 기준을 정해볼까요?")
    .replace("단기·장기 이동평균 기간을 정해 주세요.", "단기·장기 이동평균 기간을 정해볼까요?")
    .replace("CCI 기준값을 정해 주세요.", "CCI 기준값을 정해볼까요?")
    .replace("저평가 기준을 정해 주세요.", "저평가 기준을 정해볼까요?")
    .replace(
      "어떤 조건에서 매수할지 말씀해 주세요.",
      "어떤 조건에서 매수할지 함께 정해볼까요?",
    )
    .replace(
      /마지막으로 청산 조건을 정해 주세요\. 손절·익절·트레일링 스탑·보유기간 중 하나 이상을 자유롭게 말씀해 주세요\./,
      "이제 언제 매도할지 정하면 전략이 완성됩니다. 손절·익절·트레일링 스탑·보유기간 중 하나를 정해볼까요?",
    )
    .replace(
      "마지막으로 청산 조건을 정해 주세요.",
      "이제 언제 매도할지 정하면 전략이 완성됩니다. 매도 조건을 함께 정해볼까요?",
    );
}

export function buildBuilderTurnPresentation({
  state,
  reply,
  parsed,
  prompt = "",
}: {
  state: Record<string, any>;
  reply: string;
  parsed?: ParsedSummary | null;
  prompt?: string;
}): BuilderTurnPresentation {
  const summaryItems: BuilderSummaryItem[] = [];
  const targetFromState = (state.single_label
    ? String(state.single_label).replace(/\s*\(\d{6}\)$/, "")
    : null) ||
    (state.theme_label ? String(state.theme_label) : null) ||
    (state.universe ? UNIVERSE_LABELS[state.universe] ?? state.universe : null);
  const targetExplicit = Boolean(state.theme_label) || hasExplicitUniverse(prompt, parsed);
  const target = targetExplicit
    ? targetFromState || (parsed ? getDisplayUniverseLabels(parsed).join(" · ") : null)
    : null;
  const entryLabel = buildEntryLabel(state, parsed);
  const exitLabels = parsed ? getDisplayExitLabels(parsed) : [];
  const riskLabel = buildRiskLabel(state, parsed);
  const holdingCountFromState = hasValue(state.holding_count);
  const holdingCount = holdingCountFromState ? state.holding_count : parsed?.max_positions;
  const holdingCountExplicit =
    Boolean(parsed?.target_symbols?.length) || hasExplicitMaxPositions(prompt);
  const rebalanceFromState = hasValue(state.rebalance_cycle);
  const rebalanceCycle = rebalanceFromState
    ? state.rebalance_cycle
    : parsed?.rebalancing_period;
  const rebalanceExplicit =
    Boolean(parsed?.target_symbols?.length) || hasExplicitRebalancing(prompt);
  const backtestPeriod = state.backtest_period ?? state.period ?? parsed?.backtest_period;
  const backtestPeriodExplicit = hasExplicitBacktestPeriod(prompt);
  const initialCapitalFromState = state.initial_capital ?? state.init_cash;
  const initialCapital = hasValue(initialCapitalFromState)
    ? Number(initialCapitalFromState)
    : parsed?.initial_capital;
  const initialCapitalExplicit = hasExplicitInitialCapital(prompt);

  if (target) {
    summaryItems.push({
      label: state.single_label || state.theme_label ? "대상 종목" : "유니버스",
      value: target,
    });
  }
  if (state.sector || parsed?.sector) {
    const sector = state.sector ?? parsed?.sector;
    summaryItems.push({
      label: "업종",
      value: Array.isArray(sector) ? sector.join(" · ") : String(sector),
    });
  }
  if (entryLabel) summaryItems.push({ label: "매수 조건", value: entryLabel });
  if (exitLabels.length > 0) summaryItems.push({ label: "매도 조건", value: exitLabels.join(" · ") });
  if (holdingCount && holdingCountExplicit) {
    summaryItems.push({
      label: "최대 보유",
      value: `${holdingCount}종목`,
    });
  }
  if (rebalanceCycle && rebalanceExplicit) {
    const normalizedCycle = String(rebalanceCycle);
    const cycle = REBALANCE_LABELS[normalizedCycle] ?? normalizedCycle;
    summaryItems.push({
      label: "리밸런싱",
      value: cycle,
    });
  }
  if (backtestPeriod && backtestPeriodExplicit) {
    const normalizedPeriod = String(backtestPeriod).toLowerCase();
    summaryItems.push({
      label: "백테스트 기간",
      value: PERIOD_LABELS[normalizedPeriod] ?? String(backtestPeriod),
    });
  }
  if (initialCapital && initialCapitalExplicit) {
    summaryItems.push({
      label: "초기 자본",
      value: formatInitialCapital(initialCapital),
    });
  }
  if (riskLabel) summaryItems.push({ label: "리스크 관리", value: riskLabel });

  const entryComplete = isEntryComplete(state, parsed);
  const riskComplete = state.risk_done === true || Boolean(riskLabel);
  const exitComplete = exitLabels.length > 0 ||
    (entryComplete && PAIRED_EXIT_STRATEGIES.has(state.strategy_type)) ||
    riskComplete;

  return {
    summaryItems,
    progressItems: [
      { label: "유니버스", complete: Boolean(target) && targetExplicit },
      { label: "매수 조건", complete: entryComplete },
      { label: "매도 조건", complete: exitComplete },
      { label: "최대 보유", complete: Boolean(holdingCount) && holdingCountExplicit },
      { label: "리밸런싱", complete: Boolean(rebalanceCycle) && rebalanceExplicit },
      { label: "리스크 관리", complete: riskComplete },
      { label: "백테스트 기간", complete: Boolean(backtestPeriod) && backtestPeriodExplicit },
      { label: "초기 자본", complete: Boolean(initialCapital) && initialCapitalExplicit },
    ],
    question: makeBuilderQuestionFriendly(reply),
  };
}
