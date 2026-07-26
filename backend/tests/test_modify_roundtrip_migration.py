"""수정 이관 라운드트립 정규화 + 레거시 수정 폴백 제거 (2026-07-26 사고 회귀).

사고: "제주반도체 종목도 추가해줘"가 라운드트립 가드에 막혀(기간 None인 골든크로스를
왕복이 Registry 표준값 20/60으로 채워 '표현 불가'로 오폭) 레거시 레인으로 떨어졌고,
레거시 결정론은 추가/교체를 구분하지 않으므로(계약상 LLM 소유) 유니버스가 언급 종목
하나로 교체됐다. 수정 2겹:
① 엔진 실효값 정규화(materialize_engine_defaults) — None 파라미터를 엔진이 어차피
   쓰는 값(ma 5/20 등)으로 명시 채워 의미 불변으로 라운드트립을 성립시킨다
② llm_first에서 레거시 수정 폴백 제거 — 인터프리터가 처리 못 하면 전략 보존+되묻기
   (FR-STR-019h), 원문 regex 해석 레인으로 절대 떨어지지 않는다
"""

import pytest

import main
from engine.nl_parser import ParsedStrategy, TechnicalSignal
from main import NLParseRequest, _run_nl_parse
from strategy_conversation import primary
from strategy_conversation.compiler.engine_defaults import materialize_engine_defaults
from strategy_conversation.interpreter.models import StrategyIntent


@pytest.fixture(autouse=True)
def _clean_cache():
    main._nl_parse_cache.clear()
    yield
    main._nl_parse_cache.clear()


def _prev_cross_strategy(**overrides) -> ParsedStrategy:
    """기간 없는 골든/데드크로스 + 지정 종목 2개(사고 당시 전략의 최소 재현)."""
    base = dict(
        description="골든크로스 매수, 데드크로스 매도",
        entry_signals=[TechnicalSignal(indicator="ma_crossover", signal_type="buy")],
        exit_signals=[TechnicalSignal(indicator="ma_crossover", signal_type="sell")],
        target_symbols=["005930", "000660"],
        stop_loss_pct=15.0,
        take_profit_pct=30.0,
    )
    base.update(overrides)
    return ParsedStrategy(**base)


# ── ① 엔진 실효값 정규화 ──────────────────────────────────────────────────────

def test_materialize_fills_engine_effective_values_only_for_none():
    parsed = _prev_cross_strategy()
    out = materialize_engine_defaults(parsed)
    # 엔진 실효값(signals.py 기본값)이지 Registry 표준값(20/60)이 아니다
    assert (out.entry_signals[0].short_period, out.entry_signals[0].long_period) == (5, 20)
    assert (out.exit_signals[0].short_period, out.exit_signals[0].long_period) == (5, 20)


def test_materialize_never_touches_explicit_values():
    parsed = _prev_cross_strategy(entry_signals=[
        TechnicalSignal(indicator="ma_crossover", signal_type="buy",
                        short_period=10, long_period=50),
    ])
    out = materialize_engine_defaults(parsed)
    assert (out.entry_signals[0].short_period, out.entry_signals[0].long_period) == (10, 50)


def test_materialize_excludes_ema_mode_switch_hazard():
    # ema 듀얼 크로스 기간 None은 엔진이 가격-EMA 모드로 동작을 전환하므로 채우지 않는다
    parsed = _prev_cross_strategy(entry_signals=[
        TechnicalSignal(indicator="ema", signal_type="buy"),
    ])
    out = materialize_engine_defaults(parsed)
    assert out.entry_signals[0].short_period is None


def test_normalized_strategy_roundtrips_losslessly():
    """정규화 후에는 decompile→compile 왕복이 원본과 일치한다(가드 통과)."""
    from strategy_conversation.compiler.strategy_compiler import compile_strategy
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.interpreter.models import ValidationReport

    prev = materialize_engine_defaults(_prev_cross_strategy())
    spec = decompile_strategy(prev)
    roundtrip = compile_strategy(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=spec, confidence=1.0),
        ValidationReport(is_valid=True, status="READY"),
        prev.description,
    ).model_copy(update={
        "description": prev.description, "entry_filters": prev.entry_filters,
    })
    assert roundtrip.model_dump() == prev.model_dump()


# ── ② 사고 재현: 종목 추가가 LLM 레인에서 합집합으로 처리된다 ─────────────────

def _stub_interpreter(monkeypatch, intent: StrategyIntent):
    class _Result:
        pass

    _Result.intent = intent
    _Result.model_name = "test"
    _Result.prompt_version = "test"
    _Result.repair_attempts = 0
    _Result.latency_ms = 0.0

    class _Interpreter:
        def interpret(self, *_a, **_k):
            return _Result()

    monkeypatch.setattr(primary, "_get_interpreter", lambda _cls: _Interpreter())


def test_symbol_add_reaches_llm_lane_and_unions(monkeypatch):
    _stub_interpreter(monkeypatch, StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY",
        "patches": [{"op": "add", "path": "/universe/symbols/-",
                     "value": "제주반도체",
                     "source_text": "제주반도체 종목도 추가해줘"}],
        "confidence": 1.0,
    }))
    result = primary.run_primary_modification(
        "제주반도체 종목도 추가해줘", _prev_cross_strategy().model_dump(),
    )
    assert result is not None, "라운드트립 가드가 정규화된 전략을 거부하면 안 된다"
    assert result["interpreter"]["mode"] == "primary_modify"
    # 기존 지정 종목이 보존되고 제주반도체(080220)가 **추가**된다 — 교체 아님
    assert result["parsed"].target_symbols == ["005930", "000660", "080220"]


# ── ③ llm_first 레거시 수정 폴백 제거 ────────────────────────────────────────

def test_llm_first_modify_never_falls_back_to_legacy_lane(monkeypatch):
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "primary")
    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "llm_first")
    monkeypatch.setattr(primary, "run_primary_modification", lambda *a, **k: None)

    prev = _prev_cross_strategy().model_dump()
    result = _run_nl_parse(NLParseRequest(prompt="종목을 좀 바꿔줘", previous_parsed=prev))
    # 레거시 레인(원문 regex 해석)이 아니라 전략 보존+되묻기로 끝난다
    assert result["clarification_priority"] == "interpretation_failed"
    assert result["parsed"]["target_symbols"] == ["005930", "000660"]


def test_fast_path_first_rollback_keeps_legacy_lane(monkeypatch):
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "primary")
    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "fast_path_first")
    monkeypatch.setattr(primary, "run_primary_modification", lambda *a, **k: None)

    prev = _prev_cross_strategy().model_dump()
    result = _run_nl_parse(NLParseRequest(prompt="손절 10%로 바꿔줘", previous_parsed=prev))
    # 롤백 모드에서는 레거시 결정적 수정이 그대로 동작한다
    assert result.get("clarification_priority") != "interpretation_failed"
    assert result["parsed"]["stop_loss_pct"] == 10.0
