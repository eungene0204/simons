import type { StrategyDSL } from "@/types/strategy";

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
  ranking_metric?: "return" | null;
  ranking_lookback_days?: number | null;
  // 지정 종목(단일 종목) 백테스트 대상 종목코드(FR-STR-068). 비어 있으면 유니버스 전략.
  target_symbols?: string[];
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
};

const KO_NUMBER_FORMAT = new Intl.NumberFormat("ko-KR");

// 시총처럼 원 단위 큰 금액(>=1억)을 '100억' / '1조' / '1조 5,000억' 형태로 표시한다.
// 1억 미만이거나 숫자가 아니면 원본을 그대로 둔다(단위가 모호한 값 오변환 방지).
export function formatMarketCapValue(value: number): string {
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
// 진입 게이트 필터(추세·거래대금·RSI 결합) 배지 라벨. 인식 못 하면 빈 문자열(배지 생략).
export function formatEntryFilter(filter: {
  indicator: string;
  mode?: string | null;
  period?: number | null;
  operator?: string | null;
  value?: number | null;
}): string {
  if (filter.indicator === "ema" && (filter.mode === "above" || filter.mode === "below")) {
    return `${filter.period ?? 200}일선 ${filter.mode === "above" ? "위" : "아래"}`;
  }
  if (filter.indicator === "trading_value") {
    return `거래대금 ${KO_NUMBER_FORMAT.format(filter.value ?? 100)}억 이상`;
  }
  if (filter.indicator === "rsi") {
    return `RSI ${filter.value ?? 30} 이하`;
  }
  return "";
}

export function formatFundamentalFilter(filter: {
  metric: string;
  operator: string;
  value: number;
}): string {
  const label = METRIC_LABELS[filter.metric] ?? filter.metric;
  // EPS·영업이익 부호 필터는 '흑자/적자' 키워드 조건의 표현형 — 사용자 어휘로 배지를 만든다.
  if (filter.metric === "eps" && filter.value === 0) {
    if (filter.operator === ">") return "흑자 기업 (EPS > 0)";
    if (filter.operator === "<") return "적자 기업 (EPS < 0)";
  }
  if (filter.metric === "ebit" && filter.value === 0) {
    if (filter.operator === ">") return "영업이익 흑자 기업";
    if (filter.operator === "<") return "영업이익 적자 기업";
  }
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

// 백테스트 기간 배지. 명시 날짜가 있으면 그 창을 그대로 보여준다 — 상대 기간 라벨
// ("5년")은 신규 상장 코호트처럼 창이 조정된 경우 실제 실행 구간과 어긋난다.
export function formatBacktestPeriodLabel(parsed: {
  backtest_period?: string | null;
  backtest_start_date?: string | null;
  backtest_end_date?: string | null;
}): string | null {
  const from = parsed.backtest_start_date ?? null;
  const to = parsed.backtest_end_date ?? null;
  if (from) return `${from} ~ ${to ?? "현재"}`;
  if (to) return `~ ${to}`;
  const period = parsed.backtest_period ? String(parsed.backtest_period).toLowerCase() : null;
  if (!period) return null;
  return PERIOD_LABELS[period] ?? period;
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
    return INDICATOR_LABELS.ai_drop_model;
  }

  // 브레이크아웃은 기준 기간(lookback_period)에 따라 의미가 달라진다 — 252일(≈52주)은 "52주 신고가",
  // 그 밖의 N일은 "N일 고점 돌파"(매수)/"N일 저점 이탈"(매도)로 구체화한다. 기간 미상이면 일반 라벨.
  if (signal.indicator === "breakout") {
    const isDown =
      signal.signal_type === "sell" || (signal.signal_type == null && context === "exit");
    const days = signal.lookback_period ?? null;
    if (days === 252) return isDown ? "52주 신저가 이탈" : "52주 신고가 돌파";
    if (days != null) return isDown ? `${days}일 저점 이탈` : `${days}일 고점 돌파`;
    return INDICATOR_LABELS.breakout;
  }

  // RSI 반등(mode "rebound")은 단순 임계값 비교가 아니라 과매도/과매수 임계선을 '다시 돌파'하는
  // 크로스오버다(backend/engine/signals.py). 배지가 "RSI"로만 나오면 이 뉘앙스가 사라지므로,
  // 매수=상향 반등 / 매도=하향 반전으로 임계값과 함께 표기한다. 순수 임계값 비교(mode 없음)는
  // 기존대로 "RSI"만 노출한다.
  if (signal.indicator === "rsi" && signal.mode === "rebound") {
    const isDown =
      signal.signal_type === "sell" || (signal.signal_type == null && context === "exit");
    const threshold = signal.value ?? (isDown ? 70 : 30);
    return isDown ? `RSI ${threshold} 하향 반전` : `RSI ${threshold} 상향 반등`;
  }

  // 순수 임계값 비교 RSI는 operator/value가 있으면 "RSI 50 이상"처럼 구체적으로 표기한다.
  // 정보가 없으면(레거시 데이터 등) 기존대로 "RSI"만 노출한다.
  if (signal.indicator === "rsi" && signal.operator != null && signal.value != null) {
    const opKr = OPERATOR_KO_LABELS[signal.operator] ?? signal.operator;
    return `RSI ${signal.value} ${opKr}`;
  }

  if (signal.indicator === "ai_model" && (context === "exit" || signal.signal_type === "sell")) {
    return INDICATOR_LABELS.ai_drop_model;
  }

  const cross = DIRECTIONAL_CROSS_LABELS[signal.indicator];
  if (cross) {
    // signal_type이 없으면 청산 컨텍스트를 하향(데드)으로 본다.
    const isDown =
      signal.signal_type === "sell" || (signal.signal_type == null && context === "exit");
    if (signal.indicator === "macd" && signal.mode === "zero") {
      return isDown ? "MACD 제로선 하향 돌파" : "MACD 제로선 상향 돌파";
    }
    return isDown ? cross.dead : cross.golden;
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
  if (!from && !to) return "신규 상장";
  if (!from) return `${to} 이전 상장`;
  const year = from.slice(0, 4);
  if (from === `${year}-01-01` && to === `${year}-12-31`) return `${year}년 상장`;
  return to ? `${from}~${to} 상장` : `${from} 이후 상장`;
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
  const sectorLabel = sectors.map((sector) => `${sector} 업종`);

  // ETF 테마/상품명 필터 배지 — 상품명("KODEX 200", 라틴 브랜드 포함)은 그대로,
  // 테마 키워드("반도체", "미국")는 "테마"를 붙인다.
  if (parsed.etf_theme) {
    sectorLabel.push(
      /[a-z]/i.test(parsed.etf_theme) ? parsed.etf_theme : `${parsed.etf_theme} 테마`
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
    ...normalizedUniverses.map((universe) => UNIVERSE_LABELS[universe] ?? universe),
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

// 포트폴리오(보유 종목 수) 배지 문구. 지정 종목 백테스트는 "최대 N종목"(유니버스 선정)이
// 아니라 지정 종목 집중 투자임을 드러낸다.
export function getPositionLabel(parsed: ParsedSummary): string {
  const targetCount = parsed.target_symbols?.length ?? 0;
  if (targetCount === 1) return "단일 종목 집중 투자";
  if (targetCount > 1) return `지정 종목 ${targetCount}개 균등 투자`;
  return `최대 ${parsed.max_positions}종목`;
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
    positionText: `${getPositionLabel(parsed)}${parsed.hold_period_days ? ` · ${parsed.hold_period_days}일 보유` : ""}`,
    riskText: [
      stopLossPct ? `손절 ${stopLossPct}%` : "",
      takeProfitPct ? `익절 ${takeProfitPct}%` : "",
      trailingStopPct ? `트레일링 스탑 ${trailingStopPct}%` : "",
    ].filter(Boolean).join(", ") || undefined,
    rebalancingText:
      parsed.rebalancing_period && parsed.rebalancing_period !== "none"
        ? `${REBAL_LABELS[parsed.rebalancing_period] ?? parsed.rebalancing_period} 리밸런싱`
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
    .map((token) => UNIVERSE_LABELS[token] ?? token.toUpperCase())
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
    ranking_metric: (risk.ranking_metric as "return" | null) ?? null,
    ranking_lookback_days: num(risk.ranking_lookback_days),
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

  const stopLossPct = formatPercent(stopLoss);
  const takeProfitPct = formatPercent(takeProfit);
  const trailingStopPct = formatPercent(trailingStop);

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
            (sector) => `${sector} 업종`
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
      ? `${targetStockLabels.length === 1 ? "단일 종목 집중 투자" : `지정 종목 ${targetStockLabels.length}개 균등 투자`}${maxHoldingDays ? ` · ${maxHoldingDays}일 보유` : ""}`
      : maxPositions
        ? `최대 ${maxPositions}종목${maxHoldingDays ? ` · ${maxHoldingDays}일 보유` : ""}`
        : undefined,
    riskText:
      [
        stopLossPct ? `손절 ${stopLossPct}%` : "",
        takeProfitPct ? `익절 ${takeProfitPct}%` : "",
        trailingStopPct ? `트레일링 스탑 ${trailingStopPct}%` : "",
      ]
        .filter(Boolean)
        .join(", ") || undefined,
    rebalancingText:
      rebalancingPeriod && rebalancingPeriod !== "none"
        ? `${REBAL_LABELS[rebalancingPeriod] ?? rebalancingPeriod} 리밸런싱`
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
    { label: "유니버스", chips: showUniverse ? [universeName!] : [] },
    { label: "진입신호", chips: (summary.entryBlocks ?? []).filter(Boolean) },
    { label: "청산신호", chips: (summary.exitBlocks ?? []).filter(Boolean) },
    {
      label: "리스트",
      chips: [summary.positionText, summary.rebalancingText].filter(
        (value): value is string => Boolean(value)
      ),
    },
    { label: "리스크 관리", chips: summary.riskText ? [summary.riskText] : [] },
  ];

  return groups.filter((group) => group.chips.length > 0);
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
    universeName: targetSymbols.length ? targetSymbols.join(" · ") : universeName,
    blockNames: [...entryBlocks, ...exitBlocks],
    entryBlocks,
    exitBlocks,
    positionText: targetSymbols.length
      ? `${targetSymbols.length === 1 ? "단일 종목 집중 투자" : `지정 종목 ${targetSymbols.length}개 균등 투자`}${maxHoldingDays ? ` · ${maxHoldingDays}일 보유` : ""}`
      : maxPositions
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
