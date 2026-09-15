"""거래량 배수 지표(volume_ratio, 엔진 v16.10) 배선 전체 회귀.

배경(2026-09-15): "거래량이 20일 평균보다 1.5배 많은 종목"의 배수가 OBV 교차(volume_spike)로
근사되며 사라졌다. 당일 거래량 ÷ 직전 N일 평균 거래량을 배수 임계와 비교하는 지표를 신설해
정확히 표현한다. 이 파일은 ① IndicatorEngine 컬럼(직전 N일 평균, 당일 제외) ② SignalEngine
벡터·행별 판정과 매매사유 ③ 컨버터·레지스트리·온톨로지 ④ 검증기의 정본 착지(volume_spike+value →
volume_ratio) ⑤ primary 레인 end-to-end(스텁 LLM)를 고정한다.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from engine import trade_reason as tr
from engine.indicators import IndicatorEngine
from engine.nl_parser import TechnicalSignal
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.registry import concept_ontology, indicator_registry
from strategy_conversation.validation.capability_validator import validate_capability


def _frame(volumes: list[float]) -> pl.DataFrame:
    n = len(volumes)
    dates = pl.datetime_range(
        pl.datetime(2024, 1, 1), pl.datetime(2024, 1, 1) + pl.duration(days=n - 1),
        interval="1d", eager=True,
    )
    close = [100.0] * n
    return pl.DataFrame({"date": dates, "open": close, "high": close, "low": close,
                         "close": close, "volume": volumes})


_COND = {"id": "volume_ratio", "params": {"period": 3, "operator": ">=", "value": 1.5, "signalType": "buy"}}


# ── ① 지표 계산: 직전 N일 평균(당일 제외) ─────────────────────────────────────

def test_indicator_engine_uses_previous_n_day_average():
    out = IndicatorEngine.calculate(_frame([100, 100, 100, 300, 100]), [_COND])
    col = out["volume_3_prev_sma"].to_list()
    # 4번째 봉(거래량 300)의 평균은 앞 3봉(100·100·100)=100 — 당일 300은 평균에 들어가지 않는다.
    assert col[3] == 100.0
    assert col[4] == (100 + 100 + 300) / 3
    assert all(v is None or np.isnan(v) for v in col[:3])


# ── ② 신호 판정과 매매사유 ────────────────────────────────────────────────────

def test_signal_engine_flags_days_where_volume_exceeds_multiple():
    df = IndicatorEngine.calculate(_frame([100, 100, 100, 300, 100, 140]), [_COND])
    engine = SignalEngine()
    # 4번째 봉: 300/100 = 3배 ≥ 1.5 → 매수. 6번째 봉: 140/((100+300+100)/3) = 0.84 → 아니다.
    assert list(engine._eval_vec(_COND, df)) == [False, False, False, True, False, False]
    # 행별 경로(실시간 신호)도 같은 판정이다.
    assert [engine.evaluate_condition(_COND, i, df) for i in range(len(df))] == \
        [False, False, False, True, False, False]
    _sigs, reasons = engine.generate_signals(df, {"logic": "AND", "conditions": [_COND]})
    rendered = tr.render_kr(tr.decode(reasons[3]))
    assert "거래량이 3일 평균의 1.5배" in rendered and "이상" in rendered
    assert reasons[5] is None


def test_signal_engine_zero_average_is_fail_closed():
    df = IndicatorEngine.calculate(_frame([0, 0, 0, 300]), [_COND])
    assert list(SignalEngine()._eval_vec(_COND, df)) == [False, False, False, False]


# ── ③ 컨버터·레지스트리·온톨로지 ─────────────────────────────────────────────

def test_converter_and_registry_wiring():
    sig = TechnicalSignal(indicator="volume_ratio", signal_type="buy", period=20, operator=">=", value=1.5)
    cond = _tech_signal_to_condition(sig)
    assert cond["id"] == "volume_ratio"
    assert (cond["params"]["period"], cond["params"]["operator"], cond["params"]["value"]) == (20, ">=", 1.5)
    spec = indicator_registry.resolve("technical.volume_ratio")
    assert spec is not None and spec.engine_binding == ("technical_signal", "volume_ratio")
    assert indicator_registry.resolve("거래량배수").id == "technical.volume_ratio"
    onto = concept_ontology.get_ontology()
    assert onto.members["technical.volume_ratio"] == "class.volume"
    assert "unsupported.volume_multiple" not in onto.members
    assert indicator_registry.REGISTRY.get("unsupported.volume_multiple") is None


# ── ④ 검증기: 옛 자리(volume_spike + value) → volume_ratio 정본 착지 ─────────

def _intent(cond: dict) -> StrategyIntent:
    return StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": ["반도체"]},
        "entry_conditions": [cond],
        "portfolio": {"selection_count": 5, "rebalance_frequency": "monthly"},
    })


def test_validator_lands_volume_spike_with_value_on_volume_ratio():
    intent = _intent({"factor": "technical.volume_spike", "operator": ">=", "value": 1.5,
                      "unit": "ratio", "parameters": {"period": 20},
                      "source_text": "거래량이 20일 평균보다 1.5배 많은"})
    errors, _w, unsupported, _f = validate_capability(intent)
    cond = intent.strategy.entry_conditions[0]
    assert cond.factor == "technical.volume_ratio"
    assert (cond.operator, cond.value, cond.parameters.get("period")) == (">=", 1.5, 20)
    assert cond.approximated is False  # 정확 표현 — 근사 안내 대상이 아니다
    assert errors == [] and unsupported == []


def test_validator_defaults_operator_to_gte_when_only_value_given():
    intent = _intent({"factor": "technical.volume_spike", "value": 3, "source_text": "평소보다 3배"})
    validate_capability(intent)
    cond = intent.strategy.entry_conditions[0]
    assert cond.factor == "technical.volume_ratio" and cond.operator == ">=" and cond.value == 3


def test_validator_keeps_plain_volume_spike():
    intent = _intent({"factor": "technical.volume_spike", "source_text": "거래량이 급증한"})
    validate_capability(intent)
    cond = intent.strategy.entry_conditions[0]
    assert cond.factor == "technical.volume_spike" and cond.value is None


# ── ⑤ primary 레인 end-to-end ────────────────────────────────────────────────

def test_primary_lane_compiles_volume_ratio_without_approximation_notice(monkeypatch):
    from tests.test_strategy_conversation import _full_intent_dict, _run_primary_with

    data = _full_intent_dict(
        universe={"markets": ["KOSPI", "KOSDAQ"], "sectors": []},
        entry_conditions=[
            {"factor": "technical.volume_ratio", "operator": ">=", "value": 1.5, "unit": "ratio",
             "parameters": {"period": 20}, "source_text": "거래량이 20일 평균보다 1.5배 많은"},
        ],
        portfolio={"selection_count": 5, "rebalance_frequency": "monthly"},
    )
    result = _run_primary_with(
        monkeypatch, data,
        "거래량이 20일 평균보다 1.5배 많은 종목을 5종목 매월 리밸런싱, 손절 8%")
    assert result is not None
    sig = result["parsed"].entry_signals[0]
    assert (sig.indicator, sig.period, sig.operator, sig.value) == ("volume_ratio", 20, ">=", 1.5)
    assert not [n for n in result["notices"] if "가깝게 반영" in n or "반영하지 못했어요" in n], result["notices"]


def test_interpreter_prompt_routes_volume_multiple_to_volume_ratio():
    from strategy_conversation.interpreter.prompts import PROMPT_VERSION, build_system_prompt

    assert PROMPT_VERSION >= "6.0"
    prompt = build_system_prompt()
    assert "technical.volume_ratio" in prompt
    assert "배수 임계값은 표현 불가" not in prompt
    assert "unsupported_features에도 넣으세요" not in prompt
