from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal, Union

from engine.version import ENGINE_VERSION

class Condition(BaseModel):
    type: str # "indicator" | "flow" | "risk" | "ml" | "filter"
    id: str
    params: Dict[str, Any]
    weight: Optional[float] = 1.0

class ConditionGroup(BaseModel):
    conditions: List[Condition]
    # SignalEngine.generate_signals의 결합 방식(AND/OR). 미선언 시 model_dump가 조용히
    # 버려(extra=ignore) 엔진이 기본값 OR로 떨어진다 — 반드시 선언한다.
    logic: Optional[str] = None

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
    # 재무 팩터 랭킹의 방향(top=높은 순, bottom=낮은 순 — 예: PER 낮은 상위 N). 스키마에
    # 없으면 model_dump가 조용히 버려 엔진이 방향을 못 받는다 — ranking_metric과 동일 함정.
    ranking_direction: Optional[str] = None
    # 비율 선정(FR-BT-060): 상위 X% 편입 — max_positions(개수) 대신 후보 수 기준 비율.
    # 분위 그룹(ranking_quantile_groups): 랭킹 후보를 종목 수 동일한 G개 그룹으로 나눠
    # 그룹별 백테스트 비교(예: PER 십분위). 스키마에 없으면 model_dump가 조용히 버려
    # 엔진이 못 받는다 — ranking_metric 0거래 사고와 동일 함정이라 반드시 선언한다.
    max_positions_pct: Optional[float] = None
    ranking_quantile_groups: Optional[int] = None
    # 분위 그룹당 보유 상한(FR-BT-060b) — 각 그룹이 자기 구간의 랭킹 상위 N종목만 보유.
    ranking_group_cap: Optional[int] = None
    # 복합 순위 합산(FR-BT-063): ranking_metric='composite'일 때 구성 지표 목록
    # [{metric, direction, lookback_days?}, ...]. 스키마에 없으면 model_dump가 조용히 버려
    # 엔진이 구성 지표를 못 받는다 — ranking_metric 0거래 사고와 동일 함정.
    ranking_components: Optional[List[Dict[str, Any]]] = None
    execution_timing: Optional[str] = "next_open"
    # 신호 후 N거래일 지연 체결 — next_open의 shift 폭(1=다음 거래일 시가, N=N번째 거래일 시가).
    # 엔진은 options.execution_delay_days → risk.execution_delay_days 순으로 읽는다. 스키마에
    # 없으면 model_dump가 조용히 버려 지연이 사라진다 — ranking_metric 0거래 사고와 동일 함정.
    execution_delay_days: Optional[int] = None
    # 12-1 모멘텀(v16.14): 수익률 랭킹에서 최근 N거래일을 뺀다(252/21 = 12개월에서 최근 1개월 제외).
    # 복합 순위 구성 지표는 ranking_components[*].skip_days·group을 쓴다. 스키마 미선언 시
    # model_dump가 조용히 버린다 — ranking_metric 0거래 사고와 같은 함정.
    ranking_skip_days: Optional[int] = None
    # 비중 방식: 'equal'(동일 비중) | 'inverse_volatility'(변동성 역비중, v16.14 — 1/σ(N일)에 비례).
    allocation_type: Optional[str] = "equal"
    allocation_lookback_days: Optional[int] = None
    # 시장 국면 필터(v16.14): {"index": "KOSPI", "ma_period": 200, "exposure_pct": 30} — 지수가
    # N일 이동평균 아래인 날은 목표 노출을 exposure_pct%로 줄인다(나머지 현금).
    # v16.16: "triggers"(["below_ma","volatility_spike"], 없으면 below_ma)·"volatility_multiple"·
    # "volatility_period" — 지수 N일 변동성이 직전 1년 평균의 K배 이상인 날도(OR) 약세일로 본다.
    market_regime: Optional[Dict[str, Any]] = None
    rebalancing_period: Optional[str] = "none"
    # 리밸런싱 방식(FR-BT-067): 'reconstitute'=리밸런싱일마다 목표 종목 재선정,
    # 'weights_only'=보유 종목 유지하고 비중만 균등 리셋. 스키마에 없으면 model_dump가
    # 조용히 버려 엔진이 못 받는다 — ranking_metric 0거래 사고와 동일 함정.
    rebalance_method: Optional[str] = "reconstitute"
    skip_risk_management: Optional[bool] = False
    skip_position_setting: Optional[bool] = False
    init_cash: Optional[float] = 10000000.0

