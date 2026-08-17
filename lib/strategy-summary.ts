import type { StrategyDSL } from "@/types/strategy";
import { getLanguage, t } from "@/lib/i18n";

export interface ParsedSummary {
  description: string;
  universe: string[];
  // 섹터/업종 제한(정본 섹터명, 예: "반도체"). 복수면 배열(합집합). 없으면 null/생략.
  sector?: string | string[] | null;
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
    operator?: string | null;
    value?: number | null;
    lookback_period?: number | null;
    // 이동평균 크로스 기간(백엔드 TechnicalSignal과 동일 계약) — 크로스 칩 기간 명시화
    // (2026-07-26)가 값으로 싣는다. 미지정이면 엔진 실효 기본값(5/20)으로 동작.
    short_period?: number | null;
    long_period?: number | null;
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
  }> | null;
  // 비율 선정(FR-BT-060) — 상위 X% 편입(개수 대신 비율). 있으면 max_positions보다 우선.
  max_positions_pct?: number | null;
  // 지정 종목(단일 종목) 백테스트 대상 종목코드(FR-STR-068). 비어 있으면 유니버스 전략.
  target_symbols?: string[];
  // 지정 종목이 어느 테마 조회에서 왔는지(없으면 사용자가 직접 지목한 종목).
  // 선정 범위 판정의 입력이다 — getSelectionScope 참조.
  theme_universe?: string | null;
  max_positions: number;
  hold_period_days: number | null;
  rebalancing_period: string;
  stop_loss_pct: number | null;
  take_profit_pct: number | null;
  trailing_stop_pct?: number | null;
  backtest_period: string;
  backtest_start_date?: string | null;
  backtest_end_date?: string | null;
  initial_capital: number;
}

interface BacktestRequestLike {
  symbols?: string[];
  // 지정 종목 백테스트의 표시용 메타데이터(코드→종목명). 백엔드 to_backtest_request가 채운다.
  target_stocks?: Array<{ symbol: string; name?: string }> | null;
}

