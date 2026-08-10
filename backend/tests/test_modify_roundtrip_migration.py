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
    _Result.unreflected_numbers = []

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


def test_add_cue_reaches_interpreter_instead_of_raw_regex_shortcut(monkeypatch):
    """2026-08-02 감사 재현: main.py가 request.prompt(원문)에 clarification_for_add
    (regex: '추가/넣/...' cue + detect_metric)를 인터프리터보다 먼저 돌리던 코드가
    있었다 — 재무 팩터를 값 없이 언급하면(예: "영업이익률을 추가해 볼까?") 인터프리터를
    한 번도 호출하지 않고 원문 정규식이 곧장 되묻기를 확정했다(대원칙 1 위반 — 원문이
    "ESS 종목 중에서 거래대금 상위만 넣어줘"처럼 다른 내용과 섞이면 그 내용째 삼켜졌다).
    제거 후에는 값 없는 조건 추가라도 인터프리터가 항상 원문 전체를 먼저 본다."""
    calls = []

    class _Result:
        pass

    class _Interpreter:
        def interpret(self, user_input, **kwargs):
            calls.append(user_input)
            r = _Result()
            r.intent = StrategyIntent.model_validate({
                "intent": "MODIFY_STRATEGY",
                "patches": [{"op": "add", "path": "/entry_conditions/-",
                             "value": {"factor": "fundamental.operating_margin",
                                       "operator": None, "value": None},
                             "source_text": "영업이익률을 추가해 볼까?"}],
                "confidence": 1.0,
            })
            r.model_name = "test"
            r.prompt_version = "test"
            r.repair_attempts = 0
            r.latency_ms = 0.0
            r.unreflected_numbers = []
            return r

    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "primary")
    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "llm_first")
    monkeypatch.setattr(primary, "_get_interpreter", lambda _cls: _Interpreter())
    prompt = "영업이익률을 추가해 볼까?"
    result = _run_nl_parse(NLParseRequest(prompt=prompt, previous_parsed=_prev_cross_strategy().model_dump()))
    assert calls == [prompt], "원문 정규식 가로채기가 인터프리터 호출 전에 응답을 확정하면 안 된다"
    assert result is not None
    assert "영업이익률" in (result.get("clarification_question") or "")


