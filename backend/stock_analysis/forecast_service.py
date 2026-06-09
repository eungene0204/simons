"""
ForecastModelService — AI 예측 모델 보조 신호(단일 책임: 예측 수집).

주의(project_ai_auxiliary_usage): 검증 결과 AI 모델은 사이클 전체 알파가 없어
'보조 신호'로만 노출하고 추천을 좌우하지 않는다(RecommendationEngine에서 낮은
가중치). 모델 로딩은 비용이 크고 polars 데드락 이슈가 있어 best-effort로 시도하고,
실패하면 forecast=None('데이터 없음')을 반환한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    forecast: Optional[str] = None   # positive | slightly_positive | neutral | slightly_negative | negative
    up_prob: Optional[float] = None
    down_prob: Optional[float] = None


class ForecastModelService:
    """AI 엔진은 라우트에서 주입한다. engine=None이면 forecast 데이터 없음(None)."""

    def __init__(self, engine=None) -> None:
        self._engine = engine

    def analyze(self, ohlcv: Optional[pd.DataFrame]) -> ForecastResult:
        if ohlcv is None or ohlcv.empty:
            return ForecastResult()
        engine = self._engine
        if engine is None:
            return ForecastResult()
        try:
            up_probs, down_probs = engine.predict_signals(ohlcv)
            up = float(up_probs[-1])
            down = float(down_probs[-1])
        except Exception:
            logger.debug("AI 예측 실패 — forecast 데이터 없음", exc_info=True)
            return ForecastResult()

        net = up - down
        if net > 0.1:
            forecast = "positive"
        elif net > 0.03:
            forecast = "slightly_positive"
        elif net < -0.1:
            forecast = "negative"
        elif net < -0.03:
            forecast = "slightly_negative"
        else:
            forecast = "neutral"
        return ForecastResult(forecast=forecast, up_prob=round(up, 3), down_prob=round(down, 3))
