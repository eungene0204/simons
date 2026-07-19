from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal, Union

class Condition(BaseModel):
    type: str # "indicator" | "flow" | "risk" | "ml" | "filter"
    id: str
    params: Dict[str, Any]
    weight: Optional[float] = 1.0

class ConditionGroup(BaseModel):
    conditions: List[Condition]

class RiskManagement(BaseModel):
    position_size_pct: float
    max_positions: Optional[int] = 1
    min_cash_reserve_pct: Optional[float] = 0.0
    max_daily_buy_pct: Optional[float] = 100.0
    liquidity_limit_pct: Optional[float] = 10.0
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    max_holding_days: Optional[int] = None
    max_mdd_limit_pct: Optional[float] = None
    ranking_enabled: Optional[bool] = True
    ranking_weight_value: Optional[float] = 0.5
    ranking_weight_quality: Optional[float] = 0.5
    # 상대강도(모멘텀) 랭킹 — 진입 조건이 없으면 이 랭킹 자체가 '선정=진입'이 된다.
    # 이 두 필드가 스키마에 없으면 Pydantic이 조용히 버려서(extra=ignore) 엔진이 랭킹을
    # 못 받아 0거래가 된다(프론트는 risk.ranking_metric으로 전송함).
    ranking_metric: Optional[str] = None
    ranking_lookback_days: Optional[int] = None
    execution_timing: Optional[str] = "next_open"
    allocation_type: Optional[str] = "equal"
    rebalancing_period: Optional[str] = "none"
    skip_risk_management: Optional[bool] = False
    skip_position_setting: Optional[bool] = False
    init_cash: Optional[float] = 10000000.0

class BacktestRequest(BaseModel):
    symbols: List[str]
    universe_id: Optional[str] = None
    # 섹터/업종 제한(정본 섹터명, 복수면 리스트 — 엔진이 합집합으로 필터). 스키마에 없으면
    # model_dump가 조용히 버려(extra=ignore) 엔진이 필터를 못 받는다 — ranking_metric
    # 0거래 사고와 동일 함정이라 반드시 선언한다.
    sector: Optional[Union[str, List[str]]] = None
    # ETF 유니버스(universe_id="etf") 전용 테마/상품명 필터("반도체", "KODEX 200").
    # sector와 동일하게 스키마 미선언 시 model_dump가 조용히 버리므로 반드시 선언한다.
    etf_theme: Optional[str] = None
    entry: ConditionGroup
    exit: ConditionGroup
    risk: RiskManagement
    period: str = "5Y"
    options: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="백테스트 옵션 (fee_rate, slippage_rate 등)"
    )

class SignalResult(BaseModel):
    date: str
    symbol: str
    type: str # 'entry' | 'exit'
    price: float
    quantity: int
    amount: float
    condition: str

class AssetStats(BaseModel):
    symbol: str
    sector: Optional[str] = "-"
    totalReturn: float
    trades: int
    winRate: float
    profit: float

class VBTNativeResult(BaseModel):
    """Pure VectorBT engine metrics (native SL/TP/trailing stop)."""
    totalReturn: float = 0.0
    cagr: float = 0.0
    buyAndHoldReturn: float = 0.0
    maxDrawdown: float = 0.0
    winRate: float = 0.0
    profitFactor: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: Optional[float] = 0.0
    avgHoldingDays: Optional[float] = 0.0
    volatility: float = 0.0
    trades: int = 0
    avgProfit: Optional[float] = 0.0
    avgLoss: Optional[float] = 0.0
    maxConsecutiveWins: Optional[int] = 0
    maxConsecutiveLosses: Optional[int] = 0
    equity: List[float] = Field(default_factory=list)
    benchmark_equity: Optional[List[float]] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)
    finalEquity: Optional[float] = 0.0
    initialCapital: Optional[float] = 10000000.0


