"""거래대금 배수 지표(trading_value_ratio, 엔진 v16.13) 배선 전체 회귀.

배경(2026-09-18): "최근 거래대금이 30일 평균보다 높은"을 엔진이 표현하지 못해 거래량 급증(OBV 교차)
이나 거래량 배수로 근사됐고, 인용 정규식 재분류와 근사 탐지가 겹쳐 안내가 두 줄 나갔다. 당일
거래대금(종가×거래량) ÷ 직전 N일 평균 거래대금을 배수 임계와 비교하는 지표를 신설해 정확히
표현한다. 이 파일은 ① IndicatorEngine 컬럼(직전 N일 평균, 당일 제외) ② SignalEngine 벡터·행별
판정과 매매사유 ③ 컨버터·레지스트리·온톨로지 ④ 검증기의 정본 착지(trading_value + 평균 기간,
값 없음 → trading_value_ratio) ⑤ primary 레인 end-to-end(스텁 LLM)를 고정한다.
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


def _frame(closes: list[float], volumes: list[float]) -> pl.DataFrame:
    n = len(volumes)
    dates = pl.datetime_range(
        pl.datetime(2024, 1, 1), pl.datetime(2024, 1, 1) + pl.duration(days=n - 1),
        interval="1d", eager=True,
    )
    return pl.DataFrame({"date": dates, "open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": volumes})


_COND = {"id": "trading_value_ratio",
         "params": {"period": 3, "operator": ">", "value": 1, "signalType": "buy"}}


# ── ① 지표 계산: 직전 N일 평균 거래대금(당일 제외) ─────────────────────────────

def test_indicator_engine_uses_previous_n_day_average_trading_value():
    out = IndicatorEngine.calculate(
        _frame([100, 100, 100, 200, 100], [10, 10, 10, 10, 10]), [_COND])
    col = out["trading_value_3_prev_sma"].to_list()
    # 4번째 봉의 평균은 앞 3봉 거래대금(1000·1000·1000) — 당일(2000)은 들어가지 않는다.
    assert col[3] == 1000.0
    assert col[4] == (1000 + 1000 + 2000) / 3
    assert all(v is None or np.isnan(v) for v in col[:3])


# ── ② 신호 판정과 매매사유 ────────────────────────────────────────────────────

def test_signal_engine_compares_trading_value_not_volume():
    # 거래량은 그대로인데 주가만 두 배 — 거래량 배수로는 1배(아니다), 거래대금 배수로는 2배(맞다).
    # 5번째 봉: 거래량 5로 절반 → 거래대금 500 < 평균(1333) → 아니다.
    df = IndicatorEngine.calculate(
        _frame([100, 100, 100, 200, 100], [10, 10, 10, 10, 5]), [_COND])
    engine = SignalEngine()
    assert list(engine._eval_vec(_COND, df)) == [False, False, False, True, False]
    assert [engine.evaluate_condition(_COND, i, df) for i in range(len(df))] == \
        [False, False, False, True, False]
    _sigs, reasons = engine.generate_signals(df, {"logic": "AND", "conditions": [_COND]})
    rendered = tr.render_kr(tr.decode(reasons[3]))
    assert "거래대금이 3일 평균의 1배" in rendered and "초과" in rendered
    assert reasons[4] is None


def test_signal_engine_zero_average_is_fail_closed():
    df = IndicatorEngine.calculate(_frame([100] * 4, [0, 0, 0, 300]), [_COND])
    assert list(SignalEngine()._eval_vec(_COND, df)) == [False, False, False, False]


# ── ③ 컨버터·레지스트리·온톨로지 ─────────────────────────────────────────────

def test_converter_and_registry_wiring():
    sig = TechnicalSignal(indicator="trading_value_ratio", signal_type="buy", period=30,
                          operator=">", value=1)
    cond = _tech_signal_to_condition(sig)
    assert cond["id"] == "trading_value_ratio"
    assert (cond["params"]["period"], cond["params"]["operator"], cond["params"]["value"]) == (30, ">", 1)
    spec = indicator_registry.resolve("technical.trading_value_ratio")
    assert spec is not None and spec.engine_binding == ("technical_signal", "trading_value_ratio")
    assert indicator_registry.resolve("거래대금배수").id == "technical.trading_value_ratio"
    assert concept_ontology.get_ontology().members["technical.trading_value_ratio"] == "class.volume"


# ── ④ 검증기: 옛 자리(trading_value + 평균 기간, 값 없음) → 정본 착지 ─────────

def _intent(cond: dict) -> StrategyIntent:
    return StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["KOSDAQ"]},
        "entry_conditions": [cond],
        "portfolio": {"selection_count": 9, "rebalance_frequency": "weekly"},
    })


def test_validator_lands_trading_value_with_period_on_ratio():
    for factor in ("fundamental.trading_value", "technical.trading_value"):
        intent = _intent({"factor": factor, "operator": ">", "value": None,
                          "parameters": {"period": 30},
                          "source_text": "최근 거래대금이 30일 평균보다 높은"})
        errors, _w, unsupported, _f = validate_capability(intent)
        cond = intent.strategy.entry_conditions[0]
        assert cond.factor == "technical.trading_value_ratio", factor
        assert (cond.operator, cond.value, cond.parameters.get("period")) == (">", None, 30)
        assert errors == [] and unsupported == []


def test_validator_keeps_amount_threshold_trading_value():
    # 금액 임계는 기간이 있어도(기간 평균 금액) 옮기지 않는다. 기간 없는 값-대기도 그대로.
    for cond_in in (
        {"factor": "fundamental.trading_value", "operator": ">=", "value": 50,
         "parameters": {"period": 60}, "source_text": "60일 평균 거래대금 50억 이상"},
        {"factor": "fundamental.trading_value", "operator": ">=", "value": None,
         "source_text": "거래대금 조건"},
    ):
        intent = _intent(cond_in)
        validate_capability(intent)
        assert intent.strategy.entry_conditions[0].factor == "fundamental.trading_value"


# ── ⑤ primary 레인 end-to-end ────────────────────────────────────────────────

def test_primary_lane_compiles_trading_value_ratio_without_approximation_notice(monkeypatch):
    # 프롬프트 6.1이 지시하는 형태(trading_value_ratio ">" 1, period=30)가 엔진 신호까지 그대로
    # 가고, 인용이 '거래대금'을 불러도 같은 이름의 변형이라 근사·대체 안내가 붙지 않는다.
    from tests.test_strategy_conversation import _full_intent_dict, _run_primary_with

    data = _full_intent_dict(
        universe={"markets": ["KOSDAQ"], "sectors": []},
        entry_conditions=[
            {"factor": "technical.trading_value_ratio", "operator": ">", "value": 1,
             "unit": "ratio", "parameters": {"period": 30},
             "source_text": "최근 거래대금이 30일 평균보다 높은"},
        ],
        portfolio={"selection_count": 9, "rebalance_frequency": "weekly"},
    )
    result = _run_primary_with(
        monkeypatch, data,
        "KOSDAQ에서 최근 거래대금이 30일 평균보다 높은 경우만 진입, 주간 리밸런싱 최대 9종목, 손절 7%")
    assert result is not None
    sig = result["parsed"].entry_signals[0]
    assert (sig.indicator, sig.period, sig.operator, sig.value) == ("trading_value_ratio", 30, ">", 1)
    assert not [n for n in result["notices"]
                if "가깝게 반영" in n or "반영하지 못했어요" in n or "거래량 급증" in n], result["notices"]


def test_interpreter_prompt_routes_average_comparison_to_trading_value_ratio():
    from strategy_conversation.interpreter.prompts import PROMPT_VERSION, build_system_prompt

    assert PROMPT_VERSION >= "6.1"
    assert "technical.trading_value_ratio" in build_system_prompt()


# ── ⑥ 거래대금 비교 대상 대조(LLM) — 기간 없는 옛 자리 ────────────────────────
# 2026-09-18 실측(120B 4회 중 1회): 평균 기간 없이 fundamental.trading_value(값 없음)로 나와
# "일평균거래대금 기준값을 몇 억?" 헛질문. 그 형태는 '금액 미정 거래대금'과 구별되지 않으므로
# 비교 대상을 LLM이 판정하고, 결정론은 enum·범위 확인과 지표 이동만 한다.

_USER = ("KOSDAQ 중 시가총액 2000억 원 이상 종목에서 20일 EMA가 60일 EMA 위에 있고 "
         "최근 거래대금이 30일 평균보다 높은 경우만 진입해 주세요.")


def _chat(reply: str, calls: list | None = None):
    def chat(system_prompt, user_message, **kwargs):  # noqa: ANN001
        if calls is not None:
            calls.append(user_message)
        return reply
    return chat


def _bare_trading_value_intent(**overrides) -> StrategyIntent:
    cond = {"factor": "fundamental.trading_value", "operator": ">=", "value": None,
            "unit": "억원", "source_text": "최근 거래대금이 30일 평균보다 높은"}
    cond.update(overrides)
    return _intent(cond)


def test_own_average_verdict_moves_bare_trading_value_to_ratio():
    from strategy_conversation.primary import _resolve_trading_value_comparisons

    intent = _bare_trading_value_intent()
    _resolve_trading_value_comparisons(intent, _USER, _chat(
        '{"items":[{"compares":"own_average","average_days":30,"multiple":1,"operator":">"}]}'))
    cond = intent.strategy.entry_conditions[0]
    assert (cond.factor, cond.operator, cond.value, cond.unit, cond.parameters.get("period")) == (
        "technical.trading_value_ratio", ">", 1.0, "ratio", 30.0)
    errors, _w, unsupported, _f = validate_capability(intent)
    assert errors == [] and unsupported == []


def test_amount_unclear_or_failed_verdict_leaves_condition_untouched():
    # 금액 비교·판단 불가·형식 오류·항목 수 불일치는 전부 판정 없음 — 종전대로 금액을 되묻는다.
    from strategy_conversation.primary import _resolve_trading_value_comparisons

    for reply in (
        '{"items":[{"compares":"amount","average_days":null,"multiple":null,"operator":null}]}',
        '{"items":[{"compares":"unclear"}]}',
        '{"items":[{"compares":"average"}]}',   # enum 밖
        'not json',
        '{"items":[]}',
    ):
        intent = _bare_trading_value_intent()
        _resolve_trading_value_comparisons(intent, _USER, _chat(reply))
        cond = intent.strategy.entry_conditions[0]
        assert (cond.factor, cond.value) == ("fundamental.trading_value", None), reply


def test_out_of_range_transcriptions_are_dropped_not_clamped():
    # 범위 밖 기간·배수는 싣지 않는다(고쳐 쓰지 않는다) — 배수가 없으면 값-대기로 되묻는다.
    from strategy_conversation.primary import _resolve_trading_value_comparisons

    intent = _bare_trading_value_intent()
    _resolve_trading_value_comparisons(intent, _USER, _chat(
        '{"items":[{"compares":"own_average","average_days":9999,"multiple":-3,"operator":"=="}]}'))
    cond = intent.strategy.entry_conditions[0]
    assert cond.factor == "technical.trading_value_ratio"
    assert cond.value is None and cond.parameters.get("period") is None
    assert cond.operator == ">="  # 대조기 부등호가 enum 밖이면 인터프리터 부등호를 쓴다


def test_trading_value_check_asks_only_bare_trading_value_conditions():
    # 금액이 있거나 평균 기간이 실린 조건(검증기 형태 이관 소관)은 묻지 않는다 — 호출 자체가 없다.
    from strategy_conversation.primary import _resolve_trading_value_comparisons

    for overrides in ({"value": 50}, {"parameters": {"period": 30}}):
        calls: list = []
        intent = _bare_trading_value_intent(**overrides)
        _resolve_trading_value_comparisons(intent, _USER, _chat('{"items":[]}', calls))
        assert calls == [], overrides
    # 주입 스텁(chat 없음)은 건너뛴다.
    intent = _bare_trading_value_intent()
    _resolve_trading_value_comparisons(intent, _USER, None)
    assert intent.strategy.entry_conditions[0].factor == "fundamental.trading_value"
