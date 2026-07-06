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
  method?: "bayesian" | "grid";
  parameter_steps?: Record<string, number>;
  parameter_ranges?: Record<string, WalkForwardParameterRangeOverride>;
  // UI에서 고른 학습/검증 거래일 수 — 백엔드가 그대로 창 분할에 사용한다.
  is_bars?: number;
  oos_bars?: number;
  // 최적화에서 제외할 파라미터 라벨 — 해당 파라미터는 원래 설정값으로 고정된다.
  excluded_parameters?: string[];
}

export interface WalkForwardParameterRangeOverride {
  min: number;
  max: number;
  step: number;
  // 지정 시 min/max/step 대신 이 고정 후보값 집합만 탐색한다 (예: 이동평균 일선 5/10/20/60/120 중 선택).
  values?: number[];
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
  // "종목을 10개로 늘려줘"·"보유 종목을 5개로"처럼 종목/보유와 'N개'가 떨어져 있는 표현도
  // 포트폴리오 변경으로 인식한다(백엔드는 이미 max_positions를 추출하므로 도메인 게이트만 보완).
  portfolio: [/최대\s*\d+\s*종목|\d+\s*개\s*종목|\d+\s*종목|종목\s*수|보유\s*종목|종목[^.]{0,6}\d+\s*개|\d+\s*개[^.]{0,6}(?:종목|보유)|포트폴리오|리밸런싱|리밸런스|분산|집중/i],
  // 명시적 연도 범위('2002년부터 2005년까지', '2002~2005')도 백테스트 기간 변경으로 인식한다.
  backtest: [/백테스트|테스트 기간|전체 데이터|초기자금|자본금|원금|만원|억원?|\d[\d,]*원|(?:19|20)\d{2}\s*년?\s*(?:부터|까지|~|에서)|(?:19|20)\d{2}\s*[~\-]\s*(?:19|20)\d{2}/i],
};

// 결과 해석·평가 요청("결과 해석해줘", "성과 평가해줘", "원인이 뭐야")도 전략 재파싱이 아니라
// 코치 후속 질문이다 — 이유/원인/해석/평가/분석 계열을 포함한다(수정 동사가 있으면
// EXPLICIT_MODIFICATION_PATTERN이 우선해 수정 흐름으로 남는다).
const FOLLOW_UP_QUESTION_PATTERN =
  /어때|어떻게|어디|언제|왜|뭘|뭐를|무엇|추천|조언|괜찮|좋을까|될까|볼까|봐야|팔아야|팔까|사야|살까|매도해야|매수해야|청산해야|이유|원인|해석해|평가해|분석해/i;

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

// '10게'처럼 숫자 뒤 '게'는 종목 수 단위 '개'의 흔한 오타다(백엔드 nl_parser._compact와 동일 규칙).
// 도메인 게이트가 오타 때문에 변경을 놓쳐 백엔드가 올바로 추출한 값(max_positions 등)을
// 버리는 것을 막는다. 게로 시작하는 단어(게임·게시)는 문장 끝/조사 앞에서만 보정해 보존한다.
const COUNT_TYPO_RE = /(\d)\s*게(?=$|[\s은는이가을를로도만씩요])/g;

export function correctCountTypo(text: string): string {
  return text.replace(COUNT_TYPO_RE, "$1개");
}

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
  const normalizedPrompt = correctCountTypo(prompt.trim());
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

