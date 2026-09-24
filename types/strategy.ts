import type { TradeReasonSegment } from "@/lib/trade-reason";

// Strategy DSL Types
export type ConditionType = "indicator" | "flow" | "risk" | "ml" | "filter";

export type IndicatorType =
  | "ma_crossover"
  | "rsi"
  | "macd"
  | "bollinger_bands"
  | "volume_spike"
  | "volume_ratio"
  | "trading_value_ratio"
  | "breakout"
  | "stochastic"
  | "cci"
  | "adx"
  | "williams_r"
  | "mfi"
  | "roc"
  | "relative_return"
  | "volatility";

export type FlowType = "investor_net_buy";

export type RiskType =
  | "stop_loss_pct"
  | "take_profit_pct"
  | "max_holding_days"
  | "trailing_stop";

export type MLType = "probability" | "sentiment" | "pattern";

export interface Condition {
  type: ConditionType;
  id: string;
  params: Record<string, any>;
  weight?: number; // For weighted sum
}

export interface ConditionGroup {
  conditions: Condition[];
}

export interface RiskManagement {
  position_size_pct: number; // Percentage of capital per trade
  max_positions: number; // Maximum concurrent positions
  min_cash_reserve_pct?: number; // Minimum cash reserve percentage
  max_daily_buy_pct?: number; // Maximum daily buy limit as % of capital
  stop_loss_pct?: number; // Fixed stop loss percentage
  take_profit_pct?: number; // Fixed take profit percentage
  trailing_stop_pct?: number; // Trailing stop loss percentage
  liquidity_limit_pct?: number; // Liquidity limit percentage
  max_holding_days?: number; // Maximum holding period in days
  max_daily_loss_pct?: number; // Maximum daily loss percentage
  max_total_exposure_pct?: number; // Maximum total exposure
  max_sector_exposure_pct?: number; // Maximum sector concentration
  max_mdd_limit_pct?: number; // Maximum drawdown limit
  /** 비율 선정(FR-BT-060) — 랭킹 후보의 상위 X%만 편입(개수 max_positions 대신). */
  max_positions_pct?: number;
  /** 분위 그룹 비교(FR-BT-060) — 랭킹 후보를 종목 수 동일 G개 그룹으로 나눠 그룹별 백테스트. */
  ranking_quantile_groups?: number;
  /** 복합 순위 합산(FR-BT-063) — ranking_metric='composite'일 때 구성 지표(백분위 순위 동일 가중 평균). */
  ranking_components?: Array<{ metric: string; direction: "top" | "bottom"; lookback_days?: number | null; weight?: number | null }>;
  execution_timing?: "next_open" | "current_close" | "next_avg";
  /** 신호 후 N거래일 지연 체결 — next_open의 체결 봉 간격(1=다음 거래일 시가, N=N번째 거래일 시가).
   *  없으면 엔진 기본값 1. current_close에서는 1 초과 값을 엔진이 거절한다. */
  execution_delay_days?: number;
  /** 정액 적립식(엔진 v16.20) — 회차 납입액과 주기. 둘 다 있어야 하고 지정 종목 전략에서만 받는다
   *  (첫 거래일은 초기 자본, 이후 각 주기의 첫 거래일마다 납입). */
  contribution_amount?: number | null;
  contribution_period?: ContributionPeriod | null;
  /** 정기 인출(엔진 v16.33) — 회차 인출액과 주기. 각 주기 첫 거래일마다 현금·보유 매도로 마련해 내보낸다. */
  withdrawal_amount?: number | null;
  withdrawal_period?: ContributionPeriod | null;
  /** 조건부 납입액 규칙(엔진 v16.21) — 납입일에 condition이 성립하면 그 회차 납입액을 amount로(set)/amount만큼 더(add). */
  contribution_rules?: Array<{ condition: Record<string, unknown>; amount: number; mode: "set" | "add" }> | null;
  /** 현금 풀(엔진 v16.22) — 'cash_pool'이면 초기 자본(보유 현금)에서 회차 매수액을 꺼낸다. 하한은 %·금액 중 하나. */
  contribution_funding?: "cash_pool" | null;
  cash_reserve_pct?: number | null;
  cash_reserve_amount?: number | null;
  max_buy_cash_pct?: number | null;
  /** 비중 방식 — 엔진 v16.28: 시총가중·최소분산·리스크패리티(ERC)·최대샤프·최소CVaR·고정 배분 추가. */
  allocation_type?: "equal" | "fixed_pct" | "inverse_volatility" | "market_cap" | "min_variance" | "risk_parity" | "max_sharpe" | "min_cvar" | "fixed";
  allocation_lookback_days?: number | null;
  /** 고정 배분(정적 자산배분, 엔진 v16.28) — {종목코드: 비중 %}. allocation_type='fixed'일 때. */
  target_weights?: Record<string, number> | null;
  /** 밴드 리밸런싱(%p, 엔진 v16.28) — 보유 비중이 목표에서 이만큼 벗어나면 되돌린다. */
  rebalance_threshold_pct?: number | null;
  /** 최소 보유 기간(거래일, 엔진 v16.28) — 그 안에는 매도 조건·손절·익절·편출 미적용. */
  min_holding_days?: number | null;
  /** 손절·익절·트레일링 뒤 재진입 금지 기간(거래일, 엔진 v16.28). */
  stop_cooldown_days?: number | null;
  /** 트레일링 스탑 활성화 수익률(%, 엔진 v16.28). */
  trailing_stop_activation_pct?: number | null;
  /** 지정가(%, 엔진 v16.28) — 매수는 전일 종가 대비 -x%, 매도(조건 청산)는 +y%. */
  entry_limit_pct?: number | null;
  exit_limit_pct?: number | null;
  /** 분할 매수(엔진 v16.28) — count회차, 회차마다 step_pct% 낮은 가격. */
  entry_tranches?: { count: number; step_pct: number } | null;
  /** 분할 익절(엔진 v16.28) — profit_pct 도달 시 보유 비중의 sell_pct% 매도. */
  partial_take_profits?: Array<{ profit_pct: number; sell_pct: number }> | null;
  /** 포지션 사이징(엔진 v16.28) — ATR 위험 예산 또는 켈리. */
  position_sizing?: { method: "atr_risk" | "kelly"; risk_per_trade_pct?: number; atr_period?: number; atr_multiple?: number; kelly_fraction?: number } | null;
  /** 현금 대체 자산(종목코드, 엔진 v16.28) — 미투자 현금을 이 자산으로 보유. */
  cash_asset?: string | null;
  /** 절대 모멘텀 임계(%, 엔진 v16.28) — 수익률 랭킹에서 최근 수익률이 이 값 이하면 편입하지 않음. */
  absolute_momentum_threshold_pct?: number | null;
  /** 매크로 조건 필터(엔진 v16.31) — 금리·환율·VIX 시계열 조건 충족일의 목표 노출(OR, 가장 낮은 노출). */
  macro_filters?: Array<{ series: string; mode?: "level" | "change" | "ma"; operator: "<" | "<=" | ">" | ">="; value?: number | null; period?: number | null; exposure_pct: number }> | null;
  /** 전술 자산배분 템플릿(엔진 v16.29) — VAA/DAA/PAA. ranking_metric='taa'·allocation_type='schedule'. */
  taa?: { model: "vaa" | "daa" | "paa"; offensive: string[]; defensive: string[]; canary?: string[]; top_n?: number | null } | null;
  rebalancing_period?: string;
  /** 리밸런싱 방식(FR-BT-067) — 'reconstitute'=리밸런싱일마다 목표 종목 재선정,
   *  'weights_only'=종목 교체 없이 비중만 균등 리셋. 없으면 엔진 기본값(종목 교체). */
  rebalance_method?: "reconstitute" | "weights_only";
  skip_risk_management?: boolean;
  skip_position_setting?: boolean;
}

