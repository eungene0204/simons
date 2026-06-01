import type { ParsedSummary } from "./strategySummary";

export interface StrategyBacktestRequest {
  symbols?: string[];
  universe_id?: string;
  entry?: { conditions?: Array<Record<string, unknown>> };
  exit?: { conditions?: Array<Record<string, unknown>> };
  risk?: Record<string, unknown>;
  period?: string;
  options?: Record<string, unknown>;
}

type CandidateStrategy = Partial<ParsedSummary> & Record<string, unknown>;

export type RequestedDomain =
  | "universe"
  | "entry"
  | "exit"
  | "risk"
  | "portfolio"
  | "backtest";

export interface AdvisorWalkForwardSettings {
  n_splits: number;
  train_pct: number;
  anchor: boolean;
  target_metric: string;
  n_trials: number;
}

export interface AdvisorWalkForwardResult {
  status?: string;
  aggregate?: Record<string, unknown>;
  walk_forward_efficiency?: unknown;
}

const DOMAIN_PATTERNS: Record<RequestedDomain, RegExp[]> = {
  universe: [/코스피200|코스피 200|코스피|코스닥|kospi200|kospi|kosdaq|유니버스|전체 시장|시장/i],
  entry: [/진입|매수|골든크로스|rsi|macd|볼린저|브레이크아웃|돌파|pbr|per|roe|부채비율|시총|거래대금|필터|저평가|ai/i],
  exit: [/청산|매도|팔아|팔까|팔지|보유|데드크로스|하락/i],
  risk: [/손절|익절|트레일링|리스크|mdd/i],
  portfolio: [/최대\s*\d+\s*종목|\d+\s*개\s*종목|\d+\s*종목|포트폴리오|리밸런싱|리밸런스|분산|집중/i],
  backtest: [/백테스트|테스트 기간|전체 데이터|초기자금|자본금|원금|만원|억원?|\d[\d,]*원/i],
};

const FOLLOW_UP_QUESTION_PATTERN =
  /어때|어떻게|어디|언제|왜|뭘|뭐를|무엇|추천|조언|괜찮|좋을까|될까|볼까|봐야|팔아야|팔까|사야|살까|매도해야|매수해야|청산해야/i;

const EXPLICIT_MODIFICATION_PATTERN =
  /바꿔|변경|수정|추가|삭제|제외|빼|넣어|설정|적용|로\s*(해|바꿔|설정)|으로\s*(해|바꿔|설정)/i;

type PendingRiskChange = {
  trailing_stop_pct?: number;
};

function hasMatch(text: string, patterns: RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(text));
}

function extractPercentage(text: string): number | null {
  const match = text.match(/(\d+(?:\.\d+)?)\s*%/);
  if (!match) return null;
  const value = Number(match[1]);
  if (!Number.isFinite(value) || value <= 0 || value > 100) return null;
  return value;
}

function inferPendingRiskChange(userPrompt: string, previousCoachText?: string | null): PendingRiskChange | null {
  if (!previousCoachText) return null;
  const percentage = extractPercentage(userPrompt);
  if (percentage === null) return null;

  const promptLooksLikeAnswer = /정해|설정|해줘|해주세요|로\s*해|으로\s*해|추가|적용/.test(userPrompt);
  if (!promptLooksLikeAnswer) return null;

  if (/트레일링\s*스[탑톱]|trailing/i.test(previousCoachText) && /몇\s*%|퍼센트|비율/.test(previousCoachText)) {
    return { trailing_stop_pct: percentage };
  }

  return null;
}

export function detectRequestedDomains(prompt: string): Set<RequestedDomain> {
  const normalizedPrompt = prompt.trim();
  const domains = new Set<RequestedDomain>();

  if (!normalizedPrompt) return domains;

  (Object.keys(DOMAIN_PATTERNS) as RequestedDomain[]).forEach((domain) => {
    if (hasMatch(normalizedPrompt, DOMAIN_PATTERNS[domain])) {
      domains.add(domain);
    }
  });

  return domains;
}

