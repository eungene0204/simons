// Strategy DSL Types
export type ConditionType = "indicator" | "flow" | "risk" | "ml" | "filter";

export type IndicatorType =
  | "ma_crossover"
  | "rsi"
  | "macd"
  | "bollinger_bands"
  | "volume_spike"
  | "breakout"
  | "stochastic"
  | "cci"
  | "adx"
  | "williams_r"
  | "mfi"
  | "roc";

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
  execution_timing?: "next_open" | "current_close";
  allocation_type?: "equal" | "fixed_pct";
  rebalancing_period?: string;
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
    reason: string;
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
  /** 분위 그룹 비교 결과(FR-BT-060). 분위 그룹 전략일 때만 존재. */
  quantileGroups?: QuantileGroupsResult;
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
  };
  /** 이 결과를 산출한 백테스트 엔진 버전 (backend engine/version.py). */
  engineVersion?: string;
  executionTime?: number;
  fromCache?: boolean;
  cachedAt?: string;
  cacheKey?: string;
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
