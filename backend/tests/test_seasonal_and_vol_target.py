"""계절 필터(seasonal_months)·목표 변동성(target_volatility_pct) — 엔진 v16.25 회귀.

계절 필터: 행 날짜의 달이 목록에 없으면 노출 0(전량 현금, 사유 '계절 필터 청산'), 있으면 1.
목표 변동성: 1회 실행 자산곡선의 최근 20거래일 변동성(연환산)이 목표를 넘는 날 노출을
목표÷실현 비율(5%p 단위 내림, 최대 100%)로 낮춰 재실행. 둘 다 없으면 결과 비트 동일.
해석 레인: seasonality·volatility_target 스펙 → ParsedStrategy → 요청/해시 → 디컴파일 왕복,
목표 값이 비면 되묻기 + 값 대기(엔진 요청에 싣지 않음).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest_engine import BacktestEngine
from engine import trade_reason as tr
from engine.nl_parser import ParsedStrategy, VolatilityTarget
from engine.simulator import Simulator, VOL_TARGET_WINDOW
from engine.strategy_converter import compute_strategy_id, to_backtest_request, to_canonical_strategy_dsl
from strategy_conversation.compiler.strategy_compiler import compile_partial, compile_strategy
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation

_OPTS = {"execution_type": "same_close", "fee_rate": 0, "slippage_rate": 0, "sell_tax_rate": 0}
_CASH = 10_000_000.0


def _frames(closes, syms=("A", "B"), start="2024-03-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    px = pd.DataFrame({s: list(map(float, closes)) for s in syms}, index=idx)
    ents = pd.DataFrame(True, index=idx, columns=list(syms))
    exts = pd.DataFrame(False, index=idx, columns=list(syms))
    rank = pd.DataFrame({s: float(len(syms) - k) for k, s in enumerate(syms)}, index=idx)
    return idx, px, ents, exts, rank


def _risk(**extra):
    base = {"max_positions": 2, "init_cash": _CASH, "allocation_type": "equal",
            "rebalancing_period": "monthly"}
    base.update(extra)
    return base


# ── 계절 필터 ─────────────────────────────────────────────────────────────────

def test_seasonal_exposure_is_one_in_listed_months_and_zero_elsewhere():
    idx = pd.bdate_range("2024-03-25", "2024-05-05")
    exp = BacktestEngine._seasonal_exposure([11, 12, 1, 2, 3, 4], idx)
    months = pd.DatetimeIndex(idx).month
    assert np.array_equal(exp, np.where(np.isin(months, [3, 4]), 1.0, 0.0))


@pytest.mark.parametrize("extra", [{}, {"entry_signal_driven": True}])
def test_seasonal_zero_days_liquidate_with_seasonal_reason(extra):
    """4월까지 투자·5월 현금·(6월 첫 거래일 재편입은 목록 밖이라 없음) — 노출·사유 배열을 엔진과 같은 규칙으로 넘긴다."""
    idx, px, ents, exts, rank = _frames([100.0] * 45, start="2024-04-01")
    exp = BacktestEngine._seasonal_exposure([4], idx)
    reason = tr.encode([tr.part(tr.SEASONAL_EXIT, "4")])
    reasons = np.array([reason if e <= 0 else None for e in exp], dtype=object)
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, _risk(**extra), _OPTS, rank_df=rank,
                 exposure=exp, exposure_reasons=reasons)
    first_may = int(np.where(pd.DatetimeIndex(idx).month == 5)[0][0])
    assert pf.cash().iloc[first_may] == pytest.approx(pf.value().iloc[first_may])   # 전량 현금
    assert pf.cash().iloc[first_may - 1] < pf.value().iloc[first_may - 1] * 0.05     # 4월 말까지 투자
    got = {r for by_date in sim.exit_reason_overrides.values() for r in by_date.values()}
    assert reason in got


# ── 목표 변동성 ───────────────────────────────────────────────────────────────

def _volatile_path(n=60, seed=0, daily_sigma=0.04):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0, daily_sigma, n)
    return list(100.0 * np.cumprod(1.0 + rets))


def test_vol_target_reduces_exposure_when_realized_exceeds_target():
    """일 변동성 4%(연환산 ≈63%) 경로에 목표 10% → 워밍업(20일) 뒤 노출이 1 아래로 내려간다."""
    idx, px, ents, exts, rank = _frames(_volatile_path())
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, _risk(target_volatility_pct=10, entry_signal_driven=True),
                 _OPTS, rank_df=rank)
    assert sim.vol_target_days is not None and sim.vol_target_days > 0
    invested = 1.0 - pf.cash().to_numpy() / pf.value().to_numpy()
    assert invested[:VOL_TARGET_WINDOW].max() > 0.9                # 워밍업 구간은 100%
    assert invested[VOL_TARGET_WINDOW + 2:].max() < 0.9            # 이후 노출 축소
    got = {r for by_date in sim.exit_reason_overrides.values() for r in by_date.values()}
    assert tr.encode([tr.part(tr.VOL_TARGET_REDUCE, "10")]) in got


def test_vol_target_never_levers_up_and_quiet_path_is_bit_identical():
    idx, px, ents, exts, rank = _frames([100.0 + 0.01 * i for i in range(40)])   # 거의 무변동
    base = Simulator().run(px, px, ents, exts, _risk(), _OPTS, rank_df=rank)
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, _risk(target_volatility_pct=10), _OPTS, rank_df=rank)
    assert sim.vol_target_days == 0
    assert np.array_equal(pf.value().values, base.value().values)


def test_vol_target_next_open_applies_from_next_bar():
    idx, px, ents, exts, rank = _frames(_volatile_path())
    opts = dict(_OPTS, execution_type="next_open")
    sim_c = Simulator(); sim_c.run(px, px, ents, exts, _risk(target_volatility_pct=10, entry_signal_driven=True), _OPTS, rank_df=rank)
    sim_o = Simulator(); sim_o.run(px, px, ents, exts, _risk(target_volatility_pct=10, entry_signal_driven=True), opts, rank_df=rank)
    assert sim_o.vol_target_days == sim_c.vol_target_days or abs(sim_o.vol_target_days - sim_c.vol_target_days) <= 1


# ── 해석 레인 ─────────────────────────────────────────────────────────────────

def _intent(**strategy_extra):
    strategy = {
        "universe": {"markets": ["KOSPI"], "sectors": [], "symbols": []},
        "entry_conditions": [], "exit_conditions": [],
        "ranking": [{"metric": "ranking.return", "lookback_days": 60, "direction": "top"}],
        "portfolio": {"selection_count": 10, "rebalance_frequency": "monthly"},
        "risk_management": {}, "backtest": {},
    }
    strategy.update(strategy_extra)
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "status": "READY", "confidence": 0.9, "strategy": strategy,
    })


def test_seasonality_and_vol_target_compile_round_trip_and_reach_request():
    validated, report = run_validation(_intent(
        seasonality={"invest_months": ["11", 12, 1, 2, 3, 4, 4], "source_text": "11월부터 4월까지만 투자"},
        volatility_target={"target_percent": "10%", "source_text": "목표 연변동성 10%"},
    ))
    assert report.errors == [] and not report.unsupported_features
    parsed = compile_strategy(validated, report, "x")
    assert parsed.seasonal_months == [11, 12, 1, 2, 3, 4]
    assert parsed.volatility_target == VolatilityTarget(target_pct=10.0)
    req = to_backtest_request(parsed, resolve_symbols=False)
    assert req["risk"]["seasonal_months"] == [11, 12, 1, 2, 3, 4]
    assert req["risk"]["target_volatility_pct"] == 10.0
    spec = decompile_strategy(parsed)
    assert spec.seasonality.invest_months == [11, 12, 1, 2, 3, 4]
    assert spec.volatility_target.target_percent == 10.0
    canonical = to_canonical_strategy_dsl(parsed)
    assert canonical["seasonal_months"] == [1, 2, 3, 4, 11, 12]
    assert canonical["volatility_target"] == {"target_pct": 10.0}


def test_vol_target_without_value_asks_and_is_not_sent_to_engine():
    validated, report = run_validation(_intent(
        volatility_target={"target_percent": None, "source_text": "변동성 타깃으로 노출 조정"},
    ))
    assert any(q.field == "strategy.volatility_target.target_percent" for q in report.clarification_questions)
    parsed, dropped, pending = compile_partial(validated, report, "x")   # 되묻기 진행 중의 부분 컴파일
    assert "목표 변동성" in dropped and any(p["label"] == "목표 변동성" for p in pending)
    assert parsed.volatility_target == VolatilityTarget(target_pct=None)
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["target_volatility_pct"] is None


def test_all_twelve_months_is_not_a_filter_and_absence_keeps_hash():
    validated, report = run_validation(_intent(seasonality={"invest_months": list(range(1, 13)), "source_text": "매달"}))
    assert validated.strategy.seasonality is None and report.unsupported_features
    validated2, report2 = run_validation(_intent())
    base = compile_strategy(validated2, report2, "x")
    dumped = to_canonical_strategy_dsl(base)
    assert "seasonal_months" not in dumped and "volatility_target" not in dumped
    assert ParsedStrategy(description="x", seasonal_months=[13, 0, 5, 5]).seasonal_months == [5]
    assert compute_strategy_id(base) == compute_strategy_id(ParsedStrategy.model_validate(base.model_dump()))