export function isAdvisorFollowUpPrompt(prompt: string): boolean {
  const normalizedPrompt = prompt.trim();
  if (!normalizedPrompt) return false;
  if (
    FOLLOW_UP_QUESTION_PATTERN.test(normalizedPrompt) &&
    !EXPLICIT_MODIFICATION_PATTERN.test(normalizedPrompt)
  ) {
    return true;
  }
  if (detectRequestedDomains(normalizedPrompt).size > 0) return false;
  return /개선|추천|조언|어떻게|어디|뭘|뭐를|다음|후속|보완|고쳐|봐야|볼까/.test(normalizedPrompt);
}

function mergeParsedSummary(
  previous: ParsedSummary,
  next: ParsedSummary,
  requestedDomains: Set<RequestedDomain>,
  pendingRiskChange?: PendingRiskChange | null
): ParsedSummary {
  return {
    ...next,
    universe: requestedDomains.has("universe") ? next.universe : previous.universe,
    fundamental_filters: requestedDomains.has("entry") ? next.fundamental_filters : previous.fundamental_filters,
    entry_signals: requestedDomains.has("entry") ? next.entry_signals : previous.entry_signals,
    exit_signals: requestedDomains.has("exit") ? next.exit_signals : previous.exit_signals,
    max_positions: requestedDomains.has("portfolio") ? next.max_positions : previous.max_positions,
    hold_period_days: requestedDomains.has("exit") ? next.hold_period_days : previous.hold_period_days,
    rebalancing_period: requestedDomains.has("portfolio") ? next.rebalancing_period : previous.rebalancing_period,
    stop_loss_pct: requestedDomains.has("risk") ? (next.stop_loss_pct ?? previous.stop_loss_pct) : previous.stop_loss_pct,
    take_profit_pct: requestedDomains.has("risk") ? (next.take_profit_pct ?? previous.take_profit_pct) : previous.take_profit_pct,
    trailing_stop_pct: pendingRiskChange?.trailing_stop_pct ?? (requestedDomains.has("risk")
      ? (next.trailing_stop_pct ?? previous.trailing_stop_pct)
      : previous.trailing_stop_pct),
    backtest_period: requestedDomains.has("backtest") ? next.backtest_period : previous.backtest_period,
    initial_capital: requestedDomains.has("backtest") ? next.initial_capital : previous.initial_capital,
  };
}

