"""유니버스 사전 필터 확장(엔진 v16.32) — 적자기업 제외·시가총액 하위 분위 제외.

배경(2026-09-23): 경쟁 플랫폼이 원클릭으로 제공하는 사전 필터 중 '적자기업 제외'와
'소형주(시총 하위 %) 제외'가 우리에게는 없었다(시총 상위 N·거래대금 하위 %만 있었다).

고정하는 것: ① 판정(모르는 칸 처리가 두 필터에서 다르다) ② 해석 레인 관통(스키마·검증·
컴파일·디컴파일·정본 DSL·엔진 요청) ③ ETF·엉뚱한 기준 값은 조용히 확정하지 않는다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import universe_prefilters as pf
from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation

_IDX = pd.bdate_range("2024-01-01", periods=3)


def _panel(values_by_sym):
    return pd.DataFrame(values_by_sym, index=_IDX, dtype=float)


def _compile(*, universe=None):
    intent, report = run_validation(StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["KOSPI"], **(universe or {})},
        "entry_conditions": [{"factor": "fundamental.per", "operator": "<=", "value": 10,
                              "source_text": "PER 10 이하"}],
        "portfolio": {"selection_count": 20, "rebalance_frequency": "monthly"},
    }))
    return compile_partial(intent, report, "PER 10 이하")[0], report


# ── ① 판정 ─────────────────────────────────────────────────────────────────────

def test_bottom_percentile_keeps_upper_names_and_drops_unknown():
    """시가총액 하위 분위 제외 — 값이 없는 칸은 후보에서 뺀다(fail-closed)."""
    mask = pf.bottom_percentile_mask(
        _panel({"A": [100, 100, 100], "B": [50, 50, 50],
                "C": [10, 10, 10], "D": [np.nan] * 3}), 50)

    assert mask["A"].all() and mask["B"].all()   # 상위 절반은 남는다
    assert not mask["C"].any()                   # 하위 50%는 제외
    assert not mask["D"].any()                   # 시총 미상은 판정 불가 → 제외


def test_profitability_keeps_unknown_financials():
    """적자기업 제외 — 적자로 확인된 칸만 뺀다. 재무 미상은 남긴다(생존 편향 방지)."""
    ok, known = pf.profitability_mask([_panel({"A": [10, 10, 10], "B": [-5, -5, -5],
                                               "C": [np.nan] * 3})])

    assert ok["A"].all()
    assert not ok["B"].any()
    assert ok["C"].all()          # 모르는 종목은 유니버스에 남는다
    assert not known["C"].any()   # 다만 판정하지 못했다는 사실은 따로 드러난다


def test_profitability_both_requires_every_panel_to_pass():
    """'both'는 당기순손실·영업손실 둘 다 아니어야 통과한다."""
    net = _panel({"A": [10, 10, 10], "B": [10, 10, 10]})
    ebit = _panel({"A": [5, 5, 5], "B": [-1, -1, -1]})
    ok, known = pf.profitability_mask([net, ebit])

    assert ok["A"].all()
    assert not ok["B"].any()
    assert known["A"].all() and known["B"].all()


def test_profitability_judges_day_by_day():
    """판정은 그 시점 값으로 한다 — 흑자 전환 뒤에는 다시 후보가 된다."""
    ok, _known = pf.profitability_mask([_panel({"A": [-3, -3, 4]})])

    assert list(ok["A"]) == [False, False, True]


def test_profitability_requires_a_panel():
    with pytest.raises(ValueError):
        pf.profitability_mask([])


# ── ② 해석 레인 관통 ───────────────────────────────────────────────────────────

def test_filters_reach_engine_request_and_canonical_dsl():
    parsed, report = _compile(universe={
        "market_cap_exclude_bottom_percent": 20,
        "exclude_loss_making": "net",
    })

    assert report.errors == []
    assert parsed.universe_market_cap_exclude_bottom_pct == 20
    assert parsed.universe_exclude_loss_making == "net"
    dsl = to_canonical_strategy_dsl(parsed)
    assert dsl["universe_market_cap_exclude_bottom_pct"] == 20
    assert dsl["universe_exclude_loss_making"] == "net"
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["universe_market_cap_exclude_bottom_pct"] == 20
    assert risk["universe_exclude_loss_making"] == "net"


def test_filters_round_trip_through_decompiler():
    """수정 턴에서 필터가 풀리지 않는다."""
    parsed, _report = _compile(universe={
        "market_cap_exclude_bottom_percent": 20, "exclude_loss_making": "operating"})
    universe = decompile_strategy(parsed).universe

    assert universe.market_cap_exclude_bottom_percent == 20
    assert universe.exclude_loss_making == "operating"


def test_absent_filters_leave_keys_out_of_canonical_dsl():
    """말하지 않으면 정본 DSL에 키가 남지 않는다(기존 전략 해시 불변)."""
    parsed, _report = _compile()
    dsl = to_canonical_strategy_dsl(parsed)

    assert "universe_market_cap_exclude_bottom_pct" not in dsl
    assert "universe_exclude_loss_making" not in dsl


# ── ③ 조용한 확정 금지 ─────────────────────────────────────────────────────────

def test_unknown_loss_basis_is_reported_not_guessed():
    _parsed, report = _compile(universe={"exclude_loss_making": "yes"})

    assert any("적자기업 제외 기준" in item for item in report.unsupported_features)


def test_etf_universe_cannot_exclude_loss_making():
    """ETF에는 손익계산서가 없다 — 적용된 척하지 않고 미지원으로 알린다."""
    parsed, report = _compile(universe={"markets": ["ETF"], "exclude_loss_making": "net"})

    assert parsed.universe_exclude_loss_making is None
    assert any("ETF" in item for item in report.unsupported_features)