class BacktestResponse(BaseModel):
    symbols: List[str]
    totalReturn: float
    cagr: float
    buyAndHoldReturn: float
    maxDrawdown: float
    winRate: float
    profitFactor: float
    sharpe: float
    sortino: float
    calmar: Optional[float] = 0.0
    avgHoldingDays: Optional[float] = 0.0
    volatility: float
    trades: int
    avgProfit: Optional[float] = 0.0
    avgLoss: Optional[float] = 0.0
    maxConsecutiveWins: Optional[int] = 0
    maxConsecutiveLosses: Optional[int] = 0
    equity: List[float]
    benchmark_equity: Optional[List[float]] = Field(default_factory=list)
    dates: List[str]
    signals: List[SignalResult]
    perAssetStats: Optional[Dict[str, AssetStats]] = Field(default_factory=dict)
    warnings: Optional[List[str]] = Field(default_factory=list)
    # 데이터 커버리지 리포트(펀더멘털 지표별 종목·기간 커버리지). 없으면 null.
    dataCoverage: Optional[Dict[str, Any]] = None
    version: Optional[str] = "1.0"
    executionTime: Optional[float] = 0.0
    vbtResult: Optional[VBTNativeResult] = None

class OptimizationRequest(BaseModel):
    base_strategy: BacktestRequest
    user_prompt: str
    target_metric: Optional[str] = "cagr"
    n_trials: Optional[int] = 50
    ranges: Dict[str, Any]  # {path: [values]} or {path: {type, min, max, step}}


# ─── Walk-Forward Analysis ────────────────────────────────────────────────────

class WalkForwardRequest(BaseModel):
    base_strategy: BacktestRequest
    ranges: Dict[str, Any]
    n_splits: Optional[int] = 5
    train_pct: Optional[float] = 0.7
    anchor: Optional[bool] = False   # False=rolling, True=anchored(expanding)
    target_metric: Optional[str] = "cagr"
    n_trials: Optional[int] = 30
    method: Optional[Literal["bayesian", "grid"]] = "bayesian"
    # UI가 보여준 학습/검증 거래일 수 그대로 사용하는 명시적 분할 (지정 시 n_splits/train_pct보다 우선)
    is_bars: Optional[int] = Field(default=None, ge=1)
    oos_bars: Optional[int] = Field(default=None, ge=1)


class WalkForwardWindowResult(BaseModel):
    window: int
    is_period: str
    oos_period: str
    best_params: Dict[str, Any]
    is_metrics: Dict[str, Any]
    oos_metrics: Dict[str, Any]
    oos_equity: List[float]
    oos_dates: List[str]
    error: Optional[str] = None


class WalkForwardResponse(BaseModel):
    status: str
    message: Optional[str] = None
    n_splits: Optional[int] = 0
    anchor: Optional[bool] = False
    target_metric: Optional[str] = None
    windows: Optional[List[WalkForwardWindowResult]] = Field(default_factory=list)
    aggregate: Optional[Dict[str, float]] = Field(default_factory=dict)
    combined_equity: Optional[List[float]] = Field(default_factory=list)
    combined_dates: Optional[List[str]] = Field(default_factory=list)
    walk_forward_efficiency: Optional[float] = 0.0
    # IS 평균 수익이 0 이하이면 WFE 비율 해석이 불가 — response_model이 필드를 걸러내므로 반드시 선언
    wfe_valid: Optional[bool] = True

class OptimizationResultItem(BaseModel):
    iteration: int
    parameters: Dict[str, Any]
    metrics: Dict[str, float]
    target_value: float

class OptimizationResponse(BaseModel):
    status: str
    message: Optional[str] = None
    target_metric: Optional[str] = None
    total_iterations: Optional[int] = 0
    tested_ranges: Optional[Dict[str, Any]] = None
    best_parameters: Optional[Dict[str, Any]] = None
    best_metrics: Optional[Dict[str, float]] = None
    top_results: Optional[List[OptimizationResultItem]] = None
    report: Optional[str] = None