def test_modify_turn_replans_next_question_via_dag_planner(monkeypatch):
    """수정 턴 재계획(Phase 4) — 최신 입력은 답변 귀속이 아니라 State 변경 판정이 먼저다.

    '삼성전자 관련 etf를 매수하자'는 매수 조건 답변이 아니라 유니버스(테마) 수정이고,
    다음 질문은 갱신된 State 기준으로 DAG planner가 다시 계획한다(우선순위 마커로
    프론트 고정 게이트 삼킴 방지)."""
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "primary")
    monkeypatch.setattr(
        primary, "_dag_planner_clarification",
        lambda user_input, parsed, explicit_fields=None, declined_fields=None: (
            "어떤 조건에서 매수할까요?", ["RSI 30 이하에서 매수"], "매수조건",
        ),
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
    # 재계획 질문의 pending_ask — 프론트가 에코해 다음 칩 클릭의 결정론 귀속에 쓴다
    assert result["pending_ask"]["topic"] == "매수조건"
    assert result["pending_ask"]["question"] == "어떤 조건에서 매수할까요?"
    # 재계획 질문의 칩도 planner 문구가 아니라 슬롯 SOT 정본이다(2026-08-02 사용자
    # 결정) — ETF 유니버스이므로 재무 칩(PER·ROE)은 제외된 정본이어야 한다.
    from engine import strategy_slots
    assert result["pending_ask"]["chips"] == strategy_slots.suggestions_for_topic(
        "매수조건", universe=["ETF"])
    assert "PER 10 이하" not in result["pending_ask"]["chips"]
    # 칩=값 결속 — 칩이 뜻하는 값을 발행 시점에 확정해 함께 싣는다(클릭 시 재해석 없음)
    assert result["pending_ask"]["chip_bindings"]["RSI 30 이하에서 매수"][
        "entry_signals"][0]["indicator"] == "rsi"


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


# ── ④ 테마 유니버스 교체 (2026-07-30 "쿠팡 관련주로 수정해줘" 사고 회귀) ─────────
#
# 사고: 토스 관련주 6종목으로 만들어진 전략에 "쿠팡 관려주로 수정해줘"를 넣자 전략이
# 토스 그대로 유지됐다. 원인 3겹 — ① 테마로 종목을 채운 뒤 테마 이름을 지워(sector=None)
# 초안에 "이 종목들이 어디서 왔는지"가 남지 않았고 ② 수정 레인에는 지식 조회(KG) 체인
# 자체가 없어 인터프리터가 종목코드를 직접 알아내야 하는 처지가 됐으며(실제로는 기존
# 코드를 그대로 복사한 무변경 패치를 냈다) ③ 그 결과 나간 되묻기는 우선순위 마커가 없어
# 프론트 설정 게이트("어떤 조건에서 매수할지…")에 덮여 사라졌다.

def _theme_strategy(term: str = "토스(toss)") -> ParsedStrategy:
    from engine.nl_parser import apply_theme_companies

    parsed = _prev_cross_strategy(target_symbols=[])
    assert apply_theme_companies(parsed, term), f"카탈로그에 '{term}' 테마가 있어야 한다"
    return parsed


def test_theme_origin_survives_modify_roundtrip():
    """테마 출처가 초안까지 왕복해야 인터프리터가 테마 교체를 표현할 수 있다."""
    from strategy_conversation.compiler.strategy_compiler import compile_strategy
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.interpreter.models import ValidationReport

    prev = materialize_engine_defaults(_theme_strategy())
    assert prev.theme_universe == "토스(toss)"
    spec = decompile_strategy(prev)
    assert spec.universe.theme == "토스(toss)", "초안에 테마 출처가 실려야 한다"
    roundtrip = compile_strategy(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=spec, confidence=1.0),
        ValidationReport(is_valid=True, status="READY"),
        prev.description,
    ).model_copy(update={
        "description": prev.description, "entry_filters": prev.entry_filters,
    })
    assert roundtrip.model_dump() == prev.model_dump()


def test_theme_replacement_asks_scope_and_keeps_strategy(monkeypatch):
    """테마 교체 패치는 지식 조회 체인으로 넘어가고, 확정 전까지 전략은 무변경이다."""
    _stub_interpreter(monkeypatch, StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY",
        "patches": [{"op": "replace", "path": "/universe/sectors",
                     "value": ["쿠팡"], "source_text": "쿠팡 관려주로"}],
        "confidence": 0.8,
    }))
    prev = _theme_strategy()
    result = primary.run_primary_modification("쿠팡 관려주로 수정해줘", prev.model_dump())
    assert result is not None
    assert result["interpreter"]["mode"] == "primary_modify_theme_ask"
    # 카탈로그 정본 표기를 칩으로 제시하고 확인받는다(생성 경로와 같은 계약 — 자동 확정 금지)
    assert result["clarification_suggestions"] == ["쿠팡(coupang)"]
    assert result["pending_ask"]["topic"] == "유니버스"
    # 확정 전까지 전략은 이전 테마 그대로 — 조용한 오해석도, 조용한 소실도 없다
    assert result["parsed"].theme_universe == "토스(toss)"
    assert result["parsed"].target_symbols == prev.target_symbols
    # 유니버스 범위 질문은 조건 질문보다 선행 — 프론트 게이트가 삼키지 않게 마커를 단다
    assert result["clarification_priority"] == "sector_unresolved"


def test_theme_scope_chip_replaces_only_theme_origin_symbols():
    """범위 칩 클릭은 이전 **테마에서 온** 종목만 새 테마의 상장사로 교체한다."""
    prev = _theme_strategy()
    result = primary.run_chip_answer(
        "쿠팡(coupang)", prev.model_dump(),
        {"topic": "유니버스", "question": "이 범위로 바꿀까요?", "chips": ["쿠팡(coupang)"]},
    )
    assert result is not None
    parsed = result["parsed"]
    assert parsed.theme_universe == "쿠팡(coupang)"
    assert set(parsed.target_symbols) != set(prev.target_symbols)
    assert len(parsed.target_symbols) > len(prev.target_symbols)


