"""시장 대비 초과수익률 지표(relative_return, 엔진 v16.7) 배선 전체 회귀.

배경(2026-09-13): "최근 3개월 동안 시장보다 덜 떨어진 종목"이 지수 시계열이 없어
UNSUPPORTED_REQUEST로 떨어졌다. 지수 저장소(data/index)를 신설한 뒤 이 지표로 정확히
표현한다. 이 파일은 ① IndicatorEngine 계산식(종목 N봉 수익률 − 지수 N봉 수익률, %p)과
index_close 부재 시 NaN(fail-closed) ② SignalEngine 매수/매도 기본 방향·매매사유 세그먼트
③ 레지스트리/온톨로지/컴파일러/컨버터의 canonical 매핑 ④ 미국 시장 거절 ⑤ primary 레인
end-to-end(스텁 LLM)를 고정한다.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

import ui_language
from engine.indicators import IndicatorEngine
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition
from strategy_conversation.compiler.strategy_compiler import compile_strategy
from strategy_conversation.interpreter.models import (
    StrategyCondition, StrategyIntent, StrategySpec, UniverseSpec, ValidationReport,
)
from strategy_conversation.registry import concept_ontology, indicator_registry
from strategy_conversation.validation.capability_validator import validate_capability


def _frame(close: list[float], index_close: list[float] | None) -> pl.DataFrame:
    n = len(close)
    dates = pl.datetime_range(
        pl.datetime(2024, 1, 1), pl.datetime(2024, 1, 1) + pl.duration(days=n - 1),
        interval="1d", eager=True,
    )
    data = {"date": dates, "open": close, "high": close, "low": close, "close": close,
            "volume": [1_000_000.0] * n}
    if index_close is not None:
        data["index_close"] = index_close
    return pl.DataFrame(data)


_COND = {"id": "relative_return", "params": {"period": 2, "operator": ">", "value": 0, "signalType": "buy"}}


# ── ① 지표 계산 ──────────────────────────────────────────────────────────────

def test_indicator_engine_computes_excess_return_in_percent_points():
    # 종목 100→110(2봉 +10%), 지수 2000→2040(2봉 +2%) → 초과수익률 +8%p
    out = IndicatorEngine.calculate(
        _frame([100.0, 105.0, 110.0, 99.0], [2000.0, 2020.0, 2040.0, 2040.0]), [_COND])
    col = out["relative_return_2"].to_list()
    assert col[0] is None or np.isnan(col[0])
    assert col[2] == pytest.approx(8.0)
    # 종목 105→99(−5.714%), 지수 2020→2040(+0.990%) → −6.70%p
    assert col[3] == pytest.approx((99 / 105 - 1) * 100 - (2040 / 2020 - 1) * 100)


def test_indicator_engine_leaves_nan_without_index_close():
    """지수 조인이 없으면(지수 파일 부재·미국 종목) 0으로 위장하지 않고 NaN → 조건 False."""
    out = IndicatorEngine.calculate(_frame([100.0, 105.0, 110.0], None), [_COND])
    assert all(v is None or np.isnan(v) for v in out["relative_return_2"].to_list())
    assert list(SignalEngine()._eval_vec(_COND, out)) == [False, False, False]


# ── ② 신호 평가·매매사유 ─────────────────────────────────────────────────────

def test_signal_engine_default_direction_and_operator():
    engine = SignalEngine()
    df = pl.DataFrame({"relative_return_63": [3.0, -2.0, 0.0, float("nan")]})
    buy = {"id": "relative_return", "params": {"period": 63, "signalType": "buy"}}
    sell = {"id": "relative_return", "params": {"period": 63, "signalType": "sell"}}
    assert list(engine._eval_vec(buy, df)) == [True, False, False, False]
    assert list(engine._eval_vec(sell, df)) == [False, True, False, False]
    explicit = {"id": "relative_return", "params": {"period": 63, "operator": "<", "value": -1, "signalType": "buy"}}
    assert list(engine._eval_vec(explicit, df)) == [False, True, False, False]
    assert engine.evaluate_condition(buy, 0, df) is True
    assert engine.evaluate_condition(buy, 1, df) is False


def test_condition_description_names_market_excess_return():
    desc = SignalEngine().get_condition_description(
        {"id": "relative_return", "params": {"period": 63, "operator": ">", "value": 0, "signalType": "buy"}})
    assert "시장 대비 초과수익률(63일)" in desc and "0" in desc


def test_trade_reason_carries_measured_excess_return():
    # [회귀 2026-09-13] "시장 대비 초과수익률(63일) 0%p 이상"만 보이면 얼마나 앞섰는지 읽을 수 없다 —
    # 신호가 난 봉의 실측값을 사유에 함께 싣는다. 벡터 경로(generate_signals)와 행별 경로(evaluate_group)
    # 모두 같은 문장이어야 한다.
    from engine import trade_reason as tr
    engine = SignalEngine()
    df = pl.DataFrame({"relative_return_63": [4.26, -2.0, 0.0, float("nan")], "close": [1.0, 1.0, 1.0, 1.0]})
    cond = {"id": "relative_return", "params": {"period": 63, "operator": ">", "value": 0, "signalType": "buy"}}
    group = {"logic": "AND", "conditions": [cond]}

    _, reasons = engine.generate_signals(df, group)
    assert reasons[1] is None and reasons[2] is None and reasons[3] is None
    text = tr.render_kr(tr.decode(reasons[0]))
    assert text == "시장 대비 초과수익률(63일) +4.3%p"

    ok, row_reason = engine.evaluate_group(group, 0, df)
    assert ok and tr.render_kr(tr.decode(row_reason)) == text

    # 실측값이 없으면(정적 서술 요청) 종전 문장 그대로다.
    assert engine.get_condition_description(cond) == "시장 대비 초과수익률(63일) 0%p 이상"


# ── ③ 레지스트리·온톨로지·컴파일·컨버터 ──────────────────────────────────────

def test_registry_and_ontology_know_the_leaf():
    spec = indicator_registry.resolve("technical.relative_return")
    assert spec is not None and spec.supported == "SUPPORTED"
    assert spec.engine_binding == ("technical_signal", "relative_return")
    assert indicator_registry.resolve("초과수익률").id == "technical.relative_return"
    onto = concept_ontology.get_ontology()
    assert onto.members["technical.relative_return"] == "class.oscillator"
    assert onto.polarity["technical.relative_return"] == "higher_better"


def _intent(markets, operator=">", period=63) -> StrategyIntent:
    spec = StrategySpec(
        universe=UniverseSpec(markets=markets),
        entry_conditions=[StrategyCondition(
            factor="technical.relative_return", operator=operator, value=0.0,
            parameters={"period": period}, source_text="시장보다 덜 떨어진",
        )],
    )
    return StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)


def test_compile_and_convert_to_engine_condition():
    parsed = compile_strategy(_intent(["KOSPI200"]), ValidationReport(is_valid=True, status="READY"),
                              "최근 3개월 동안 시장보다 덜 떨어진 종목")
    sig = parsed.entry_signals[0]
    assert (sig.indicator, sig.period, sig.operator, sig.value) == ("relative_return", 63, ">", 0.0)
    cond = _tech_signal_to_condition(sig)
    assert cond["id"] == "relative_return"
    assert cond["params"] == {"signalType": "buy", "period": 63, "operator": ">", "value": 0.0}


# ── ④ 미국 시장 거절 ─────────────────────────────────────────────────────────

def test_validator_rejects_relative_return_on_us_markets():
    intent = _intent(["SP500"])
    with ui_language.bind("en"):
        errors, _w, unsupported, _f = validate_capability(intent)
    assert any("isn't available for US markets" in e for e in errors), errors
    assert any("미국 시장 ×" in u for u in unsupported)
    assert intent.strategy.entry_conditions == []


def test_validator_keeps_relative_return_on_kr_markets():
    intent = _intent(["KOSPI"])
    errors, _w, _u, _f = validate_capability(intent)
    assert not any("미국 시장" in e for e in errors)
    assert [c.factor for c in intent.strategy.entry_conditions] == ["technical.relative_return"]


def test_validator_lands_relative_return_ranking_on_exact_ranking_metric():
    """[2026-09-15, 엔진 v16.10] LLM이 랭킹 metric을 조건 지표 technical.relative_return으로 내면
    정본 ranking.relative_return(종목 수익률 − 자기 시장 지수 수익률 순위)으로 옮긴다.
    09-14의 ranking.return 근사(같은 시장에서만 순서 동일)와 그 안내는 폐지 — 코스피+코스닥
    혼합에서도 종목마다 제 지수를 빼므로 정확하다."""
    for markets in (["KOSPI200"], ["KOSPI", "KOSDAQ"], []):
        intent = StrategyIntent(intent="CREATE_STRATEGY", strategy={
            "universe": {"markets": markets},
            "ranking": [{"metric": "technical.relative_return", "lookback_days": 60,
                         "direction": "top"}],
            "portfolio": {"selection_count": 5},
        })
        errors, warnings, unsupported, _f = validate_capability(intent)
        assert unsupported == [], unsupported
        assert not any("랭킹 기준" in e for e in errors), errors
        assert [(r.metric, r.lookback_days) for r in intent.strategy.ranking] == [("ranking.relative_return", 60)]
        assert not any("가깝게 반영" in w or "순위와 같아" in w for w in warnings), warnings


def test_validator_rejects_relative_return_ranking_on_us_markets():
    """미국 시장은 지수 시계열이 없다 — 조건과 같은 계약으로 오류+제거+안내."""
    intent = StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["SP500"]},
        "ranking": [{"metric": "ranking.relative_return", "lookback_days": 60}],
        "portfolio": {"selection_count": 5},
    })
    errors, _w, unsupported, _f = validate_capability(intent)
    assert intent.strategy.ranking == []
    assert any("미국 시장" in e for e in errors), errors
    assert any("시장 대비 초과수익률 랭킹" in u for u in unsupported), unsupported


def test_registry_and_ontology_register_relative_return_ranking():
    spec = indicator_registry.resolve("ranking.relative_return")
    assert spec is not None and spec.engine_binding == ("ranking", "relative_return")
    onto = concept_ontology.get_ontology()
    assert onto.members["ranking.relative_return"] == "class.ranking"
    assert onto.polarity["ranking.relative_return"] == "higher_better"
    assert concept_ontology.natural_ranking_direction("ranking.relative_return") == "top"


def test_compiler_binds_relative_return_ranking_to_engine_metric():
    from strategy_conversation.compiler.strategy_compiler import compile_strategy

    intent = StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": []},
        "ranking": [{"metric": "ranking.relative_return", "lookback_days": 60}],
        "portfolio": {"selection_count": 5, "rebalance_frequency": "monthly"},
        "risk_management": {"stop_loss": 10},
    })
    validate_capability(intent)
    parsed = compile_strategy(intent, ValidationReport(is_valid=True, status="READY"), "시장 대비 수익률 상위 5종목")
    assert (parsed.ranking_metric, parsed.ranking_lookback_days, parsed.ranking_direction) == ("relative_return", 60, None)


# ── ④-1 랭킹용 지수 패널(engine/market_index) ───────────────────────────────

def test_relative_return_panel_subtracts_each_symbols_own_market_index(tmp_path, monkeypatch):
    """코스피 종목은 코스피 지수를, 코스닥 종목은 코스닥 지수를 뺀다. 지수 없는 종목은 NaN."""
    import pandas as pd
    from engine import market_index

    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    for market, closes in (("KOSPI", [100.0, 110.0, 121.0, 133.1]), ("KOSDAQ", [100.0, 90.0, 81.0, 72.9])):
        pl.DataFrame({"date": list(dates), "open": closes, "high": closes, "low": closes,
                      "close": closes, "volume": [1.0] * 4, "source": ["t"] * 4}).write_parquet(
            index_dir / f"{market}.parquet")
    monkeypatch.setattr(market_index, "market_for_symbol",
                        lambda s: {"A": "KOSPI", "B": "KOSDAQ"}.get(s))
    raw = pd.DataFrame({"A": [100, 120, 144, 172.8], "B": [100, 120, 144, 172.8], "US": [1, 2, 3, 4]},
                       index=dates, dtype=float)
    panel = market_index.relative_return_panel(raw, 1, data_dir)
    # A: 20% − 10% = +10%p, B: 20% − (−10%) = +30%p, US: 지수 없음 → NaN
    assert abs(panel.loc[dates[1], "A"] - 0.10) < 1e-9
    assert abs(panel.loc[dates[1], "B"] - 0.30) < 1e-9
    assert panel["US"].isna().all()
    assert np.isnan(panel.loc[dates[0], "A"])  # 첫 봉은 수익률 미정


# ── ⑤ primary 레인 end-to-end(스텁 LLM) ─────────────────────────────────────

def test_primary_lane_compiles_relative_return_condition(monkeypatch):
    from tests.test_strategy_conversation import _full_intent_dict, _run_primary_with

    data = _full_intent_dict(
        entry_conditions=[{"factor": "technical.relative_return", "operator": ">", "value": 0,
                           "parameters": {"period": 63}, "source_text": "시장보다 덜 떨어진"}],
        portfolio={"selection_count": 10, "rebalance_frequency": "monthly"},
    )
    result = _run_primary_with(
        monkeypatch, data, "최근 3개월 동안 시장보다 덜 떨어진 종목 10개를 매월 리밸런싱")
    assert result is not None
    sig = result["parsed"].entry_signals[0]
    assert (sig.indicator, sig.period, sig.operator, sig.value) == ("relative_return", 63, ">", 0.0)
    assert not [n for n in result["notices"] if "지원하지 않아" in n or "가깝게 반영" in n]
