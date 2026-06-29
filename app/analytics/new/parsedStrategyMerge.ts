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
  // 백엔드의 익절/손절 결정적 추출과 보조를 맞춘다: '수익…매도'(익절), '하락…매도'·'손실'(손절)도 risk로 인식.
  risk: [/손절|익절|트레일링|리스크|mdd|낙폭|목표\s*수익|수익\s*(?:확정|실현)|수익[^.]{0,8}(?:매도|팔)|손실|하락[^.]{0,8}(?:매도|팔)|stop\s*loss|take\s*profit|trailing/i],
  portfolio: [/최대\s*\d+\s*종목|\d+\s*개\s*종목|\d+\s*종목|포트폴리오|리밸런싱|리밸런스|분산|집중/i],
  // 명시적 연도 범위('2002년부터 2005년까지', '2002~2005')도 백테스트 기간 변경으로 인식한다.
  backtest: [/백테스트|테스트 기간|전체 데이터|초기자금|자본금|원금|만원|억원?|\d[\d,]*원|(?:19|20)\d{2}\s*년?\s*(?:부터|까지|~|에서)|(?:19|20)\d{2}\s*[~\-]\s*(?:19|20)\d{2}/i],
};

const FOLLOW_UP_QUESTION_PATTERN =
  /어때|어떻게|어디|언제|왜|뭘|뭐를|무엇|추천|조언|괜찮|좋을까|될까|볼까|봐야|팔아야|팔까|사야|살까|매도해야|매수해야|청산해야/i;

const EXPLICIT_MODIFICATION_PATTERN =
  /바꿔|변경|수정|추가|삭제|제외|빼|넣어|설정|적용|로\s*(해|바꿔|설정)|으로\s*(해|바꿔|설정)/i;

type RiskField = "stop_loss_pct" | "take_profit_pct" | "trailing_stop_pct" | "max_mdd_limit_pct";
type PendingRiskChange = Partial<Record<RiskField, number>>;
// 백엔드가 이번 프롬프트에서 결정적으로 바꾼 리스크 필드(단일 진실 소스). null = 삭제.
// 프론트는 자체 정규식으로 재추측하지 않고 이 값을 그대로 신뢰한다.
type RiskOverrides = Partial<Record<RiskField, number | null>>;

function hasOverride(overrides: RiskOverrides | null | undefined, field: RiskField): boolean {
  return !!overrides && Object.prototype.hasOwnProperty.call(overrides, field);
}