// 백엔드가 previous_parsed와 병합해 내려준 next는 권위 있는 완전한 전략이다 — 요청되지 않은
// 필드의 LLM 환각은 백엔드 `_gate_modification_hallucinations`가 이미 걸러냈다. 따라서 프론트는
// next를 그대로 신뢰하고, 백엔드가 알 수 없는 '코치 맥락' 리스크 답변(pendingRiskChange)만
// 그 위에 얹는다. 예전의 도메인 게이트(프롬프트 정규식으로 필드별 적용 여부를 재판정)는
// 백엔드 로직을 중복·재추측하다 오타 등으로 올바른 값을 버리는 버그의 원인이라 제거했다.
function mergeParsedSummary(
  next: ParsedSummary,
  pendingRiskChange?: PendingRiskChange | null,
  riskOverrides?: RiskOverrides | null
): ParsedSummary {
  // 우선순위: 백엔드 결정적 추출(riskOverrides) > 코치 맥락 추론(pendingRiskChange) > 백엔드 병합값.
  const resolveRisk = (field: "stop_loss_pct" | "take_profit_pct" | "trailing_stop_pct"): number | null => {
    if (hasOverride(riskOverrides, field)) return riskOverrides![field] ?? null;
    const pending = pendingRiskChange?.[field];
    if (pending != null) return pending;
    return next[field] ?? null;
  };

  return {
    ...next,
    stop_loss_pct: resolveRisk("stop_loss_pct"),
    take_profit_pct: resolveRisk("take_profit_pct"),
    trailing_stop_pct: resolveRisk("trailing_stop_pct"),
  };
}