export interface UniverseSelection {
  id: string; // e.g., "kospi", "kosdaq", "US_TECH_TOP10"
  filters: Record<string, any>;
}

export interface StrategyDSL {
  id: string;
  name: string;
  description: string;
  version: string;
  universe: UniverseSelection;
  entry: ConditionGroup;
  exit: ConditionGroup;
  risk: RiskManagement;
  created_at: string;
  updated_at: string;
}

// Signal Block Definitions
export interface SignalBlock {
  id: string;
  name: string;
  description: string;
  category: "indicator" | "flow" | "risk" | "ml" | "filter";
  hidden?: boolean;
  icon?: string;
  defaultParams: Record<string, any>;
  paramSchema: {
    [key: string]: {
      type: "number" | "string" | "boolean" | "select";
      label: string;
      min?: number;
      max?: number;
      step?: number;
      options?: { value: any; label: string }[];
      tooltip?: string;
      suffix?: string;
    };
  };
}

// VectorBT Native Engine Result (for comparison)
export interface VBTNativeResult {
  totalReturn: number;
  cagr: number;
  buyAndHoldReturn: number;
  maxDrawdown: number;
  winRate: number;
  profitFactor: number;
  sharpe: number;
  sortino: number;
  kelly?: number;
  volatility: number;
  trades: number;
  avgProfit?: number;
  avgLoss?: number;
  maxConsecutiveWins?: number;
  maxConsecutiveLosses?: number;
  equity: number[];
  /** 벤치마크 지수 미존재 구간은 null (엔진 v11.0) */
  benchmark_equity?: (number | null)[];
  /** 벤치마크가 백테스트 구간의 일부만 덮는가 (엔진 v11.0) */
  benchmark_partial?: boolean;
  dates: string[];
  finalEquity?: number;
  initialCapital?: number;
}

