"""볼린저 밴드 지정 교차(엔진 v16.39) 회귀.

2026-10-10 사고: 엔진은 볼린저의 밴드를 역할로만 정했고(매수=종가≤하단, 매도=종가≥상단) 컴파일러는
연산자를 버렸다. 그래서 예시 '볼린저밴드 상단을 돌파하면 매수, 하단에 닿으면 청산'이 하단 매수·
상단 청산으로 **정반대** 백테스트됐고, '하단 터치 후 중심선 회복 시 매수'는 하단에 닿는 순간 매수로
조용히 바뀌었다(전수 게이트는 볼린저 '존재'만 봐서 통과).
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from engine import strategy_slots
from engine.nl_parser import ParsedStrategy, TechnicalSignal
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition
from strategy_conversation.compiler.strategy_compiler import (
    StrategyCompileError,
    _compile_condition,
    compile_partial,
)
from strategy_conversation.compiler.strategy_decompiler import _decompile_technical
from strategy_conversation.interpreter.models import StrategyCondition, StrategyIntent
from strategy_conversation.interpreter.quote_check import render_condition
from strategy_conversation.registry.concept_ontology import ontology_prompt_sections
from strategy_conversation.response.output_guard import guard_text
from strategy_conversation.validation.pipeline import run_validation


def _cond(factor, operator=None, **params):
    return StrategyCondition(factor=factor, operator=operator, value=None,
                             parameters=params, source_text="인용")


def _frame(close):
    close = np.asarray(close, dtype=float)
    s = pl.Series(close)
    sma = s.rolling_mean(20).to_numpy()
    sd = s.rolling_std(20).to_numpy()
    return pl.DataFrame({"close": close, "close_20_sma": sma,
                         "boll_ub": sma + 2 * sd, "boll_lb": sma - 2 * sd})


def _engine_cond(**params):
    return {"type": "indicator", "id": "bollinger_bands",
            "params": {"signalType": "buy", **params}}


# ── 엔진 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("params", [
    {"band": "upper", "cross": "above"}, {"band": "upper", "cross": "below"},
    {"band": "middle", "cross": "above"}, {"band": "middle", "cross": "below"},
    {"band": "lower", "cross": "above"}, {"band": "lower", "cross": "below"},
    {"band": "middle", "cross": "above", "touchLookback": 10},
    {"signalType": "buy"}, {"signalType": "sell"},
])
def test_vector_and_row_evaluators_agree(params):
    rng = np.random.default_rng(7)
    df = _frame(100 + np.cumsum(rng.normal(0, 2, 400)))
    engine = SignalEngine()
    cond = _engine_cond(**params)
    vec = engine._eval_vec(cond, df)
    row = np.array([engine.evaluate_condition(cond, i, df) for i in range(len(df))])
    assert (vec == row).all()


def test_upper_cross_above_fires_on_breakout_not_at_lower_band():
    """상단 상향 돌파 매수는 레거시(하단 이하 매수)와 다른 날에 발화한다 — 뒤집힘 방지."""
    rng = np.random.default_rng(3)
    df = _frame(100 + np.cumsum(rng.normal(0, 2, 400)))
    engine = SignalEngine()
    upper = engine._eval_vec(_engine_cond(band="upper", cross="above"), df)
    close, ub, lb = (df[c].to_numpy() for c in ("close", "boll_ub", "boll_lb"))
    assert upper.any()
    assert (close[upper] > ub[upper]).all()          # 돌파한 날은 종가가 상단 위
    assert not (close[upper] <= lb[upper]).any()     # 하단 터치일이 아니다


def test_touch_lookback_requires_prior_lower_touch():
    """하단 터치 후 중심선 회복: 직전 N거래일 안에 하단 터치가 없으면 중심선 돌파만으로는 발화하지 않는다."""
    rng = np.random.default_rng(11)
    df = _frame(100 + np.cumsum(rng.normal(0, 2, 500)))
    engine = SignalEngine()
    plain = engine._eval_vec(_engine_cond(band="middle", cross="above"), df)
    touched = engine._eval_vec(_engine_cond(band="middle", cross="above", touchLookback=10), df)
    close, lb = df["close"].to_numpy(), df["boll_lb"].to_numpy()
    assert touched.sum() < plain.sum()
    assert (touched <= plain).all()
    for i in np.flatnonzero(touched):
        window = slice(max(i - 10, 0), i)
        assert (close[window] <= lb[window]).any()


def test_band_reason_segments():
    engine = SignalEngine()
    segs = engine._base_condition_segments(_engine_cond(band="lower", cross="below"))
    assert segs == [{"t": "종가가 볼린저 밴드 하단 하향 이탈"}]
    segs = engine._base_condition_segments(_engine_cond(band="middle", cross="above", touchLookback=5))
    assert segs[0] == {"t": "최근 {0}거래일 내 하단 터치 후", "a": [5]}
    assert segs[-1] == {"t": "종가가 볼린저 밴드 중심선 상향 돌파"}


# ── 엔진 요청: 레거시는 그대로 ──────────────────────────────────────────────────

def test_legacy_bollinger_request_unchanged():
    """밴드 없는 기존 전략은 요청에 새 키가 실리지 않는다(결과·해시 불변)."""
    cond = _tech_signal_to_condition(TechnicalSignal(indicator="bollinger_bands", signal_type="buy"))
    assert not {"band", "cross", "touchLookback"} & set(cond["params"])


def test_band_bollinger_request_carries_band():
    sig = TechnicalSignal(indicator="bollinger_bands", signal_type="buy", band="middle",
                          cross="above", touch_lookback=10)
    params = _tech_signal_to_condition(sig)["params"]
    assert (params["band"], params["cross"], params["touchLookback"]) == ("middle", "above", 10)


# ── 컴파일러·디컴파일러 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("role,cond,expected", [
    ("entry", _cond("technical.bollinger_upper_breakout"), ("buy", "upper", "above", None)),
    ("exit", _cond("technical.bollinger_lower_touch"), ("sell", "lower", "below", None)),
    ("entry", _cond("technical.bollinger_lower_rebound"), ("buy", "lower", "above", None)),
    ("exit", _cond("technical.bollinger_middle_down"), ("sell", "middle", "below", None)),
    ("exit", _cond("technical.bollinger_upper_fall"), ("sell", "upper", "below", None)),
    ("entry", _cond("technical.bollinger_middle_up"), ("buy", "middle", "above", None)),
    ("entry", _cond("technical.bollinger_middle_recovery", touch_lookback=10), ("buy", "middle", "above", 10)),
])
def test_band_conditions_compile_and_round_trip(role, cond, expected):
    _, sig = _compile_condition(cond, role)
    assert (sig.signal_type, sig.band, sig.cross, sig.touch_lookback) == expected
    back = _decompile_technical(sig)
    assert back.factor == cond.factor
    if cond.parameters.get("touch_lookback"):
        assert back.parameters["touch_lookback"] == cond.parameters["touch_lookback"]


@pytest.mark.parametrize("role,cond", [
    # 레거시 볼린저의 정반대 조합 — 종전에는 조용히 뒤집혔다. 이제 제외+안내.
    ("entry", _cond("technical.bollinger_bands", "crosses_above")),
    ("exit", _cond("technical.bollinger_bands", "crosses_below")),
    # 하단 터치 인정 기간이 없으면(되묻기 대상) 컴파일하지 않는다.
    ("entry", _cond("technical.bollinger_middle_recovery")),
])
def test_unrepresentable_bollinger_raises(role, cond):
    with pytest.raises(StrategyCompileError):
        _compile_condition(cond, role)


@pytest.mark.parametrize("role,op", [("entry", "crosses_below"), ("exit", "crosses_above")])
def test_legacy_bollinger_consistent_direction_still_compiles(role, op):
    """저장된 레거시 전략(디컴파일 표기: 매수=crosses_below, 매도=crosses_above)은 그대로 왕복한다."""
    _, sig = _compile_condition(_cond("technical.bollinger_bands", op), role)
    assert sig.band is None
    assert _decompile_technical(sig).operator == op


# ── 프롬프트 어휘 ────────────────────────────────────────────────────────────────

def test_prompt_vocabulary_offers_band_leaves_and_hides_legacy():
    text = "\n".join(ontology_prompt_sections())
    for leaf in ("technical.bollinger_upper_breakout", "technical.bollinger_upper_fall",
                 "technical.bollinger_middle_up", "technical.bollinger_middle_down",
                 "technical.bollinger_lower_touch", "technical.bollinger_lower_rebound",
                 "technical.bollinger_middle_recovery"):
        assert f"- {leaf} " in text
    assert "- technical.bollinger_bands " not in text


def test_quote_check_line_names_the_band():
    line = render_condition(_cond("technical.bollinger_lower_touch"), "exit_conditions")
    assert line.startswith("매도") and "하단에 닿" in line


# ── 되묻기·칩 ───────────────────────────────────────────────────────────────────

def _middle_recovery_intent(**params):
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 1.0,
        "strategy": {
            "universe": {"markets": ["KOSDAQ"], "sectors": []},
            "entry_conditions": [{
                "factor": "technical.bollinger_middle_recovery", "operator": None, "value": None,
                "parameters": params,
                "source_text": "볼린저밴드 하단을 터치한 뒤 중심선을 회복하는 시점에 매수"}],
            "exit_conditions": [{
                "factor": "technical.bollinger_upper_breakout", "operator": None, "value": None,
                "parameters": {}, "source_text": "상단에 도달하면 매도"}],
        },
    })


def test_missing_touch_lookback_is_asked_and_held_back():
    validated, report = run_validation(_middle_recovery_intent())
    field = "strategy.entry_conditions[0].parameters.touch_lookback"
    assert field in report.missing_fields
    question = next(q for q in report.clarification_questions if q.field == field)
    assert question.recommended_value is None                  # 기본값을 정하지 않는다(사용자 결정)
    assert guard_text(question.question) == question.question  # 규제 가드가 지우지 않는다
    parsed, _, pending = compile_partial(validated, report, None)
    assert not any(s.band == "middle" for s in parsed.entry_signals)  # 값 확정 전 엔진에 보내지 않음
    assert pending


def test_touch_lookback_question_offers_bound_chips():
    from strategy_conversation.primary import _clarification_items

    validated, report = run_validation(_middle_recovery_intent())
    item = next(i for i in _clarification_items(report, validated)
                if any("중심선 회복" in c for c in i["chips"]))
    assert item["chips"] == [strategy_slots.bollinger_touch_chip("entry", n) for n in (5, 10, 20)]


def test_touch_chips_skipped_for_custom_bollinger_period():
    """칩은 기본 기간 신호를 결속하므로, 사용자가 다른 기간을 말했으면 칩 없이 묻는다."""
    from strategy_conversation.primary import _clarification_items

    validated, report = run_validation(_middle_recovery_intent(period=10))
    items = _clarification_items(report, validated)
    assert not any("중심선 회복" in c for i in items for c in i["chips"])


def test_touch_chip_binding_appends_signal_once():
    base = ParsedStrategy(description="볼린저").model_dump()
    chip = strategy_slots.bollinger_touch_chip("entry", 10)
    patch = strategy_slots.bollinger_touch_chip_patch(chip, base)
    assert patch is not None
    sig = patch["entry_signals"][-1]
    assert (sig["band"], sig["cross"], sig["touch_lookback"], sig["signal_type"]) == ("middle", "above", 10, "buy")
    # 결속 결과가 엔진 모델로 그대로 읽힌다.
    ParsedStrategy.model_validate({**base, **patch})
    # 이미 같은 신호가 있으면 바꿀 것이 없다 → 결속 실패(칩 미노출).
    assert strategy_slots.bollinger_touch_chip_patch(chip, {**base, **patch}) is None
    assert strategy_slots.bollinger_touch_chip_patch("손절 -10%", base) is None


# ── 검증기: 표현 불가 조합은 그 조건만 제외+안내 ─────────────────────────────────

def _intent_with(entry, exit_=()):
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 1.0,
        "strategy": {"universe": {"markets": ["KOSPI"], "sectors": []},
                     "entry_conditions": list(entry), "exit_conditions": list(exit_)},
    })


def test_validator_flags_inverted_legacy_bollinger():
    """레거시 볼린저 '상단 돌파 매수'(진입 crosses_above)는 검증 에러 — 전량 컴파일이 전략 전체를
    던지지 않고 이 조건만 제외+안내로 흐른다(이동평균 방향 규칙과 같은 계약)."""
    _, report = run_validation(_intent_with([
        {"factor": "technical.bollinger_bands", "operator": "crosses_above", "value": None,
         "parameters": {}, "source_text": "볼린저밴드 상단을 돌파하면 매수"}]))
    assert any("밴드를 지정하지 않으면" in e for e in report.errors)


def test_validator_accepts_band_leaves():
    _, report = run_validation(_intent_with(
        [{"factor": "technical.bollinger_upper_breakout", "operator": None, "value": None,
          "parameters": {}, "source_text": "상단을 돌파하면 매수"}],
        [{"factor": "technical.bollinger_lower_touch", "operator": None, "value": None,
          "parameters": {}, "source_text": "하단에 닿으면 청산"}]))
    assert not any("볼린저" in e for e in report.errors)


def test_bollinger_leaves_are_same_name_variants_of_legacy():
    """정확히 반영한 '볼린저밴드 상단을 돌파하면서'에 대체(근사) 안내가 붙지 않고, 조건 회수가
    레거시 볼린저를 되살리지 않는다(2026-10-10 실측 120B)."""
    from strategy_conversation.primary import _substituted_factor
    from strategy_conversation.registry import indicator_registry as reg

    cond = _cond("technical.bollinger_upper_breakout")
    cond.source_text = "볼린저밴드 상단을 돌파하면서"
    assert not _substituted_factor(cond, reg.resolve(cond.factor), reg)


def test_condition_recall_does_not_revive_legacy_bollinger():
    from strategy_conversation.interpreter.condition_recall import recover_missing_conditions

    intent = _intent_with(
        [{"factor": "technical.bollinger_upper_breakout", "operator": None, "value": None,
          "parameters": {}, "source_text": "볼린저밴드 상단을 돌파하면서"}],
        [{"factor": "technical.bollinger_lower_touch", "operator": None, "value": None,
          "parameters": {}, "source_text": "하단에 닿으면 청산하고 싶습니다."}])
    user = "KOSPI 종목 중 볼린저밴드 상단을 돌파하면서 거래량도 급증한 종목만 매수하고, 볼린저밴드 하단에 닿으면 청산"
    recovered = recover_missing_conditions(intent, user, chat=None, phrases=["볼린저밴드 하단에 닿으면"])
    assert recovered == []


# ── 형식 위반 재생성: 쪼개진 '하단 터치 후 중심선 회복' ──────────────────────────

def test_split_lower_touch_and_middle_up_is_flagged_for_regeneration():
    """120B 실측(2026-10-10 3/3): 인용 두 조각·조건 두 개로 쪼개면 같은 날 성립할 수 없어 신호가 0이다."""
    from strategy_conversation.interpreter.output_repair import (
        split_bollinger_recovery_error,
        split_bollinger_recovery_fields,
    )

    intent = _intent_with(
        [{"factor": "technical.bollinger_lower_touch", "operator": None, "value": None,
          "parameters": {}, "source_text": "볼린저밴드 하단을 터치한 뒤"},
         {"factor": "technical.bollinger_middle_up", "operator": None, "value": None,
          "parameters": {}, "source_text": "중심선을 회복하는 시점에"}],
        [{"factor": "technical.bollinger_upper_breakout", "operator": None, "value": None,
          "parameters": {}, "source_text": "상단에 도달하면"}])
    paths = split_bollinger_recovery_fields(intent)
    assert paths == ["strategy.entry_conditions[0]", "strategy.entry_conditions[1]"]
    assert "technical.bollinger_middle_recovery" in split_bollinger_recovery_error(paths)


def test_single_bollinger_entry_is_not_flagged():
    from strategy_conversation.interpreter.output_repair import split_bollinger_recovery_fields

    intent = _intent_with([{"factor": "technical.bollinger_middle_recovery", "operator": None,
                            "value": None, "parameters": {}, "source_text": "하단 터치 후 중심선 회복"}])
    assert split_bollinger_recovery_fields(intent) == []


def test_split_bollinger_regenerates_once(monkeypatch):
    """1차 출력이 쪼개져 있으면 같은 레인으로 1회 재생성하고, 재생성본을 쓴다."""
    import json as _json
    from strategy_conversation.interpreter.llm_strategy_interpreter import StrategyInterpreter

    def body(entry):
        return _json.dumps({"intent": "CREATE_STRATEGY", "confidence": 0.9, "strategy": {
            "universe": {"markets": ["KOSDAQ"], "sectors": []},
            "entry_conditions": entry,
            "exit_conditions": [{"factor": "technical.bollinger_upper_breakout", "source_text": "상단에 도달하면"}]}},
            ensure_ascii=False)

    first = body([{"factor": "technical.bollinger_lower_touch", "source_text": "볼린저밴드 하단을 터치한 뒤"},
                  {"factor": "technical.bollinger_middle_up", "source_text": "중심선을 회복하는 시점에"}])
    second = body([{"factor": "technical.bollinger_middle_recovery",
                    "source_text": "볼린저밴드 하단을 터치한 뒤 중심선을 회복하는 시점에 매수"}])
    replies = iter([first, second])
    calls = []

    def fake_chat(system, user, **_):
        calls.append(user)
        return next(replies)

    interpreter = StrategyInterpreter(chat_fn=fake_chat, model="stub-model")
    result = interpreter.interpret(
        "KOSDAQ에서 볼린저밴드 하단을 터치한 뒤 중심선을 회복하는 시점에 매수하고, 상단에 도달하면 매도하고 싶어요.")
    intent = result.intent
    assert len(calls) == 2
    assert result.repair_attempts == 1
    assert [c.factor for c in intent.strategy.entry_conditions] == ["technical.bollinger_middle_recovery"]


def test_invented_upper_touch_leaf_resolves():
    from strategy_conversation.registry.indicator_registry import resolve

    assert resolve("technical.bollinger_upper_touch").id == "technical.bollinger_upper_breakout"
    assert resolve("technical.bollinger_lower_breakout").id == "technical.bollinger_lower_touch"


def test_lower_touch_next_to_middle_recovery_is_flagged():
    """회복 개념이 하단 터치 이력을 이미 품는다 — 옆에 하단 터치를 덧붙이면 같은 날 성립 불가(실측 1/3)."""
    from strategy_conversation.interpreter.output_repair import split_bollinger_recovery_fields

    intent = _intent_with(
        [{"factor": "technical.bollinger_middle_recovery", "operator": None, "value": None,
          "parameters": {}, "source_text": "하단을 터치한 뒤 중심선을 회복하는 시점에"},
         {"factor": "technical.bollinger_lower_touch", "operator": None, "value": None,
          "parameters": {}, "source_text": "볼린저밴드 하단을 터치한 뒤"}])
    assert split_bollinger_recovery_fields(intent) == [
        "strategy.entry_conditions[1]", "strategy.entry_conditions[0]"]


def test_null_value_source_in_patch_value_is_normalized():
    """수정 턴 패치 값의 "value_source": null이 스키마 위반으로 패치 전체를 거부하던 사고(2026-10-10)."""
    import json as _json
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.conversation.patch_applier import apply_patches
    from strategy_conversation.interpreter.models import PatchOp

    spec = decompile_strategy(ParsedStrategy(
        description="t", universe=["KOSPI200"],
        entry_signals=[TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=20)],
        exit_signals=[TechnicalSignal(indicator="ma_crossover", signal_type="sell",
                                      short_period=5, long_period=20)]))
    patch = PatchOp.model_validate({"op": "replace", "path": "/exit_conditions/0", "value": {
        "factor": "technical.bollinger_upper_touch", "operator": None, "value": None,
        "value_source": None, "source_text": "볼린저밴드 상단 닿으면 매도"}})
    new = apply_patches(spec, [patch])
    assert new.exit_conditions[0].value_source == "MISSING"
