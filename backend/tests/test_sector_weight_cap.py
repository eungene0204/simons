"""섹터별 비중 상한(max_sector_weight_pct, 엔진 v16.19) 배선 회귀.

배경(2026-09-20): "섹터별 비중은 총자산의 25%를 상한으로 한다"가 미지원 안내로 나갔고,
해석기는 그 값을 **종목당 상한**(v16.18)으로 실어 조용히 다른 전략을 만들었다.

종목당 상한과 다른 점: 같은 섹터 종목들의 목표 비중 **합**에 거는 제약이라 원소별 min이
아니라 그 섹터 안 비례 축소다(섹터 안 상대 비중은 보존). 잘린 몫은 재배분하지 않고 현금이다.

고정하는 것: ① 두 실행 경로(순수 리밸런싱·조건 루프) ② 섹터 안 비례 축소 ③ 상한이 없거나
걸리지 않으면 결과 불변 ④ 섹터를 모르는 종목은 제약 대상이 아니다 ⑤ 해석 레인 관통.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.simulator import Simulator, _apply_sector_cap, _sector_groups, _sector_weight_cap
from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation

_OPTS = {"execution_type": "same_close", "fee_rate": 0, "slippage_rate": 0}
_CASH = 10_000_000.0


def _frames(syms, n=6):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    px = pd.DataFrame(100.0, index=idx, columns=list(syms))
    ents = pd.DataFrame(True, index=idx, columns=list(syms))
    exts = pd.DataFrame(False, index=idx, columns=list(syms))
    rank = pd.DataFrame({s: float(len(syms) - k) for k, s in enumerate(syms)}, index=idx)
    return px, ents, exts, rank


def _risk(**extra):
    base = {"max_positions": 4, "init_cash": _CASH, "allocation_type": "equal",
            "rebalancing_period": "monthly"}
    base.update(extra)
    return base


def _weights(pf) -> pd.Series:
    return pf.asset_value(group_by=False).iloc[0] / _CASH


@pytest.fixture
def two_sectors(monkeypatch):
    """A·B는 한 섹터, C·D는 다른 섹터로 보이게 한다(섹터 마스터에 의존하지 않는다)."""
    mapping = {"A": "반도체", "B": "반도체", "C": "은행", "D": "은행"}

    def fake_sector(symbol):
        return mapping.get(str(symbol))

    monkeypatch.setattr("engine.ksic_sectors.sector_for_symbol", fake_sector)
    return mapping


# ── ① 순수 계산 ──────────────────────────────────────────────────────────────

def test_cap_scales_only_the_sector_that_exceeds_it():
    groups = {"반도체": np.array([0, 1]), "은행": np.array([2, 3])}
    row = np.array([0.30, 0.30, 0.20, 0.20])

    out = _apply_sector_cap(row.copy(), groups, 0.25)

    # 반도체 합 60% > 25% → 비례 축소(12.5%씩). 은행 합 40%는… 도 넘으므로 함께 축소된다.
    assert out[:2] == pytest.approx([0.125, 0.125])
    assert out[2:] == pytest.approx([0.125, 0.125])


def test_cap_preserves_relative_weights_inside_the_sector():
    groups = {"반도체": np.array([0, 1])}
    row = np.array([0.45, 0.15])        # 3:1

    out = _apply_sector_cap(row.copy(), groups, 0.30)

    assert out.sum() == pytest.approx(0.30)
    assert out[0] / out[1] == pytest.approx(3.0)   # 섹터 안 상대 비중 보존


def test_cap_leaves_sectors_under_the_limit_untouched():
    groups = {"반도체": np.array([0, 1]), "은행": np.array([2, 3])}
    row = np.array([0.40, 0.40, 0.10, 0.10])

    out = _apply_sector_cap(row.copy(), groups, 0.50)

    assert out[2:] == pytest.approx([0.10, 0.10])   # 합 20% — 손대지 않는다


def test_single_member_sectors_are_not_grouped(monkeypatch):
    """혼자뿐인 섹터는 묶음이 아니다 — 그 제약은 종목당 상한과 같아진다."""
    monkeypatch.setattr("engine.ksic_sectors.sector_for_symbol",
                        lambda s: {"A": "반도체", "B": "반도체", "C": "은행"}.get(str(s)))

    groups = _sector_groups(["A", "B", "C"])

    assert set(groups) == {"반도체"}


def test_unknown_sector_symbols_are_not_constrained(monkeypatch):
    monkeypatch.setattr("engine.ksic_sectors.sector_for_symbol",
                        lambda s: None if str(s) == "Z" else "반도체")

    groups = _sector_groups(["A", "B", "Z"])

    assert "Z" not in [s for members in groups.values() for s in members]
    assert len(groups["반도체"]) == 2


@pytest.mark.parametrize("raw,expected", [(None, None), (100, None), (0, None), (25, 0.25)])
def test_cap_ratio_parsing(raw, expected):
    assert _sector_weight_cap({"max_sector_weight_pct": raw}) == expected


# ── ② 시뮬레이터 두 경로 ────────────────────────────────────────────────────

@pytest.mark.parametrize("extra", [{}, {"stop_loss_pct": 50}])
def test_sector_cap_limits_combined_weight_in_both_paths(two_sectors, extra):
    """4종목 동일가중(각 25%)·두 섹터에 상한 30% → 섹터마다 30%, 나머지 40%는 현금."""
    px, ents, exts, rank = _frames(["A", "B", "C", "D"])

    pf = Simulator().run(px, px, ents, exts,
                         _risk(max_sector_weight_pct=30, **extra), _OPTS, rank_df=rank)
    weights = _weights(pf)

    assert weights[["A", "B"]].sum() == pytest.approx(0.30, abs=1e-6)
    assert weights[["C", "D"]].sum() == pytest.approx(0.30, abs=1e-6)
    assert weights.sum() == pytest.approx(0.60, abs=1e-6)


@pytest.mark.parametrize("extra", [{}, {"stop_loss_pct": 50}])
def test_absent_cap_is_bit_identical(two_sectors, extra):
    px, ents, exts, rank = _frames(["A", "B", "C", "D"])

    base = Simulator().run(px, px, ents, exts, _risk(**extra), _OPTS, rank_df=rank)
    with_cap = Simulator().run(px, px, ents, exts,
                               _risk(max_sector_weight_pct=None, **extra), _OPTS, rank_df=rank)

    assert base.value().equals(with_cap.value())


@pytest.mark.parametrize("extra", [{}, {"stop_loss_pct": 50}])
def test_non_binding_cap_is_bit_identical(two_sectors, extra):
    """섹터 합(50%)에 걸리지 않는 상한은 결과를 바꾸지 않는다."""
    px, ents, exts, rank = _frames(["A", "B", "C", "D"])

    base = Simulator().run(px, px, ents, exts, _risk(**extra), _OPTS, rank_df=rank)
    with_cap = Simulator().run(px, px, ents, exts,
                               _risk(max_sector_weight_pct=60, **extra), _OPTS, rank_df=rank)

    assert base.value().equals(with_cap.value())


def test_sector_cap_applies_after_position_cap(two_sectors):
    """종목당 상한으로 이미 줄어든 비중에 섹터 합을 다시 맞춘다(둘 다 지켜진다)."""
    px, ents, exts, rank = _frames(["A", "B", "C", "D"])

    pf = Simulator().run(px, px, ents, exts,
                         _risk(max_position_weight_pct=20, max_sector_weight_pct=30),
                         _OPTS, rank_df=rank)
    weights = _weights(pf)

    assert weights.max() <= 0.20 + 1e-9
    assert weights[["A", "B"]].sum() == pytest.approx(0.30, abs=1e-6)


# ── ③ 해석 레인 관통 ────────────────────────────────────────────────────────

def _compile(sector_cap):
    intent, report = run_validation(StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["KOSPI"]},
        "ranking": [{"metric": "ranking.return", "lookback_days": 60}],
        "portfolio": {"selection_count": 10, "rebalance_frequency": "monthly",
                      "max_sector_weight_percent": sector_cap},
    }))
    return compile_partial(intent, report, "수익률 상위 10종목")[0], report


def test_sector_cap_reaches_engine_request_and_canonical_dsl():
    parsed, report = _compile(25)

    assert report.errors == [] and parsed.max_sector_weight_pct == 25
    assert to_canonical_strategy_dsl(parsed)["max_sector_weight_pct"] == 25
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["max_sector_weight_pct"] == 25


def test_sector_cap_round_trips_through_decompiler():
    parsed, _report = _compile(25)

    assert decompile_strategy(parsed).portfolio.max_sector_weight_percent == 25


def test_out_of_range_sector_cap_is_rejected_not_clamped():
    _parsed, report = _compile(150)

    assert any("섹터별 비중 상한" in message for message in report.errors)


def test_sector_cap_is_independent_of_position_cap():
    """섹터 상한을 말해도 종목당 상한 칸은 채워지지 않는다(v16.19가 고친 오해석)."""
    parsed, _report = _compile(25)

    assert parsed.max_position_weight_pct is None