/** 분위 그룹 1개의 요약 결과(FR-BT-060) — 백엔드 `_quantile_group_summary` 계약. */
export interface QuantileGroupSummary {
  group: number;
  /** 예: "1그룹 (PER(주가수익비율) 낮은 순 0~10%)" */
  label: string;
  /** 랭킹 순 백분위 구간 [시작%, 끝%] */
  pctRange: number[];
  totalReturn: number;
  cagr: number;
  maxDrawdown: number;
  sharpe: number;
  winRate: number;
  trades: number;
  finalEquity: number;
  /** 다운샘플된 자산곡선(그래프용, 최대 ~300 포인트) */
  equity: number[];
  dates: string[];
}

/** 분위 그룹 비교 결과(FR-BT-060) — 랭킹 후보를 종목 수 동일 G개 그룹으로 나눠 각각 백테스트. */
/** 팩터 예측력 통계(엔진 v16.26) — 리밸런싱일 점수 순위와 다음 리밸런싱일까지 수익률 순위의 스피어만 IC. */
/** 결과 심화 분석(엔진 v16.30) — 귀인·팩터 노출·거래 분포·위험·턴오버·유동성·다중 벤치마크. 과거 통계이며 예측·추천이 아니다. */
export interface AnalyticsStat { mean: number | null; median: number | null; worst: number | null; best: number | null; count: number }
export interface AnalyticsHistogramBin { from: number | null; to: number | null; count: number; unit: string }
export interface AnalyticsResult {
  attribution: {
    symbols: Array<{ symbol: string; name: string; sector: string; pnl: number | null; contributionPct: number | null; trades: number }>;
    sectors: Array<{ sector: string; pnl: number | null; contributionPct: number | null; symbols: number; trades: number }>;
    total: number | null; totalContributionPct?: number | null; symbolCount?: number;
  };
  factorExposure: {
    available: boolean; reason?: string; symbols?: number; observations?: number; minSymbols?: number;
    alphaAnnualPct?: number | null; alphaTStat?: number | null; r2?: number | null;
    loadings?: Array<{ factor: string; beta: number | null; tStat: number | null }>; note?: string;
  };
  tradeDistribution: {
    trades: number;
    returnHistogram: AnalyticsHistogramBin[];
    holdingHistogram: AnalyticsHistogramBin[];
    holdingDays?: { mean: number | null; median: number | null; max: number };
    mae: { all: AnalyticsStat | null; winners: AnalyticsStat | null; losers: AnalyticsStat | null } | null;
    mfe: { all: AnalyticsStat | null; winners: AnalyticsStat | null; losers: AnalyticsStat | null } | null;
    points: Array<[number | null, number | null, number | null]>;
  };
  riskStats: {
    var95: number | null; cvar95: number | null; var99: number | null; cvar99: number | null;
    rollingSharpe: Array<number | null>; rollingBeta: Array<number | null>; window: number;
  };
  turnover: { total: number | null; annual: number | null };
  liquidity: {
    orders: number; maxParticipation: number | null; meanParticipation: number | null; p95Participation: number | null;
    shareAboveCap: number | null; capitalAtCap: number | null; cap: number; reason?: string;
  };
  benchmarks: Array<{
    symbol: string; name: string; totalReturn: number | null; cagr: number | null; maxDrawdown: number | null; partial: boolean;
    beta: number | null; alpha: number | null; trackingError: number | null; informationRatio: number | null;
  }>;
  /** 실제 보유했던 종목 간 상관행렬과 롱온리 효율적 프론티어(엔진 v16.33, 과거 통계). */
  portfolioMix?: PortfolioMixResult | null;
}

