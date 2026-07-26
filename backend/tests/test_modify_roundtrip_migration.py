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


def test_etf_theme_strategy_roundtrips_losslessly():
    """ETF 테마 전략의 왕복 — decompiler가 etf_theme을 빠뜨려 '반도체'→None 불일치로
    모든 수정이 레거시 레인에 떨어지던 2026-07-27 '삼성전자 투자 etf' 사고 회귀."""
    from strategy_conversation.compiler.strategy_compiler import compile_strategy
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.interpreter.models import ValidationReport

    prev = materialize_engine_defaults(_prev_cross_strategy(
        universe=["ETF"], etf_theme="반도체", target_symbols=[],
    ))
    spec = decompile_strategy(prev)
    assert spec.universe.etf_theme == "반도체"
    roundtrip = compile_strategy(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=spec, confidence=1.0),
        ValidationReport(is_valid=True, status="READY"),
        prev.description,
    ).model_copy(update={
        "description": prev.description, "entry_filters": prev.entry_filters,
    })
    assert roundtrip.etf_theme == "반도체"
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


def test_modify_turn_replans_next_question_via_dag_planner(monkeypatch):
    """수정 턴 재계획(Phase 4) — 최신 입력은 답변 귀속이 아니라 State 변경 판정이 먼저다.

    '삼성전자 관련 etf를 매수하자'는 매수 조건 답변이 아니라 유니버스(테마) 수정이고,
    다음 질문은 갱신된 State 기준으로 DAG planner가 다시 계획한다(우선순위 마커로
    프론트 고정 게이트 삼킴 방지)."""
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "primary")
    monkeypatch.setattr(
        primary, "_dag_planner_clarification",
        lambda user_input, parsed: ("어떤 조건에서 매수할까요?", ["RSI 30 이하에서 매수"]),
    )
    _stub_interpreter(monkeypatch, StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY",
        "patches": [{"op": "replace", "path": "/universe/etf_theme",
                     "value": "삼성전자", "source_text": "삼성전자 관련 etf를 매수하자"}],
        "confidence": 1.0,
    }))
    prev = _prev_cross_strategy(universe=["ETF"], etf_theme="반도체",
                                target_symbols=[], entry_signals=[], exit_signals=[])
    result = primary.run_primary_modification(
        "삼성전자 관련 etf를 매수하자", prev.model_dump(),
    )
    assert result is not None
    assert result["parsed"].etf_theme == "삼성전자"  # 유니버스 수정 — 매수 조건 아님
    assert result["clarification_question"] == "어떤 조건에서 매수할까요?"
    assert result["clarification_priority"] == "dag_planner"


def test_self_doubt_patch_surfaces_question_instead_of_applying(monkeypatch):
    """자기 의심 패치 게이트 — 인터프리터가 패치 대상 필드에 스스로 질문을 병행하면
    (모델이 해석을 불확실하다고 표시), 패치 적용 대신 그 질문을 표면화한다.
    2026-07-27 사고: '삼성전자 관련 etf'를 KOSPI200으로 재해석 패치+같은 필드 질문 병행
    → 조용히 적용되어 ETF 유니버스 소실."""
    _stub_interpreter(monkeypatch, StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY",
        "patches": [{"op": "replace", "path": "/universe/markets/0",
                     "value": "KOSPI200", "source_text": "삼성전자 관련 etf"}],
        "clarification_questions": [{
            "field": "universe.markets",
            "question": "'삼성전자 관련 ETF'는 지수(KOSPI200)를 뜻하시나요, 테마 ETF를 뜻하시나요?",
        }],
        "confidence": 0.8,
    }))
    prev = _prev_cross_strategy(universe=["ETF"], etf_theme="반도체", target_symbols=[])
    result = primary.run_primary_modification(
        "삼성전자 관련 etf를 매수하자", prev.model_dump(),
    )
    assert result is not None
    assert result["interpreter"]["mode"] == "primary_modify_self_doubt"
    assert result["parsed"].universe == ["ETF"]  # 전략 무변경 — 조용한 오해석 차단
    assert result["parsed"].etf_theme == "반도체"
    assert "삼성전자 관련 ETF" in result["clarification_question"]


def test_theme_scan_never_applies_stocks_to_etf_universe():
    """ETF 단독 유니버스에 테마 관련 '상장사'를 적용하면 주식 유니버스로 조용히
    교체된다(2026-07-27 '삼성전자 관련 etf 매수' → 삼성그룹 상장사 10곳 사고)."""
    from engine.nl_parser import apply_theme_universe

    parsed = ParsedStrategy(description="반도체 etf 전략", universe=["ETF"],
                            etf_theme="반도체")
    assert apply_theme_universe(parsed, "삼성전자 관련 etf 매수") is None
    assert parsed.target_symbols == []


def test_modify_primary_result_not_overridden_by_raw_theme_scan(monkeypatch):
    """인터프리터 primary가 처리한 수정 턴은 원문 테마 스캔을 끈다 — 스캔이 켜져 있으면
    인터프리터의 etf_theme 교체 결과를 apply_theme_universe(원문 '관련' 큐)가 테마
    상장사로 덮어쓴다(같은 사고의 배선 레벨 회귀)."""
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "primary")
    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "llm_first")
    etf_parsed = ParsedStrategy(description="반도체 etf 전략", universe=["ETF"],
                                etf_theme="삼성전자")
    primary_result = {
        "parsed": etf_parsed,
        "clarification_question": "어떤 조건에서 매수할까요?",
        "clarification_suggestions": ["RSI 30 이하에서 매수"],
        "clarification_priority": "dag_planner",
        "notices": [],
        "interpreter": {"mode": "primary_modify"},
    }
    monkeypatch.setattr(primary, "run_primary_modification",
                        lambda *a, **k: dict(primary_result))

    prev = _prev_cross_strategy(universe=["ETF"], etf_theme="반도체",
                                target_symbols=[]).model_dump()
    result = _run_nl_parse(NLParseRequest(prompt="삼성전자 관련 etf 매수",
                                          previous_parsed=prev))
    assert result["parsed"]["universe"] == ["ETF"]
    assert result["parsed"]["etf_theme"] == "삼성전자"
    assert not result["parsed"]["target_symbols"]
    assert result["clarification_priority"] == "dag_planner"


def test_complete_patch_survives_other_slot_completeness_question(monkeypatch):
    """완결된 패치는 다른 슬롯의 완결성 질문 때문에 폐기되지 않는다 — 2026-07-27 사고:
    '최근 3개월 수익률 상위 매수' 랭킹 패치가 수락되고도 리밸런싱 완결성 질문에
    needs_value(전략 무변경)로 묶여 답변이 사라지고 매수 조건을 재질문."""
    _stub_interpreter(monkeypatch, StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY",
        "patches": [{"op": "add", "path": "/ranking/-",
                     "value": {"metric": "return", "lookback_days": 90},
                     "source_text": "최근 3개월 수익률 상위"}],
        "confidence": 1.0,
    }))
    prev = _prev_cross_strategy(universe=["ETF"], etf_theme="반도체", target_symbols=[],
                                entry_signals=[], exit_signals=[])
    result = primary.run_primary_modification(
        "최근 3개월 수익률 상위 매수", prev.model_dump(),
    )
    assert result is not None
    assert result["interpreter"]["mode"] == "primary_modify"
    assert result["parsed"].ranking_metric == "return"  # 답변 보존 — 폐기 금지
    assert result["parsed"].ranking_lookback_days == 90
    assert result["parsed"].universe == ["ETF"]


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
