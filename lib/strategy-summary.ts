import type { StrategyDSL } from "@/types/strategy";
import { getLanguage, t } from "@/lib/i18n";
import { formatUsd, isUsUniverseId } from "@/lib/us-symbols";

export interface ParsedSummary {
  description: string;
  universe: string[];
  // 섹터/업종 제한(정본 섹터명, 예: "반도체"). 복수면 배열(합집합). 없으면 null/생략.
  sector?: string | string[] | null;
  // 미국 유니버스의 업종 필터(GICS 정본 라벨) — 한국 sector와 분류 체계가 달라 필드가
  // 따로다(FR-STR-074 ⑩). 배지에 드러내지 않으면 유니버스가 조용히 좁혀진 것처럼 보인다.
  us_industry?: string | null;
  // 업종 제외 필터(엔진 v16.24, 정본 섹터명) — 배지에 드러내지 않으면 제외가 조용히 사라진 것처럼 보인다.
  exclude_sectors?: string[] | null;
  // ETF 유니버스 전용 테마/상품명 필터("반도체", "KODEX 200"). 없으면 null/생략.
  etf_theme?: string | null;
  // 신규 상장(IPO) 유니버스(FR-STR-073) — 상장일이 이 구간에 속하는 종목만 대상.
  // 대상 시기를 되묻는 중이면 개념만 true다.
  new_listing_only?: boolean | null;
  listing_from?: string | null;
  listing_to?: string | null;
  fundamental_filters: Array<{ metric: string; operator: string; value: number }>;
  entry_signals: Array<{
    indicator: string;
    signal_type?: string | null;
    mode?: string | null;
    timeframe?: string | null;
    operator?: string | null;
    value?: number | null;
    lookback_period?: number | null;
    // 이동평균 크로스 기간(백엔드 TechnicalSignal과 동일 계약) — 크로스 칩 기간 명시화
    // (2026-07-26)가 값으로 싣는다. 미지정이면 엔진 실효 기본값(5/20)으로 동작.
    short_period?: number | null;
    long_period?: number | null;
    period?: number | null;
  }>;
  exit_signals: Array<{
    indicator: string;
    signal_type?: string | null;
    mode?: string | null;
    operator?: string | null;
    value?: number | null;
    lookback_period?: number | null;
    short_period?: number | null;
    long_period?: number | null;
    period?: number | null;
  }>;
  // 진입 게이트 필터(추세·거래대금·RSI 결합) — 진입 신호와 AND 결합. 빌더 전용, 없으면 생략.
  entry_filters?: Array<{
    indicator: string;
    mode?: string | null;
    period?: number | null;
    operator?: string | null;
    value?: number | null;
  }>;
  ranking_metric?: string | null;
  ranking_lookback_days?: number | null;
  // 재무 팩터 랭킹의 방향(top=높은 순, bottom=낮은 순). 모멘텀('return')은 항상 top.
  ranking_direction?: "top" | "bottom" | null;
  // 분위 그룹 비교(FR-BT-060) — 랭킹 후보를 종목 수 동일한 G개 그룹으로 나눠 비교.
  ranking_quantile_groups?: number | null;
  // 분위 그룹당 보유 상한(FR-BT-060b) — 각 그룹이 자기 구간의 랭킹 상위 N종목만 보유.
  ranking_group_cap?: number | null;
  // 복합 순위 합산(FR-BT-063) — ranking_metric='composite'일 때 구성 지표(방향 포함).
  ranking_components?: Array<{
    metric: string;
    direction: "top" | "bottom";
    lookback_days?: number | null;
    // 최근 N거래일 제외(엔진 v16.14, 12-1 모멘텀)·묶음 점수 이름.
    skip_days?: number | null;
    group?: string | null;
    // 지표별 가중치(엔진 v16.24) — 없거나 1이면 동일 가중.
    weight?: number | null;
  }> | null;
  // 단일 수익률 랭킹의 최근 제외 기간(엔진 v16.14).
  ranking_skip_days?: number | null;
  // 잔차 반전 시그널(엔진 v16.17)의 잔차 누적 기간 — 회귀 기간은 ranking_lookback_days.
  ranking_accumulation_days?: number | null;
  // 비중 방식(엔진 v16.14·v16.28) — equal=동일 비중, inverse_volatility=변동성 역비중, market_cap=시가총액,
  // min_variance=최소 분산, risk_parity=위험 기여 균등, max_sharpe=최대 샤프, min_cvar=최소 CVaR, fixed=고정 배분.
  allocation_type?: "equal" | "inverse_volatility" | "market_cap" | "min_variance" | "risk_parity" | "max_sharpe" | "min_cvar" | "fixed" | null;
  allocation_lookback_days?: number | null;
  // 경쟁 격차 1차(엔진 v16.28) — 비어 있는 값은 되묻는 중(값 미정).
  target_weights?: Record<string, number> | null;
  rebalance_threshold_pct?: number | null;
  min_holding_days?: number | null;
  stop_cooldown_days?: number | null;
  trailing_stop_activation_pct?: number | null;
  entry_limit_pct?: number | null;
  exit_limit_pct?: number | null;
  entry_tranches?: { count?: number | null; step_pct?: number | null } | null;
  partial_take_profits?: Array<{ profit_pct?: number | null; sell_pct?: number | null }> | null;
  position_sizing?: { method: "atr_risk" | "kelly"; risk_per_trade_pct?: number | null; atr_period?: number | null; atr_multiple?: number | null; kelly_fraction?: number | null } | null;
  cash_asset?: string | null;
  absolute_momentum_threshold_pct?: number | null;
  execution_timing?: string | null;
  slippage_model?: string | null;
  // 매크로 조건 필터(엔진 v16.31) — 시리즈·값·비율이 비면 되묻는 중(값 미정).
  macro_filters?: MacroFilterSummary[] | null;
  // 전술 자산배분 템플릿(엔진 v16.29) — 자산 목록이 비면 되묻는 중.
  taa?: { model: string; offensive?: string[]; defensive?: string[]; canary?: string[]; top_n?: number | null } | null;
  // 종목당 비중 상한(%, 엔진 v16.18) — 편입·리밸런싱 시점 목표 비중의 상한.
  max_position_weight_pct?: number | null;
  max_sector_weight_pct?: number | null;
  universe_market_cap_top_n?: number | null;
  universe_liquidity_exclude_bottom_pct?: number | null;
  universe_market_cap_exclude_bottom_pct?: number | null;
  universe_exclude_loss_making?: string | null;
  universe_liquidity_lookback_days?: number | null;
  ranking_entry_delay_days?: number | null;
  ranking_expiry_days?: number | null;
  // 시장 국면 필터(엔진 v16.14) — 기간·비율이 비어 있으면 되묻는 중(값 미정).
  market_regime?: MarketRegimeSummary | null;
  // 계절 필터(엔진 v16.25) — 투자하는 달(1~12). 그 밖의 달은 전량 현금.
  seasonal_months?: number[] | null;
  // 목표 변동성(엔진 v16.25) — target_pct가 비어 있으면 되묻는 중(값 미정).
  volatility_target?: { target_pct?: number | null } | null;
  // 비율 선정(FR-BT-060) — 상위 X% 편입(개수 대신 비율). 있으면 max_positions보다 우선.
  max_positions_pct?: number | null;
  // 지정 종목(단일 종목) 백테스트 대상 종목코드(FR-STR-068). 비어 있으면 유니버스 전략.
  target_symbols?: string[];
  // 지정 종목이 어느 테마 조회에서 왔는지(없으면 사용자가 직접 지목한 종목).
  // 선정 범위 판정의 입력이다 — getSelectionScope 참조.
  theme_universe?: string | null;
  max_positions: number;
  // 보유 수의 출처 표식 — 사용자가 종목 수를 직접 말했는가(백엔드 컴파일러가 채운다).
  // max_positions는 기본값 10이 물질화되는 필드라 값만으로는 '말했다'와 '안 말했다'를
  // 구분할 수 없다. 선정 범위 판정의 입력이다 — getSelectionScope 참조.
  max_positions_explicit?: boolean | null;
  hold_period_days: number | null;
  rebalancing_period: string;
  // 리밸런싱 방식(FR-BT-067) — 'reconstitute'(종목 교체) | 'weights_only'(비중 조정).
  // 리밸런싱을 켠 KR 전략에서만 사용자가 고른다(미국 레인은 이번 범위 밖).
  rebalance_method?: string | null;
  stop_loss_pct: number | null;
  take_profit_pct: number | null;
  trailing_stop_pct?: number | null;
  backtest_period: string;
  backtest_start_date?: string | null;
  backtest_end_date?: string | null;
  initial_capital: number;
  // 거래 비용(%, 백엔드 ParsedStrategy 단위). 수수료·슬리피지는 기본값이 물질화되므로
  // 사용자가 말했는지는 explicit_fields(provenance)가 가른다. 거래세 null=시행일 기준 법정 세율.
  fee_rate?: number | null;
  slippage_rate?: number | null;
  sell_tax_rate?: number | null;
  // 정액 적립식(엔진 v16.20) — 둘 다 있고 지정 종목이 있어야 적립식이다.
  contribution_amount?: number | null;
  contribution_period?: string | null;
  // 정기 인출(엔진 v16.33) — 적립과 같은 계약(둘 다 있고 대상이 있어야 인출이다).
  withdrawal_amount?: number | null;
  withdrawal_period?: string | null;
  // 비교 지수(엔진 v16.33) — 사용자가 고른 정본 id. 없으면 유니버스 기본 지수.
  benchmark?: string | null;
  // 조건부 납입액 규칙(엔진 v16.21) — 납입일에 signal이 성립하면 그 회차 납입액을 amount로(set) / amount만큼 더(add).
  contribution_rules?: Array<{ signal: ParsedSummary["entry_signals"][number]; amount: number; mode: "set" | "add" }> | null;
  // 현금 풀(엔진 v16.22) — 보유 현금에서 꺼내 사는 적립. reserve_stated만 참이면 하한 수준을 되묻는 중이다.
  cash_pool?: { reserve_pct?: number | null; reserve_amount?: number | null; reserve_stated?: boolean; max_buy_pct?: number | null } | null;
}

interface BacktestRequestLike {
  symbols?: string[];
  // 지정 종목 백테스트의 표시용 메타데이터(코드→종목명). 백엔드 to_backtest_request가 채운다.
  target_stocks?: Array<{ symbol: string; name?: string }> | null;
}

type LegacyStrategySummaryFields = {
  universe?: string | string[] | { id?: string; filters?: Record<string, unknown> };
  fundamental_filters?: Array<{ metric: string; operator: string; value: number }>;
  entry_signals?: Array<{ indicator: string; signal_type?: string | null; mode?: string | null; lookback_period?: number | null; short_period?: number | null; long_period?: number | null; period?: number | null }>;
  exit_signals?: Array<{ indicator: string; signal_type?: string | null; mode?: string | null; lookback_period?: number | null; short_period?: number | null; long_period?: number | null; period?: number | null }>;
  max_positions?: number | null;
  hold_period_days?: number | null;
  rebalancing_period?: string | null;
  rebalance_method?: string | null;
  stop_loss_pct?: number | null;
  take_profit_pct?: number | null;
  trailing_stop_pct?: number | null;
  // 저장된 settings에는 실행 창·초기 자본도 함께 남는다(backtestCache.upsertStrategyForResult,
  // save-with-backtest의 dsl = 실행 요청) — 저장 전략 페이지도 기간·자본 행을 정확히 보이기 위해 읽는다.
  period?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  initial_capital?: number | null;
};

export const UNIVERSE_LABELS: Record<string, string> = {
  kospi: "KOSPI",
  kosdaq: "KOSDAQ",
  kospi200: "KOSPI 200",
  etf: "ETF",
  KOR_KOSPI200: "KOSPI 200",
  KOR_KOSDAQ150: "KOSDAQ 150",
  US_TECH_TOP10: "미국 테크 Top 10",
  CRYPTO_TOP10: "크립토 Top 10",
};