class BacktestRequest(BaseModel):
    symbols: List[str]
    universe_id: Optional[str] = None
    # 단일/지정 종목 백테스트(FR-STR-068) 마커와 표시용 종목 메타데이터.
    # 엔진은 symbols+universe_id=None만으로 동작하지만, 스키마에 없으면 model_dump가
    # 조용히 버려(extra=ignore) 로그·실행 스냅샷에서 모드 정보가 사라진다(ranking_metric
    # 0거래 사고와 동일 함정) — 반드시 선언한다.
    backtest_mode: Optional[str] = None
    target_stocks: Optional[List[Dict[str, Any]]] = None
    # 섹터/업종 제한(정본 섹터명, 복수면 리스트 — 엔진이 합집합으로 필터). 스키마에 없으면
    # model_dump가 조용히 버려(extra=ignore) 엔진이 필터를 못 받는다 — ranking_metric
    # 0거래 사고와 동일 함정이라 반드시 선언한다.
    sector: Optional[Union[str, List[str]]] = None
    # ETF 유니버스(universe_id="etf") 전용 테마/상품명 필터("반도체", "KODEX 200").
    # sector와 동일하게 스키마 미선언 시 model_dump가 조용히 버리므로 반드시 선언한다.
    etf_theme: Optional[str] = None
    # 미국 유니버스 전용 업종 필터(GICS 정본 라벨 — "Airlines", "Health Care").
    # 한국 sector와 분류 체계가 달라 필드를 분리했다. 위와 동일한 이유로 반드시 선언한다.
    us_industry: Optional[str] = None
    # 신규 상장 유니버스(FR-STR-073) — 상장일이 이 구간에 속하는 종목만 대상으로 한다.
    # 위 두 필드와 동일한 이유로 반드시 선언한다(미선언 시 model_dump가 조용히 버림).
    listing_from: Optional[str] = None
    listing_to: Optional[str] = None
    entry: ConditionGroup
    exit: ConditionGroup
    risk: RiskManagement
    period: str = "5Y"
    # 명시적 백테스트 창(YYYY-MM-DD). 엔진(`backtest_engine`)은 이 값이 있으면 상대 기간
    # (period)보다 우선해 창을 잡는다. **위 필드들과 동일한 함정** — 선언이 없으면
    # model_dump가 조용히 버려 엔진이 못 받는다. 실측 사고(2026-08-01): '최근 10년' 요청이
    # 파싱·요약 카드(2016~2026)까지 정상이었는데 실행만 2022-01-03~2026-07-31이었다
    # (period="5Y" 폴백 창과 정확히 일치). camelCase인 것은 엔진 요청 계약이 그렇기 때문이다
    # (`strategy_converter.to_backtest_request`가 startDate/endDate로 싣는다).
    startDate: Optional[str] = None
    endDate: Optional[str] = None
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
    # 매매사유의 구조화 표현(engine/trade_reason.py 세그먼트) — /us가 t()로 번역해 표시한다.
    # 미선언 시 response_model이 걸러내 /backtest 응답에서 사라지고, 프론트가 한국어 정본
    # 문장(condition)으로 폴백해 /us 거래 내역·CSV에 한글이 나간다(2026-09-04 사고).
    conditionParts: Optional[List[Dict[str, Any]]] = None
    # 매도 신호의 순손익(원, 수수료·거래세 차감). 매수 신호는 None.
    pnl: Optional[float] = None

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
    # 벤치마크 지수가 아직 존재하지 않던 구간은 null — 0으로 채우면 그 구간
    # 벤치마크가 평탄했다는 거짓 곡선이 된다(엔진 v11.0).
    benchmark_equity: Optional[List[Optional[float]]] = Field(default_factory=list)
    # 벤치마크가 백테스트 구간의 일부만 덮는가 — True면 전략과 기간이 달라
    # 두 수익률의 차이(초과수익률)를 그대로 비교할 수 없다(엔진 v11.0).
    benchmark_partial: bool = False
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
    # null = 손실 거래가 0건이라 총이익÷총손실이 정의되지 않음(∞). 0.0(=이익 없음)과 다르다.
    profitFactor: Optional[float] = None
    # 켈리 기준(%) = W − (1−W)/R. 승·패 한쪽 표본이 없으면 R을 못 구해 null.
    kelly: Optional[float] = None
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
    # 초기자본(v16.12) — equity[0]은 첫 거래일 종가 평가액이라 첫날 체결이 있으면 다르다.
    # 미선언 시 response_model이 걸러내 프론트가 equity[0]을 초기자금으로 쓴다.
    initialCapital: Optional[float] = None
    # 벤치마크 지수가 아직 존재하지 않던 구간은 null — 0으로 채우면 그 구간
    # 벤치마크가 평탄했다는 거짓 곡선이 된다(엔진 v11.0).
    benchmark_equity: Optional[List[Optional[float]]] = Field(default_factory=list)
    # 벤치마크가 백테스트 구간의 일부만 덮는가 — True면 전략과 기간이 달라
    # 두 수익률의 차이(초과수익률)를 그대로 비교할 수 없다(엔진 v11.0).
    benchmark_partial: bool = False
    dates: List[str]
    signals: List[SignalResult]
    perAssetStats: Optional[Dict[str, AssetStats]] = Field(default_factory=dict)
    warnings: Optional[List[str]] = Field(default_factory=list)
    # 경고의 구조화 표현(engine/result_warnings.py) — warnings와 같은 순서, /us 영어 표시용.
    # 미선언 시 response_model이 걸러내 /backtest 응답에서 사라진다 — conditionParts와 같은 함정.
    warningParts: Optional[List[List[Dict[str, Any]]]] = None
    # 데이터 커버리지 리포트(펀더멘털 지표별 종목·기간 커버리지). 없으면 null.
    dataCoverage: Optional[Dict[str, Any]] = None
    # 이 결과가 실제로 적용한 거래 비용(engine/simulator.py applied_trading_costs) —
    # {buyFeeRate, sellFeeRate, slippageRate, sellTaxRate|null, sellTaxRateRange|null}, 소수 비율.
    # 미선언 시 response_model이 걸러내 결과 로그에서 사라진다 — 반드시 선언한다.
    tradingCosts: Optional[Dict[str, Any]] = None
    # 분위 그룹 비교 결과(FR-BT-060) — {groups: [{group, label, pctRange, totalReturn, ...}],
    # metricLabel, orderLabel, groupCount, mainGroup}. 없으면 null. 미선언 시 response_model이
    # 필드를 걸러내 프론트가 그룹 비교를 못 받는다 — 반드시 선언한다.
    quantileGroups: Optional[Dict[str, Any]] = None
    # 리밸런싱 기간별 결과 비교(FR-BT-064) — {periods: [{period, cagr, mdd, sharpe, profitFactor,
    # trades, turnover, ...}], currentPeriod, positionCapAbsent}. 백테스트마다 6주기 재시뮬레이션으로
    # 동봉한다. 미선언 시 response_model이 걸러내 프론트가 못 받는다 — 반드시 선언한다.
    rebalanceComparison: Optional[Dict[str, Any]] = None
    version: Optional[str] = ENGINE_VERSION
    executionTime: Optional[float] = 0.0
    vbtResult: Optional[VBTNativeResult] = None