def test_market_only_patch_filters_theme_symbols(monkeypatch):
    """[회귀 2026-08-02] 테마 지정 종목 전략에 "코스피에만 속한 종목으로 변경" —
    시장 패치는 검증을 통과해도 지정 종목 모드에선 실행에 반영되지 않아(변환기가
    target_symbols 우선) 무변경으로 끝났다. 패치 적용 후 테마 유래 종목을 종목
    마스터 정본 소속으로 결정론 필터링한다(삼성전자=KOSPI 유지, 고영=KOSDAQ 제외)."""
    _stub_interpreter(monkeypatch, StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY",
        "patches": [{"op": "replace", "path": "/universe/markets",
                     "value": ["KOSPI"],
                     "source_text": "코스피에만 속한 종목으로 변경"}],
        "confidence": 1.0,
    }))
    prev = _prev_cross_strategy(
        universe=["KOSPI", "KOSDAQ"],
        target_symbols=["005930", "098460"], theme_universe="HBM",
    )
    result = primary.run_primary_modification(
        "코스피에만 속한 종목으로 변경 할 수 있나?", prev.model_dump(),
    )
    assert result is not None
    assert result["interpreter"]["mode"] == "primary_modify"
    parsed = result["parsed"]
    assert parsed.universe == ["KOSPI"]
    assert parsed.target_symbols == ["005930"]
    assert parsed.theme_universe == "HBM"  # 출처 보존 — 이후 테마 교체 판정 근거
    # 되돌리기 근거 — 이 턴이 바꾼 필드에 종목 목록도 포함된다
    assert "target_symbols" in result["changed_fields"]


def test_market_switch_rederives_from_full_theme(monkeypatch):
    """[회귀 2026-08-02 2차] 코스피로 좁힌 테마 전략에 "코스닥 종목만" — 현재 목록엔
    코스닥이 0곳이므로 테마 전체 구성에서 코스닥 소속으로 다시 좁힌다(무변경 금지)."""
    import engine.knowledge_graph as kg

    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: {
        "term": "HBM",
        "companies": [
            {"symbol": "005930", "name": "삼성전자", "support": 1, "first_known_date": None},
            {"symbol": "098460", "name": "고영", "support": 1, "first_known_date": None},
            {"symbol": "348210", "name": "넥스틴", "support": 1, "first_known_date": None},
        ],
        "first_known_date": None,
    })
    _stub_interpreter(monkeypatch, StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY",
        "patches": [{"op": "replace", "path": "/universe/markets",
                     "value": ["KOSDAQ"],
                     "source_text": "코피닥 종목만 선택"}],
        "confidence": 1.0,
    }))
    prev = _prev_cross_strategy(
        universe=["KOSPI"], target_symbols=["005930"], theme_universe="HBM",
    )
    result = primary.run_primary_modification(
        "미안해 코피닥 종목만 선택 해줘", prev.model_dump(),
    )
    assert result is not None
    parsed = result["parsed"]
    assert parsed.universe == ["KOSDAQ"]
    assert parsed.target_symbols == ["098460", "348210"]  # 테마 전체의 코스닥 소속
    assert parsed.theme_universe == "HBM"


