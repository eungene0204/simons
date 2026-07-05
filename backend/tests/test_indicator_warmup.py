"""워크포워드 OOS 창의 지표 워밍업 회귀 테스트.

엔진은 startDate 이전으로 워밍업 구간(_WARMUP_CALENDAR_DAYS, 최소 400 캘린더일)을
프리로드해 지표를 계산한 뒤 창 밖 행을 제거한다. 이 워밍업 산정(_max_indicator_period)이
전략이 실제 참조하는 최대 지표 기간을 놓치면 OOS 창 초입 신호가 조용히 사라진다 —
여기서는 산정 로직이 모든 최적화 가능 파라미터를 커버하는지 고정한다.
"""

import pytest

from backtest_engine import _max_indicator_period


def _entry(*conditions):
    return {"conditions": list(conditions)}


class TestMaxIndicatorPeriod:
    def test_ma_crossover_uses_long_period(self):
        group = _entry({"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 300}})
        assert _max_indicator_period(group) == 300

    def test_ema_dual_and_single_period(self):
        dual = _entry({"id": "ema", "params": {"shortPeriod": 10, "longPeriod": 150}})
        single = _entry({"id": "ema", "params": {"period": 120}})
        assert _max_indicator_period(dual) == 150
        assert _max_indicator_period(single) == 120

    def test_breakout_lookback_period(self):
        group = _entry({"id": "breakout", "params": {"lookbackPeriod": 250}})
        assert _max_indicator_period(group) == 250

    def test_rsi_cci_volume_spike_periods(self):
        group = _entry(
            {"id": "rsi", "params": {"period": 60}},
            {"id": "cci", "params": {"period": 90}},
            {"id": "volume_spike", "params": {"period": 45}},
        )
        assert _max_indicator_period(group) == 90

    def test_nested_groups_and_multiple_sides(self):
        entry = _entry({"conditions": [{"id": "ma_crossover", "params": {"shortMA": 20, "longMA": 200}}]})
        exit_ = _entry({"id": "rsi", "params": {"period": 14}})
        assert _max_indicator_period(entry, exit_) == 200

    def test_warmup_calendar_days_covers_max_period(self):
        """워밍업 캘린더일 공식(×1.6 + 40)이 거래일→캘린더일 환산을 여유 있게 덮는다."""
        max_period = 300
        warmup = max(400, int(max_period * 1.6) + 40)
        # 거래일 300일 ≈ 캘린더 435일(×1.45) 이상 필요
        assert warmup >= int(max_period * 1.45)