export const METRIC_LABELS: Record<string, string> = {
  per: "PER",
  pbr: "PBR",
  psr: "PSR",
  pcr: "PCR",
  ev_ebitda: "EV/EBITDA",
  roe_or_gpa: "ROE",
  // 레거시 표기(백엔드 별칭 정규화 이전에 저장된 전략)도 라벨 없이 'roe >= 15'로 날것
  // 노출되지 않게 매핑한다.
  roe: "ROE",
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
  // 백엔드 FundamentalFilter.metric enum 34개를 전부 덮는다 — 빠지면 요약 카드에 'ocf_growth >= 10'
  // 처럼 내부 식별자가 그대로 나간다(2026-09-15 KR 예시 화면 전수 조사 실측). 회귀:
  // lib/strategy-summary.labels.test.ts(백엔드 enum × 이 표 전수 대조).
  ev_ebit: "EV/EBIT",
  eps_growth: "EPS증가율",
  ebitda_growth: "EBITDA증가율",
  ocf_growth: "영업현금흐름증가율",
  fcf_growth: "잉여현금흐름증가율",
  roic: "ROIC",
  fcf_margin: "FCF 마진",
  fcf_yield: "FCF 수익률",
  asset_growth: "자산성장률",
  accruals_ratio: "발생액 비율",
  f_score: "F-score",
  ncav_ratio: "시가총액/NCAV 비율",
  revenue_growth_qoq: "매출 분기성장률(QoQ)",
  revenue_growth_yoy: "매출 분기성장률(YoY)",
  operating_income_growth_qoq: "영업이익 분기성장률(QoQ)",
  operating_income_growth_yoy: "영업이익 분기성장률(YoY)",
  net_income_growth_qoq: "순이익 분기성장률(QoQ)",
  net_income_growth_yoy: "순이익 분기성장률(YoY)",
  market_cap: "시총",
  trading_value: "거래대금",
  dividend_yield: "배당수익률",
  payout_rate: "배당성향",
  dividend_growth: "배당성장률",
  dividend_streak_years: "연속 배당 연수",
  eps: "EPS",
  ebit: "영업이익",
  net_income: "당기순이익",
  owner_net_income: "지배주주순이익",
  operating_cf_amount: "영업활동현금흐름",
  investing_cf_amount: "투자활동현금흐름",
  financing_cf_amount: "재무활동현금흐름",
};

const KO_NUMBER_FORMAT = new Intl.NumberFormat("ko-KR");

// **억원 단위** 금액을 '3,000억' / '3조' / '1조 5,000억' 형태로 표시한다.
// 시총 필터의 정본 단위가 억원이다(레지스트리 indicator_registry market_cap "억원",
// 엔진 data_resolver `(close × shares) / 1e8`) — 단위 없이 '3000'만 보이면 사용자는
// 원·억·조 중 무엇인지 알 수 없다(2026-08-01 지적).
export function formatEokAmount(eok: number): string {
  if (!Number.isFinite(eok)) return String(eok);
  // 영어 표기: 억/조 단위 대신 KRW 십억(B)·백만(M) 단위로 환산한다.
  if (getLanguage() === "en") return formatEokAmountEn(eok);

  const rounded = Math.round(eok);
  if (rounded < 10_000) {
    return t("{0}억", KO_NUMBER_FORMAT.format(rounded));
  }

  const jo = Math.floor(rounded / 10_000);
  const remainderEok = rounded % 10_000;
  return remainderEok === 0
    ? t("{0}조", KO_NUMBER_FORMAT.format(jo))
    : t("{0}조 {1}억", KO_NUMBER_FORMAT.format(jo), KO_NUMBER_FORMAT.format(remainderEok));
}

function formatEokAmountEn(eok: number): string {
  const won = eok * 100_000_000;
  const trim = (v: number) => KO_NUMBER_FORMAT.format(Number(v.toFixed(v >= 100 ? 0 : 1)));
  if (won >= 1_000_000_000_000) return `₩${trim(won / 1_000_000_000_000)}T`;
  if (won >= 1_000_000_000) return `₩${trim(won / 1_000_000_000)}B`;
  return `₩${trim(won / 1_000_000)}M`;
}

// **원 단위** 큰 금액(>=1억)을 한글 단위로 표시한다(초기자금 등).
// 1억 미만이거나 숫자가 아니면 원본을 그대로 둔다(단위가 모호한 값 오변환 방지).
// 억 미만 잔액은 **끊어서 함께 적는다**("1억 5,000만"). 억 단위 표시기(formatEokAmount)에
// 넘겨 반올림하면 사용자가 말한 금액이 바뀐다 — 1억 5천만원이 '2억원'으로 보였다
// (2026-09-10 실측). 만원 단위로 떨어지지 않는 금액은 원 단위 그대로 둔다.
export function formatMarketCapValue(value: number): string {
  if (!Number.isFinite(value) || value < 100_000_000) return String(value);
  if (getLanguage() === "en") return formatEokAmountEn(value / 100_000_000);

  const jo = Math.floor(value / 1_000_000_000_000);
  const eok = Math.floor((value % 1_000_000_000_000) / 100_000_000);
  const man = (value % 100_000_000) / 10_000;
  if (!Number.isInteger(man)) return KO_NUMBER_FORMAT.format(value);

  const parts: string[] = [];
  if (jo) parts.push(t("{0}조", KO_NUMBER_FORMAT.format(jo)));
  if (eok) parts.push(t("{0}억", KO_NUMBER_FORMAT.format(eok)));
  if (man) parts.push(t("{0}만", KO_NUMBER_FORMAT.format(man)));
  return parts.join(" ");
}

// 펀더멘털 필터 배지 문자열을 만든다. 시총은 한글 단위로, 거래대금은 억 단위 표시, 나머지는 원본 숫자로 표시.
// 진입 게이트 필터(추세·거래대금·RSI 결합) 배지 라벨. 인식 못 하면 빈 문자열(배지 생략).
export function formatEntryFilter(filter: {
  indicator: string;
  mode?: string | null;
  period?: number | null;
  operator?: string | null;
  value?: number | null;
}): string {
  if (filter.indicator === "ema" && (filter.mode === "above" || filter.mode === "below")) {
    return t("{0}일선 {1}", filter.period ?? 200, filter.mode === "above" ? t("위") : t("아래"));
  }
  if (filter.indicator === "trading_value") {
    return t("거래대금 {0} 이상", formatEokAmount(filter.value ?? 100));
  }
  if (filter.indicator === "rsi") {
    return t("RSI {0} 이하", filter.value ?? 30);
  }
  return "";
}

export function formatFundamentalFilter(filter: {
  metric: string;
  operator: string;
  value: number;
}): string {
  const label = t(METRIC_LABELS[filter.metric] ?? filter.metric);
  // EPS·영업이익 부호 필터는 '흑자/적자' 키워드 조건의 표현형 — 사용자 어휘로 배지를 만든다.
  if (filter.metric === "eps" && filter.value === 0) {
    if (filter.operator === ">") return t("흑자 기업 (EPS > 0)");
    if (filter.operator === "<") return t("적자 기업 (EPS < 0)");
  }
  if (filter.metric === "ebit" && filter.value === 0) {
    if (filter.operator === ">") return t("영업이익 흑자 기업");
    if (filter.operator === "<") return t("영업이익 적자 기업");
  }
  let value: string;
  if (
    filter.metric === "market_cap" ||
    filter.metric === "net_income" ||
    filter.metric === "owner_net_income" ||
    filter.metric === "operating_cf_amount" ||
    filter.metric === "investing_cf_amount" ||
    filter.metric === "financing_cf_amount"
  ) {
    // 필터 값은 억원 단위다 — 원 단위로 오해해 변환하면 3000억이 '3000'으로 보인다.
    value = formatEokAmount(filter.value);
  } else if (filter.metric === "trading_value") {
    value = formatEokAmount(filter.value);
  } else {
    value = String(filter.value);
  }
  return `${label} ${filter.operator} ${value}`;
}

// 초기 자금 상한(100억원). 백엔드 정본은 `backend/engine/nl_parser.py MAX_INITIAL_CAPITAL`이며
// 여기 값은 설정 패널이 서버 왕복 전에 같은 판정을 하기 위한 사본이다 — 바꿀 때 함께 바꾼다.
// 상한이 필요한 이유: 1회 매수 금액이 전일 거래대금의 10%를 넘으면 엔진이 그 종목의 진입을
// 통째로 지우므로(engine/loader.py check_liquidity), 시장이 소화 못 할 자금은 "거래대금 부족"
// 으로 전 종목이 빠진 빈 백테스트가 된다.
export const MAX_INITIAL_CAPITAL = 10_000_000_000;

// 백테스트 가능한 데이터 구간. 백엔드 정본은 `backend/engine/nl_parser.py`의
// DATA_FLOOR_DATE·data_ceiling_date()이며, 여기 값은 설정 패널이 서버 왕복 전에 같은
// 판정을 하기 위한 사본이다. 상한은 '오늘' — 미래는 시뮬레이션할 수 없다.
export const BACKTEST_DATA_FLOOR_DATE = "1996-01-01";