def test_unmet_market_constraint_keeps_strategy_and_notifies(monkeypatch):
    """[회귀 2026-08-02 2차] 테마 전체에도 해당 시장 종목이 없으면 — universe 패치까지
    되돌려 전략을 원상 유지하고, 반영하지 못했음을 안내한다(침묵 금지: universe만
    뒤집힌 채 무안내로 끝나 오타 미해석으로 오인되던 사고)."""
    import engine.knowledge_graph as kg

    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: {
        "term": "HBM",
        "companies": [
            {"symbol": "005930", "name": "삼성전자", "support": 1, "first_known_date": None},
        ],
        "first_known_date": None,
    })
    _stub_interpreter(monkeypatch, StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY",
        "patches": [{"op": "replace", "path": "/universe/markets",
                     "value": ["KOSDAQ"],
                     "source_text": "코스닥 종목만 선택"}],
        "confidence": 1.0,
    }))
    prev = _prev_cross_strategy(
        universe=["KOSPI"], target_symbols=["005930"], theme_universe="HBM",
    )
    result = primary.run_primary_modification(
        "코스닥 종목만 선택 해줘", prev.model_dump(),
    )
    assert result is not None
    parsed = result["parsed"]
    assert parsed.universe == ["KOSPI"]  # 시장 패치 원상 복구 — 반쪽 상태 금지
    assert parsed.target_symbols == ["005930"]
    assert any("반영하지 못했어요" in n and "유지했어요" in n for n in result["notices"])


def test_theme_replacement_never_touches_user_specified_symbols():
    """사용자가 직접 지목한 종목은 테마 교체가 건드리지 않는다(기존 가드 유지)."""
    from engine.nl_parser import replace_theme_universe

    parsed = _prev_cross_strategy()  # target_symbols=삼성전자·SK하이닉스, 테마 출처 없음
    assert replace_theme_universe(parsed, "쿠팡(coupang)") is None
    assert parsed.target_symbols == ["005930", "000660"]
    assert parsed.theme_universe is None


def test_failed_theme_replacement_restores_previous_theme():
    """새 테마 조회가 실패하면 기존 테마 종목을 잃지 않는다(원상복구)."""
    from engine.nl_parser import replace_theme_universe

    parsed = _theme_strategy()
    before = list(parsed.target_symbols)
    assert replace_theme_universe(parsed, "존재하지않는테마xyz") is None
    assert parsed.target_symbols == before
    assert parsed.theme_universe == "토스(toss)"


def test_unapplied_modify_clarification_carries_priority_marker(monkeypatch):
    """전략 무변경 되묻기는 우선순위 마커를 달고 나간다 — 프론트 설정 게이트가
    자기 질문으로 덮어쓰면 '요청이 반영되지 않았다'는 사실이 화면에서 사라진다."""
    _stub_interpreter(monkeypatch, StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY",
        "patches": [{"op": "replace", "path": "/universe/markets/0",
                     "value": "KOSPI200", "source_text": "삼성전자 관련 etf"}],
        "clarification_questions": [{
            "field": "universe.markets",
            "question": "'삼성전자 관련 ETF'는 지수를 뜻하시나요, 테마 ETF를 뜻하시나요?",
        }],
        "confidence": 0.8,
    }))
    prev = _prev_cross_strategy(universe=["ETF"], etf_theme="반도체", target_symbols=[])
    result = primary.run_primary_modification(
        "삼성전자 관련 etf를 매수하자", prev.model_dump(),
    )
    assert result["interpreter"]["mode"] == "primary_modify_self_doubt"
    assert result["clarification_priority"] == "modify_unapplied"


# ── § 7 CONFIRM: 추천값 수락(자유 서술 레인) ────────────────────────────────────
# CONFIRM_RECOMMENDATION은 IntentType·프롬프트에는 있었지만 어디서도 처리되지 않아,
# "응 그걸로 해줘"가 patches 없는 의도로 떨어져 "해석하지 못했어요"로 끝났다.

def _confirm_intent() -> StrategyIntent:
    return StrategyIntent.model_validate(
        {"intent": "CONFIRM_RECOMMENDATION", "patches": [], "confidence": 1.0})


def test_confirmation_promotes_the_asked_field_without_changing_the_value(monkeypatch):
    """확정 대상은 LLM에 묻지 않는다 — 직전 질문(pending_ask.topic)이 결정론으로 정한다."""
    _stub_interpreter(monkeypatch, _confirm_intent())
    prev = ParsedStrategy.model_validate({"description": "테스트 전략"})
    result = primary.run_primary_modification(
        "응 그걸로 해줘", prev.model_dump(),
        previous_explicit_fields=["universe"],
        pending_ask={"topic": "최대 보유", "question": "몇 종목?", "chips": ["최대 5종목"]},
    )
    assert result is not None
    assert result["interpreter"]["mode"] == "primary_modify_confirm"
    assert result["parsed"].max_positions == prev.max_positions
    assert result["explicit_fields"] == ["universe", "max_positions"]


