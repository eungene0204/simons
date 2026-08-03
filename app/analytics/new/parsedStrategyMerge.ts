import factorRegistry from "@/data/fundamental-factors.json";
import type { ParsedSummary } from "./strategySummary";

export interface StrategyBacktestRequest {
  symbols?: string[];
  universe_id?: string;
  sector?: string | null;
  entry?: { conditions?: Array<Record<string, unknown>> };
  exit?: { conditions?: Array<Record<string, unknown>> };
  risk?: Record<string, unknown>;
  period?: string;
  // 명시적 백테스트 창(YYYY-MM-DD). 엔진은 이 창을 상대 기간(period)보다 우선한다.
  // 타입에 없으면 요청을 다루는 코드가 창의 존재를 모른 채 지나간다(2026-08-01 정리).
  startDate?: string | null;
  endDate?: string | null;
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
  risk: [/손절|익절|트레일링|리스크|mdd|낙폭|목표\s*(?:수익|이익)|(?:수익|이익)\s*(?:확정|실현)|(?:수익|이익)[^.]{0,20}(?:매도|팔)|손실|하락[^.]{0,8}(?:매도|팔)|stop\s*loss|take\s*profit|trailing/i],
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
// 백엔드가 이번 프롬프트에서 결정적으로 바꾼 리스크 필드(단일 진실 소스). null = 삭제.
// 프론트는 자체 정규식으로 재추측하지 않고 이 값을 그대로 신뢰한다.
type RiskOverrides = Partial<Record<RiskField, number | null>>;

function hasOverride(overrides: RiskOverrides | null | undefined, field: RiskField): boolean {
  return !!overrides && Object.prototype.hasOwnProperty.call(overrides, field);
}

const RISK_FIELD_PATTERNS: Record<RiskField, RegExp[]> = {
  stop_loss_pct: [/손절|stop\s*loss|손실|하락[^.]{0,8}(?:매도|팔)/i],
  take_profit_pct: [/익절|take\s*profit|목표\s*(?:수익|이익)|(?:수익|이익)\s*(확정|실현)|(?:수익|이익)[^0-9]*(\d+(?:\.\d+)?)\s*%|(?:수익|이익)[^.]{0,20}(?:매도|팔)/i],
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

// [프론트는 백엔드 판단에 관여하지 않는다] 코치 맥락으로 필드 없는 퍼센트 답변을 리스크 필드에
// 귀속하는 추론(inferPendingRiskChange 등)은 백엔드로 이관했다(resolve_coach_context_risk,
// FR-STR-019e) — previous_coach_text를 파스 요청에 실어 보내고 백엔드가 판단해 parsed에 반영한다.
// 프론트는 그 결과를 그대로 신뢰한다.

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

export function buildStrategyHorizonComparisonResponse(prompt: string): string | null {
  const normalizedPrompt = prompt.trim();
  const mentionsShortHorizon = /단기|단타|스윙|짧(?:게|은\s*(?:기간|보유|주기))/.test(normalizedPrompt);
  const mentionsLongHorizon = /장기|장투|오래\s*(?:보유|가져|들고)|긴\s*(?:기간|보유|주기)/.test(normalizedPrompt);
  const asksForComparison = /뭐가|어느|어떤|차이|비교|대비|\bvs\b|좋|나아|유리|선택|설명|알려/i.test(normalizedPrompt);

  if (!mentionsShortHorizon || !mentionsLongHorizon || !asksForComparison) {
    return null;
  }

  return [
    "단기와 장기는 어느 한쪽이 더 좋다고 정할 수 있는 관계가 아니라, 연구할 보유기간과 거래 빈도 가정이 다릅니다.",
    "",
    "• 단기 전략: 짧은 보유기간과 높은 거래 빈도를 가정하므로 수수료·슬리피지와 신호 변화의 영향을 확인합니다.",
    "• 장기 전략: 긴 보유기간과 낮은 거래 빈도를 가정하므로 장기간의 변동성과 최대 낙폭을 함께 확인합니다.",
    "",
    "전략으로 구성하려면 연구하려는 보유기간(며칠 또는 몇 개월)과 진입 조건을 알려주세요.",
  ].join("\n");
}

/** 익절 되묻기 문구·선택지. 입력이 없다 — 무엇을 물을지는 LLM이 고른 라벨이 이미 정했고,
 *  여기서는 그 라벨에 대응하는 정해진 문구를 고를 뿐이다(계약상 허용 패턴). */
export function takeProfitPrompt(): { message: string; suggestions: string[] } {
  return {
    message: "익절 기준은 매수가 대비 수익률로 설정합니다. 예시 값은 5%, 10%, 15%입니다. 적용할 익절 기준을 몇 %로 할까요?",
    suggestions: ["익절 5%", "익절 10%", "익절 15%"],
  };
}

/** 재무 지표 되묻기 문구·선택지 — 지표 키(정본 JSON)로 찾는다. 원문을 읽지 않는다. */
export function fundamentalFactorPromptFor(
  key: string,
): { message: string; suggestions: string[] } | null {
  const entry = (factorRegistry as FactorRegistryEntry[]).find((e) => e.key === key);
  if (!entry) return null;
  const direction = DIRECTION_WORD[entry.direction] ?? "이상";
  return {
    message: `${entry.label} 몇${entry.unit} ${direction}일 때 진입할까요?`,
    suggestions: entry.recommend.map(
      (v) => `${entry.label} ${fundamentalValueLabel(v, entry.unit)} ${direction}`,
    ),
  };
}

// [레거시 — 원문 정규식 레인] 되묻기 판정은 분류 LLM의 clarify_target으로 이관됐다
// (nl_interpretation_contract § 11-20). 아래 두 함수는 더 이상 턴 중재에 쓰이지 않는다.
export function buildTakeProfitPercentagePrompt(prompt: string): {
  message: string;
  suggestions: string[];
} | null {
  const normalizedPrompt = prompt.trim();
  if (
    !detectRequestedRiskFields(normalizedPrompt).has("take_profit_pct") ||
    extractPercentage(normalizedPrompt) !== null ||
    /빼|삭제|제외|없애|해제/.test(normalizedPrompt) ||
    /뭐야|무슨\s*뜻|뜻이|의미|개념|설명(?:해|해줘|해주세요)|어떻게\s*작동|원리/.test(normalizedPrompt) ||
    /왜|안\s*(?:돼|되|됨)|문제|오류|결과|백테스트|성과|거래\s*내역|분석|평가/.test(normalizedPrompt) ||
    /(?:익절|목표\s*(?:수익|이익)).{0,12}(?:설정돼|설정되어|적용돼|적용되어|포함돼|포함되어|있어\??$|있나\??$|있나요|있습니까)/.test(normalizedPrompt)
  ) {
    return null;
  }

  return {
    message: "익절 기준은 매수가 대비 수익률로 설정합니다. 예시 값은 5%, 10%, 15%입니다. 적용할 익절 기준을 몇 %로 할까요?",
    suggestions: ["익절 5%", "익절 10%", "익절 15%"],
  };
}

// 재무 팩터 추가 요청("영업이익률을 추가해 볼까?")에서 기준값이 없으면 되묻기 위한 표.
// [단일 소스] label·unit·direction·recommend는 data/fundamental-factors.json이 정본이며
// 백엔드 condition_builder와 공유한다(두 곳 하드코딩 → drift 제거). 지표 인식 pattern만
// JS 로컬(한글 경계 등 언어별 동작 차이). JSON 순서 = 감지 우선순위(배당성향/성장 → 배당수익률).
type FactorRegistryEntry = { key: string; label: string; unit: string; direction: string; recommend: number[] };

// 지표 인식 별칭(JS 로컬). JS \b는 ASCII 경계라 "PER도"의 한글 앞에서 경계가 성립한다.
const FUNDAMENTAL_FACTOR_PATTERNS: Record<string, RegExp> = {
  operating_margin: /영업이익률|영업\s*마진/,
  net_margin: /순이익률|순\s*마진/,
  gross_margin: /매출총이익률|총이익률/,
  per: /\bper\b|주가수익비율/i,
  pbr: /\bpbr\b|주가순자산/i,
  psr: /\bpsr\b|주가매출/i,
  pcr: /\bpcr\b|주가현금흐름/i,
  roe_or_gpa: /\broe\b|자기자본이익|자기자본수익/i,
  roa: /\broa\b|총자산이익|총자본순이익/i,
  ev_ebitda: /ev.?ebitda|이브이에비타|에비타/i,
  debt_ratio: /부채비율/,
  current_ratio: /유동비율/,
  payout_rate: /배당성향/,
  dividend_growth: /배당성장|배당증가/,
  dividend_yield: /배당수익률|배당률|고배당|배당/,
  market_cap: /시가총액|시총/,
  trading_value: /거래대금/,
};

const DIRECTION_WORD: Record<string, "이상" | "이하"> = { ">=": "이상", "<=": "이하" };

// 공유 JSON에서 데이터를 읽어 JS 패턴이 있는 지표만, JSON 순서(=우선순위) 그대로 스펙을 만든다.
const FUNDAMENTAL_FACTOR_SPECS: Array<{
  pattern: RegExp;
  label: string;
  unit: string;
  direction: "이상" | "이하";
  recommend: number[];
}> = (factorRegistry as FactorRegistryEntry[])
  .filter((entry) => FUNDAMENTAL_FACTOR_PATTERNS[entry.key])
  .map((entry) => ({
    pattern: FUNDAMENTAL_FACTOR_PATTERNS[entry.key],
    label: entry.label,
    unit: entry.unit,
    direction: DIRECTION_WORD[entry.direction] ?? "이상",
    recommend: entry.recommend,
  }));

function fundamentalValueLabel(value: number, unit: string): string {
  if (unit === "억" && value >= 10000 && value % 10000 === 0) return `${value / 10000}조`;
  return `${value}${unit}`;
}

/**
 * 기존 전략에 재무 팩터를 값 없이 추가하려는 요청("영업이익률을 추가해 볼까?")을 감지해
 * 그 지표의 기준을 되묻는다(추천 칩 포함). 값이 이미 있거나·정의/분석 질문·제거 요청이면 null.
 *
 * 칩("영업이익률 15% 이상")은 라벨이 붙은 완결 지시문이라, 클릭 시 그대로 재전송되면 값이
 * 있으므로 이 함수는 null을 반환하고 일반 수정 파싱(parse_strategy → 백엔드 병합)으로 흐른다.
 * buildTakeProfitPercentagePrompt와 동형 패턴(프론트 클라리피케이션).
 */
export function buildFundamentalFactorPrompt(prompt: string): {
  message: string;
  suggestions: string[];
} | null {
  const p = prompt.trim();
  if (!p) return null;
  // 추가/설정 의도가 있어야 한다(정의 질문·분석 질문·제거 요청은 제외).
  if (!/추가|넣|더해|더하|포함|고려|볼까|보자|쓰자|써보|적용|반영|걸[어자]|설정/.test(p)) return null;
  if (/뭐야|무슨\s*뜻|뜻이|의미|개념|설명(?:해|해줘|해주세요)|어떻게\s*작동|원리/.test(p)) return null;
  if (/빼|삭제|제외|없애|해제/.test(p)) return null;
  if (/왜|안\s*(?:돼|되|됨)|문제|오류|결과|성과|거래\s*내역|평가/.test(p)) return null;
  // 숫자가 있으면 기준값이 함께 온 것으로 보고 일반 수정 파싱으로 흘려보낸다(백엔드가 완결).
  if (/\d/.test(p)) return null;

  const spec = FUNDAMENTAL_FACTOR_SPECS.find((s) => s.pattern.test(p));
  if (!spec) return null;

  return {
    message: `${spec.label} 몇${spec.unit} ${spec.direction}일 때 진입할까요?`,
    suggestions: spec.recommend.map(
      (v) => `${spec.label} ${fundamentalValueLabel(v, spec.unit)} ${spec.direction}`,
    ),
  };
}

// 백엔드가 previous_parsed와 병합해 내려준 next는 권위 있는 완전한 전략이다 — 요청되지 않은
// 필드의 LLM 환각은 백엔드 `_gate_modification_hallucinations`가 이미 걸러냈다. 따라서 프론트는
// 백엔드가 병합·환각필터링·코치맥락해석을 모두 마쳐 내려준 next를 그대로 신뢰한다. riskOverrides는
// 백엔드가 이번 프롬프트에서 바꾼 리스크 필드의 단일 진실 소스로, next에 이미 반영됐지만 명시적으로
// 다시 덮어써 일관성을 보장한다(프론트는 자체 판단을 얹지 않는다).
function mergeParsedSummary(
  next: ParsedSummary,
  riskOverrides?: RiskOverrides | null
): ParsedSummary {
  const resolveRisk = (field: "stop_loss_pct" | "take_profit_pct" | "trailing_stop_pct"): number | null => {
    if (hasOverride(riskOverrides, field)) return riskOverrides![field] ?? null;
    return next[field] ?? null;
  };

  return {
    ...next,
    stop_loss_pct: resolveRisk("stop_loss_pct"),
    take_profit_pct: resolveRisk("take_profit_pct"),
    trailing_stop_pct: resolveRisk("trailing_stop_pct"),
  };
}

function shouldRemoveHallucinatedProfitGrowth(
  prompt: string,
  filters: ParsedSummary["fundamental_filters"]
): boolean {
  const compact = prompt.replace(/\s+/g, "");
  const mentionsProfitability = compact.includes("흑자");
  const mentionsProfitGrowth =
    /(?:당기)?순이익(?:증가율|성장률)/.test(compact);
  const mentionsDifferentProfitContext =
    /(?:영업이익|영업활동?현금흐름|현금흐름).{0,3}흑자/.test(compact);
  const mentionsProfitabilityHistory =
    /(?:흑자|적자).{0,6}(?:전환|탈출|연속|유지|지속)|연속.{0,4}(?:흑자|적자)|턴어라운드/.test(
      compact
    );
  const hasProfitableEpsFilter = filters.some(
    (filter) =>
      filter.metric.toLowerCase() === "eps" &&
      filter.operator === ">" &&
      filter.value === 0
  );

  return (
    mentionsProfitability &&
    !mentionsProfitGrowth &&
    !mentionsDifferentProfitContext &&
    !mentionsProfitabilityHistory &&
    hasProfitableEpsFilter
  );
}

function removeHallucinatedProfitGrowthFromParsed(
  parsed: ParsedSummary,
  prompt: string
): ParsedSummary {
  if (!shouldRemoveHallucinatedProfitGrowth(prompt, parsed.fundamental_filters)) {
    return parsed;
  }

  return {
    ...parsed,
    fundamental_filters: parsed.fundamental_filters.filter(
      (filter) => filter.metric.toLowerCase() !== "net_income_growth"
    ),
  };
}

function removeHallucinatedProfitGrowthFromRequest(
  request: StrategyBacktestRequest | null,
  shouldRemove: boolean
): StrategyBacktestRequest | null {
  if (!request || !shouldRemove || !request.entry?.conditions) return request;

  return {
    ...request,
    entry: {
      ...request.entry,
      conditions: request.entry.conditions.filter((condition) => {
        const id = typeof condition.id === "string" ? condition.id.toLowerCase() : "";
        return id.replace(/_filter$/, "") !== "net_income_growth";
      }),
    },
  };
}

function mergeBacktestRequest(
  previous: StrategyBacktestRequest | null | undefined,
  next: StrategyBacktestRequest | null | undefined,
  riskOverrides?: RiskOverrides | null
): StrategyBacktestRequest | null {
  if (!next) return previous ?? null;

  const mergedRisk: Record<string, unknown> = { ...(next.risk ?? {}) };

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

export function mergeStrategyModification(params: {
  previousParsed: ParsedSummary | null;
  nextParsed: ParsedSummary;
  previousBacktestRequest?: StrategyBacktestRequest | null;
  nextBacktestRequest?: StrategyBacktestRequest | null;
  userPrompt: string;
  // 백엔드가 결정적으로 추출한 리스크 필드(단일 진실 소스). 있으면 프론트 정규식보다 우선.
  riskOverrides?: RiskOverrides | null;
}) {
  // [프론트는 백엔드 판단을 재판정하지 않는다] 백엔드가 권위 있는 병합·환각필터링·코치맥락
  // 리스크 해석(resolve_coach_context_risk)까지 마친 결과를 주므로 프론트는 그대로 신뢰한다.
  // 예전의 되묻기 재판정(shouldReusePreviousClarification)·코치맥락 추론(inferPendingRiskChange)은
  // 모두 제거/백엔드 이관했다.
  const riskOverrides = params.riskOverrides ?? null;

  const mergedParsed = mergeParsedSummary(params.nextParsed, riskOverrides);
  const shouldRemoveProfitGrowth = shouldRemoveHallucinatedProfitGrowth(
    params.userPrompt,
    mergedParsed.fundamental_filters
  );
  const parsed = removeHallucinatedProfitGrowthFromParsed(
    mergedParsed,
    params.userPrompt
  );
  const mergedBacktestRequest = mergeBacktestRequest(
    params.previousBacktestRequest,
    params.nextBacktestRequest,
    riskOverrides
  );
  const backtestRequest = removeHallucinatedProfitGrowthFromRequest(
    mergedBacktestRequest,
    shouldRemoveProfitGrowth
  );

  return {
    parsed,
    backtestRequest,
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
    // 저장된 전략 DSL에는 symbols가 없을 수 있다(유니버스는 universe_id로 저장, 엔진이 PIT
    // 마스터로 종목을 재해석). 백엔드 스키마는 symbols 필드 자체를 요구하므로 빈 배열로 채운다.
    base_strategy: { ...baseStrategy, symbols: baseStrategy.symbols ?? [] },
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
  pcr: "PCR",
  roe: "ROE",
  roe_or_gpa: "ROE",
  roa: "ROA",
  debt_ratio: "부채비율",
  current_ratio: "유동비율",
  quick_ratio: "당좌비율",
  reserve_ratio: "유보율",
  net_margin: "순이익률",
  gross_margin: "매출총이익률",
  operating_margin: "영업이익률",
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
