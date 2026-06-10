"""
ForecastModelService — AI 예측 모델 보조 신호(단일 책임: 예측 수집·자기보정).

주의(project_ai_auxiliary_usage): 검증 결과 이 AI 모델은 방향 예측 알파가 없고,
**유일하게 입증된 가치는 약세장 하방 방어**다. 따라서 매매를 결정하는 추천 점수에는
넣지 않고(RecommendationEngine에서 제외), 순수 '보조 게이지'로만 노출한다.

또한 점수 분포가 매우 좁고 보정되어 있지 않다(상승 0.20~0.35, 하락 0.32~0.42).
하락확률이 항상 상승확률보다 커서 절대 임계값(net=up-down)으로 라벨링하면 전 종목이
'하락'으로 나온다. 그래서 **종목 자기 시계열 퍼센타일**로 오늘 점수를 보정한다.

모델 로딩은 비용이 크고 polars 데드락 이슈가 있어 best-effort로 시도하고, 실패하면
forecast=None('데이터 없음')을 반환한다(엔진 미주입이면 기본적으로 데이터 없음).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 하방 리스크 게이지 임계(자기 시계열 퍼센타일 기준).
_ELEVATED_PCTL = 85   # 평소 대비 상위 15% → ⚠️ 단기 하방 주의
_MODERATE_PCTL = 65   # 상위 35% → 다소 높음


@dataclass
class ForecastResult:
    forecast: Optional[str] = None        # positive | slightly_positive | neutral | slightly_negative | negative
    up_prob: Optional[float] = None
    down_prob: Optional[float] = None
    down_pctl: Optional[int] = None       # 오늘 하락확률의 자기 시계열 퍼센타일(0~100)
    up_pctl: Optional[int] = None         # 오늘 상승확률의 자기 시계열 퍼센타일
    down_risk_level: Optional[str] = None # elevated | moderate | calm


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
            up_arr = np.asarray(up_probs, dtype=float)
            down_arr = np.asarray(down_probs, dtype=float)
        except Exception:
            logger.debug("AI 예측 실패 — forecast 데이터 없음", exc_info=True)
            return ForecastResult()

        # 앞쪽 (lookback-1) bar는 0으로 패딩되어 분포를 왜곡한다 — 유효 구간만 사용.
        valid = (up_arr != 0) | (down_arr != 0)
        if valid.sum() < 30:
            return ForecastResult()  # 자기보정 분포가 부족하면 데이터 없음.

        up_hist = up_arr[valid]
        down_hist = down_arr[valid]
        up_today = float(up_arr[-1])
        down_today = float(down_arr[-1])

        up_pctl = self._percentile_of(up_hist, up_today)
        down_pctl = self._percentile_of(down_hist, down_today)

        return ForecastResult(
            forecast=self._directional_label(up_pctl, down_pctl),
            up_prob=round(up_today, 3),
            down_prob=round(down_today, 3),
            up_pctl=up_pctl,
            down_pctl=down_pctl,
            down_risk_level=self._risk_level(down_pctl),
        )

    @staticmethod
    def _percentile_of(hist: np.ndarray, value: float) -> int:
        """value가 hist 분포에서 차지하는 백분위(0~100). 자기 시계열 보정."""
        return int(round(float(np.mean(hist <= value)) * 100))

    @staticmethod
    def _risk_level(down_pctl: int) -> str:
        if down_pctl >= _ELEVATED_PCTL:
            return "elevated"
        if down_pctl >= _MODERATE_PCTL:
            return "moderate"
        return "calm"

    @staticmethod
    def _directional_label(up_pctl: int, down_pctl: int) -> str:
        """방향은 자기 퍼센타일 우열로 판정(절대값 아님). 알파 약해 보조 표시용."""
        spread = up_pctl - down_pctl
        if spread >= 30:
            return "positive"
        if spread >= 10:
            return "slightly_positive"
        if spread <= -30:
            return "negative"
        if spread <= -10:
            return "slightly_negative"
        return "neutral"
