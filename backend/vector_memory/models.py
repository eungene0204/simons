"""Data models for vector memory infrastructure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PrimitiveMetadata = str | int | float | bool


@dataclass(frozen=True)
class NormalizedBacktestMemory:
    strategyDsl: dict[str, Any]
    strategySummary: str
    indicators: list[str]
    entryConditions: list[str]
    exitConditions: list[str]
    riskManagement: dict[str, Any]
    marketRegime: str
    sectorBias: list[str]
    holdingPeriod: int
    rebalanceFrequency: str
    capital: float
    return_: float = field(metadata={"external_name": "return"})
    CAGR: float = 0.0
    Sharpe: float = 0.0
    Sortino: float = 0.0
    Calmar: float = 0.0
    WinRate: float = 0.0
    ProfitFactor: float = 0.0
    MDD: float = 0.0
    volatility: float = 0.0
    turnover: float = 0.0
    tradeCount: int = 0
    averageHoldingDays: float = 0.0
    failureReason: str = ""
    successReason: str = ""
    strategyVersion: str = "v1"

    def to_payload(self) -> dict[str, Any]:
        return {
            "strategyDsl": self.strategyDsl,
            "strategySummary": self.strategySummary,
            "indicators": self.indicators,
            "entryConditions": self.entryConditions,
            "exitConditions": self.exitConditions,
            "riskManagement": self.riskManagement,
            "marketRegime": self.marketRegime,
            "sectorBias": self.sectorBias,
            "holdingPeriod": self.holdingPeriod,
            "rebalanceFrequency": self.rebalanceFrequency,
            "capital": self.capital,
            "return": self.return_,
            "CAGR": self.CAGR,
            "Sharpe": self.Sharpe,
            "Sortino": self.Sortino,
            "Calmar": self.Calmar,
            "WinRate": self.WinRate,
            "ProfitFactor": self.ProfitFactor,
            "MDD": self.MDD,
            "volatility": self.volatility,
            "turnover": self.turnover,
            "tradeCount": self.tradeCount,
            "averageHoldingDays": self.averageHoldingDays,
            "failureReason": self.failureReason,
            "successReason": self.successReason,
            "strategyVersion": self.strategyVersion,
        }


@dataclass(frozen=True)
class VectorMemoryDocument:
    id: str
    strategy_hash: str
    document: str
    metadata: dict[str, PrimitiveMetadata]


@dataclass(frozen=True)
class VectorMemoryMatch:
    id: str
    similarity_score: float
    document: str
    metadata: dict[str, Any]