/** 자산 상관·효율적 프론티어(엔진 v16.33) — 과거 데이터의 기술 통계이며 추천이 아니다. */
export interface PortfolioMixResult {
  available: boolean;
  reason?: string;
  symbols?: string[];
  observations?: number;
  correlation?: Array<Array<number | null>>;
  avgCorrelation?: number | null;
  maxCorrelation?: number | null;
  minCorrelation?: number | null;
  strategy?: { returnPct: number | null; volatilityPct: number | null; sharpe: number | null };
  frontier?: PortfolioMixPoint[];
  minVariance?: PortfolioMixPoint | null;
  maxSharpe?: PortfolioMixPoint | null;
  frontierReason?: string;
}

export interface PortfolioMixPoint {
  returnPct: number | null;
  volatilityPct: number | null;
  sharpe: number | null;
  weights: Array<{ symbol: string; weightPct: number | null }>;
}

export interface FactorIcResult {
  meanIc: number;
  icStd: number;
  /** meanIc ÷ icStd. IC 표준편차 0이면 null */
  icir: number | null;
  /** IC가 양수였던 기간 비율(0~1) */
  positiveRate: number;
  periods: number;
  quantiles: number;
  /** 점수 상위 1/quantiles 그룹 평균 수익률 − 하위 그룹(%p, 기간 평균) */
  topBottomSpread: number;
}

export interface QuantileGroupsResult {
  groups: QuantileGroupSummary[];
  /** 랭킹 지표 표시명(예: "PER(주가수익비율)") */
  metricLabel: string;
  /** 정렬 설명(예: "PER(주가수익비율) 낮은 순") */
  orderLabel: string;
  groupCount: number;
  /** 메인 결과가 어느 그룹의 포트폴리오인지(항상 1) */
  mainGroup: number;
  /** 그룹당 보유 상한(FR-BT-060b). 없으면 그룹 구간 전체 보유 */
  groupCap?: number | null;
}

// Backtest Result Types
/** 백엔드 표시 문구 세그먼트(매매사유·경고 공통) — {t: 한국어 정본 템플릿, a: 인자} 또는 {s: 리터럴}. */
export type BacktestWarningSegment = { t: string; a?: unknown[]; m?: number[] } | { s: string };


export type ContributionPeriod = "daily" | "weekly" | "monthly" | "bimonthly" | "quarterly" | "semiannual" | "yearly";

/** 정액 적립식 결과 요약(backend engine/result_handler.py format_contribution_results). */
export interface BacktestContributions {
  period: ContributionPeriod;
  /** 회차 납입액(시장 통화). */
  amount: number;
  /** 납입 횟수(초기 자본 포함). */
  count: number;
  totalContributed: number;
  finalValue: number;
  /** 평가 손익 = 기말 평가액 − 총 납입액. */
  profit: number;
  /** 단순 수익률(%) = 평가 손익 ÷ 총 납입액. 납입 시점은 반영하지 않는다. */
  simpleReturn: number;
  /** 금액가중 수익률(연 %, XIRR). 해가 없으면 null. */
  moneyWeightedReturn: number | null;
  /** 현금 풀(v16.22) — 'cash_pool'이면 밖에서 돈이 들어오지 않고 보유 현금(초기 자본)에서 꺼내 샀다. 아래 키는 그때만 있다. */
  funding?: "cash_pool";
  investedTotal?: number;
  finalCash?: number;
  cashReserve?: number;
  maxBuyCashPct?: number | null;
  limitedRounds?: number;
  /** 조건부 납입액 규칙별 적용 결과(v16.21) — 규칙이 없으면 키가 없다. */
  rules?: Array<{ amount: number; mode: "set" | "add"; applied: number; condition: string }>;
  /** 거래일별 누적 납입액 — dates·equity와 같은 길이. */
  cumulative: number[];
}

