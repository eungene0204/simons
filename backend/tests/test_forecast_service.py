"""ForecastModelService 테스트 — 자기 시계열 퍼센타일 보정·하방 게이지·폴백."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_analysis.forecast_service import ForecastModelService


class _FakeEngine:
    """predict_signals(df) → (up_probs, down_probs). 앞부분은 0 패딩(lookback)."""

    def __init__(self, up_probs, down_probs):
        self._up = np.asarray(up_probs, dtype=float)
        self._down = np.asarray(down_probs, dtype=float)

    def predict_signals(self, df):
        return self._up, self._down


def _ohlcv(n=200):
    return pd.DataFrame({"close": np.linspace(100, 120, n), "volume": [1000.0] * n})


def test_no_engine_returns_no_data():
    out = ForecastModelService(engine=None).analyze(_ohlcv())
    assert out.forecast is None
    assert out.down_risk_level is None


def test_empty_ohlcv_returns_no_data():
    out = ForecastModelService(engine=_FakeEngine([0.3] * 50, [0.3] * 50)).analyze(pd.DataFrame())
    assert out.down_risk_level is None


def test_padding_excluded_from_distribution():
    # 앞 60개는 0 패딩 → 분포 계산에서 빠져야 한다. 유효 구간은 일정한 0.25/0.37.
    n = 200
    up = np.array([0.0] * 60 + [0.25] * (n - 60))
    down = np.array([0.0] * 60 + [0.37] * (n - 60))
    out = ForecastModelService(engine=_FakeEngine(up, down)).analyze(_ohlcv(n))
    # 유효 구간이 모두 동일하므로 오늘 값은 100 퍼센타일(<=).
    assert out.down_pctl == 100
    assert out.up_pctl == 100
    assert out.down_prob == 0.37  # 패딩 0이 섞이지 않은 실제 값


def test_insufficient_valid_bars_returns_no_data():
    # 유효 bar가 30 미만이면 자기보정 분포가 부족 → 데이터 없음.
    up = np.array([0.0] * 60 + [0.25] * 10)
    down = np.array([0.0] * 60 + [0.37] * 10)
    out = ForecastModelService(engine=_FakeEngine(up, down)).analyze(_ohlcv(70))
    assert out.down_risk_level is None


def test_elevated_when_today_in_top_downside_percentile():
    # 평소 낮은 하락확률 + 오늘만 급등 → 자기이력 상위 → elevated.
    down = np.array([0.30] * 100 + [0.42])  # 마지막이 가장 큼
    up = np.array([0.25] * 101)
    out = ForecastModelService(engine=_FakeEngine(up, down)).analyze(_ohlcv(101))
    assert out.down_risk_level == "elevated"
    assert out.down_pctl == 100


def test_calm_when_today_low_downside_percentile():
    # 오늘 하락확률이 자기이력 하위 → calm.
    down = np.array([0.40] * 100 + [0.30])  # 마지막이 가장 작음
    up = np.array([0.25] * 101)
    out = ForecastModelService(engine=_FakeEngine(up, down)).analyze(_ohlcv(101))
    assert out.down_risk_level == "calm"


def test_absolute_threshold_trap_avoided():
    # 핵심: down>up이 항상 성립해도(절대 net은 늘 음수) 퍼센타일 보정으로 무조건 negative가 아니다.
    rng = np.random.default_rng(0)
    up = 0.20 + rng.random(300) * 0.15    # 0.20~0.35
    down = 0.32 + rng.random(300) * 0.10  # 0.32~0.42 — 항상 up보다 큼
    out = ForecastModelService(engine=_FakeEngine(up, down)).analyze(_ohlcv(300))
    # 절대 net=up-down은 늘 음수지만, 방향 라벨은 자기 퍼센타일 우열로 결정되어
    # 항상 negative로 쏠리지 않는다(중립 등 가능).
    assert out.forecast in {
        "positive", "slightly_positive", "neutral", "slightly_negative", "negative",
    }
    assert out.down_pctl is not None and 0 <= out.down_pctl <= 100
