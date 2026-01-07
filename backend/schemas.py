from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class Condition(BaseModel):
    type: str # "indicator" | "flow" | "risk" | "ml" | "filter"
    id: str
    params: Dict[str, Any]
    weight: Optional[float] = 1.0

class ConditionGroup(BaseModel):
    logic: str # "AND" | "OR" | "WEIGHTED_SUM"
    conditions: List[Condition]

class RiskManagement(BaseModel):
    position_size_pct: float
    max_positions: Optional[int] = 1
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    max_holding_days: Optional[int] = None
    init_cash: Optional[float] = 10000000.0

class BacktestRequest(BaseModel):
    symbol: str
    entry: ConditionGroup
    exit: ConditionGroup
    risk: RiskManagement
    period: str = "full"
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)

class SignalResult(BaseModel):
    date: str
    type: str # 'entry' | 'exit'
    price: float
    quantity: int
    amount: float
    condition: str

class BacktestResponse(BaseModel):
    symbol: str
    totalReturn: float
    cagr: float
    buyAndHoldReturn: float
    maxDrawdown: float
    winRate: float
    profitFactor: float
    sharpe: float
    sortino: float
    volatility: float
    equity: List[float]
    benchmark_equity: Optional[List[float]] = Field(default_factory=list)
    dates: List[str]
    signals: List[SignalResult]
    warnings: Optional[List[str]] = Field(default_factory=list)
    version: Optional[str] = "1.0"