export interface BacktestTradingCosts {
  buyFeeRate: number;
  sellFeeRate: number;
  slippageRate: number;
  sellTaxRate: number | null;
  sellTaxRateRange?: [number, number] | null;
  /** 배당 재투자에 적용한 배당소득세율(소수, 엔진 v16.33). 배당 미반영이면 null. */
  dividendTaxRate?: number | null;
}

/** 위험조정 지표의 기준 금리(엔진 v16.33) — source: market=시장 단기금리 평균, explicit=요청값, unavailable=자료 없음. */
export interface BacktestRiskFreeRate {
  annualPct: number;
  source: "market" | "explicit" | "unavailable";
  series?: string | null;
  label?: string | null;
  labelEn?: string | null;
  coverage?: number;
}

/** 물가(CPI) 기준 실질 수익률(엔진 v16.33). covered=false면 물가 자료가 창 끝까지 닿지 않았다. */
export interface BacktestInflation {
  totalPct: number | null;
  annualPct: number | null;
  realCagrPct?: number | null;
  realTotalReturnPct?: number | null;
  series: string;
  label: string;
  label_en?: string;
  from: string;
  to: string;
  windowTo: string;
  covered: boolean;
}

/** 정기 인출 집계(엔진 v16.33). */
export interface BacktestWithdrawals {
  period: string;
  amount: number;
  count: number;
  totalWithdrawn: number;
  shortfallRounds: number;
}

