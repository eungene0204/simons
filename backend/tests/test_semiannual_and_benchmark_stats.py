"""엔진 v16.25 — 반기 리밸런싱 대화 레인 허용 + 벤치마크 대비 통계(베타·알파·정보비율·추적오차).

- 반기(semiannual)는 엔진 rebalance.py가 이미 알았지만 대화 레인 허용 목록·ParsedStrategy Literal에
  빠져 요청할 수 없었다(2026-09-23 격차 조사).
- 벤치마크 대비 통계는 정의 불가(벤치 없음·표본<2·분산 0)를 0으로 위장하지 않고 None으로 낸다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.rebalance import compute_rebalance_dates
from engine.result_handler import ResultHandler
from engine.strategy_converter import to_backtest_request
from strategy_conversation.compiler.strategy_compiler import compile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.registry.capability_registry import normalize_rebalance_frequency
from strategy_conversation.validation.pipeline import run_validation


def _intent(freq):
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "status": "READY", "confidence": 0.9,
        "strategy": {
            "universe": {"markets": ["KOSPI"], "sectors": [], "symbols": []},
            "entry_conditions": [], "exit_conditions": [],
            "ranking": [{"metric": "ranking.return", "lookback_days": 60, "direction": "top"}],
            "portfolio": {"selection_count": 10, "rebalance_frequency": freq},
            "risk_management": {}, "backtest": {},
        },
    })


@pytest.mark.parametrize("raw", ["반기", "반기마다", "6개월마다", "semiannual", "semi-annual"])
def test_semiannual_aliases_normalize(raw):
    assert normalize_rebalance_frequency(raw) == "semiannual"


def test_semiannual_passes_validation_and_reaches_request():
    validated, report = run_validation(_intent("semiannual"))
    assert not report.unsupported_features and report.errors == []
    parsed = compile_strategy(validated, report, "60일 수익률 상위 10종목, 반기 리밸런싱")
    assert parsed.rebalancing_period == "semiannual"
    req = to_backtest_request(parsed, resolve_symbols=False)
    assert req["risk"]["rebalancing_period"] == "semiannual"


def test_semiannual_rebalance_dates_are_first_trading_days_of_jan_and_jul():
    idx = pd.bdate_range("2024-01-01", "2024-12-31")
    dates = idx[compute_rebalance_dates(idx, "semiannual")]
    assert [d.strftime("%Y-%m-%d") for d in dates] == ["2024-01-01", "2024-07-01"]


# ── 벤치마크 대비 통계 ────────────────────────────────────────────────────────

def _series(values, start="2024-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_beta_two_when_strategy_is_double_the_benchmark():
    b = _series([0.01, -0.02, 0.015, 0.005, -0.01, 0.02])
    s = 2.0 * b
    out = ResultHandler.benchmark_relative_stats(s, b, b.notna(), 0.0, 246.0)
    assert out["beta"] == pytest.approx(2.0)
    assert out["alpha"] == pytest.approx(0.0, abs=1e-9)
    assert out["trackingError"] == pytest.approx(float((s - b).std(ddof=1)) * np.sqrt(246) * 100)
    assert out["informationRatio"] == pytest.approx(float((s - b).mean()) * 246 * 100 / out["trackingError"])


def test_alpha_is_annualized_percent_of_intercept():
    b = _series([0.01, -0.01, 0.01, -0.01])
    s = b + 0.001                                        # 매일 0.1%p 초과 → 베타 1, 알파 0.1%×246
    out = ResultHandler.benchmark_relative_stats(s, b, None, 0.0, 246.0)
    assert out["beta"] == pytest.approx(1.0)
    assert out["alpha"] == pytest.approx(0.001 * 246 * 100)
    assert out["trackingError"] == pytest.approx(0.0)
    assert out["informationRatio"] is None               # 추적오차 0 → 정의 불가


def test_undefined_cases_return_none_not_zero():
    b = _series([0.01, 0.01, 0.01])                      # 벤치 분산 0
    s = _series([0.02, 0.0, 0.01])
    out = ResultHandler.benchmark_relative_stats(s, b, None, 0.0, 246.0)
    assert out["beta"] is None and out["alpha"] is None
    assert ResultHandler.benchmark_relative_stats(s, None, None, 0.0, 246.0)["beta"] is None
    # 커버리지 마스크가 표본을 1개로 줄이면 전부 None
    valid = pd.Series([True, False, False], index=b.index)
    assert ResultHandler.benchmark_relative_stats(s, _series([0.01, 0.02, 0.03]), valid, 0.0, 246.0)["beta"] is None