type LegacyStrategySummaryFields = {
  universe?: string | string[] | { id?: string; filters?: Record<string, unknown> };
  fundamental_filters?: Array<{ metric: string; operator: string; value: number }>;
  entry_signals?: Array<{ indicator: string; signal_type?: string | null; mode?: string | null; lookback_period?: number | null }>;
  exit_signals?: Array<{ indicator: string; signal_type?: string | null; mode?: string | null; lookback_period?: number | null }>;
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
  market_cap: "시총",
  trading_value: "거래대금",
  dividend_yield: "배당수익률",
  payout_rate: "배당성향",
  dividend_growth: "배당성장률",
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
export function formatMarketCapValue(value: number): string {
  if (!Number.isFinite(value) || value < 100_000_000) return String(value);
  return formatEokAmount(value / 100_000_000);
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
export function formatInitialCapital(value: number): string {
  if (Number.isFinite(value) && value >= 100_000_000) {
    const amount = formatMarketCapValue(value);
    return getLanguage() === "en" ? amount : t("{0}원", amount);
  }
  return t("{0}원", KO_NUMBER_FORMAT.format(value));
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
  volatility: "변동성",
  ai_model: "AI 매수 예측",
  ai_drop_model: "AI 하락 예측",
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

export function getSignalLabel(
  signal: {
    indicator: string;
    signal_type?: string | null;
    mode?: string | null;
    operator?: string | null;
    value?: number | null;
    lookback_period?: number | null;
  },
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

  const newListingLabel = formatNewListingLabel(parsed);
  if (newListingLabel) sectorLabel.push(newListingLabel);

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
  return (
    (parsed.entry_signals?.length ?? 0) > 0 ||
    (parsed.fundamental_filters?.length ?? 0) > 0 ||
    parsed.ranking_metric != null
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
  // 테마 유래 종목이라도 선정 기준(랭킹)이 있을 때만 후보군이다 — 기준이 없으면
  // 무엇을 기준으로 자를지 아무도 말하지 않았으므로 전부 매수한다.
  if (parsed.theme_universe && parsed.ranking_metric) return "CANDIDATE_POOL";
  return "EXPLICIT";
}

// 포트폴리오(보유 종목 수) 배지 문구. 지정 종목 백테스트는 "최대 N종목"(유니버스 선정)이
// 아니라 지정 종목 집중 투자임을 드러낸다. 테마 후보군에서 선정하는 전략은 지정이 아니므로
// 유니버스 전략과 같은 문구를 쓴다(실제로 그 종목 수만큼만 산다).
export function getPositionLabel(parsed: ParsedSummary): string {
  const scope = getSelectionScope(parsed);
  const targetCount = parsed.target_symbols?.length ?? 0;
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

/** 복합 순위 합산(FR-BT-063)의 구성 지표 하나 — "ROE 높은 순"·"PER 낮은 순"·"20일 수익률 높은 순". */
function componentLabel(
  c: { metric: string; direction: "top" | "bottom"; lookback_days?: number | null },
  defaultLookback: number | null | undefined,
): string {
  const dir = c.direction === "bottom" ? t("낮은 순") : t("높은 순");
  if (c.metric === "return" || c.metric === "volatility") {
    const days = c.lookback_days ?? defaultLookback;
    const name = c.metric === "return" ? t("수익률") : t("변동성");
    // 산정 기간 미정이면 일수를 붙이지 않는다(단일 랭킹 라벨과 같은 계약).
    return days != null ? t("{0}일 {1} {2}", days, name, dir) : t("{0}(산정 기간 미정) {1}", name, dir);
  }
  return `${t(METRIC_LABELS[c.metric] ?? c.metric)} ${dir}`;
}

export function getRankingLabel(parsed: ParsedSummary): string | null {
  // 산정 기간 미정(되묻기 진행 중)에 60일을 표시하면 조용한 확정으로 읽힌다(2026-08-10
  // 사용자 지시 "60일 강제 금지") — 기간이 정해진 뒤에만 일수를 붙인다.
  if (parsed.ranking_metric === "composite" && parsed.ranking_components?.length) {
    // 복합 순위 합산(FR-BT-063) — 구성 지표별 순위를 합산해 상위 선정. 내부명 대신
    // 지표 정본 라벨과 방향을 그대로 보여 준다.
    const parts = parsed.ranking_components.map((c) =>
      componentLabel(c, parsed.ranking_lookback_days),
    );
    return t("복합 순위 상위 ({0} 순위 합산)", parts.join(" + "));
  }
  if (parsed.ranking_metric === "return") {
    const days = parsed.ranking_lookback_days;
    return days != null ? t("{0}일 수익률 상위", days) : t("수익률 상위(산정 기간 미정)");
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
    positionText: `${getPositionLabel(parsed)}${parsed.hold_period_days ? t(" · {0}일 보유", parsed.hold_period_days) : ""}`,
    riskText: [
      stopLossPct ? t("손절 {0}%", stopLossPct) : "",
      takeProfitPct ? t("익절 {0}%", takeProfitPct) : "",
      trailingStopPct ? t("트레일링 스탑 {0}%", trailingStopPct) : "",
    ].filter(Boolean).join(", ") || undefined,
    rebalancingText:
      parsed.rebalancing_period && parsed.rebalancing_period !== "none"
        ? t("{0} 리밸런싱", t(REBAL_LABELS[parsed.rebalancing_period] ?? parsed.rebalancing_period))
        : undefined,
  };
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
  listing_from?: string | null;
  listing_to?: string | null;
  entry?: { conditions?: Array<{ id?: string; type?: string; params?: Record<string, unknown> }> } | null;
  exit?: { conditions?: Array<{ id?: string; type?: string; params?: Record<string, unknown> }> } | null;
  risk?: Record<string, unknown> | null;
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

  const rankingLabel = getRankingLabel({
    ranking_metric: (risk.ranking_metric as string | null) ?? null,
    ranking_lookback_days: num(risk.ranking_lookback_days),
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
    exit_signals: (req.exit?.conditions ?? [])
      .map((c) => (c.id ? { indicator: String(c.id) } : null))
      .filter((s): s is { indicator: string } => Boolean(s)),
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
    positionText: targetStockLabels.length
      ? `${targetStockLabels.length === 1 ? t("단일 종목 집중 투자") : t("지정 종목 {0}개 균등 투자", targetStockLabels.length)}${maxHoldingDays ? t(" · {0}일 보유", maxHoldingDays) : ""}`
      : maxPositions
        ? `${t("최대 {0}종목", maxPositions)}${maxHoldingDays ? t(" · {0}일 보유", maxHoldingDays) : ""}`
        : undefined,
    riskText:
      [
        stopLossPct ? t("손절 {0}%", stopLossPct) : "",
        takeProfitPct ? t("익절 {0}%", takeProfitPct) : "",
        trailingStopPct ? t("트레일링 스탑 {0}%", trailingStopPct) : "",
      ]
        .filter(Boolean)
        .join(", ") || undefined,
    rebalancingText:
      rebalancingPeriod && rebalancingPeriod !== "none"
        ? t("{0} 리밸런싱", t(REBAL_LABELS[rebalancingPeriod] ?? rebalancingPeriod))
        : undefined,
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
    { label: t("유니버스"), chips: showUniverse ? [universeName!] : [] },
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

function getIndicatorLabel(indicator: string): string {
  return t(INDICATOR_LABELS[indicator] ?? indicator);
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
      ? t("{0} 리밸런싱", t(REBAL_LABELS[rebalancingPeriod] ?? rebalancingPeriod))
      : undefined;

  return {
    strategyName: strategy.name,
    universeName: targetSymbols.length ? targetSymbols.join(" · ") : universeName,
    blockNames: [...entryBlocks, ...exitBlocks],
    entryBlocks,
    exitBlocks,
    positionText: targetSymbols.length
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
  };
}