export interface BacktestResult {
  executionId: string;
  strategyId: string;
  symbol?: string; // Kept for backward compatibility
  symbols?: string[]; 
  totalReturn: number;
  cagr: number;
  buyAndHoldReturn: number;
  maxDrawdown: number;
  winRate: number;
  /** 총이익÷총손실. null = 손실 거래 0건이라 정의되지 않음(∞) — 0(이익 없음)과 다르다 */
  profitFactor: number | null;
  sharpe: number;
  sortino: number;
  /** 켈리 기준(%) = W − (1−W)/R. null = 승·패 한쪽 표본이 없어 R을 못 구함 */
  kelly?: number | null;
  volatility?: number;
  calmar?: number;
  /** 벤치마크 대비 통계(엔진 v16.25). null = 벤치마크 없음·표본 부족으로 정의 불가 */
  beta?: number | null;
  /** 젠센 알파(연환산 %) — 결과 카드의 '초과 수익(α)'(총수익률 차)과 다른 값 */
  alpha?: number | null;
  trackingError?: number | null;
  informationRatio?: number | null;
  avgHoldingDays?: number;
  /** 포지션 보유일 비율 (%) — 2026-07 엔진 감사에서 추가된 통계 */
  exposure?: number;
  /** 최장 수중(underwater) 기간 (거래일) */
  maxDrawdownDuration?: number;
  /** 평균 거래 수익률 (%) = 승률×평균수익 − 패률×평균손실 */
  expectancy?: number;
  /** 순이익 ÷ 최대 낙폭 금액 */
  recoveryFactor?: number;
  trades: number;
  avgProfit?: number;
  avgLoss?: number;
  maxConsecutiveWins?: number;
  maxConsecutiveLosses?: number;
  finalEquity: number;
  initialCapital: number;
  /** 최종자산 - 초기자본 (백엔드 엔진이 직접 계산해 내려줌) */
  totalProfit?: number;
  equity: number[];
  /** 벤치마크 지수 미존재 구간은 null (엔진 v11.0) */
  benchmarkEquity?: (number | null)[];
  dates: string[];
  tradesList: Array<{
    date: string;
    symbol: string;
    type: "buy" | "sell";
    price: number;
    quantity: number;
    amount?: number;
    /** 매도 체결의 순손익(원, 수수료·거래세 차감). 매수·구버전 결과에는 없다. */
    pnl?: number;
    /** 백엔드가 만든 한국어 정본 문장. 파츠가 없는 구버전 결과의 표시값이다. */
    reason: string;
    /** 표시 번역용 구조화 사유(템플릿+인자). 구버전 결과에는 없다 — lib/trade-reason.ts */
    reasonParts?: TradeReasonSegment[];
  }>;
  monthlyReturns: Record<string, number>;
  yearlyReturns: Record<string, number>;
  signals: Array<{
    date: string;
    symbol: string;
    type: "entry" | "exit";
    condition: string;
    price: number;
    quantity?: number;
    amount?: number;
    /** 청산 신호의 순손익(원, 수수료·거래세 차감). 진입·구버전 결과에는 없다. */
    pnl?: number;
  }>;
  perAssetStats?: Record<string, {
    symbol: string;
    totalReturn: number;
    trades: number;
    winRate: number;
    profit: number;
  }>;
  benchmarkLabel?: string;
  /** 벤치마크가 백테스트 구간의 일부만 덮는가 — true면 전략과 기간이 달라
   *  초과수익률(두 수익률의 차이)을 비교값으로 쓸 수 없다 (엔진 v11.0) */
  benchmarkPartial?: boolean;
  universeId?: string;
  warnings?: string[];
  /** warnings와 같은 순서의 구조화 경고(한국어 정본 템플릿+인자, backend/engine/result_warnings.py).
   *  /us 표시 번역용 — 구버전 저장 결과에는 없다(그때는 warnings 문장을 사전 키로 조회). */
  warningParts?: BacktestWarningSegment[][];
  /** 분위 그룹 비교 결과(FR-BT-060). 분위 그룹 전략일 때만 존재. */
  quantileGroups?: QuantileGroupsResult;
  /** 팩터 예측력 통계(엔진 v16.26). 랭킹+정기 리밸런싱 전략일 때만 존재. */
  factorIc?: FactorIcResult | null;
  /** 결과 심화 분석(엔진 v16.30). 최적화 세션·구버전 결과에는 없음. */
  analytics?: AnalyticsResult | null;
  /** 연환산 회전율(%, 엔진 v16.30). */
  turnover?: number | null;
  /** 리밸런싱 기간별 결과 비교(FR-BT-064) — 같은 전략을 6주기로 재시뮬레이션한 지표.
   *  엔진이 백테스트마다 동봉한다(구버전 저장 결과에는 없음). */
  rebalanceComparison?: {
    periods: Array<{
      period: string; cagr?: number | null; mdd?: number | null; sharpe?: number | null;
      profitFactor?: number | null; trades?: number; turnover?: number | null;
      totalReturn?: number | null; winRate?: number | null; finalEquity?: number | null; error?: string | null;
    }>;
    currentPeriod?: string;
    positionCapAbsent?: boolean;
  } | null;
  /** 데이터 커버리지 리포트 — 펀더멘털 지표별 종목·기간 커버리지(데이터 부족 투명성). */
  dataCoverage?: {
    baseData: string[];
    metrics: Array<{
      key: string;
      label: string;
      status: "used" | "partial" | "unused";
      periodCoveragePct: number;
      symbolCoveragePct: number;
      symbolsWithData: number;
      symbolsTotal: number;
      /** 결측이 아니라 적자·자본잠식이라 비율 산정 불가로 제외된 행 수(진짜 결측과 분리). */
      negativeExcludedRows: number;
      negativeExcludedPct: number;
      availableFrom: string | null;
      availableTo: string | null;
    }>;
    usedData: string[];
    partialData: string[];
    unusedData: string[];
    warnings: string[];
    warningParts?: BacktestWarningSegment[][];
  };
  /** 이 결과가 실제로 적용한 거래 비용(소수 비율, backend engine/simulator.py applied_trading_costs).
   *  sellTaxRate는 고정 세율일 때만 값이고, 시행일 기준 법정 세율 스케줄이면 null + sellTaxRateRange.
   *  구버전 저장 결과에는 없다. */
  tradingCosts?: BacktestTradingCosts | null;
  /** 샤프·소르티노·정보비율의 기준 금리와 그 근거(엔진 v16.33). */
  riskFreeRate?: BacktestRiskFreeRate | null;
  /** 물가 조정 실질 수익률(엔진 v16.33). 물가 자료가 없으면 null. */
  inflation?: BacktestInflation | null;
  /** 정기 인출 결과(엔진 v16.33). 인출 요청이 없으면 null. */
  withdrawals?: BacktestWithdrawals | null;
  /** 정액 적립식 결과(엔진 v16.20). 이 값이 있으면 totalReturn·cagr·maxDrawdown·sharpe는 납입 효과를
   *  걷어낸 시간가중 수익률 기준이고, equity는 납입으로도 오른다 — '최종÷초기−1' 계산을 쓰지 않는다. */
  contributions?: BacktestContributions | null;
  /** 이 결과를 산출한 백테스트 엔진 버전 (backend engine/version.py). */
  engineVersion?: string;
  executionTime?: number;
  fromCache?: boolean;
  cachedAt?: string;
  cacheKey?: string;
  /** 이 결과를 만든 엔진 요청(BacktestRequest 키만). 기록 저장 시 함께 남겨 결과 페이지가
   *  같은 전략을 다시 실행(리밸런싱 기간별 비교 FR-BT-064)할 수 있게 한다 — 원천 Strategy 행이
   *  없는 기록에서도 동작하도록. 구버전 기록에는 없다. */
  executedRequest?: Record<string, unknown> | null;
  vbtResult?: VBTNativeResult;
  aiSummary?: string | null;
  aiScore?: number | null;
  aiStrengths?: string[];
  aiWeaknesses?: string[];
  aiImprovements?: string[];
  advisorScore?: number | null;
  riskScore?: number | null;
  overfitRisk?: string | null;
  // 전략 검증 전문가 리포트(10섹션) — 저장된 기록 재조회 시 metrics blob에서 하이드레이트.
  aiTopInsights?: string[];
  aiHiddenRisks?: string[];
  aiOverfittingAnalysis?: string;
  aiStrategyProfile?: string[];
  aiStrategyProfileNote?: string;
  aiValidationRoadmap?: Array<{ title: string; reason: string; priority: number }>;
  aiFinalVerdict?: string;
}