export function backtestDataCeilingDate(today: Date = new Date()): string {
  const local = new Date(today.getTime() - today.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

// 초기자금 배지 문자열을 만든다. 1억 이상이면 '50억원'처럼 한글 단위로, 미만이면 콤마 포함 원 단위로 표시.
export function formatInitialCapital(value: number, options?: { usd?: boolean }): string {
  // 미국 전략의 초기 자본은 엔진 숫자가 곧 달러다(시장 통화) — 원화 표기($10,000을
  // "10,000원")로 나가면 값 자체가 오독된다(2026-08-26).
  if (options?.usd) return formatUsd(value);
  if (Number.isFinite(value) && value >= 100_000_000) {
    const amount = formatMarketCapValue(value);
    return getLanguage() === "en" ? amount : t("{0}원", amount);
  }
  return t("{0}원", KO_NUMBER_FORMAT.format(value));
}

/** 전략의 유니버스가 미국 시장인가 — 초기 자본 통화(달러) 표기 판정. */
export function isUsParsedUniverse(universe: string[] | null | undefined): boolean {
  return (universe ?? []).some((u) => isUsUniverseId(normalizeUniverseId(u)));
}

export const PERIOD_LABELS: Record<string, string> = {
  "1y": "1년",
  "3y": "3년",
  "5y": "5년",
  full: "전체",
};

// 명시 창의 길이가 딱 떨어지면 사용자가 말한 단위("10년"·"18개월")로 되돌린다.
// '최근 10년간' 같은 버킷 밖 기간은 명시 날짜로 변환돼 저장되므로(BacktestSpec), 창만
// 보여주면 사용자는 자기가 말한 기간이 반영됐는지 알 수 없다(2026-08-02 지적).
// 길이 계산은 날짜 산술이지 해석이 아니다 — 딱 떨어지지 않는 창(직접 지정한 연도 범위 등)은
// null을 돌려 원래의 창 표기를 그대로 쓴다.
export function explicitWindowSpanLabel(
  from: string | null | undefined,
  to: string | null | undefined,
): string | null {
  if (!from || !to) return null;
  const start = new Date(`${from}T00:00:00Z`);
  const end = new Date(`${to}T00:00:00Z`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
  if (start.getUTCDate() !== end.getUTCDate()) return null;
  const months =
    (end.getUTCFullYear() - start.getUTCFullYear()) * 12 +
    (end.getUTCMonth() - start.getUTCMonth());
  if (months <= 0) return null;
  return months % 12 === 0 ? t("{0}년", months / 12) : t("{0}개월", months);
}

// 백테스트 기간 배지. 명시 날짜가 있으면 그 창을 그대로 보여준다 — 상대 기간 라벨
// ("5년")은 신규 상장 코호트처럼 창이 조정된 경우 실제 실행 구간과 어긋난다.
// 창의 길이가 딱 떨어지면 그 길이를 앞세운다(사용자가 말한 '10년'이 반영됐는지 보이도록).
export function formatBacktestPeriodLabel(parsed: {
  backtest_period?: string | null;
  backtest_start_date?: string | null;
  backtest_end_date?: string | null;
}): string | null {
  const from = parsed.backtest_start_date ?? null;
  const to = parsed.backtest_end_date ?? null;
  const span = explicitWindowSpanLabel(from, to);
  if (span) return `${span} (${from} ~ ${to})`;
  if (from) return `${from} ~ ${to ?? t("현재")}`;
  if (to) return `~ ${to}`;
  const period = parsed.backtest_period ? String(parsed.backtest_period).toLowerCase() : null;
  if (!period) return null;
  return t(PERIOD_LABELS[period] ?? period);
}

export const REBAL_LABELS: Record<string, string> = {
  none: "없음",
  daily: "매일",
  weekly: "매주",
  monthly: "매월",
  bimonthly: "격월",
  quarterly: "분기",
  semiannual: "반기",
  yearly: "매년",
};

// 리밸런싱 방식(FR-BT-067) 표기. 백엔드 칩 정본(engine/strategy_slots.py
// REBALANCE_METHOD_CHIP_VALUES)이 정하는 두 값과 1:1이다.
export const REBAL_METHOD_LABELS: Record<string, string> = {
  reconstitute: "종목 교체",
  weights_only: "비중 조정",
};

/** 리밸런싱 배지 문구 — 주기와 방식을 한 칸에 함께 보인다.
 *  방식이 배지에 없으면 사용자가 고른 값이 화면 어디에도 남지 않아, 무엇으로 돌았는지
 *  결과만 보고는 알 수 없다(주기만 보이던 종전 표기). 방식 미지정(기존 전략)은 종전
 *  표기를 그대로 둔다 — 고르지 않은 값을 화면이 확정해 보이지 않는다. */
export function formatRebalancingText(
  period: string | null | undefined,
  method: string | null | undefined,
  translate: (template: string, ...values: Array<string | number>) => string,
): string | undefined {
  if (!period || period === "none") return undefined;
  const base = translate("{0} 리밸런싱", translate(REBAL_LABELS[period] ?? period));
  const methodLabel = method ? REBAL_METHOD_LABELS[method] : undefined;
  return methodLabel ? `${base} · ${translate(methodLabel)}` : base;
}

export const FUNDAMENTAL_FILTER_SECTION_LABEL = "진입 신호";

export const INDICATOR_LABELS: Record<string, string> = {
  ma_crossover: "MA 크로스",
  rsi: "RSI",
  ema: "EMA 크로스",
  macd: "MACD",
  bollinger_bands: "볼린저밴드",
  breakout: "브레이크아웃",
  volume_spike: "거래량 급증",
  volume_ratio: "거래량 배수",
  trading_value_ratio: "거래대금 배수",
  stochastic: "스토캐스틱",
  cci: "CCI",
  adx: "ADX",
  volatility: "변동성",
  williams_r: "Williams %R",
  mfi: "MFI",
  roc: "ROC",
  relative_return: "시장 대비 초과수익률",
  // 엔진 TechnicalSignal.indicator(backend/engine/nl_parser.py)에 있는 지표는 **빠짐없이**
  // 여기 라벨이 있어야 한다 — 없으면 배지가 내부 변수명을 그대로 노출한다
  // (2026-08-18: 'trading_value'가 진입 신호 배지로 그대로 나갔다).
  // 누락 감지는 backend/tests/test_nl_parser_overrides.py의 라벨 대조 테스트가 한다.
  trading_value: "거래대금",
  ai_model: "AI 매수 예측",
  ai_drop_model: "AI 하락 예측",
  // 캔들 패턴(엔진 v16.29)
  candle_hammer: "망치형 캔들 패턴",
  candle_hanging_man: "교수형 캔들 패턴",
  candle_inverted_hammer: "역망치형 캔들 패턴",
  candle_shooting_star: "유성형 캔들 패턴",
  candle_doji: "도지 캔들 패턴",
  candle_bullish_engulfing: "상승 장악형 캔들 패턴",
  candle_bearish_engulfing: "하락 장악형 캔들 패턴",
  candle_piercing_line: "관통형 캔들 패턴",
  candle_dark_cloud_cover: "먹구름형 캔들 패턴",
  candle_morning_star: "샛별형 캔들 패턴",
  candle_evening_star: "저녁별형 캔들 패턴",
  candle_three_white_soldiers: "적삼병 캔들 패턴",
  candle_three_black_crows: "흑삼병 캔들 패턴",
};

const OPERATOR_KO_LABELS: Record<string, string> = {
  "<": "미만",
  "<=": "이하",
  ">": "초과",
  ">=": "이상",
};

// 크로스 계열(이동평균/EMA/MACD)은 방향에 따라 골든/데드로 구체화한다.
// 매수(buy)/진입=상향 돌파=골든크로스, 매도(sell)/청산=하향 돌파=데드크로스.
const DIRECTIONAL_CROSS_LABELS: Record<string, { golden: string; dead: string }> = {
  ma_crossover: { golden: "MA 골든크로스", dead: "MA 데드크로스" },
  ema: { golden: "EMA 골든크로스", dead: "EMA 데드크로스" },
  macd: { golden: "MACD 골든크로스", dead: "MACD 데드크로스" },
};

/** 이동평균(SMA/EMA) 신호의 기간까지 담은 라벨. 기간을 모르면 null(일반 라벨로 폴백). */
function movingAverageLabel(
  signal: { indicator: string; short_period?: number | null; long_period?: number | null; period?: number | null; mode?: string | null },
  isDown: boolean,
): string | null {
  const isEma = signal.indicator === "ema";
  if (!isEma && signal.indicator !== "ma_crossover") return null;
  const short = signal.short_period ?? null;
  // 선이 하나뿐인 조건(가격 vs 이동평균)의 기간은 long_period에 담겨 온다(컴파일러 계약).
  const long = signal.long_period ?? signal.period ?? null;
  if (long == null) return null;
  const stays = signal.mode === "above" || signal.mode === "below";
  const down = stays ? signal.mode === "below" : isDown;
  const priceRelative = short == null || short === 1;

  if (isEma) {
    if (priceRelative) {
      if (stays) return down ? t("종가가 EMA{0} 아래 유지", long) : t("종가가 EMA{0} 위 유지", long);
      return down ? t("가격 EMA{0} 하향 돌파", long) : t("가격 EMA{0} 상향 돌파", long);
    }
    if (stays) {
      return down ? t("EMA{0}이 EMA{1} 아래 유지", short, long) : t("EMA{0}이 EMA{1} 위 유지", short, long);
    }
    return down ? t("EMA{0}-EMA{1} 데드크로스", short, long) : t("EMA{0}-EMA{1} 골든크로스", short, long);
  }
  if (priceRelative) {
    if (stays) return down ? t("종가가 {0}일선 아래 유지", long) : t("종가가 {0}일선 위 유지", long);
    return down ? t("종가가 {0}일선 하향 이탈", long) : t("종가가 {0}일선 상향 돌파", long);
  }
  if (stays) {
    return down ? t("{0}일선이 {1}일선 아래 유지", short, long) : t("{0}일선이 {1}일선 위 유지", short, long);
  }
  return down ? t("{0}일선-{1}일선 데드크로스", short, long) : t("{0}일선-{1}일선 골든크로스", short, long);
}

export function getSignalLabel(
  signal: {
    indicator: string;
    signal_type?: string | null;
    mode?: string | null;
    operator?: string | null;
    value?: number | null;
    lookback_period?: number | null;
    short_period?: number | null;
    long_period?: number | null;
    period?: number | null;
    timeframe?: string | null;
  },
  context: "entry" | "exit"
): string {
  const base = getSignalLabelBase(signal, context);
  // 다중 타임프레임(엔진 v16.29) — 주봉·월봉 기준이면 꼬리를 붙인다(매매사유와 같은 문구).
  if (signal.timeframe === "weekly") return `${base}${t(" (주봉 기준)")}`;
  if (signal.timeframe === "monthly") return `${base}${t(" (월봉 기준)")}`;
  return base;
}

function getSignalLabelBase(
  signal: Parameters<typeof getSignalLabel>[0],
  context: "entry" | "exit"
): string {
  if (signal.indicator === "ai_drop_model") {
    return t(INDICATOR_LABELS.ai_drop_model);
  }

  // 브레이크아웃은 기준 기간(lookback_period)에 따라 의미가 달라진다 — 252일(≈52주)은 "52주 신고가",
  // 그 밖의 N일은 "N일 고점 돌파"(매수)/"N일 저점 이탈"(매도)로 구체화한다. 기간 미상이면 일반 라벨.
  if (signal.indicator === "breakout") {
    const isDown =
      signal.signal_type === "sell" || (signal.signal_type == null && context === "exit");
    const days = signal.lookback_period ?? null;
    if (days === 252) return isDown ? t("52주 신저가 이탈") : t("52주 신고가 돌파");
    if (days != null) return isDown ? t("{0}일 저점 이탈", days) : t("{0}일 고점 돌파", days);
    return t(INDICATOR_LABELS.breakout);
  }

  // RSI 반등(mode "rebound")은 단순 임계값 비교가 아니라 과매도/과매수 임계선을 '다시 돌파'하는
  // 크로스오버다(backend/engine/signals.py). 배지가 "RSI"로만 나오면 이 뉘앙스가 사라지므로,
  // 매수=상향 반등 / 매도=하향 반전으로 임계값과 함께 표기한다. 순수 임계값 비교(mode 없음)는
  // 기존대로 "RSI"만 노출한다.
  if (signal.indicator === "rsi" && signal.mode === "rebound") {
    const isDown =
      signal.signal_type === "sell" || (signal.signal_type == null && context === "exit");
    const threshold = signal.value ?? (isDown ? 70 : 30);
    return isDown ? t("RSI {0} 하향 반전", threshold) : t("RSI {0} 상향 반등", threshold);
  }

  // 순수 임계값 비교 RSI는 operator/value가 있으면 "RSI 50 이상"처럼 구체적으로 표기한다.
  // 정보가 없으면(레거시 데이터 등) 기존대로 "RSI"만 노출한다.
  if (signal.indicator === "rsi" && signal.operator != null && signal.value != null) {
    const opKr = t(OPERATOR_KO_LABELS[signal.operator] ?? signal.operator);
    return `RSI ${signal.value} ${opKr}`;
  }

  // 변동성(연환산 %)도 RSI처럼 operator/value가 있으면 "변동성 30% 이하"로 구체화한다.
  if (signal.indicator === "volatility" && signal.operator != null && signal.value != null) {
    const opKr = t(OPERATOR_KO_LABELS[signal.operator] ?? signal.operator);
    return t("변동성 {0}% {1}", signal.value, opKr);
  }

  // 거래대금 신호의 임계는 억원 단위다(registry technical.trading_value) — 금액이 빠지면
  // "거래대금"만 남아 조건을 읽을 수 없으므로 진입 게이트 배지(formatEntryFilter)와 같은
  // 표기로 금액을 함께 싣는다.
  if (signal.indicator === "trading_value" && signal.value != null) {
    const opKr = t(OPERATOR_KO_LABELS[signal.operator ?? ">="] ?? signal.operator ?? "");
    return t("거래대금 {0} {1}", formatEokAmount(signal.value), opKr);
  }

  // 거래량 배수(엔진 v16.10, 당일 거래량 ÷ 직전 N일 평균)는 배수와 기간이 조건의 정체다 —
  // "거래량 배수"만 나가면 사용자가 말한 1.5배가 카드에서 사라진다.
  if (signal.indicator === "volume_ratio" && signal.value != null) {
    const opKr = t(OPERATOR_KO_LABELS[signal.operator ?? ">="] ?? signal.operator ?? "");
    return t("거래량 {0}일 평균의 {1}배 {2}", signal.period ?? 20, signal.value, opKr);
  }

  // 거래대금 배수(엔진 v16.13, 당일 거래대금 ÷ 직전 N일 평균) — 거래량 배수와 같은 이유로 배수·기간을 싣는다.
  if (signal.indicator === "trading_value_ratio" && signal.value != null) {
    const opKr = t(OPERATOR_KO_LABELS[signal.operator ?? ">="] ?? signal.operator ?? "");
    return t("거래대금 {0}일 평균의 {1}배 {2}", signal.period ?? 20, signal.value, opKr);
  }

  if (signal.indicator === "ai_model" && (context === "exit" || signal.signal_type === "sell")) {
    return t(INDICATOR_LABELS.ai_drop_model);
  }

  const cross = DIRECTIONAL_CROSS_LABELS[signal.indicator];
  if (cross) {
    // signal_type이 없으면 청산 컨텍스트를 하향(데드)으로 본다.
    const isDown =
      signal.signal_type === "sell" || (signal.signal_type == null && context === "exit");
    if (signal.indicator === "macd" && signal.mode === "zero") {
      return isDown ? t("MACD 제로선 하향 돌파") : t("MACD 제로선 상향 돌파");
    }
    // 이동평균 계열은 기간이 조건의 정체다 — 기간을 버리면 '종가 vs 60일선'과
    // '20일선 vs 60일선'이 같은 'MA 골든크로스' 한 문구가 되어 서로 다른 두 조건이
    // 요약 카드에 쌍둥이로 나간다(2026-09-10 사용자 지적). 매매사유(engine/trade_reason.py)와
    // 같은 문구를 쓴다 — short=1은 종가다.
    const maLabel = movingAverageLabel(signal, isDown);
    if (maLabel) return maLabel;
    return t(isDown ? cross.dead : cross.golden);
  }

  return t(INDICATOR_LABELS[signal.indicator] ?? signal.indicator);
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
    case "ETF":
      return "etf";
    default:
      return normalized;
  }
}

function formatPercent(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  return Number.isInteger(value) ? value.toFixed(0) : value.toString();
}

/** 하락 방향 비율(손절·트레일링 스탑)은 항상 마이너스 부호를 붙여 표기한다 — 부호 없는
 *  "손절 8%"는 방향이 드러나지 않아 익절과 구분되지 않는다(2026-07-30 지적). 값은 크기로
 *  저장되므로 표기 시점에 부호를 붙이고, 이미 음수로 들어온 값에는 중복해서 붙이지 않는다. */
export function formatDownsidePercent(value: number | null | undefined): string | null {
  const pct = formatPercent(value);
  if (pct === null) return null;
  return pct.startsWith("-") ? pct : `-${pct}`;
}

// 신규 상장 유니버스 배지(FR-STR-073). 상장 구간이 한 해 전체면 "2026년 상장",
// 아직 시기를 되묻는 중이면 개념만 "신규 상장". 제한이 없으면 null(배지 없음).
export function formatNewListingLabel(parsed: {
  new_listing_only?: boolean | null;
  listing_from?: string | null;
  listing_to?: string | null;
}): string | null {
  const from = parsed.listing_from ?? null;
  const to = parsed.listing_to ?? null;
  if (!parsed.new_listing_only && !from && !to) return null;
  if (!from && !to) return t("신규 상장");
  if (!from) return t("{0} 이전 상장", to);
  const year = from.slice(0, 4);
  if (from === `${year}-01-01` && to === `${year}-12-31`) return t("{0}년 상장", year);
  return to ? t("{0}~{1} 상장", from, to) : t("{0} 이후 상장", from);
}

export function getDisplayUniverseLabels(
  parsed: ParsedSummary,
  backtestRequest?: BacktestRequestLike | null
): string[] {
  // 지정 종목(단일 종목) 백테스트: 유니버스 대신 대상 종목 자체를 배지로 보여준다.
  // 이름은 backtest_request.target_stocks(백엔드 해석)에서 가져오고 없으면 코드만 표시.
  if (parsed.target_symbols && parsed.target_symbols.length > 0) {
    const nameBySymbol = new Map(
      (backtestRequest?.target_stocks ?? []).map((s) => [s.symbol, s.name])
    );
    return parsed.target_symbols.map((code) => {
      const name = nameBySymbol.get(code);
      return name ? `${name} (${code})` : code;
    });
  }

  const normalizedUniverses = parsed.universe.map(normalizeUniverseId);

  // 복수 섹터(배열)는 업종별로 개별 배지를 만든다("반도체 업종", "기계/장비 업종").
  const sectors = Array.isArray(parsed.sector)
    ? parsed.sector
    : parsed.sector
      ? [parsed.sector]
      : [];
  const sectorLabel = sectors.map((sector) => t("{0} 업종", sector));

  // ETF 테마/상품명 필터 배지 — 상품명("KODEX 200", 라틴 브랜드 포함)은 그대로,
  // 테마 키워드("반도체", "미국")는 "테마"를 붙인다.
  if (parsed.etf_theme) {
    sectorLabel.push(
      /[a-z]/i.test(parsed.etf_theme) ? parsed.etf_theme : t("{0} 테마", parsed.etf_theme)
    );
  }

  // 미국 업종 필터 배지 — 라벨이 영문 정본이라 "{0} 업종"으로 감싼다("Airlines 업종").
  if (parsed.us_industry) sectorLabel.push(t("{0} 업종", parsed.us_industry));
  // 업종 제외 배지(엔진 v16.24) — "금융지주 업종 제외".
  for (const excluded of parsed.exclude_sectors ?? []) sectorLabel.push(t("{0} 업종 제외", excluded));

  const newListingLabel = formatNewListingLabel(parsed);
  if (newListingLabel) sectorLabel.push(newListingLabel);
  // 유니버스 사전 필터(엔진 v16.19) — 빼면 '시가총액 상위 500종목 중 …'을 말한 전략이
  // "코스피·코스닥 전체"로만 보여 반영 여부를 알 수 없다(2026-09-21 실측: 라벨 함수만 있고 미배선).
  sectorLabel.push(...formatUniverseFilterLabels(parsed));

  if (
    normalizedUniverses.length === 1 &&
    normalizedUniverses[0] === "kospi200" &&
    (backtestRequest?.symbols?.length ?? 0) > 220
  ) {
    return ["KOSPI", ...sectorLabel];
  }

  return [
    ...normalizedUniverses.map((universe) => t(UNIVERSE_LABELS[universe] ?? universe)),
    ...sectorLabel,
  ];
}

// 백테스트가 실제로 매매를 만들어내려면 최소한 하나의 '매수(종목 선정) 기준'이 있어야 한다.
// 매수 기준 없이 유니버스·최대 종목만 있으면 진입 시그널이 전혀 발생하지 않아 0매매로 끝난다
// (backend/engine/signals.py: 조건 없는 그룹은 all-False 시그널 반환). 청산·리스크 설정만으로는
// 살 종목을 고를 수 없으므로 매수 기준 판정에서 제외한다.
export function hasBuyCriteria(parsed: ParsedSummary | null | undefined): boolean {
  if (!parsed) return false;
  // 정액 적립식은 납입 일정이 곧 매수 규칙이다 — 여기서 빠지면 실행 버튼은 열렸는데 실행 핸들러가
  // "매수 기준 없음"으로 빌더를 처음부터 다시 시작해 유니버스를 되묻는다(2026-09-22 사용자 보고).
  if (hasContributionPlan(parsed)) return true;
  // 정기 인출만 말한 전략도 '지정 종목을 사서 들고 있다'가 매수 규칙이다(엔진 v16.33 현금흐름 레인).
  if (hasWithdrawalPlan(parsed)) return true;
  return (
    (parsed.entry_signals?.length ?? 0) > 0 ||
    (parsed.fundamental_filters?.length ?? 0) > 0 ||
    parsed.ranking_metric != null
  );
}

/** 납입액과 주기가 둘 다 있고 사 모을 대상(지정 종목 또는 ETF 상품 유니버스)이 있는 전략인가 —
 *  반쪽 요청은 적립식이 아니다(백엔드 strategy_slots.has_contribution_plan과 동형). 프론트의 유일한
 *  사본 — 되묻기 게이트(backtestReadiness)와 실행 게이트(hasBuyCriteria)가 둘 다 이 함수를 본다. */
export function hasContributionPlan(parsed: ParsedSummary | null | undefined): boolean {
  return Boolean(
    parsed &&
      (parsed.contribution_amount ?? 0) > 0 &&
      parsed.contribution_period &&
      ((parsed.target_symbols?.length ?? 0) > 0 || parsed.etf_theme),
  );
}

/** 인출액과 주기가 둘 다 있고 대상이 있는 전략인가 — 백엔드 strategy_slots.has_withdrawal_plan과 동형. */
export function hasWithdrawalPlan(parsed: ParsedSummary | null | undefined): boolean {
  return Boolean(
    parsed &&
      (parsed.withdrawal_amount ?? 0) > 0 &&
      parsed.withdrawal_period &&
      ((parsed.target_symbols?.length ?? 0) > 0 || parsed.etf_theme),
  );
}

/** 종목 선정 범위 — 백엔드 `engine/selection_scope.py`의 판정을 그대로 옮긴 것.
 *
 * **판정 정본은 백엔드다.** 여기 있는 것은 배지 문구를 고르기 위한 미러이며, 규칙이
 * 갈리면 화면과 실제 실행이 어긋난다(테마 후보군을 "36개 균등 투자"로 표시해 놓고
 * 엔진은 랭킹으로 10개만 사는 상태). 규칙을 바꿀 때는 양쪽을 함께 고친다. */
export type SelectionScope = "EXPLICIT" | "CANDIDATE_POOL" | "UNIVERSE";

export function getSelectionScope(parsed: ParsedSummary): SelectionScope {
  if (!(parsed.target_symbols?.length ?? 0)) return "UNIVERSE";
  // 테마 유래 종목이라도 선정 기준이 있을 때만 후보군이다 — 기준이 없으면
  // 무엇을 기준으로 자를지 아무도 말하지 않았으므로 전부 매수한다.
  // 선정 기준은 셋 중 하나다 — 랭킹·보유 수·비율 선정. 셋 다 사용자가 말했을 때만
  // 값이 선다(보유 수는 기본값이 물질화되므로 출처 표식을 본다). 백엔드
  // engine/selection_scope.py와 같은 술어여야 한다.
  if (
    parsed.theme_universe &&
    (parsed.ranking_metric ||
      parsed.max_positions_explicit ||
      parsed.max_positions_pct != null)
  ) {
    return "CANDIDATE_POOL";
  }
  return "EXPLICIT";
}

// 포트폴리오(보유 종목 수) 배지 문구. 지정 종목 백테스트는 "최대 N종목"(유니버스 선정)이
// 아니라 지정 종목 집중 투자임을 드러낸다. 테마 후보군에서 선정하는 전략은 지정이 아니므로
// 유니버스 전략과 같은 문구를 쓴다(실제로 그 종목 수만큼만 산다).
export function getPositionLabel(parsed: ParsedSummary): string {
  const scope = getSelectionScope(parsed);
  const targetCount = parsed.target_symbols?.length ?? 0;
  // 유니버스 적립식(2026-09-22)은 대상 ETF 전체에 균등 분할한다 — 물질화 기본값 '최대 10종목'은 실행과
  // 어긋난다(엔진 적립 레인은 max_positions를 읽지 않는다).
  if (hasContributionPlan(parsed) && targetCount === 0) {
    return t("대상 ETF 전체 균등 적립");
  }
  if (scope === "EXPLICIT") {
    return targetCount === 1 ? t("단일 종목 집중 투자") : t("지정 종목 {0}개 균등 투자", targetCount);
  }
  // 분위 그룹·비율 선정(FR-BT-060)은 종목 수가 아니라 그룹/비율이 편입 규모를 정의한다 —
  // "최대 10종목"(물질화 기본값)으로 표시하면 실제 실행(분위 밴드 전체 편입)과 어긋난다.
  if (parsed.ranking_quantile_groups) {
    return parsed.ranking_group_cap
      ? t("{0}분위 그룹 · 그룹당 {1}종목", parsed.ranking_quantile_groups, parsed.ranking_group_cap)
      : t("{0}분위 그룹 비교 (메인: 1그룹)", parsed.ranking_quantile_groups);
  }
  if (parsed.max_positions_pct != null) {
    return t("상위 {0}% 편입", parsed.max_positions_pct);
  }
  return t("최대 {0}종목", parsed.max_positions);
}

export type MacroFilterSummary = {
  series?: string | null;
  mode?: string | null;
  operator?: string | null;
  value?: number | null;
  period?: number | null;
  exposure_pct?: number | null;
};

// 매크로 시리즈 라벨(backend/engine/macro_data.py MACRO_SERIES와 1:1 — 한국어 정본, 영어는 t()).
export const MACRO_SERIES_LABELS: Record<string, string> = {
  vix: "VIX(변동성 지수)", usdkrw: "원/달러 환율", usdjpy: "엔/달러 환율", dxy: "달러 인덱스",
  us10y: "미국 10년물 국채 금리", us2y: "미국 2년물 국채 금리", us3m: "미국 3개월물 국채 금리",
  us_spread: "미국 장단기 금리차(10년−2년)", fed_funds: "미국 기준금리(연준)",
  kr10y: "한국 국고채 10년 금리(월간)", kr3m: "한국 CD 3개월 금리(월간)", gold: "금 선물", wti: "WTI 원유 선물",
};

/** 매크로 조건 필터 표기(엔진 v16.31). 값이 비면 값 미정으로 적는다(조용한 확정 금지). */
export function formatMacroFilterLabels(filters: MacroFilterSummary[] | null | undefined): string[] {
  if (!filters?.length) return [];
  return filters.map((f) => {
    const label = f.series ? t(MACRO_SERIES_LABELS[f.series] ?? f.series) : t("금리(종류 미정)");
    const op = f.operator ? ({ ">": t("초과"), ">=": t("이상"), "<": t("미만"), "<=": t("이하") } as Record<string, string>)[f.operator] : null;
    const pending = !f.series || f.exposure_pct == null || !op
      || (f.mode === "ma" ? f.period == null : f.value == null || (f.mode === "change" && f.period == null));
    if (pending) return t("{0} 매크로 조건(값 미정)", label);
    const cond = f.mode === "ma"
      ? t("{0}일 이동평균 {1}", f.period, f.operator === ">" || f.operator === ">=" ? t("위") : t("아래"))
      : f.mode === "change"
        ? t("{0}일 변화율 {1}% {2}", f.period, f.value, op)
        : `${f.value} ${op}`;
    return t("{0} {1}이면 투자 비중 {2}%", label, cond, f.exposure_pct);
  });
}

export type MarketRegimeSummary = {
  index?: string | null;
  // 약세 판정 종류(엔진 v16.16) — 없으면 이동평균(below_ma) 단독.
  triggers?: string[] | null;
  ma_period?: number | null;
  volatility_period?: number | null;
  volatility_multiple?: number | null;
  exposure_pct?: number | null;
};

// 변동성 급등 판정의 산정 기간 — 말하지 않으면 엔진이 20거래일로 계산한다
// (backend/engine/market_index.py REGIME_VOL_DEFAULT_PERIOD와 같은 값).
const REGIME_VOL_DEFAULT_PERIOD = 20;

/** 비중 방식 표기(엔진 v16.14) — 동일 비중(기본)이면 null(따로 적지 않는다). */
export function formatAllocationLabel(
  type: string | null | undefined,
  lookbackDays: number | null | undefined,
): string | null {
  if (type === "inverse_volatility") {
    return lookbackDays != null
      ? t("변동성 역비중({0}일 변동성)", lookbackDays)
      : t("변동성 역비중(산정 기간 미정)");
  }
  // 경쟁 격차 1차(엔진 v16.28) — 수익률 기반 최적화는 산정 기간을 함께 적는다.
  const optimizer: Record<string, string> = {
    min_variance: "최소 분산 비중", risk_parity: "리스크 패리티 비중",
    max_sharpe: "최대 샤프 비중", min_cvar: "최소 CVaR 비중",
  };
  if (type && optimizer[type]) {
    return lookbackDays != null
      ? t("{0}({1}일 수익률)", t(optimizer[type]), lookbackDays)
      : t("{0}(산정 기간 미정)", t(optimizer[type]));
  }
  if (type === "market_cap") return t("시가총액 비중");
  if (type === "fixed") return t("고정 비중(정적 배분)");
  return null;
}

/** 경쟁 격차 1차(엔진 v16.28) 설정 라벨 — 값이 비면 값 미정으로 적는다(조용한 확정 금지). */
export function formatExecutionTuningLabels(parsed: {
  target_weights?: Record<string, number> | null;
  rebalance_threshold_pct?: number | null;
  min_holding_days?: number | null;
  stop_cooldown_days?: number | null;
  trailing_stop_activation_pct?: number | null;
  entry_limit_pct?: number | null;
  exit_limit_pct?: number | null;
  entry_tranches?: { count?: number | null; step_pct?: number | null } | null;
  partial_take_profits?: Array<{ profit_pct?: number | null; sell_pct?: number | null }> | null;
  position_sizing?: { method: string; risk_per_trade_pct?: number | null; atr_multiple?: number | null; kelly_fraction?: number | null } | null;
  cash_asset?: string | null;
  absolute_momentum_threshold_pct?: number | null;
  execution_timing?: string | null;
  slippage_model?: string | null;
}): string[] {
  const labels: string[] = [];
  if (parsed.target_weights && Object.keys(parsed.target_weights).length > 0) {
    labels.push(Object.entries(parsed.target_weights).map(([k, v]) => `${k} ${v}%`).join(" / "));
  }
  if (parsed.rebalance_threshold_pct != null) labels.push(t("밴드 리밸런싱 {0}%p", parsed.rebalance_threshold_pct));
  if (parsed.min_holding_days != null) labels.push(t("최소 {0}일 보유", parsed.min_holding_days));
  if (parsed.stop_cooldown_days != null) labels.push(t("청산 후 {0}일 재진입 금지", parsed.stop_cooldown_days));
  if (parsed.trailing_stop_activation_pct != null) labels.push(t("트레일링 +{0}%부터 작동", parsed.trailing_stop_activation_pct));
  if (parsed.entry_limit_pct != null) labels.push(t("매수 지정가 전일 종가 -{0}%", parsed.entry_limit_pct));
  if (parsed.exit_limit_pct != null) labels.push(t("매도 지정가 전일 종가 +{0}%", parsed.exit_limit_pct));
  if (parsed.entry_tranches) {
    const { count, step_pct } = parsed.entry_tranches;
    labels.push(count != null && step_pct != null
      ? t("분할 매수 {0}회({1}% 간격)", count, step_pct)
      : t("분할 매수(회차·간격 미정)"));
  }
  for (const p of parsed.partial_take_profits ?? []) {
    labels.push(p.profit_pct != null && p.sell_pct != null
      ? t("분할 익절 +{0}%에 {1}% 매도", p.profit_pct, p.sell_pct)
      : t("분할 익절(단계 미정)"));
  }
  if (parsed.position_sizing) {
    const ps = parsed.position_sizing;
    if (ps.method === "atr_risk") {
      labels.push(ps.risk_per_trade_pct != null
        ? t("ATR 사이징(거래당 위험 {0}%)", ps.risk_per_trade_pct)
        : t("ATR 사이징(위험 % 미정)"));
    } else {
      labels.push(ps.kelly_fraction != null
        ? t("켈리 사이징({0}배)", ps.kelly_fraction)
        : t("켈리 사이징(배수 미정)"));
    }
  }
  if (parsed.cash_asset) labels.push(t("현금 대체 자산 {0}", parsed.cash_asset));
  if (parsed.absolute_momentum_threshold_pct != null) {
    labels.push(t("절대 모멘텀 {0}% 이하 편입 제외", parsed.absolute_momentum_threshold_pct));
  }
  if (parsed.execution_timing === "next_avg") labels.push(t("다음 날 평균가 체결"));
  if (parsed.slippage_model === "volume_impact") labels.push(t("거래량 비례 슬리피지"));
  return labels;
}

/** 종목당 비중 상한 표기(엔진 v16.18). */
export function formatWeightCapLabel(capPct: number | null | undefined): string | null {
  return capPct != null ? t("종목당 비중 상한 {0}%", capPct) : null;
}

/** 섹터별 비중 상한 표기(엔진 v16.19) — 같은 업종 종목의 비중 합에 걸린다. */
export function formatSectorWeightCapLabel(capPct: number | null | undefined): string | null {
  return capPct != null ? t("섹터별 비중 상한 {0}%", capPct) : null;
}

/** 유니버스 사전 필터 표기(엔진 v16.19, v16.32 확장) — 시총 상위 N·하위 % 제외·거래대금 하위 % 제외·적자기업 제외. */
export function formatUniverseFilterLabels(parsed: {
  universe_market_cap_top_n?: number | null;
  universe_liquidity_exclude_bottom_pct?: number | null;
  universe_liquidity_lookback_days?: number | null;
  universe_market_cap_exclude_bottom_pct?: number | null;
  universe_exclude_loss_making?: string | null;
}): string[] {
  const labels: string[] = [];
  if (parsed.universe_market_cap_top_n != null) {
    labels.push(t("시가총액 상위 {0}종목", parsed.universe_market_cap_top_n));
  }
  if (parsed.universe_market_cap_exclude_bottom_pct != null) {
    labels.push(t("시가총액 하위 {0}% 제외", parsed.universe_market_cap_exclude_bottom_pct));
  }
  if (parsed.universe_liquidity_exclude_bottom_pct != null) {
    const days = parsed.universe_liquidity_lookback_days ?? 20;
    labels.push(t("{0}일 평균 거래대금 하위 {1}% 제외", days, parsed.universe_liquidity_exclude_bottom_pct));
  }
  // 원문을 그대로 t() 인자로 쓴다 — 모듈 상수에 담아 넘기면 번역 커버리지 게이트가 키를 못 본다.
  const lossMode = parsed.universe_exclude_loss_making;
  if (lossMode === "net") labels.push(t("당기순손실 기업 제외"));
  else if (lossMode === "operating") labels.push(t("영업손실 기업 제외"));
  else if (lossMode === "both") labels.push(t("당기순손실·영업손실 기업 제외"));
  return labels;
}

/** 시장 국면 필터 표기(엔진 v16.14). 기간·비율이 비면 값 미정으로 적는다(조용한 확정 금지). */
export function formatMarketRegimeLabel(regime: MarketRegimeSummary | null | undefined): string | null {
  if (!regime) return null;
  const index = t(regime.index === "KOSDAQ" ? "코스닥" : "코스피");
  const triggers = regime.triggers?.length ? regime.triggers : ["below_ma"];
  const usesMa = triggers.includes("below_ma");
  const usesVol = triggers.includes("volatility_spike");
  const pending =
    regime.exposure_pct == null ||
    (usesMa && regime.ma_period == null) ||
    (usesVol && regime.volatility_multiple == null);
  if (pending) {
    return usesVol
      ? t("{0} 시장 국면 필터(값 미정)", index)
      : t("{0} 이동평균 국면 필터(값 미정)", index);
  }
  if (!usesVol) {
    return t("{0} {1}일 이동평균 아래면 투자 비중 {2}%", index, regime.ma_period, regime.exposure_pct);
  }
  const volPeriod = regime.volatility_period ?? REGIME_VOL_DEFAULT_PERIOD;
  if (!usesMa) {
    return t(
      "{0} {1}일 변동성이 평소의 {2}배 이상이면 투자 비중 {3}%",
      index, volPeriod, regime.volatility_multiple, regime.exposure_pct,
    );
  }
  return t(
    "{0} {1}일 이동평균 아래이거나 {2}일 변동성이 평소의 {3}배 이상이면 투자 비중 {4}%",
    index, regime.ma_period, volPeriod, regime.volatility_multiple, regime.exposure_pct,
  );
}

/** 계절 필터 표기(엔진 v16.25) — "11·12·1·2·3·4월에만 투자". */
export function formatSeasonalLabel(months: number[] | null | undefined): string | null {
  if (!months || months.length === 0) return null;
  return t("{0}월에만 투자", months.join("·"));
}

/** 목표 변동성 표기(엔진 v16.25) — 값이 비면 값 미정으로 적는다(조용한 확정 금지). */
export function formatVolTargetLabel(
  target: { target_pct?: number | null } | number | null | undefined,
): string | null {
  if (target == null) return null;
  const pct = typeof target === "number" ? target : target.target_pct;
  return pct == null ? t("목표 변동성(값 미정)") : t("목표 연변동성 {0}%", pct);
}

/** 복합 순위 합산(FR-BT-063)의 구성 지표 하나 — "ROE 높은 순"·"PER 낮은 순"·"20일 수익률 높은 순". */
function componentLabel(
  c: {
    metric: string; direction: "top" | "bottom"; lookback_days?: number | null;
    skip_days?: number | null; weight?: number | null;
  },
  defaultLookback: number | null | undefined,
): string {
  const base = componentBaseLabel(c, defaultLookback);
  // 가중치(엔진 v16.24) — 1이 아닌 값만 드러낸다(동일 가중은 표기하지 않는다).
  return c.weight != null && c.weight !== 1 ? t("{0} (가중치 {1})", base, c.weight) : base;
}

function componentBaseLabel(
  c: {
    metric: string; direction: "top" | "bottom"; lookback_days?: number | null;
    skip_days?: number | null;
  },
  defaultLookback: number | null | undefined,
): string {
  const dir = c.direction === "bottom" ? t("낮은 순") : t("높은 순");
  if (c.metric === "return" || c.metric === "volatility") {
    const days = c.lookback_days ?? defaultLookback;
    const name = c.metric === "return" ? t("수익률") : t("변동성");
    if (c.metric === "return" && days != null && c.skip_days) {
      return t("{0}일 수익률(최근 {1}일 제외) {2}", days, c.skip_days, dir);
    }
    // 산정 기간 미정이면 일수를 붙이지 않는다(단일 랭킹 라벨과 같은 계약).
    return days != null ? t("{0}일 {1} {2}", days, name, dir) : t("{0}(산정 기간 미정) {1}", name, dir);
  }
  return `${t(METRIC_LABELS[c.metric] ?? c.metric)} ${dir}`;
}

/** 구성 지표를 묶음 점수(group) 단위로 모은 표기 — 묶음은 "묶음(A·B·C)" 한 덩어리로 적는다. */
function groupedComponentLabels(
  components: NonNullable<ParsedSummary["ranking_components"]>,
  defaultLookback: number | null | undefined,
): string[] {
  const out: string[] = [];
  const groups = new Map<string, string[]>();
  for (const c of components) {
    const label = componentLabel(c, defaultLookback);
    if (!c.group) {
      out.push(label);
      continue;
    }
    if (!groups.has(c.group)) {
      groups.set(c.group, []);
      out.push(`\u0000${c.group}`);
    }
    groups.get(c.group)!.push(label);
  }
  return out.map((item) =>
    item.startsWith("\u0000")
      ? t("묶음 점수({0})", groups.get(item.slice(1))!.join("·"))
      : item,
  );
}

/** 전술 자산배분 표기(엔진 v16.29). 자산이 비면 값 미정으로 적는다(상품을 대신 고르지 않는다). */
export function formatTaaLabel(
  taa: ParsedSummary["taa"] | null | undefined,
): string | null {
  if (!taa) return null;
  const model = String(taa.model || "").toUpperCase();
  const offensive = taa.offensive?.length ?? 0;
  const defensive = taa.defensive?.length ?? 0;
  if (!offensive || !defensive) return t("전술 자산배분 {0}(자산 미정)", model);
  return t("전술 자산배분 {0} (공격 {1}·방어 {2})", model, offensive, defensive);
}

export function getRankingLabel(parsed: ParsedSummary): string | null {
  if (parsed.ranking_metric === "taa") {
    return formatTaaLabel(parsed.taa) ?? t("전술 자산배분");
  }
  // 산정 기간 미정(되묻기 진행 중)에 60일을 표시하면 조용한 확정으로 읽힌다(2026-08-10
  // 사용자 지시 "60일 강제 금지") — 기간이 정해진 뒤에만 일수를 붙인다.
  if (parsed.ranking_metric === "composite" && parsed.ranking_components?.length) {
    // 복합 순위 합산(FR-BT-063) — 구성 지표별 순위를 합산해 상위 선정. 내부명 대신
    // 지표 정본 라벨과 방향을 그대로 보여 준다.
    const parts = groupedComponentLabels(parsed.ranking_components, parsed.ranking_lookback_days);
    return t("복합 순위 상위 ({0} 순위 합산)", parts.join(" + "));
  }
  if (parsed.ranking_metric === "return") {
    const days = parsed.ranking_lookback_days;
    // bottom=수익률 낮은 순(역발상) — 엔진 v16.2가 방향을 존중하므로 라벨도 방향을 드러낸다.
    if (parsed.ranking_direction === "bottom") {
      return days != null ? t("{0}일 수익률 하위", days) : t("수익률 하위(산정 기간 미정)");
    }
    if (days != null && parsed.ranking_skip_days) {
      return t("{0}일 수익률(최근 {1}일 제외) 상위", days, parsed.ranking_skip_days);
    }
    return days != null ? t("{0}일 수익률 상위", days) : t("수익률 상위(산정 기간 미정)");
  }
  if (parsed.ranking_metric === "relative_return") {
    // 시장 대비 초과수익률 랭킹(엔진 v16.10) — 종목 수익률에서 자기 시장 지수 수익률을 뺀 순위.
    const days = parsed.ranking_lookback_days;
    if (parsed.ranking_direction === "bottom") {
      return days != null
        ? t("{0}일 시장 대비 수익률 하위", days)
        : t("시장 대비 수익률 하위(산정 기간 미정)");
    }
    return days != null
      ? t("{0}일 시장 대비 수익률 상위", days)
      : t("시장 대비 수익률 상위(산정 기간 미정)");
  }
  if (parsed.ranking_metric === "residual_reversal") {
    // 잔차 반전 시그널 랭킹(엔진 v16.17) — 시장·섹터 회귀 잔차의 반전 시그널 순위.
    // 허용 밖 값을 되묻는 동안에는 기간이 비어 있다(백엔드가 임의 값으로 채우지 않는다).
    const lookback = parsed.ranking_lookback_days;
    const accumulation = parsed.ranking_accumulation_days;
    const bottom = parsed.ranking_direction === "bottom";
    if (lookback == null || accumulation == null) {
      return bottom ? t("잔차 반전 시그널 하위(기간 미정)") : t("잔차 반전 시그널 상위(기간 미정)");
    }
    return bottom
      ? t("잔차 반전 시그널 하위 (회귀 {0}일·누적 {1}일)", lookback, accumulation)
      : t("잔차 반전 시그널 상위 (회귀 {0}일·누적 {1}일)", lookback, accumulation);
  }
  if (parsed.ranking_metric === "pead") {
    // 실적 서프라이즈 시그널 랭킹(엔진 v16.19) — SUE와 발표일 초과수익률의 z-score 평균.
    // 범위 밖 값을 되묻는 동안에는 자격 창이 비어 있다(백엔드가 임의 값으로 채우지 않는다).
    const delay = parsed.ranking_entry_delay_days;
    const expiry = parsed.ranking_expiry_days;
    const bottom = parsed.ranking_direction === "bottom";
    if (delay == null || expiry == null) {
      return bottom ? t("실적 서프라이즈 시그널 하위(기간 미정)") : t("실적 서프라이즈 시그널 상위(기간 미정)");
    }
    return bottom
      ? t("실적 서프라이즈 시그널 하위 (발표 {0}일 후 편입·{1}일 경과 제외)", delay, expiry)
      : t("실적 서프라이즈 시그널 상위 (발표 {0}일 후 편입·{1}일 경과 제외)", delay, expiry);
  }
  if (parsed.ranking_metric === "volatility") {
    // 엔진의 방향 미지정 기본은 bottom(저변동성 선호) — backtest_engine 변동성 분기 미러.
    const days = parsed.ranking_lookback_days;
    const prefix = days != null ? t("{0}일 ", days) : "";
    const suffix = days != null ? "" : t("(산정 기간 미정)");
    return parsed.ranking_direction === "top"
      ? t("{0}변동성 높은 순 상위{1}", prefix, suffix)
      : t("{0}변동성 낮은 순 상위{1}", prefix, suffix);
  }
  if (parsed.ranking_metric) {
    // 재무 팩터 랭킹(예: 영업이익률 상위 20종목) — 지표명은 필터 배지와 같은 정본 라벨.
    const label = t(METRIC_LABELS[parsed.ranking_metric] ?? parsed.ranking_metric);
    return parsed.ranking_direction === "bottom" ? t("{0} 낮은 순 상위", label) : t("{0} 상위", label);
  }
  return null;
}

/** 지표가 만드는 청산 신호만. 손절·익절·트레일링·보유 기간은 제외한다.
 *
 * 리스크·포트폴리오 항목을 **따로 보여주는 화면**(전략 요약 카드, 진행 상황 카드)이 쓴다 —
 * 거기서 `getDisplayExitLabels`를 쓰면 같은 설정이 한 카드에서 두 번 읽힌다(2026-08-02 지시).
 * 진입/청산 두 칸만 있는 결과 화면 배지는 위험 청산까지 실어야 하므로 그쪽은 그대로 둔다.
 * 두 화면이 각자 필터링하면 또 갈리므로 술어를 여기 하나로 둔다.
 */
export function getSignalExitLabels(
  parsed: Pick<ParsedSummary, "exit_signals"> | null | undefined,
): string[] {
  return (parsed?.exit_signals ?? []).map((signal) => getSignalLabel(signal, "exit"));
}

export function getDisplayExitLabels(parsed: ParsedSummary): string[] {
  const labels: string[] = [];

  for (const signal of parsed.exit_signals) {
    labels.push(getSignalLabel(signal, "exit"));
  }

  const takeProfitPct = formatPercent(parsed.take_profit_pct);
  const stopLossPct = formatDownsidePercent(parsed.stop_loss_pct);
  const trailingStopPct = formatDownsidePercent(parsed.trailing_stop_pct);

  if (stopLossPct) {
    labels.push(t("손절 {0}% 하락시 매도", stopLossPct));
  }
  if (takeProfitPct) {
    labels.push(t("익절 {0}% 이상 수익시 매도", takeProfitPct));
  }
  if (trailingStopPct) {
    labels.push(t("트레일링 스탑 {0}% 하락시 매도", trailingStopPct));
  }
  if (parsed.hold_period_days) {
    labels.push(t("최대 {0}일 보유 후 매도", parsed.hold_period_days));
  }

  return labels;
}

export function buildStrategySummary(
  parsed: ParsedSummary | null,
  backtestRequest?: BacktestRequestLike | null
) {
  if (!parsed) return undefined;

  const exitLabels = getDisplayExitLabels(parsed);
  const stopLossPct = formatDownsidePercent(parsed.stop_loss_pct);
  const takeProfitPct = formatPercent(parsed.take_profit_pct);
  const trailingStopPct = formatDownsidePercent(parsed.trailing_stop_pct);

  // 재무 필터(PBR 등)도 매수 기준이므로 진입 신호 배지에 포함한다.
  // 기술적 진입 신호만 넣으면, 재무 필터 단독 전략에서 entryBlocks가 비어
  // 백테스트 결과 화면이 blockNames(진입+청산 혼합) 폴백으로 청산 배지를 진입에 잘못 노출한다.
  // 모멘텀 랭킹(수익률 상위)은 진입 신호 블록이 아니라 ranking_metric으로 표현되며 엔진에서
  // '선정=진입'으로 동작한다(backend/backtest_engine.py: 진입 조건이 없으면 랭킹 자체가 진입).
  // 배지에서 빠지면 진입 신호가 사라진 것처럼 보이므로 진입 신호로 함께 노출한다.
  const rankingLabel = getRankingLabel(parsed);
  const entryLabels = [
    ...parsed.fundamental_filters.map(formatFundamentalFilter),
    ...parsed.entry_signals.map((signal) => getSignalLabel(signal, "entry")),
    // 옵션 진입 게이트 필터(추세·거래대금·RSI 결합)도 매수 조건이므로 진입 배지에 포함.
    ...(parsed.entry_filters ?? []).map(formatEntryFilter).filter((s): s is string => Boolean(s)),
    ...(rankingLabel ? [rankingLabel] : []),
  ];

  return {
    strategyName: parsed.description,
    universeName: getDisplayUniverseLabels(parsed, backtestRequest).join(", "),
    blockNames: [...entryLabels, ...exitLabels],
    entryBlocks: entryLabels,
    exitBlocks: exitLabels,
    positionText: [
      `${getPositionLabel(parsed)}${parsed.hold_period_days ? t(" · {0}일 보유", parsed.hold_period_days) : ""}`,
      formatAllocationLabel(parsed.allocation_type, parsed.allocation_lookback_days),
      formatWeightCapLabel(parsed.max_position_weight_pct),
      formatSectorWeightCapLabel(parsed.max_sector_weight_pct),
      ...formatExecutionTuningLabels(parsed),
    ].filter(Boolean).join(" · "),
    riskText: [
      stopLossPct ? t("손절 {0}%", stopLossPct) : "",
      takeProfitPct ? t("익절 {0}%", takeProfitPct) : "",
      trailingStopPct ? t("트레일링 스탑 {0}%", trailingStopPct) : "",
      formatMarketRegimeLabel(parsed.market_regime) ?? "",
      formatSeasonalLabel(parsed.seasonal_months) ?? "",
      formatVolTargetLabel(parsed.volatility_target) ?? "",
      ...formatMacroFilterLabels(parsed.macro_filters),
    ].filter(Boolean).join(", ") || undefined,
    rebalancingText: formatRebalancingText(
      parsed.rebalancing_period, parsed.rebalance_method, t,
    ),
    // 백테스트 기간·초기 자본 — 대화 카드(ParsedSummaryBubble)와 같은 행을 결과 화면에도
    // 보이기 위한 값(2026-08-18: 카드에만 있고 결과 화면 요약 DTO에는 칸이 없어 빠졌다).
    backtestPeriodText: formatBacktestPeriodLabel(parsed) ?? undefined,
    initialCapitalText: formatInitialCapital(
      parsed.initial_capital ?? 10_000_000,
      { usd: isUsParsedUniverse(parsed.universe) },
    ),
  };
}

// 실행 요청의 기간 필드 → 배지 문자열. 상대 기간(period: "3y"/"3Y"/"6M"/"10Y"/"full")과
// 직접 지정 창(startDate/endDate, period "custom")을 모두 다룬다.
const REQUEST_PERIOD_LABELS: Record<string, string> = {
  ...PERIOD_LABELS,
  "6m": "6개월",
  "10y": "10년",
  "20y": "20년",
};

// 실행 조건(백테스트 기간·초기 자본) 텍스트 — 실행 요청·저장된 DSL(settings)·기록의
// executedRequest가 모두 같은 키(period/startDate/endDate/risk.init_cash)를 쓰므로 한 곳에서 만든다.
export function backtestRunTextsFromRequest(
  req:
    | {
        period?: string | null;
        universe_id?: string | null;
        startDate?: string | null;
        endDate?: string | null;
        risk?: Record<string, unknown> | null;
        options?: Record<string, unknown> | null;
        initial_capital?: number | null;
      }
    | null
    | undefined
): { backtestPeriodText?: string; initialCapitalText?: string; executionText?: string } {
  if (!req) return {};
  const risk = (req.risk ?? {}) as Record<string, unknown>;
  const rawCapital = risk.init_cash ?? req.initial_capital;
  const capital = typeof rawCapital === "number" && Number.isFinite(rawCapital) ? rawCapital : null;
  return {
    backtestPeriodText: formatRequestPeriodLabel(req) ?? undefined,
    initialCapitalText:
      capital != null
        ? formatInitialCapital(capital, { usd: isUsUniverseId(req.universe_id) })
        : undefined,
    executionText: formatExecutionText(req),
  };
}

// 체결 가정(체결 시점 + 신호 후 지연) — 엔진(backtest_engine)이 읽는 순서 그대로:
// options.execution_type → risk.execution_timing(없으면 next_open), 대화 레인 별칭 current_close=same_close,
// 지연은 options.execution_delay_days → risk.execution_delay_days(없으면 1, next_open에서만 뜻이 있다).
export function formatExecutionText(req: {
  risk?: Record<string, unknown> | null;
  options?: Record<string, unknown> | null;
}): string {
  const risk = (req.risk ?? {}) as Record<string, unknown>;
  const options = (req.options ?? {}) as Record<string, unknown>;
  const timingRaw = options.execution_type ?? risk.execution_timing ?? "next_open";
  const timing = timingRaw === "current_close" ? "same_close" : timingRaw;
  if (timing === "same_close") return t("당일 종가");
  const delayRaw = options.execution_delay_days ?? risk.execution_delay_days;
  const delay =
    typeof delayRaw === "number" && Number.isFinite(delayRaw) && delayRaw >= 1 ? Math.trunc(delayRaw) : 1;
  return delay > 1 ? t("신호 후 {0}번째 거래일 시가", delay) : t("익일 시가");
}

export function formatRequestPeriodLabel(req: {
  period?: string | null;
  startDate?: string | null;
  endDate?: string | null;
}): string | null {
  const from = req.startDate ?? null;
  const to = req.endDate ?? null;
  if (from || to) {
    return formatBacktestPeriodLabel({
      backtest_period: null,
      backtest_start_date: from,
      backtest_end_date: to,
    });
  }
  const period = req.period ? String(req.period).toLowerCase() : null;
  if (!period || period === "custom") return null;
  return t(REQUEST_PERIOD_LABELS[period] ?? period);
}

// 실제로 실행된 백테스트 요청(StrategyBacktestRequest)에서 요약을 만든다.
// 결과 화면 배지는 화면 상태(latestParsed)가 아니라 '이 결과를 만든 요청'에서 파생해야
// 표시와 실행이 절대 어긋나지 않는다(예: 모멘텀 랭킹이 요청에 없으면 진입 배지도 비어
// 0거래와 일관됨). risk.ranking_metric은 엔진에서 '선정=진입'이므로 진입 신호로 노출한다.
interface ExecutedBacktestRequest {
  universe_id?: string | null;
  // 지정 종목(단일 종목) 백테스트 메타데이터(FR-STR-068). universe_id=null 대신 이걸 표시.
  target_stocks?: Array<{ symbol: string; name?: string }> | null;
  sector?: string | string[] | null;
  exclude_sectors?: string[] | null;
  listing_from?: string | null;
  listing_to?: string | null;
  entry?: { conditions?: Array<{ id?: string; type?: string; params?: Record<string, unknown> }> } | null;
  exit?: { conditions?: Array<{ id?: string; type?: string; params?: Record<string, unknown> }> } | null;
  risk?: Record<string, unknown> | null;
  // 실행 창 — 상대 기간(period) 또는 직접 지정 창(startDate/endDate). 초기 자본은 risk.init_cash.
  period?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  // 체결 가정(execution_type·execution_delay_days)은 options에, 대화 레인은 risk에 싣는다.
  options?: Record<string, unknown> | null;
}

/** 실행 요청·캐논 DSL의 대상 종목이 후보군인가 — 판정 정본은 백엔드 `engine/selection_scope.py`이고,
 * 변환기가 그 결과를 `risk.ranking_enabled`(지정=false, 후보군=true)로 싣는다. 후보군은 그중에서
 * 골라 사므로 "지정 종목 N개 균등 투자"가 아니라 유니버스 전략과 같은 보유 수 문구를 쓴다
 * (2026-09-17 실측: 테마 66종목 중 60일 수익률 상위 5종목 전략이 "66개 균등 투자"로 표시됐다). */
function isCandidatePoolRisk(risk: unknown): boolean {
  return (risk as { ranking_enabled?: unknown } | null | undefined)?.ranking_enabled === true;
}

function resolveUniverseLabelFromId(universeId: string | null | undefined): string {
  const raw = (universeId ?? "").trim();
  if (!raw) return "";
  return raw
    .split("_")
    .map((token) => t(UNIVERSE_LABELS[token] ?? token.toUpperCase()))
    .join(", ");
}

export function buildStrategySummaryFromRequest(
  req: ExecutedBacktestRequest | null | undefined
) {
  if (!req) return undefined;

  const risk = (req.risk ?? {}) as Record<string, unknown>;
  const num = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? v : null;

  const stopLoss = num(risk.stop_loss_pct);
  const takeProfit = num(risk.take_profit_pct);
  const trailingStop = num(risk.trailing_stop_pct);
  const maxHoldingDays = num(risk.max_holding_days);
  const maxPositions = num(risk.max_positions);
  const rebalancingPeriod = typeof risk.rebalancing_period === "string" ? risk.rebalancing_period : "none";
  const rebalanceMethod = typeof risk.rebalance_method === "string" ? risk.rebalance_method : null;

  const allocationLabel = formatAllocationLabel(
    typeof risk.allocation_type === "string" ? risk.allocation_type : null,
    num(risk.allocation_lookback_days),
  );
  const regimeLabel = formatMarketRegimeLabel(
    risk.market_regime && typeof risk.market_regime === "object"
      ? (risk.market_regime as MarketRegimeSummary)
      : null,
  );
  const seasonalLabel = formatSeasonalLabel(
    Array.isArray(risk.seasonal_months) ? (risk.seasonal_months as number[]) : null,
  );
  const volTargetLabel = formatVolTargetLabel(num(risk.target_volatility_pct));
  const macroLabels = formatMacroFilterLabels(
    Array.isArray(risk.macro_filters) ? (risk.macro_filters as MacroFilterSummary[]) : null,
  );
  const tuningLabels = formatExecutionTuningLabels({
    ...(risk as Record<string, unknown>),
    execution_timing: (req.options as Record<string, unknown> | undefined)?.exec_price_basis === "avg"
      ? "next_avg" : null,
    slippage_model: ((req.options as Record<string, unknown> | undefined)?.slippage_model as string | null) ?? null,
  } as Parameters<typeof formatExecutionTuningLabels>[0]);
  const rankingLabel = getRankingLabel({
    ranking_metric: (risk.ranking_metric as string | null) ?? null,
    taa: (risk.taa as ParsedSummary["taa"]) ?? null,
    ranking_lookback_days: num(risk.ranking_lookback_days),
    ranking_skip_days: num(risk.ranking_skip_days),
    ranking_accumulation_days: num(risk.ranking_accumulation_days),
    ranking_direction: (risk.ranking_direction as "top" | "bottom" | null) ?? null,
    ranking_components: Array.isArray(risk.ranking_components)
      ? (risk.ranking_components as ParsedSummary["ranking_components"])
      : null,
  } as ParsedSummary);

  const entryBlocks = uniqueLabels([
    ...((req.entry?.conditions ?? [])
      .map(conditionToEntryLabel)
      .filter((label): label is string => Boolean(label))),
    ...(rankingLabel ? [rankingLabel] : []),
  ]);

  const exitBlocks = getDisplayExitLabels({
    description: "",
    universe: [],
    fundamental_filters: [],
    entry_signals: [],
    exit_signals: conditionsToExitSignals(req.exit?.conditions),
    max_positions: maxPositions ?? 0,
    hold_period_days: maxHoldingDays,
    rebalancing_period: rebalancingPeriod,
    stop_loss_pct: stopLoss,
    take_profit_pct: takeProfit,
    trailing_stop_pct: trailingStop,
    backtest_period: "full",
    initial_capital: 0,
  });

  const stopLossPct = formatDownsidePercent(stopLoss);
  const takeProfitPct = formatPercent(takeProfit);
  const trailingStopPct = formatDownsidePercent(trailingStop);

  // 지정 종목(단일 종목) 백테스트: 유니버스 라벨 대신 종목명 배지("삼성전자 (005930)").
  const targetStockLabels = (req.target_stocks ?? []).map((s) =>
    s.name ? `${s.name} (${s.symbol})` : s.symbol
  );

  return {
    // 실행된 요청에는 전략명이 없다 — 저장 시 기본 이름은 promptText가 우선 사용한다.
    strategyName: "",
    universeName: targetStockLabels.length
      ? targetStockLabels.join(" · ")
      : [
          resolveUniverseLabelFromId(req.universe_id),
          ...(Array.isArray(req.sector) ? req.sector : req.sector ? [req.sector] : []).map(
            (sector) => t("{0} 업종", sector)
          ),
          ...(req.exclude_sectors ?? []).map((sector) => t("{0} 업종 제외", sector)),
          // 실행된 요청에는 확정된 상장 구간만 실린다(되묻는 중인 개념은 실행되지 않음).
          formatNewListingLabel({
            listing_from: req.listing_from ?? null,
            listing_to: req.listing_to ?? null,
          }) ?? "",
        ]
          .filter(Boolean)
          .join(" · "),
    blockNames: [...entryBlocks, ...exitBlocks],
    entryBlocks,
    exitBlocks,
    positionText: targetStockLabels.length && !isCandidatePoolRisk(risk)
      ? `${targetStockLabels.length === 1 ? t("단일 종목 집중 투자") : t("지정 종목 {0}개 균등 투자", targetStockLabels.length)}${maxHoldingDays ? t(" · {0}일 보유", maxHoldingDays) : ""}`
      : maxPositions
        ? [
            `${t("최대 {0}종목", maxPositions)}${maxHoldingDays ? t(" · {0}일 보유", maxHoldingDays) : ""}`,
            allocationLabel,
            formatWeightCapLabel(num(risk.max_position_weight_pct)),
            formatSectorWeightCapLabel(num(risk.max_sector_weight_pct)),
            ...tuningLabels,
          ].filter(Boolean).join(" · ")
        : undefined,
    riskText:
      [
        stopLossPct ? t("손절 {0}%", stopLossPct) : "",
        takeProfitPct ? t("익절 {0}%", takeProfitPct) : "",
        trailingStopPct ? t("트레일링 스탑 {0}%", trailingStopPct) : "",
        regimeLabel ?? "",
        seasonalLabel ?? "",
        volTargetLabel ?? "",
        ...macroLabels,
      ]
        .filter(Boolean)
        .join(", ") || undefined,
    rebalancingText: formatRebalancingText(rebalancingPeriod, rebalanceMethod, t),
    ...backtestRunTextsFromRequest(req),
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

export function isRawSymbolUniverseName(value: string): boolean {
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
    chips.push(t("유니버스 {0}", universeName));
  }

  chips.push(
    ...(summary.entryBlocks ?? []),
    ...(summary.exitBlocks ?? []),
    summary.positionText,
    summary.rebalancingText,
    summary.riskText ? t("리스크 관리 {0}", summary.riskText) : undefined
  );

  return chips.filter((value): value is string => Boolean(value));
}

export interface StrategySummaryGroup {
  label: string;
  chips: string[];
}

// buildStrategySummaryChips와 같은 필드를 쓰지만, 카테고리 라벨(유니버스/진입신호/청산신호/리스트/리스크 관리)로 묶어서 반환한다.
export function buildStrategySummaryGroups(
  summary: StrategySummaryDisplay | null | undefined
): StrategySummaryGroup[] {
  if (!summary) return [];

  const universeName = summary.universeName?.trim();
  const showUniverse =
    universeName && universeName !== "미정" && !isRawSymbolUniverseName(universeName);

  const groups: StrategySummaryGroup[] = [
    // universeName은 코드가 " · "로 이어 붙인 문자열(지정 종목 라벨·업종 등) — 칩으로
    // 되돌려 한 줄에 하나씩 표시한다. '·' 연결은 항목이 늘면 끊김이 안 보인다(2026-08-06 지시).
    { label: t("유니버스"), chips: showUniverse ? universeName!.split(" · ") : [] },
    { label: t("진입신호"), chips: (summary.entryBlocks ?? []).filter(Boolean) },
    { label: t("청산신호"), chips: (summary.exitBlocks ?? []).filter(Boolean) },
    {
      label: t("리스트"),
      chips: [summary.positionText, summary.rebalancingText].filter(
        (value): value is string => Boolean(value)
      ),
    },
    { label: t("리스크 관리"), chips: summary.riskText ? [summary.riskText] : [] },
  ];

  return groups.filter((group) => group.chips.length > 0);
}

function uniqueLabels(labels: string[]): string[] {
  return Array.from(new Set(labels.filter(Boolean)));
}

type CompiledCondition = {
  id?: string;
  type?: string;
  params?: Record<string, unknown>;
};

function paramNumber(params: Record<string, unknown> | undefined, key: string): number | null {
  const raw = params?.[key];
  const value = typeof raw === "number" ? raw : raw == null ? NaN : Number(raw);
  return Number.isFinite(value) ? value : null;
}

/**
 * 컴파일된 조건(`{id, type, params}`)을 대화 카드가 쓰는 신호 모양으로 되돌린다.
 * params 키 이름은 backend/engine/strategy_converter.py::_tech_signal_to_condition의 계약
 * (signalType·period·operator·value·mode·shortMA/longMA·shortPeriod/longPeriod·lookbackPeriod).
 * 2026-09-13: 결과 화면·저장 전략 배지가 조건의 `id`만 읽고 params를 버려 "RSI 30 이하"가
 * "RSI"로, "5일선-20일선 골든크로스"가 "MA 크로스"로 뭉개졌다 — 대화 카드와 같은 라벨 함수
 * (`getSignalLabel`)를 타도록 여기서 모양만 맞춘다.
 */
function conditionToSignal(condition: CompiledCondition & { id: string }) {
  const params = condition.params;
  const signalType = params?.signalType;
  const mode = params?.mode;
  const operator = params?.operator;
  return {
    indicator: condition.id,
    signal_type: typeof signalType === "string" ? signalType : null,
    mode: typeof mode === "string" ? mode : null,
    operator: typeof operator === "string" ? operator : null,
    value: paramNumber(params, "value"),
    period: paramNumber(params, "period"),
    short_period: paramNumber(params, "shortMA") ?? paramNumber(params, "shortPeriod"),
    long_period: paramNumber(params, "longMA") ?? paramNumber(params, "longPeriod"),
    lookback_period: paramNumber(params, "lookbackPeriod"),
  };
}

function conditionToEntryLabel(condition: CompiledCondition): string | null {
  if (!condition.id) return null;

  const metric = condition.id;
  const value = paramNumber(condition.params, "value");
  // 컴파일러는 기술 신호에만 signalType을 넣는다 — 거래대금처럼 재무 필터 사전과 기술 지표
  // 사전에 모두 있는 id는 이 표식으로 가른다(재무 필터 "거래대금 >= 100억" / 게이트 "거래대금 100억 이상").
  const isTechnicalSignal = typeof condition.params?.signalType === "string";
  // 재무 필터(PBR 등). 기술 지표가 아닌 filter 타입도 재무 필터로 본다(라벨 사전에 없는 지표 대비).
  const isFundamental =
    !isTechnicalSignal &&
    (METRIC_LABELS[metric] || (condition.type === "filter" && !INDICATOR_LABELS[metric]));
  if (isFundamental && value != null) {
    return formatFundamentalFilter({
      metric,
      operator: String(condition.params?.operator ?? "<="),
      value,
    });
  }

  const signal = conditionToSignal({ ...condition, id: metric });
  // 진입 게이트 필터(추세·거래대금·RSI 결합)는 대화 카드와 같은 배지 문구를 쓴다.
  if (condition.type === "filter") {
    const gateLabel = formatEntryFilter(signal);
    if (gateLabel) return gateLabel;
  }
  return getSignalLabel(signal, "entry");
}

function conditionsToExitSignals(conditions: CompiledCondition[] | null | undefined) {
  return (conditions ?? [])
    .filter((condition): condition is CompiledCondition & { id: string } => Boolean(condition.id))
    .map(conditionToSignal);
}

// 서술형 텍스트(프롬프트/설명)에서 유니버스 라벨을 추론한다. 키워드가 없으면 null.
// 전략 프롬프트(원문 자연어)를 결정하는 단일 로직.
// settings.description(파싱 시 보존된 원문)을 우선하고, 없으면 Strategy.description으로 폴백한다.
// /analytics/[id]와 /backtest/[id]가 같은 경로·같은 로직으로 프롬프트 SOT를 공유하도록 통일.
export function resolveStrategyPrompt(
  settings: { description?: unknown } | null | undefined,
  description?: string | null
): string {
  const fromSettings =
    typeof settings?.description === "string" ? settings.description.trim() : "";
  const fromDescription = typeof description === "string" ? description.trim() : "";
  return fromSettings || fromDescription;
}

export function inferUniverseFromText(text: string | null | undefined): string | null {
  const normalized = (text ?? "").toUpperCase().replace(/\s+/g, "");
  if (!normalized) return null;
  if (normalized.includes("ETF") || normalized.includes("이티에프")) return "ETF";
  if (normalized.includes("KOSPI200")) return "KOSPI 200";
  if (normalized.includes("KOSDAQ150")) return "KOSDAQ 150";
  if (normalized.includes("KOSDAQ")) return "KOSDAQ";
  if (normalized.includes("KOSPI")) return "KOSPI";
  return null;
}

// 표시용 유니버스명을 만든다. 실제 라벨이면 그대로, 심볼 CSV/"미정"이면 컨텍스트에서 라벨을 추론한다.
// 라벨을 만들 수 없으면 null(배지 숨김).
export function resolveUniverseDisplayName(
  universeName: string | null | undefined,
  contextText?: string | null
): string | null {
  const trimmed = universeName?.trim();
  if (trimmed && trimmed !== "미정" && !isRawSymbolUniverseName(trimmed)) {
    return trimmed;
  }
  return inferUniverseFromText(contextText);
}

function inferUniverseFromLegacyStrategy(strategy: StrategyDSL | null | undefined): string {
  if (!strategy) return "미정";

  const legacyStrategy = strategy as StrategyDSL & {
    symbols?: string[];
  };
  const fromText = inferUniverseFromText(strategy.description);
  if (fromText) return fromText;

  const symbolCount = legacyStrategy.symbols?.length ?? 0;
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

  const legacyStrategy = strategy as StrategyDSL & LegacyStrategySummaryFields & {
    target_symbols?: string[];
  };
  // 지정 종목(단일 종목) 백테스트 DSL(FR-STR-068) — 캐논 DSL에는 코드만 저장된다.
  const targetSymbols = Array.isArray(legacyStrategy.target_symbols)
    ? legacyStrategy.target_symbols
    : [];
  const rawUniverse =
    Array.isArray(legacyStrategy.universe)
      ? legacyStrategy.universe[0]
      : typeof legacyStrategy.universe === "string"
        ? legacyStrategy.universe
        : legacyStrategy.universe?.id;
  const normalizedUniverse =
    (rawUniverse ? UNIVERSE_LABELS[rawUniverse] : undefined) ??
    UNIVERSE_LABELS[normalizeUniverseId(rawUniverse ?? "")];
  const displayableRawUniverse =
    rawUniverse && !isRawSymbolUniverseName(rawUniverse) ? rawUniverse : undefined;
  const universeName =
    normalizedUniverse ??
    displayableRawUniverse ??
    inferUniverseFromLegacyStrategy(strategy);
  const stopLossValue = strategy.risk?.stop_loss_pct ?? legacyStrategy.stop_loss_pct;
  const takeProfitValue = strategy.risk?.take_profit_pct ?? legacyStrategy.take_profit_pct;
  const trailingStopValue = strategy.risk?.trailing_stop_pct ?? legacyStrategy.trailing_stop_pct;
  const maxHoldingDays = strategy.risk?.max_holding_days ?? legacyStrategy.hold_period_days;
  const maxPositions = strategy.risk?.max_positions ?? legacyStrategy.max_positions;
  const rebalancingPeriod = strategy.risk?.rebalancing_period ?? legacyStrategy.rebalancing_period;
  const stopLossPct = formatDownsidePercent(stopLossValue);
  const takeProfitPct = formatPercent(takeProfitValue);
  const trailingStopPct = formatDownsidePercent(trailingStopValue);
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
    ...conditionsToExitSignals(strategy.exit?.conditions),
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
  const rebalancingText = formatRebalancingText(
    rebalancingPeriod,
    strategy.risk?.rebalance_method ?? legacyStrategy.rebalance_method,
    t,
  );

  return {
    strategyName: strategy.name,
    universeName: targetSymbols.length ? targetSymbols.join(" · ") : universeName,
    blockNames: [...entryBlocks, ...exitBlocks],
    entryBlocks,
    exitBlocks,
    positionText: targetSymbols.length && !isCandidatePoolRisk(strategy.risk)
      ? `${targetSymbols.length === 1 ? t("단일 종목 집중 투자") : t("지정 종목 {0}개 균등 투자", targetSymbols.length)}${maxHoldingDays ? t(" · {0}일 보유", maxHoldingDays) : ""}`
      : maxPositions
        ? `${t("포지션/비중 최대 {0}종목", maxPositions)}${maxHoldingDays ? t(" · {0}일 보유", maxHoldingDays) : ""}`
        : undefined,
    riskText: [
      stopLossPct ? t("손절 {0}%", stopLossPct) : "",
      takeProfitPct ? t("익절 {0}%", takeProfitPct) : "",
      trailingStopPct ? t("트레일링 스탑 {0}%", trailingStopPct) : "",
    ].filter(Boolean).join(", ") || undefined,
    rebalancingText,
    ...backtestRunTextsFromRequest({
      period: legacyStrategy.period,
      startDate: legacyStrategy.startDate,
      endDate: legacyStrategy.endDate,
      risk: (strategy.risk ?? null) as unknown as Record<string, unknown> | null,
      initial_capital: legacyStrategy.initial_capital,
    }),
  };
}
