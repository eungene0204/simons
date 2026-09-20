"""종목당 비중 상한(max_position_weight_pct, 엔진 v16.18) 배선 전체 회귀.

배경(2026-09-20): "종목당 비중은 2%를 상한으로 한다"가 "지원하지 않아 전략에 반영하지 못했어요"로
나갔다 — 엔진의 동일가중은 1/종목 수로만 계산돼 상한을 받을 자리가 없었고 대화 레인에도 칸이
없었다. 상한은 편입·리밸런싱 시점의 목표 비중에 건다(min). 잘린 몫은 재배분하지 않고 현금이다.

고정하는 것: ① 시뮬레이터 두 경로(순수 리밸런싱·조건 루프)와 역변동성·비중 유지 리밸런싱
② 상한이 없거나 걸리지 않으면 결과 불변 ③ 현금 잔류 결과 경고 ④ 해석 레인(스키마·검증·컴파일·
디컴파일·정본 DSL·엔진 요청·가상계좌용 1회 매수 비중).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import result_warnings as rw
from engine.simulator import Simulator, _weight_cap
from engine.strategy_converter import (
    compute_strategy_id, to_backtest_request, to_canonical_strategy_dsl,
)
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation

_OPTS = {"execution_type": "same_close", "fee_rate": 0, "slippage_rate": 0}
_CASH = 10_000_000.0


def _frames(n=6, syms=("A", "B")):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    px = pd.DataFrame(100.0, index=idx, columns=list(syms))
    ents = pd.DataFrame(True, index=idx, columns=list(syms))
    exts = pd.DataFrame(False, index=idx, columns=list(syms))
    rank = pd.DataFrame({s: float(len(syms) - k) for k, s in enumerate(syms)}, index=idx)
    return idx, px, ents, exts, rank


def _risk(**extra):
    base = {"max_positions": 2, "init_cash": _CASH, "allocation_type": "equal",
            "rebalancing_period": "monthly"}
    base.update(extra)
    return base


def _weights(pf) -> pd.Series:
    return pf.asset_value(group_by=False).iloc[0] / _CASH


# ── ① 시뮬레이터 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("extra", [{}, {"entry_signal_driven": True}, {"stop_loss_pct": 50},
                                   {"rebalance_method": "weights_only", "stop_loss_pct": 50}])
def test_cap_limits_each_position_and_leaves_the_rest_in_cash(extra):
    """동일가중 2종목(각 50%)에 상한 20% → 종목당 20%, 나머지 60%는 현금. 순수 리밸런싱·조건 루프 공통."""
    _idx, px, ents, exts, rank = _frames()
    pf = Simulator().run(px, px, ents, exts, _risk(max_position_weight_pct=20, **extra), _OPTS,
                         rank_df=rank)
    weights = _weights(pf)
    assert weights["A"] == pytest.approx(0.20, abs=0.001)
    assert weights["B"] == pytest.approx(0.20, abs=0.001)
    assert pf.cash().iloc[0] / _CASH == pytest.approx(0.60, abs=0.002)


@pytest.mark.parametrize("extra", [{}, {"entry_signal_driven": True}])
def test_cap_clips_only_the_overweight_leg_of_inverse_volatility(extra):
    """역변동성 3:1(75%/25%)에 상한 40% → A만 40%로 잘리고 B는 25% 그대로(재배분 없음)."""
    idx, px, ents, exts, rank = _frames()
    vol = pd.DataFrame({"A": 10.0, "B": 30.0}, index=idx)
    pf = Simulator().run(px, px, ents, exts,
                         _risk(allocation_type="inverse_volatility", max_position_weight_pct=40, **extra),
                         _OPTS, rank_df=rank, vol_df=vol)
    weights = _weights(pf)
    assert weights["A"] == pytest.approx(0.40, abs=0.001)
    assert weights["B"] == pytest.approx(0.25, abs=0.001)


# ── ② 결과 불변 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("extra", [{}, {"entry_signal_driven": True}, {"stop_loss_pct": 50}])
@pytest.mark.parametrize("cap", [None, 50, 100])
def test_absent_or_non_binding_cap_is_bit_identical(extra, cap):
    """상한이 없거나(None) 걸리지 않으면(50% = 1/2종목, 100%) 자산곡선이 1비트도 다르지 않다."""
    _idx, px, ents, exts, rank = _frames(n=40, syms=("A", "B", "C"))
    rng = np.random.default_rng(3)
    px = px * np.cumprod(1 + rng.normal(0, 0.02, size=px.shape), axis=0)
    base = Simulator().run(px, px, ents, exts, _risk(**extra), _OPTS, rank_df=rank)
    capped = Simulator().run(px, px, ents, exts, _risk(max_position_weight_pct=cap, **extra), _OPTS,
                             rank_df=rank)
    pd.testing.assert_series_equal(base.value(), capped.value())


@pytest.mark.parametrize("raw,expected", [(None, None), (2, 0.02), (100, None), (150, None), (0, None)])
def test_cap_reader_ignores_values_that_cannot_bind(raw, expected):
    assert _weight_cap({"max_position_weight_pct": raw}) == expected


# ── ③ 결과 경고 ─────────────────────────────────────────────────────────────

def test_cash_drag_warning_template_is_registered():
    from engine import trade_reason as tr

    text = tr.render_kr(tr.decode(rw.warning(rw.POSITION_WEIGHT_CAP_LEAVES_CASH, "2", 10, "20")))
    assert "종목당 비중 상한 2% × 최대 10종목" in text and "최대 20%까지만" in text


# ── ④ 해석 레인 ─────────────────────────────────────────────────────────────

def _compile(portfolio: dict):
    intent, report = run_validation(StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["KOSPI"]},
        "ranking": [{"metric": "ranking.return", "lookback_days": 60}],
        "portfolio": {"selection_count": 10, "rebalance_frequency": "monthly", **portfolio},
    }))
    return compile_partial(intent, report, "수익률 상위 10종목")[0], report


def test_cap_reaches_engine_request_and_canonical_dsl():
    parsed, report = _compile({"max_weight_percent": 2})
    assert report.errors == [] and parsed.max_position_weight_pct == 2
    assert to_canonical_strategy_dsl(parsed)["max_position_weight_pct"] == 2
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["max_position_weight_pct"] == 2
    # 1회 매수 비중을 position_size_pct로 읽는 소비자(가상계좌 자동매매)도 상한을 넘지 않는다.
    assert risk["position_size_pct"] == 2


def test_strategies_without_a_cap_keep_their_id_and_sizing():
    parsed, _report = _compile({})
    assert parsed.max_position_weight_pct is None
    assert "max_position_weight_pct" not in to_canonical_strategy_dsl(parsed)
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["position_size_pct"] == 10.0
    capped, _r = _compile({"max_weight_percent": 5})
    assert compute_strategy_id(capped) != compute_strategy_id(parsed)


@pytest.mark.parametrize("bad", [0, -3, 150])
def test_out_of_range_cap_is_an_error_and_not_applied(bad):
    parsed, report = _compile({"max_weight_percent": bad})
    assert any("종목당 비중 상한" in e for e in report.errors), report.errors
    assert parsed.max_position_weight_pct is None


def test_decompile_round_trips_the_cap():
    parsed, _report = _compile({"max_weight_percent": "2"})        # 문자열 숫자도 표기 정규화
    assert decompile_strategy(parsed).portfolio.max_weight_percent == 2


def test_prompt_exposes_the_field_in_the_output_shape():
    """형태에 키가 없으면 모델이 규칙이 있어도 그 자리를 채우지 않는다(etf_theme·selection_percent 실측)."""
    from strategy_conversation.interpreter.prompts import build_system_prompt

    prompt = build_system_prompt()
    assert '"max_weight_percent": null' in prompt
    assert "portfolio.max_weight_percent=N" in prompt