function mergeBacktestRequest(
  previous: StrategyBacktestRequest | null | undefined,
  next: StrategyBacktestRequest | null | undefined,
  requestedDomains: Set<RequestedDomain>,
  pendingRiskChange?: PendingRiskChange | null
): StrategyBacktestRequest | null {
  if (!next) return previous ?? null;
  if (!previous) return next;

  const mergedRisk = {
    ...(previous.risk ?? {}),
    ...(next.risk ?? {}),
  };

  if (!requestedDomains.has("portfolio")) {
    mergedRisk.position_size_pct = previous.risk?.position_size_pct;
    mergedRisk.max_positions = previous.risk?.max_positions;
    mergedRisk.rebalancing_period = previous.risk?.rebalancing_period;
  }

  if (!requestedDomains.has("exit")) {
    mergedRisk.max_holding_days = previous.risk?.max_holding_days;
  }

  if (!requestedDomains.has("risk")) {
    mergedRisk.stop_loss_pct = previous.risk?.stop_loss_pct;
    mergedRisk.take_profit_pct = previous.risk?.take_profit_pct;
    mergedRisk.trailing_stop_pct = previous.risk?.trailing_stop_pct;
    mergedRisk.max_mdd_limit_pct = previous.risk?.max_mdd_limit_pct;
  } else {
    for (const field of ["stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "max_mdd_limit_pct"]) {
      if (next.risk?.[field] == null && previous.risk?.[field] !== undefined) {
        mergedRisk[field] = previous.risk[field];
      }
    }
  }

  if (!requestedDomains.has("backtest")) {
    mergedRisk.init_cash = previous.risk?.init_cash;
  }

  if (pendingRiskChange?.trailing_stop_pct !== undefined) {
    mergedRisk.trailing_stop_pct = pendingRiskChange.trailing_stop_pct;
  }

  return {
    ...previous,
    ...next,
    universe_id: requestedDomains.has("universe") ? (next.universe_id ?? previous.universe_id) : previous.universe_id,
    symbols: requestedDomains.has("universe") ? (next.symbols ?? previous.symbols) : previous.symbols,
    entry: requestedDomains.has("entry") ? (next.entry ?? previous.entry) : previous.entry,
    exit: requestedDomains.has("exit") ? (next.exit ?? previous.exit) : previous.exit,
    risk: mergedRisk,
    period: requestedDomains.has("backtest") ? (next.period ?? previous.period) : previous.period,
    options: requestedDomains.has("backtest")
      ? { ...(previous.options ?? {}), ...(next.options ?? {}) }
      : previous.options,
  };
}

function clarificationLooksLikeEntryRegression(
  clarificationQuestion: string | null | undefined,
  previousParsed: ParsedSummary,
  requestedDomains: Set<RequestedDomain>
): boolean {
  if (!clarificationQuestion || requestedDomains.has("entry")) {
    return false;
  }

  const previousHadEntry =
    previousParsed.fundamental_filters.length > 0 || previousParsed.entry_signals.length > 0;

  if (!previousHadEntry) {
    return false;
  }

  return /진입 조건|매수 조건|종목을 선택|어떤 조건으로 종목/.test(clarificationQuestion);
}

export function mergeStrategyModification(params: {
  previousParsed: ParsedSummary | null;
  nextParsed: ParsedSummary;
  previousBacktestRequest?: StrategyBacktestRequest | null;
  nextBacktestRequest?: StrategyBacktestRequest | null;
  userPrompt: string;
  clarificationQuestion?: string | null;
  previousCoachText?: string | null;
}) {
  const requestedDomains = detectRequestedDomains(params.userPrompt);
  const pendingRiskChange = inferPendingRiskChange(params.userPrompt, params.previousCoachText);

  if (pendingRiskChange) {
    requestedDomains.add("risk");
  }

  if (!params.previousParsed) {
    return {
      parsed: pendingRiskChange ? { ...params.nextParsed, ...pendingRiskChange } : params.nextParsed,
      backtestRequest: pendingRiskChange
        ? {
            ...(params.nextBacktestRequest ?? params.previousBacktestRequest ?? {}),
            risk: {
              ...((params.previousBacktestRequest ?? params.nextBacktestRequest)?.risk ?? {}),
              ...((params.nextBacktestRequest ?? params.previousBacktestRequest)?.risk ?? {}),
              ...pendingRiskChange,
            },
          }
        : params.nextBacktestRequest ?? params.previousBacktestRequest ?? null,
      requestedDomains,
      shouldReusePreviousClarification: false,
    };
  }

  if (requestedDomains.size === 0) {
    return {
      parsed: params.previousParsed,
      backtestRequest: params.previousBacktestRequest ?? params.nextBacktestRequest ?? null,
      requestedDomains,
      shouldReusePreviousClarification: false,
    };
  }

  const parsed = mergeParsedSummary(params.previousParsed, params.nextParsed, requestedDomains, pendingRiskChange);
  const backtestRequest = mergeBacktestRequest(
    params.previousBacktestRequest,
    params.nextBacktestRequest,
    requestedDomains,
    pendingRiskChange
  );

  return {
    parsed,
    backtestRequest,
    requestedDomains,
    shouldReusePreviousClarification: clarificationLooksLikeEntryRegression(
      params.clarificationQuestion,
      params.previousParsed,
      requestedDomains
    ),
  };
}

function normalizedPeriod(value: unknown): string | undefined {
  if (value === "1y") return "1Y";
  if (value === "3y") return "3Y";
  if (value === "5y") return "5Y";
  if (value === "full") return "ALL";
  return typeof value === "string" ? value : undefined;
}

function signalToCondition(signal: Record<string, unknown>, fallbackSignalType: string) {
  const indicator = signal.indicator;
  if (!indicator || typeof indicator !== "string") return null;
  return {
    type: "indicator",
    id: indicator,
    params: {
      ...signal,
      signalType: signal.signal_type ?? fallbackSignalType,
      value: signal.value ?? signal.threshold,
    },
    weight: 1.0,
  };
}

function filterToCondition(filter: Record<string, unknown>) {
  const metric = filter.metric;
  if (!metric || typeof metric !== "string") return null;
  return {
    type: "filter",
    id: metric,
    params: {
      operator: filter.operator,
      value: filter.value,
    },
    weight: 1.0,
  };
}

export function buildCandidateBacktestRequest(
  previous: StrategyBacktestRequest,
  candidate: CandidateStrategy
): StrategyBacktestRequest {
  const risk = { ...(previous.risk ?? {}) };

  if (candidate.max_positions != null) {
    risk.max_positions = candidate.max_positions;
    const count = Number(candidate.max_positions);
    if (Number.isFinite(count) && count > 0) {
      risk.position_size_pct = Math.round((10000 / count)) / 100;
    }
  }
  if (candidate.stop_loss_pct !== undefined) risk.stop_loss_pct = candidate.stop_loss_pct;
  if (candidate.take_profit_pct !== undefined) risk.take_profit_pct = candidate.take_profit_pct;
  if (candidate.trailing_stop_pct !== undefined) risk.trailing_stop_pct = candidate.trailing_stop_pct;
  if (candidate.max_mdd_limit_pct !== undefined) risk.max_mdd_limit_pct = candidate.max_mdd_limit_pct;
  if (candidate.hold_period_days !== undefined) risk.max_holding_days = candidate.hold_period_days;
  if (candidate.rebalancing_period !== undefined) risk.rebalancing_period = candidate.rebalancing_period;
  if (candidate.initial_capital !== undefined) risk.init_cash = candidate.initial_capital;

  const entryConditions = [
    ...((candidate.fundamental_filters ?? []) as Array<Record<string, unknown>>)
      .map(filterToCondition)
      .filter(Boolean),
    ...((candidate.entry_signals ?? []) as Array<Record<string, unknown>>)
      .map((signal) => signalToCondition(signal, "buy"))
      .filter(Boolean),
  ] as Array<Record<string, unknown>>;

  const exitConditions = ((candidate.exit_signals ?? []) as Array<Record<string, unknown>>)
    .map((signal) => signalToCondition(signal, "sell"))
    .filter(Boolean) as Array<Record<string, unknown>>;

  return {
    ...previous,
    entry: entryConditions.length > 0 ? { conditions: entryConditions } : previous.entry,
    exit: exitConditions.length > 0 ? { conditions: exitConditions } : previous.exit,
    risk,
    period: normalizedPeriod(candidate.backtest_period) ?? previous.period,
  };
}

export function buildWalkForwardRequest(
  baseStrategy: StrategyBacktestRequest,
  settings: AdvisorWalkForwardSettings,
  ranges: Record<string, unknown> = {}
) {
  return {
    base_strategy: baseStrategy,
    ranges,
    n_splits: settings.n_splits,
    train_pct: settings.train_pct,
    anchor: settings.anchor,
    target_metric: settings.target_metric,
    n_trials: settings.n_trials,
  };
}

function metricNumber(value: unknown): number | null {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function normalizeReturnScale(value: number): number {
  return Math.abs(value) > 1 ? value / 100 : value;
}

function oosCagr(result: AdvisorWalkForwardResult | null | undefined): number | null {
  const aggregate = result?.aggregate;
  if (!aggregate) return null;
  const raw = metricNumber(aggregate.avg_oos_cagr ?? aggregate.avg_oos_totalReturn);
  return raw === null ? null : normalizeReturnScale(raw);
}

export function buildAdvisorEvaluationContextFromWalkForward(
  before: AdvisorWalkForwardResult | null | undefined,
  after: AdvisorWalkForwardResult | null | undefined
) {
  const beforeOosCagr = oosCagr(before);
  const afterOosCagr = oosCagr(after);

  if (beforeOosCagr === null || afterOosCagr === null) {
    return { oos_available: false };
  }

  return {
    oos_available: true,
    oos_delta: afterOosCagr - beforeOosCagr,
    before_oos_cagr: beforeOosCagr,
    after_oos_cagr: afterOosCagr,
    before_walk_forward_efficiency: metricNumber(before?.walk_forward_efficiency),
    after_walk_forward_efficiency: metricNumber(after?.walk_forward_efficiency),
  };
}