export interface BacktestScenario {
  id: string;
  strategyId: string;
  strategyName: string;
  params: Record<string, any>;
  results: BacktestResult;
  timestamp: string;
}

export interface BacktestHistoryItem {
  id: string;
  timestamp: number;
  strategyName: string;
  // 원천 Strategy에서 해석한 원문 프롬프트(상세 조회 API에서만 채워짐)
  prompt?: string;
  // 원천 Strategy의 DSL(entry/exit/risk 등). 워크포워드 실행에 필요(상세 조회 API에서만 채워짐)
  settings?: Record<string, unknown> | null;
  universe: string;
  conditions: string[] | {
    names?: string[];
    entry?: { names: string[] };
    exit?: { names: string[] };
    position?: string;
    risk?: string;
  };
  metrics: {
    totalReturn: number;
    cagr: number;
    mdd: number;
    winRate: number;
    /** null = 손실 거래 0건이라 정의되지 않음(∞) */
    profitFactor: number | null;
    buyHold: number;
    trades: number;
    executionTime?: number;
    score?: number;
    aiSummary?: string;
    aiScore?: number;
    aiStrengths?: string[];
    aiWeaknesses?: string[];
    aiImprovements?: string[];
    advisorScore?: number | null;
    riskScore?: number | null;
    overfitRisk?: string | null;
  };
  result?: BacktestResult;
}


export interface StrategyDataset {
  symbol: string;
  dates: string[];
  prices: {
    open: number[];
    high: number[];
    low: number[];
    close: number[];
    volume: number[];
  };
  features: Record<string, number[] | any>;
}

export interface CanvasBlock {
  id: string;
  type: "filter" | "entry" | "exit";
  blockId: string;
  position: { x: number; y: number };
  params: Record<string, any>;
  connections?: string[]; // IDs of connected blocks
}

// Optimization Types
export interface OptimizationResultItem {
  iteration: number;
  parameters: Record<string, any>;
  metrics: Record<string, number>;
  target_value: number;
}

export interface OptimizationResponse {
  status: string;
  message?: string;
  target_metric?: string;
  total_iterations?: number;
  tested_ranges?: Record<string, any[]>;
  best_parameters?: Record<string, any>;
  best_metrics?: Record<string, number>;
  top_results?: OptimizationResultItem[];
  report?: string;
}
