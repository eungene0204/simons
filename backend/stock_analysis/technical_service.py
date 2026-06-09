"""
TechnicalAnalysisService — 추세/변동성/거래량 변화(단일 책임: 기술적 분석).

이동평균(20/60) 관계로 추세를, 최근 일별 수익률 표준편차로 변동성을,
최근 거래량/장기 평균 거래량 비율로 거래량 변화를 산출한다. OHLCV가 없으면
모두 None을 반환한다(환각 금지).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class TechnicalResult:
    trend: Optional[str] = None            # strong_up | up | neutral_positive | neutral | neutral_negative | down | strong_down
    volatility_pct: Optional[float] = None  # 연율화 변동성(%)
    volume_change_ratio: Optional[float] = None  # 최근5일 평균 / 직전20일 평균


class TechnicalAnalysisService:
    def analyze(self, ohlcv: Optional[pd.DataFrame]) -> TechnicalResult:
        if ohlcv is None or "close" not in ohlcv or len(ohlcv) < 20:
            return TechnicalResult()

        close = ohlcv["close"].astype(float).dropna()
        if len(close) < 20:
            return TechnicalResult()

        result = TechnicalResult()
        result.trend = self._trend(close)
        result.volatility_pct = self._volatility(close)
        if "volume" in ohlcv:
            result.volume_change_ratio = self._volume_change(ohlcv["volume"].astype(float))
        return result

    @staticmethod
    def _trend(close: pd.Series) -> Optional[str]:
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(min(60, len(close))).mean().iloc[-1]
        price = close.iloc[-1]
        if pd.isna(ma20) or pd.isna(ma60):
            return None
        # 가격과 두 이평의 정렬로 추세 강도 판정.
        above_ma20 = price > ma20
        ma20_above_ma60 = ma20 > ma60
        gap = (ma20 - ma60) / ma60 if ma60 else 0.0
        if above_ma20 and ma20_above_ma60:
            return "strong_up" if gap > 0.05 else "up"
        if not above_ma20 and not ma20_above_ma60:
            return "strong_down" if gap < -0.05 else "down"
        if above_ma20 and not ma20_above_ma60:
            return "neutral_positive"
        return "neutral_negative"

    @staticmethod
    def _volatility(close: pd.Series) -> Optional[float]:
        returns = close.pct_change().dropna().tail(60)
        if len(returns) < 5:
            return None
        daily_std = float(np.std(returns, ddof=1))
        return round(daily_std * np.sqrt(252) * 100, 1)

    @staticmethod
    def _volume_change(volume: pd.Series) -> Optional[float]:
        volume = volume.dropna()
        if len(volume) < 25:
            return None
        recent = volume.tail(5).mean()
        base = volume.tail(25).head(20).mean()
        if not base:
            return None
        return round(float(recent / base), 2)