const RISK_FIELD_PATTERNS: Record<RiskField, RegExp[]> = {
  stop_loss_pct: [/손절|stop\s*loss|손실|하락[^.]{0,8}(?:매도|팔)/i],
  take_profit_pct: [/익절|take\s*profit|목표\s*수익|수익\s*(확정|실현)|수익[^0-9]*(\d+(?:\.\d+)?)\s*%|수익[^.]{0,8}(?:매도|팔)/i],
  trailing_stop_pct: [/트레일링\s*스[탑톱]?|trailing|최고가\s*대비/i],
  max_mdd_limit_pct: [/mdd|낙폭/i],
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

function isRiskFieldSet(parsed: ParsedSummary | null | undefined, field: RiskField): boolean {
  if (!parsed) return false;
  const value = (parsed as unknown as Record<string, unknown>)[field];
  return typeof value === "number" && Number.isFinite(value);
}

function inferRiskFieldFromCoachText(
  previousCoachText: string,
  previousParsed?: ParsedSummary | null
): RiskField | null {
  const mentionedFields = (Object.keys(RISK_FIELD_PATTERNS) as RiskField[]).filter((field) =>
    hasMatch(previousCoachText, RISK_FIELD_PATTERNS[field])
  );

  if (mentionedFields.length === 1) {
    return mentionedFields[0];
  }

  // 코치가 손절을 맥락으로 다시 언급하면서 익절 추가를 권하는 경우처럼 여러 필드가 섞이면,
  // 이미 설정된 필드(재언급된 맥락)는 제외하고 코치가 새로 설정을 권하는 미설정 필드를 고른다.
  const unsetFields = mentionedFields.filter((field) => !isRiskFieldSet(previousParsed, field));
  if (unsetFields.length === 1) {
    return unsetFields[0];
  }

  return null;
}

function inferPendingRiskChange(
  userPrompt: string,
  previousCoachText?: string | null,
  previousParsed?: ParsedSummary | null
): PendingRiskChange | null {
  if (!previousCoachText) return null;
  const requestedRiskFields = detectRequestedRiskFields(userPrompt);
  if (requestedRiskFields.size > 0) return null;

  const percentage = extractPercentage(userPrompt);
  if (percentage === null) return null;

  const promptLooksLikeAnswer =
    /정해|설정|해줘|해주세요|조정|로\s*(해|바꿔|설정|조정)|으로\s*(해|바꿔|설정|조정)|추가|적용/.test(userPrompt)
    || /^\s*\d+(?:\.\d+)?\s*%\s*$/.test(userPrompt);
  if (!promptLooksLikeAnswer) return null;

  const inferredField = inferRiskFieldFromCoachText(previousCoachText, previousParsed);
  if (inferredField) {
    return { [inferredField]: percentage };
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

export function detectRequestedRiskFields(prompt: string): Set<RiskField> {
  const normalizedPrompt = prompt.trim();
  const fields = new Set<RiskField>();

  if (!normalizedPrompt) return fields;

  (Object.keys(RISK_FIELD_PATTERNS) as RiskField[]).forEach((field) => {
    if (hasMatch(normalizedPrompt, RISK_FIELD_PATTERNS[field])) {
      fields.add(field);
    }
  });

  return fields;
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
  requestedRiskFields: Set<RiskField>,
  pendingRiskChange?: PendingRiskChange | null,
  riskOverrides?: RiskOverrides | null
): ParsedSummary {
  const shouldUseRiskField = (field: RiskField) => {
    if (!requestedDomains.has("risk")) return false;
    if (requestedRiskFields.size === 0) return true;
    return requestedRiskFields.has(field);
  };

  // 우선순위: 백엔드 결정적 추출(riskOverrides) > 코치 맥락 추론(pendingRiskChange) > 프론트 정규식 게이트.
  const resolveRisk = (field: "stop_loss_pct" | "take_profit_pct" | "trailing_stop_pct"): number | null => {
    if (hasOverride(riskOverrides, field)) return riskOverrides![field] ?? null;
    const pending = pendingRiskChange?.[field];
    if (pending != null) return pending;
    return (shouldUseRiskField(field) ? (next[field] ?? previous[field]) : previous[field]) ?? null;
  };

  return {
    ...next,
    universe: requestedDomains.has("universe") ? next.universe : previous.universe,
    fundamental_filters: requestedDomains.has("entry") ? next.fundamental_filters : previous.fundamental_filters,
    entry_signals: requestedDomains.has("entry") ? next.entry_signals : previous.entry_signals,
    exit_signals: requestedDomains.has("exit") ? next.exit_signals : previous.exit_signals,
    max_positions: requestedDomains.has("portfolio") ? next.max_positions : previous.max_positions,
    hold_period_days: requestedDomains.has("exit") ? next.hold_period_days : previous.hold_period_days,
    rebalancing_period: requestedDomains.has("portfolio") ? next.rebalancing_period : previous.rebalancing_period,
    stop_loss_pct: resolveRisk("stop_loss_pct"),
    take_profit_pct: resolveRisk("take_profit_pct"),
    trailing_stop_pct: resolveRisk("trailing_stop_pct"),
    backtest_period: requestedDomains.has("backtest") ? next.backtest_period : previous.backtest_period,
    // 명시적 기간은 백엔드가 previous_parsed와 병합해 권위 있는 값을 내려주므로 그대로 따른다
    // (coarse한 backtest 도메인으로 게이트하면 '초기자금 변경' 같은 무관한 수정에 날짜가 지워진다).
    backtest_start_date: next.backtest_start_date ?? previous.backtest_start_date,
    backtest_end_date: next.backtest_end_date ?? previous.backtest_end_date,
    initial_capital: requestedDomains.has("backtest") ? next.initial_capital : previous.initial_capital,
  };
}

function mergeBacktestRequest(
  previous: StrategyBacktestRequest | null | undefined,
  next: StrategyBacktestRequest | null | undefined,
  requestedDomains: Set<RequestedDomain>,
  requestedRiskFields: Set<RiskField>,
  pendingRiskChange?: PendingRiskChange | null,
  riskOverrides?: RiskOverrides | null
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
  } else if (requestedRiskFields.size > 0) {
    for (const field of ["stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "max_mdd_limit_pct"] as RiskField[]) {
      if (!requestedRiskFields.has(field)) {
        mergedRisk[field] = previous.risk?.[field];
      } else if (next.risk?.[field] == null && previous.risk?.[field] !== undefined) {
        mergedRisk[field] = previous.risk[field];
      }
    }
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

  if (pendingRiskChange) {
    for (const field of Object.keys(pendingRiskChange) as RiskField[]) {
      if (pendingRiskChange[field] !== undefined) {
        mergedRisk[field] = pendingRiskChange[field];
      }
    }
  }

  // 백엔드 결정적 추출이 최우선 — 프론트 정규식 게이트 결과를 덮어쓴다(null = 삭제 반영).
  if (riskOverrides) {
    for (const field of Object.keys(riskOverrides) as RiskField[]) {
      mergedRisk[field] = riskOverrides[field];
    }
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
  // 백엔드가 결정적으로 추출한 리스크 필드(단일 진실 소스). 있으면 프론트 정규식보다 우선.
  riskOverrides?: RiskOverrides | null;
}) {
  const requestedDomains = detectRequestedDomains(params.userPrompt);
  const requestedRiskFields = detectRequestedRiskFields(params.userPrompt);
  const pendingRiskChange = inferPendingRiskChange(
    params.userPrompt,
    params.previousCoachText,
    params.previousParsed
  );
  const riskOverrides = params.riskOverrides ?? null;

  if (pendingRiskChange) {
    requestedDomains.add("risk");
    requestedRiskFields.add("trailing_stop_pct");
  }
  // 백엔드가 바꾼 리스크 필드가 있으면, 프론트가 프롬프트에서 risk를 못 읽어도 risk 변경으로 취급한다.
  if (riskOverrides && Object.keys(riskOverrides).length > 0) {
    requestedDomains.add("risk");
  }

  if (!params.previousParsed) {
    const firstRisk = { ...(pendingRiskChange ?? {}), ...(riskOverrides ?? {}) };
    const hasFirstRisk = Object.keys(firstRisk).length > 0;
    return {
      parsed: hasFirstRisk ? { ...params.nextParsed, ...firstRisk } : params.nextParsed,
      backtestRequest: hasFirstRisk
        ? {
            ...(params.nextBacktestRequest ?? params.previousBacktestRequest ?? {}),
            risk: {
              ...((params.previousBacktestRequest ?? params.nextBacktestRequest)?.risk ?? {}),
              ...((params.nextBacktestRequest ?? params.previousBacktestRequest)?.risk ?? {}),
              ...firstRisk,
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

  const parsed = mergeParsedSummary(
    params.previousParsed,
    params.nextParsed,
    requestedDomains,
    requestedRiskFields,
    pendingRiskChange,
    riskOverrides
  );
  const backtestRequest = mergeBacktestRequest(
    params.previousBacktestRequest,
    params.nextBacktestRequest,
    requestedDomains,
    requestedRiskFields,
    pendingRiskChange,
    riskOverrides
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

function numericValue(value: unknown): number | null {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function uniqueNumbers(values: number[], decimals = 2): number[] {
  return Array.from(
    new Set(
      values
        .filter((value) => Number.isFinite(value))
        .map((value) => Number(value.toFixed(decimals)))
    )
  ).sort((a, b) => a - b);
}

function boundedIntegerRange(value: number, min: number, max: number): number[] {
  const base = Math.round(value);
  const delta = Math.max(1, Math.round(base * 0.35));
  return uniqueNumbers([
    Math.max(min, base - delta),
    base,
    Math.min(max, base + delta),
  ], 0);
}

function boundedPercentRange(value: number): number[] {
  const delta = Math.max(2, Math.round(value * 0.4));
  return uniqueNumbers([
    Math.max(1, value - delta),
    value,
    Math.min(80, value + delta),
  ], 1);
}

function aroundValueRange(value: number): number[] {
  const abs = Math.abs(value);
  if (abs === 0) return [];
  const delta = Math.max(abs * 0.2, 0.1);
  return uniqueNumbers([value - delta, value, value + delta]);
}

function addRange(ranges: Record<string, unknown>, path: string, values: number[]) {
  if (values.length >= 2) {
    ranges[path] = values;
  }
}

function addConditionRanges(
  ranges: Record<string, unknown>,
  side: "entry" | "exit",
  conditions: Array<Record<string, unknown>> | undefined
) {
  conditions?.forEach((condition, index) => {
    const params = condition.params;
    if (!params || typeof params !== "object") return;
    const paramMap = params as Record<string, unknown>;
    const conditionId = typeof condition.id === "string" ? condition.id : "";
    const conditionType = typeof condition.type === "string" ? condition.type : "";
    const path = (key: string) => `${side}.conditions.${index}.params.${key}`;

    const shortMA = numericValue(paramMap.shortMA);
    if (shortMA !== null) addRange(ranges, path("shortMA"), boundedIntegerRange(shortMA, 2, 120));

    const longMA = numericValue(paramMap.longMA);
    if (longMA !== null) addRange(ranges, path("longMA"), boundedIntegerRange(longMA, 3, 250));

    const period = numericValue(paramMap.period);
    if (period !== null) addRange(ranges, path("period"), boundedIntegerRange(period, 2, 250));

    const thresholdKey = conditionId === "ai_model" || conditionId === "ai_drop_model" ? "threshold" : "value";
    const threshold = numericValue(paramMap[thresholdKey]);
    if (threshold !== null) {
      const range =
        conditionType === "filter"
          ? aroundValueRange(threshold)
          : threshold > 0 && threshold <= 100
            ? boundedPercentRange(threshold)
            : aroundValueRange(threshold);
      addRange(ranges, path(thresholdKey), range);
    }

    const stdDev = numericValue(paramMap.stdDev);
    if (stdDev !== null) {
      addRange(ranges, path("stdDev"), uniqueNumbers([Math.max(0.5, stdDev - 0.5), stdDev, stdDev + 0.5]));
    }
  });
}

export function buildWalkForwardParameterRanges(baseStrategy: StrategyBacktestRequest): Record<string, unknown> {
  const ranges: Record<string, unknown> = {};
  const risk = baseStrategy.risk ?? {};

  for (const field of ["stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "max_mdd_limit_pct"] as const) {
    const value = numericValue(risk[field]);
    if (value !== null && value > 0) addRange(ranges, `risk.${field}`, boundedPercentRange(value));
  }

  const maxHoldingDays = numericValue(risk.max_holding_days);
  if (maxHoldingDays !== null && maxHoldingDays > 1) {
    addRange(ranges, "risk.max_holding_days", boundedIntegerRange(maxHoldingDays, 2, 365));
  }

  addConditionRanges(ranges, "entry", baseStrategy.entry?.conditions);
  addConditionRanges(ranges, "exit", baseStrategy.exit?.conditions);

  return ranges;
}

export function hasWalkForwardParameterRanges(ranges: Record<string, unknown>): boolean {
  return Object.values(ranges).some((value) => Array.isArray(value) && value.length >= 2);
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