def test_confirmation_without_a_prior_question_does_not_guess_a_field(monkeypatch):
    """무엇을 확정했는지 알 수 없으면 임의로 고르지 않고 기존 경로로 넘긴다."""
    _stub_interpreter(monkeypatch, _confirm_intent())
    prev = ParsedStrategy.model_validate({"description": "테스트 전략"})
    assert primary.run_primary_modification(
        "응 그걸로 해줘", prev.model_dump(), pending_ask=None) is None
    # 확정 가능 슬롯이 아닌 질문(매수 조건)도 마찬가지 — 확정할 스칼라 기본값이 없다.
    assert primary.run_primary_modification(
        "응 그걸로 해줘", prev.model_dump(),
        pending_ask={"topic": "매수 조건", "question": "?", "chips": []}) is None


# ── 유니버스 확인 질문이 무응답으로 소멸하면 안내한다(2026-08-02 감사 #2) ─────────

def test_unresolved_universe_ask_is_flagged_when_topic_shifts_without_change():
    """직전 턴이 유니버스 확인('ESS로 바꿀까요?')을 물었는데 이번 턴이 그와 무관한
    화제(매도조건)로 넘어가고 유니버스 필드가 전혀 안 바뀌면, 그 확인이 조용히
    사라졌다는 사실을 notices로 알려야 한다 — dag.py의 NodeStatus.INVALIDATED는
    trace 관측에만 쓰이고 사용자 응답에는 닿지 않던 공백의 최소 보정."""
    prev = _theme_strategy().model_dump()
    request = NLParseRequest(
        prompt="RSI 30 이하에서 매수",
        previous_parsed=prev,
        pending_ask={"topic": "유니버스",
                     "question": "'ESS' 관련주는 '전력저장장치(ESS)' 테마로 정리되어 있어요. "
                                  "이 범위로 바꿀까요?",
                     "chips": ["전력저장장치(ESS)"]},
    )
    result = {
        "parsed": dict(prev),  # 유니버스 관련 필드 무변화
        "pending_ask": {"topic": "매도조건", "question": "어떤 조건에서 매도할까요?",
                         "chips": ["20일 보유 후 청산"]},
        "notices": [],
    }
    main._flag_unresolved_universe_ask(result, request)
    assert any("ESS" in n and "바뀌지 않았어요" in n for n in result["notices"])


def test_universe_ask_not_flagged_when_universe_actually_changed():
    """유니버스가 실제로 바뀌었으면(확인이 다른 방식으로 반영됐어도) 안내하지 않는다."""
    prev = _theme_strategy().model_dump()
    request = NLParseRequest(
        prompt="ESS로 바꿔줘 확정",
        previous_parsed=prev,
        pending_ask={"topic": "유니버스", "question": "이 범위로 바꿀까요?",
                     "chips": ["전력저장장치(ESS)"]},
    )
    changed = dict(prev)
    changed["theme_universe"] = "전력저장장치(ESS)"
    result = {"parsed": changed, "pending_ask": None, "notices": []}
    main._flag_unresolved_universe_ask(result, request)
    assert result["notices"] == []


def test_universe_ask_not_flagged_when_still_the_open_question():
    """다음 턴도 여전히 유니버스 질문이면(정상 재질문) 안내하지 않는다."""
    prev = _theme_strategy().model_dump()
    request = NLParseRequest(
        prompt="음...",
        previous_parsed=prev,
        pending_ask={"topic": "유니버스", "question": "이 범위로 바꿀까요?",
                     "chips": ["전력저장장치(ESS)"]},
    )
    result = {
        "parsed": dict(prev),
        "pending_ask": {"topic": "유니버스", "question": "이 범위로 바꿀까요?",
                         "chips": ["전력저장장치(ESS)"]},
        "notices": [],
    }
    main._flag_unresolved_universe_ask(result, request)
    assert result["notices"] == []