// 백엔드가 병합·환각필터링해 내려준 next를 신뢰하고(권위 있는 완전한 실행 요청), 백엔드가
// 모르는 코치 맥락 리스크(pendingRiskChange)만 그 위에 얹는다. riskOverrides는 백엔드가 이미
// next.risk에 반영했지만, 단일 진실 소스로서 명시적으로 다시 덮어써 일관성을 보장한다.
function mergeBacktestRequest(
  previous: StrategyBacktestRequest | null | undefined,
  next: StrategyBacktestRequest | null | undefined,
  pendingRiskChange?: PendingRiskChange | null,
  riskOverrides?: RiskOverrides | null
): StrategyBacktestRequest | null {
  if (!next) return previous ?? null;

  const mergedRisk: Record<string, unknown> = { ...(next.risk ?? {}) };

  if (pendingRiskChange) {
    for (const field of Object.keys(pendingRiskChange) as RiskField[]) {
      if (pendingRiskChange[field] !== undefined) {
        mergedRisk[field] = pendingRiskChange[field];
      }
    }
  }

  if (riskOverrides) {
    for (const field of Object.keys(riskOverrides) as RiskField[]) {
      mergedRisk[field] = riskOverrides[field];
    }
  }

  return {
    ...next,
    risk: mergedRisk,
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
  // 백엔드가 권위 있는 병합·환각필터링 결과를 주므로, 필드별 도메인 게이트는 더 이상 쓰지 않는다.
  // requestedDomains는 clarification 재사용 판정에만 남긴다(수정 vs 후속질문 구분은 상위
  // isAdvisorFollowUpPrompt가 이미 처리). 코치 맥락 리스크(pendingRiskChange)만 백엔드가 모르므로
  // 프론트에서 얹는다.
  const requestedDomains = detectRequestedDomains(params.userPrompt);
  const pendingRiskChange = inferPendingRiskChange(
    params.userPrompt,
    params.previousCoachText,
    params.previousParsed
  );
  const riskOverrides = params.riskOverrides ?? null;

  const parsed = mergeParsedSummary(params.nextParsed, pendingRiskChange, riskOverrides);
  const backtestRequest = mergeBacktestRequest(
    params.previousBacktestRequest,
    params.nextBacktestRequest,
    pendingRiskChange,
    riskOverrides
  );

  return {
    parsed,
    backtestRequest,
    requestedDomains,
    shouldReusePreviousClarification: params.previousParsed
      ? clarificationLooksLikeEntryRegression(
          params.clarificationQuestion,
          params.previousParsed,
          requestedDomains
        )
      : false,
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
  const resolvedRanges = applyWalkForwardParameterSteps(
    baseStrategy,
    applyWalkForwardParameterRangeOverrides(baseStrategy, ranges, settings.parameter_ranges),
    settings.parameter_steps,
    settings.parameter_ranges
  );
  const filteredRanges = filterExcludedParameterRanges(
    baseStrategy,
    resolvedRanges,
    settings.excluded_parameters
  );

  return {
    base_strategy: baseStrategy,
    ranges: filteredRanges,
    n_splits: settings.n_splits,
    train_pct: settings.train_pct,
    anchor: settings.anchor,
    target_metric: settings.target_metric,
    n_trials: settings.n_trials,
    method: settings.method ?? "bayesian",
    ...(settings.is_bars ? { is_bars: settings.is_bars } : {}),
    ...(settings.oos_bars ? { oos_bars: settings.oos_bars } : {}),
  };
}

function filterExcludedParameterRanges(
  baseStrategy: StrategyBacktestRequest,
  ranges: Record<string, unknown>,
  excludedLabels?: string[]
): Record<string, unknown> {
  if (!excludedLabels || excludedLabels.length === 0) return ranges;

  const next: Record<string, unknown> = {};
  for (const [path, range] of Object.entries(ranges)) {
    const excluded = excludedLabels.some(
      (key) => key === path || rangePathMatchesStepLabel(baseStrategy, key, path)
    );
    if (!excluded) next[path] = range;
  }
  return next;
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

function boundedStopLossRange(value: number): number[] {
  const lowerDelta = Math.max(5, value * 0.8);
  const upperDelta = Math.max(10, value * 1.5);
  return uniqueNumbers([
    Math.max(1, value - lowerDelta),
    value,
    Math.min(50, value + upperDelta),
  ], 1);
}

function boundedTakeProfitRange(value: number): number[] {
  const lowerDelta = Math.max(10, value * 0.75);
  const upperDelta = Math.max(20, value * 2);
  return uniqueNumbers([
    Math.max(1, value - lowerDelta),
    value,
    Math.min(100, value + upperDelta),
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

function rangeBounds(value: unknown): { min: number; max: number } | null {
  if (Array.isArray(value)) {
    const numbers = value.map(numericValue).filter((item): item is number => item !== null);
    if (numbers.length < 2) return null;
    return { min: Math.min(...numbers), max: Math.max(...numbers) };
  }

  if (value && typeof value === "object" && (value as Record<string, unknown>).type === "number") {
    const spec = value as Record<string, unknown>;
    const min = numericValue(spec.min);
    const max = numericValue(spec.max);
    if (min === null || max === null || min >= max) return null;
    return { min, max };
  }

  return null;
}

function isIntegerLike(value: number): boolean {
  return Number.isInteger(value);
}

function numberRangeSpec(range: unknown, step: number): Record<string, number | string> | null {
  const bounds = rangeBounds(range);
  if (!bounds || !Number.isFinite(step) || step <= 0) return null;

  const clampedStep = Math.min(Math.max(step, 1e-6), Math.max(1e-6, bounds.max - bounds.min));
  const integerSpec = isIntegerLike(bounds.min) && isIntegerLike(bounds.max) && isIntegerLike(clampedStep);

  return {
    type: "number",
    min: integerSpec ? Math.round(bounds.min) : Number(bounds.min.toFixed(4)),
    max: integerSpec ? Math.round(bounds.max) : Number(bounds.max.toFixed(4)),
    step: integerSpec ? Math.round(clampedStep) : Number(clampedStep.toFixed(4)),
  };
}

function conditionForRangePath(
  baseStrategy: StrategyBacktestRequest,
  path: string
): Record<string, unknown> | null {
  const match = path.match(/^(entry|exit)\.conditions\.(\d+)\.params\./);
  if (!match) return null;
  const side = match[1] as "entry" | "exit";
  const index = Number(match[2]);
  const conditions = side === "entry" ? baseStrategy.entry?.conditions : baseStrategy.exit?.conditions;
  return conditions?.[index] ?? null;
}

function rangePathMatchesStepLabel(baseStrategy: StrategyBacktestRequest, label: string, path: string): boolean {
  const normalized = label.toLowerCase();

  if (/손절|stop\s*loss/i.test(label)) return path === "risk.stop_loss_pct";
  if (/익절|take\s*profit/i.test(label)) return path === "risk.take_profit_pct";
  if (/트레일링|trailing/i.test(label)) return path === "risk.trailing_stop_pct";
  if (/보유기간|holding/i.test(label)) return path === "risk.max_holding_days";
  if (/보유종목수|종목|positions?/i.test(label)) return path === "risk.max_positions";
  if (/리밸런싱|rebalanc/i.test(label)) return path === "risk.rebalancing_days";

  const condition = conditionForRangePath(baseStrategy, path);
  const haystack = `${path} ${condition?.id ?? ""} ${condition?.type ?? ""} ${JSON.stringify(condition?.params ?? {})}`.toLowerCase();

  if (/pbr/i.test(normalized)) return /pbr/.test(haystack);
  if (/per/i.test(normalized)) return /per/.test(haystack);
  if (/roe/i.test(normalized)) return /roe/.test(haystack);

  const compact = normalized.replace(/\s+/g, "");
  return !!compact && haystack.replace(/\s+/g, "").includes(compact);
}

// 사용자가 UI에서 확인하고 저장한 범위를 자동 생성 범위로 다시 좁히지 않는다 —
// 예전 클램프는 "표시된 범위 ≠ 실제 탐색 범위" 불일치의 원인이었다.
function normalizeRangeOverride(
  override: WalkForwardParameterRangeOverride
): WalkForwardParameterRangeOverride | null {
  const { min, max, step } = override;
  if (!Number.isFinite(min) || !Number.isFinite(max) || !Number.isFinite(step)) return null;

  const span = max - min;
  if (span <= 0) return null;

  const nextStep = Math.min(Math.max(step, 1e-6), span);
  return {
    min: Number(min.toFixed(4)),
    max: Number(max.toFixed(4)),
    step: Number(nextStep.toFixed(4)),
  };
}

function numberRangeSpecFromOverride(
  override: WalkForwardParameterRangeOverride
): Record<string, number | string> | null {
  const normalized = normalizeRangeOverride(override);
  if (!normalized) return null;

  const integerSpec =
    isIntegerLike(normalized.min) && isIntegerLike(normalized.max) && isIntegerLike(normalized.step);

  return {
    type: "number",
    min: integerSpec ? Math.round(normalized.min) : normalized.min,
    max: integerSpec ? Math.round(normalized.max) : normalized.max,
    step: integerSpec ? Math.round(normalized.step) : normalized.step,
  };
}

export function findWalkForwardRangeBoundsForLabel(
  baseStrategy: StrategyBacktestRequest,
  label: string,
  ranges: Record<string, unknown>
): { min: number; max: number } | null {
  const matches = Object.entries(ranges)
    .filter(([path]) => rangePathMatchesStepLabel(baseStrategy, label, path))
    .map(([, range]) => rangeBounds(range))
    .filter((value): value is { min: number; max: number } => value !== null);

  if (matches.length === 0) return null;

  return {
    min: Number(Math.min(...matches.map((item) => item.min)).toFixed(4)),
    max: Number(Math.max(...matches.map((item) => item.max)).toFixed(4)),
  };
}

// values가 있으면(고정 후보값 집합, 예: 이동평균 일선) min/max/step 스펙 대신 그 목록을
// 그대로 categorical 범위로 사용한다 — grid_optimizer/optuna_optimizer 둘 다 리스트 스펙을 지원한다.
function rangeSpecFromOverride(
  override: WalkForwardParameterRangeOverride
): Record<string, number | string> | number[] | null {
  if (override.values) {
    return override.values.length > 0 ? [...override.values] : null;
  }
  return numberRangeSpecFromOverride(override);
}

function applyWalkForwardParameterRangeOverrides(
  baseStrategy: StrategyBacktestRequest,
  ranges: Record<string, unknown>,
  parameterRanges?: Record<string, WalkForwardParameterRangeOverride>
): Record<string, unknown> {
  if (!parameterRanges || Object.keys(parameterRanges).length === 0) return ranges;

  const next = { ...ranges };
  for (const [key, override] of Object.entries(parameterRanges)) {
    // path 기반 디스크립터 키는 라벨 매칭 없이 정확히 해당 경로에만 적용
    if (key in ranges) {
      const spec = rangeSpecFromOverride(override);
      if (spec) next[key] = spec;
      continue;
    }
    for (const path of Object.keys(ranges)) {
      if (!rangePathMatchesStepLabel(baseStrategy, key, path)) continue;
      const spec = rangeSpecFromOverride(override);
      if (spec) next[path] = spec;
    }
  }

  return next;
}

function applyWalkForwardParameterSteps(
  baseStrategy: StrategyBacktestRequest,
  ranges: Record<string, unknown>,
  parameterSteps?: Record<string, number>,
  parameterRanges?: Record<string, WalkForwardParameterRangeOverride>
): Record<string, unknown> {
  if (!parameterSteps || Object.keys(parameterSteps).length === 0) return ranges;

  const next = { ...ranges };
  for (const [key, step] of Object.entries(parameterSteps)) {
    if (parameterRanges?.[key]) continue;
    // path 기반 디스크립터 키는 라벨 매칭 없이 해당 경로에만 적용
    if (key in ranges) {
      const spec = numberRangeSpec(ranges[key], step);
      if (spec) next[key] = spec;
      continue;
    }
    for (const [path, range] of Object.entries(ranges)) {
      if (!rangePathMatchesStepLabel(baseStrategy, key, path)) continue;
      const spec = numberRangeSpec(range, step);
      if (spec) next[path] = spec;
    }
  }

  return next;
}

// 엔진(engine/signals.py + indicator_columns.py)이 실제로 읽는 파라미터만 최적화 대상으로
// 삼는다. 여기 없는 파라미터는 엔진이 무시하므로, 탐색해도 결과가 변하지 않는 무의미한
// 차원이 된다. 엔진에 지표 파라미터를 추가하면 이 목록도 함께 갱신해야 한다.
function optimizableParamKeys(
  conditionId: string,
  conditionType: string,
  paramMap: Record<string, unknown>
): string[] {
  if (conditionType === "filter") return ["value"];

  switch (conditionId) {
    case "ma_crossover":
      return ["shortMA", "longMA"];
    case "rsi":
      return ["period", "value"];
    case "ema":
      // 듀얼 EMA 크로스오버면 short/long, 아니면 단일 period만 엔진이 사용
      return numericValue(paramMap.shortPeriod) !== null && numericValue(paramMap.longPeriod) !== null
        ? ["shortPeriod", "longPeriod"]
        : ["period"];
    case "macd":
      return ["fastPeriod", "slowPeriod", "signalPeriod"];
    case "stochastic":
      // 기간은 항상, 임계값(value)은 level 모드에서만 엔진이 읽는다
      return paramMap.mode === "level" ? ["period", "value"] : ["period"];
    case "bollinger_bands":
      return ["period", "stdDev"];
    case "cci":
      return ["period", "value"];
    case "adx":
      return ["value"];
    case "volume_spike":
      return ["period"];
    case "breakout":
      return ["lookbackPeriod"];
    case "trading_value":
    case "price_level":
    case "price":
      return ["value"];
    case "ai_model":
    case "ai_drop_model":
      return ["threshold"];
    default:
      return [];
  }
}

// 이동평균 크로스오버(ma_crossover)의 단기/장기 이평선은 실제 매매에서 쓰이는
// 표준 일선(5/10/20/60/120일선)만 사용하도록 강제한다 — 임의의 정수 기간(예: 13일)은
// 관행적으로 쓰이지 않아 탐색 공간을 키우기만 하고 실전 적용성이 없다.
// 단기<장기 제약은 grid_optimizer.satisfies_param_order_constraints가 백엔드에서 강제한다.
export const MA_CROSSOVER_PERIOD_VALUES = [5, 10, 20, 60, 120];

function rangeForParamKey(
  key: string,
  value: number,
  conditionType: string
): number[] {
  switch (key) {
    case "shortMA":
    case "longMA":
      return [...MA_CROSSOVER_PERIOD_VALUES];
    case "shortPeriod":
    case "fastPeriod":
      return boundedIntegerRange(value, 2, 120);
    case "longPeriod":
    case "slowPeriod":
      return boundedIntegerRange(value, 3, 250);
    case "period":
    case "lookbackPeriod":
    case "signalPeriod":
      return boundedIntegerRange(value, 2, 250);
    case "stdDev":
      return uniqueNumbers([Math.max(0.5, value - 0.5), value, value + 0.5], 2);
    default:
      // value / threshold 계열
      if (conditionType === "filter") return aroundValueRange(value);
      return value > 0 && value <= 100 ? boundedPercentRange(value) : aroundValueRange(value);
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

    for (const key of optimizableParamKeys(conditionId, conditionType, paramMap)) {
      const value = numericValue(paramMap[key]);
      if (value === null) continue;
      addRange(ranges, path(key), rangeForParamKey(key, value, conditionType));
    }
  });
}

export function buildWalkForwardParameterRanges(baseStrategy: StrategyBacktestRequest): Record<string, unknown> {
  const ranges: Record<string, unknown> = {};
  const risk = baseStrategy.risk ?? {};

  for (const field of ["stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "max_mdd_limit_pct"] as const) {
    const value = numericValue(risk[field]);
    if (value === null || value <= 0) continue;
    const range =
      field === "stop_loss_pct"
        ? boundedStopLossRange(value)
        : field === "take_profit_pct"
          ? boundedTakeProfitRange(value)
          : boundedPercentRange(value);
    addRange(ranges, `risk.${field}`, range);
  }

  const maxHoldingDays = numericValue(risk.max_holding_days);
  if (maxHoldingDays !== null && maxHoldingDays > 1) {
    addRange(ranges, "risk.max_holding_days", boundedIntegerRange(maxHoldingDays, 2, 365));
  }

  const maxPositions = numericValue(risk.max_positions);
  if (maxPositions !== null && maxPositions > 1) {
    addRange(ranges, "risk.max_positions", boundedIntegerRange(maxPositions, 1, 50));
  }

  addConditionRanges(ranges, "entry", baseStrategy.entry?.conditions);
  addConditionRanges(ranges, "exit", baseStrategy.exit?.conditions);

  return ranges;
}

// ── 워크포워드 파라미터 디스크립터 ─────────────────────────────────────────
// UI 칩을 배지 텍스트가 아니라 실제 탐색 공간의 경로(path)에서 직접 생성한다.
// 라벨 정규식 매칭에 의존하던 방식은 기술지표 파라미터(MACD 기간 등)를 칩으로
// 노출하지 못해 "표시 = 실행" 원칙이 깨지는 원인이었다.

export interface WalkForwardParameterDescriptor {
  /** 백테스트 요청 내 경로 — 오버라이드/제외의 키로 그대로 사용된다 */
  path: string;
  label: string;
}

const RISK_PARAM_LABELS: Record<string, string> = {
  stop_loss_pct: "손절라인",
  take_profit_pct: "익절라인",
  trailing_stop_pct: "트레일링 스탑",
  max_mdd_limit_pct: "MDD 한도",
  max_holding_days: "보유기간",
  max_positions: "보유종목수",
};

const INDICATOR_LABELS: Record<string, string> = {
  ma_crossover: "이동평균",
  rsi: "RSI",
  ema: "EMA",
  macd: "MACD",
  stochastic: "스토캐스틱",
  bollinger_bands: "볼린저",
  cci: "CCI",
  adx: "ADX",
  volume_spike: "거래량",
  breakout: "돌파",
  trading_value: "거래대금",
  price_level: "가격",
  price: "가격",
  ai_model: "AI 진입",
  ai_drop_model: "AI 청산",
};

const PARAM_KEY_LABELS: Record<string, string> = {
  shortMA: "단기",
  longMA: "장기",
  shortPeriod: "단기",
  longPeriod: "장기",
  fastPeriod: "단기",
  slowPeriod: "장기",
  signalPeriod: "시그널",
  period: "기간",
  lookbackPeriod: "기간",
  stdDev: "표준편차",
  value: "기준값",
  threshold: "임계값",
};

const FILTER_METRIC_LABELS: Record<string, string> = {
  pbr: "PBR",
  per: "PER",
  psr: "PSR",
  roe: "ROE",
  roe_or_gpa: "ROE",
  roa: "ROA",
  debt_ratio: "부채비율",
  current_ratio: "유동비율",
  quick_ratio: "당좌비율",
  reserve_ratio: "유보율",
  net_margin: "순이익률",
  gross_margin: "매출총이익률",
  revenue_growth: "매출액증가율",
  operating_income_growth: "영업이익증가율",
  net_income_growth: "순이익증가율",
  market_cap: "시가총액",
  trading_value: "거래대금",
};

function filterMetricLabel(conditionId: string): string {
  const normalized = conditionId.replace(/_filter$/, "").toLowerCase();
  return FILTER_METRIC_LABELS[normalized] ?? normalized.toUpperCase();
}

function labelForRangePath(baseStrategy: StrategyBacktestRequest, path: string): string {
  if (path.startsWith("risk.")) {
    const key = path.slice("risk.".length);
    return RISK_PARAM_LABELS[key] ?? key;
  }

  const condition = conditionForRangePath(baseStrategy, path);
  const key = path.split(".").pop() ?? path;
  const conditionId = typeof condition?.id === "string" ? condition.id : "";

  if (condition?.type === "filter") {
    return filterMetricLabel(conditionId);
  }

  const indicatorLabel = INDICATOR_LABELS[conditionId] ?? conditionId;
  const paramLabel = PARAM_KEY_LABELS[key] ?? key;
  return `${indicatorLabel} ${paramLabel}`.trim();
}

export function buildWalkForwardParameterDescriptors(
  baseStrategy: StrategyBacktestRequest,
  ranges?: Record<string, unknown>
): WalkForwardParameterDescriptor[] {
  const resolvedRanges = ranges ?? buildWalkForwardParameterRanges(baseStrategy);
  const descriptors = Object.keys(resolvedRanges).map((path) => ({
    path,
    label: labelForRangePath(baseStrategy, path),
  }));

  // 같은 지표가 진입/청산 양쪽에 있으면 라벨이 겹친다 — 구간을 붙여 구분한다.
  const labelCounts = new Map<string, number>();
  for (const descriptor of descriptors) {
    labelCounts.set(descriptor.label, (labelCounts.get(descriptor.label) ?? 0) + 1);
  }
  const seen = new Map<string, number>();
  return descriptors.map((descriptor) => {
    if ((labelCounts.get(descriptor.label) ?? 0) <= 1) return descriptor;
    const side = descriptor.path.startsWith("exit.") ? "청산" : "진입";
    const sided = `${descriptor.label} (${side})`;
    const nth = (seen.get(sided) ?? 0) + 1;
    seen.set(sided, nth);
    return { ...descriptor, label: nth > 1 ? `${sided} ${nth}` : sided };
  });
}

export function walkForwardRangeBoundsForPath(
  ranges: Record<string, unknown>,
  path: string
): { min: number; max: number } | null {
  return rangeBounds(ranges[path]);
}

export function hasWalkForwardParameterRanges(ranges: Record<string, unknown>): boolean {
  return Object.values(ranges).some((value) => {
    if (Array.isArray(value)) return value.length >= 2;
    const bounds = rangeBounds(value);
    return !!bounds && bounds.max > bounds.min;
  });
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