class OptimizationRequest(BaseModel):
    base_strategy: BacktestRequest
    user_prompt: str
    target_metric: Optional[str] = "cagr"
    # 시행 횟수 상한 — 같은 구간에서 조합을 많이 볼수록 우연히 좋은 조합이 뽑힌다(다중 비교).
    n_trials: Optional[int] = Field(default=50, ge=1, le=200)
    ranges: Dict[str, Any]  # {path: [values]} or {path: {type, min, max, step}}


# ─── Walk-Forward Analysis ────────────────────────────────────────────────────

class WalkForwardRequest(BaseModel):
    base_strategy: BacktestRequest
    ranges: Dict[str, Any]
    n_splits: Optional[int] = 5
    train_pct: Optional[float] = 0.7
    anchor: Optional[bool] = False   # False=rolling, True=anchored(expanding)
    target_metric: Optional[str] = "cagr"
    n_trials: Optional[int] = Field(default=30, ge=1, le=100)   # 창당 시행 횟수 상한
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
    # WFE 산정 기준(현행 "cagr"). 구버전 결과(총수익률 기준)에는 없음 — 마찬가지로 선언 필수
    wfe_basis: Optional[str] = None

class OptimizationResultItem(BaseModel):
    iteration: int
    parameters: Dict[str, Any]
    # profitFactor는 손실 거래 0건이면 None(=∞) — float 강제 시 무손실 시도가 하나라도 있으면
    # 응답 전체가 검증 실패(500)한다(2026-08-19 감사).
    metrics: Dict[str, Optional[float]]
    target_value: Optional[float] = None

class OptimizationResponse(BaseModel):
    status: str
    message: Optional[str] = None
    target_metric: Optional[str] = None
    total_iterations: Optional[int] = 0
    tested_ranges: Optional[Dict[str, Any]] = None
    best_parameters: Optional[Dict[str, Any]] = None
    best_metrics: Optional[Dict[str, Optional[float]]] = None
    top_results: Optional[List[OptimizationResultItem]] = None
    report: Optional[str] = None
