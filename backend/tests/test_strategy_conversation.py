"""strategy_conversation (LLM-first 전략 대화 아키텍처 Phase 1) 유닛 테스트.

LLM 없이 결정론 계층을 검증한다: StrategyIntent 스키마·드리프트 복구, Registry,
검증 파이프라인(capability/parameter/conflict/completeness), 컴파일러,
JSON Patch 적용기, 출력 복구 루프(스텁 LLM), Shadow 러너.
"""

import json
import os

import pytest

from strategy_conversation.compiler.strategy_compiler import (
    StrategyCompileError,
    compile_strategy,
)
from strategy_conversation.conversation.patch_applier import PatchError, apply_patches
from strategy_conversation.conversation.strategy_draft import DraftStore
from strategy_conversation.interpreter.llm_strategy_interpreter import (
    InterpreterError,
    StrategyInterpreter,
)
from strategy_conversation.interpreter.models import (
    PatchOp,
    StrategyIntent,
    StrategySpec,
)
from strategy_conversation.interpreter.output_repair import extract_json_object
from strategy_conversation.registry.indicator_registry import REGISTRY, resolve
from strategy_conversation.validation.pipeline import run_validation


def _full_intent_dict(**strategy_overrides):
    strategy = {
        "universe": {"markets": ["KOSPI"], "sectors": []},
        "entry_conditions": [
            {"factor": "fundamental.per", "operator": "<=", "value": 10,
             "source_text": "PER 10 이하"}
        ],
        "exit_conditions": [],
        "ranking": [],
        "portfolio": {"selection_count": 20, "rebalance_frequency": "monthly"},
        "risk_management": {"stop_loss": 8},
        "backtest": {},
    }
    strategy.update(strategy_overrides)
    return {
        "intent": "CREATE_STRATEGY",
        "status": "READY",
        "confidence": 0.9,
        "strategy": strategy,
    }


# ─── 모델: 4B 스키마 드리프트 복구 ────────────────────────────────────────────

def test_condition_value_string_percent_coerced():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "fundamental.operating_margin", "operator": ">=",
                           "value": "10%"}],
    ))
    assert intent.strategy.entry_conditions[0].value == 10.0


def test_confidence_percent_scale_normalized():
    data = _full_intent_dict()
    data["confidence"] = 90
    assert StrategyIntent.model_validate(data).confidence == 0.9


def test_universe_korean_market_names_normalized():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        universe={"markets": ["코스피", "코스닥"], "sectors": []},
    ))
    assert intent.strategy.universe.markets == ["KOSPI", "KOSDAQ"]


def test_missing_value_marked_missing_source():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "fundamental.per", "operator": "<=", "value": None}],
    ))
    assert intent.strategy.entry_conditions[0].value_source == "MISSING"


def test_risk_negative_ratio_normalized_to_abs():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        risk_management={"stop_loss": -8},
    ))
    assert intent.strategy.risk_management.stop_loss == 8.0


def test_string_clarification_questions_promoted():
    data = _full_intent_dict()
    data["clarification_questions"] = ["기준값을 얼마로 할까요?"]
    intent = StrategyIntent.model_validate(data)
    assert intent.clarification_questions[0].question == "기준값을 얼마로 할까요?"


def test_dict_assumptions_coerced_to_strings():
    # 실측 드리프트(2026-07-16): 4B가 assumptions에 {"text": ..., "field": ...} 출력
    data = _full_intent_dict()
    data["assumptions"] = [{"text": "저평가=PER 해석", "field": "entry_conditions"}, "문자열 가정"]
    intent = StrategyIntent.model_validate(data)
    assert intent.assumptions == ["저평가=PER 해석", "문자열 가정"]


def test_factorless_condition_dropped():
    # 실측 드리프트(2026-07-16): 미지원 개념을 factor=null 조건 껍데기로 출력
    data = _full_intent_dict(
        entry_conditions=[
            {"factor": None, "operator": ">=", "value": None},
            {"factor": "fundamental.per", "operator": "<=", "value": 10},
        ],
    )
    data["unsupported_features"] = ["FCF Yield"]
    intent = StrategyIntent.model_validate(data)
    assert len(intent.strategy.entry_conditions) == 1
    assert intent.strategy.entry_conditions[0].factor == "fundamental.per"
    assert intent.unsupported_features == ["FCF Yield"]


def test_mirrored_valueless_exit_conditions_dropped():
    # 실측 드리프트(2026-07-20): 진입 조건(PER<=10, RSI)을 임계값 없이 청산 조건에 그대로
    # 복제해 출력 → 사용자가 진입에서 이미 준 PER 값을 "청산 조건의 PER 기준값?"이라며
    # 되묻던 사고. 값 없이 진입 팩터를 중복하는 청산 조건은 버린다.
    data = _full_intent_dict(
        entry_conditions=[
            {"factor": "fundamental.per", "operator": "<=", "value": 10},
            {"factor": "technical.rsi", "operator": "<=", "value": 30},
        ],
        exit_conditions=[
            {"factor": "fundamental.per", "operator": "<=", "value": None},
            {"factor": "technical.rsi", "operator": None, "value": None},
        ],
    )
    intent = StrategyIntent.model_validate(data)
    assert intent.strategy.exit_conditions == []
    _, report = run_validation(intent)
    assert not any(
        q.field.startswith("strategy.exit_conditions")
        for q in report.clarification_questions
    )


def test_opposite_event_exit_survives_mirror_guard():
    """골든크로스 진입 / 데드크로스 청산은 정당한 짝이다 — 미러 가드가 삼키면 안 된다.

    A/B 실측(2026-07-26): 이 가드가 청산을 삼키고 `_apply_prompt_overrides`의 원문
    재추출이 그것을 가리고 있었다. 보정을 끄면 '데드크로스 매도'가 소실됐다.
    """
    data = _full_intent_dict(
        entry_conditions=[
            {"factor": "technical.ma_crossover", "operator": "crosses_above",
             "value": None, "parameters": {"short_period": 20, "long_period": 60}},
        ],
        exit_conditions=[
            {"factor": "technical.ma_crossover", "operator": "crosses_below",
             "value": None, "parameters": {"short_period": 20, "long_period": 60}},
        ],
    )
    intent = StrategyIntent.model_validate(data)
    assert [c.operator for c in intent.strategy.exit_conditions] == ["crosses_below"]


def test_same_direction_event_exit_still_dropped():
    """같은 방향 이벤트 복제는 새 정보가 없으므로 기존대로 버린다(가드 완화의 경계)."""
    data = _full_intent_dict(
        entry_conditions=[
            {"factor": "technical.bollinger_bands", "operator": "crosses_above", "value": None},
        ],
        exit_conditions=[
            {"factor": "technical.bollinger_bands", "operator": "crosses_above", "value": None},
        ],
    )
    intent = StrategyIntent.model_validate(data)
    assert intent.strategy.exit_conditions == []


def test_valued_exit_condition_preserved():
    # 사용자가 청산 임계값을 실제로 준 경우(RSI>=70 매도)는 진입에 RSI가 있어도 보존한다.
    data = _full_intent_dict(
        entry_conditions=[{"factor": "technical.rsi", "operator": "<=", "value": 30}],
        exit_conditions=[{"factor": "technical.rsi", "operator": ">=", "value": 70}],
    )
    intent = StrategyIntent.model_validate(data)
    assert len(intent.strategy.exit_conditions) == 1
    assert intent.strategy.exit_conditions[0].value == 70


def test_modify_without_draft_coerced_to_create():
    # 실측 드리프트(2026-07-16): 초안 없는 단문 서술을 MODIFY_STRATEGY로 오분류
    data = _full_intent_dict()
    data["intent"] = "MODIFY_STRATEGY"
    raw = json.dumps(data, ensure_ascii=False)
    result = StrategyInterpreter(chat_fn=lambda s, u: raw, model="stub").interpret("PER 10 이하")
    assert result.intent.intent == "CREATE_STRATEGY"


def test_ready_report_has_no_leftover_questions():
    # 실측 드리프트(2026-07-16): READY인데 LLM 잉여 질문(전략 이름 등) 누출
    data = _full_intent_dict()
    data["clarification_questions"] = [
        {"field": "strategy.name", "question": "이 전략에 이름을 붙여야 하나요?"}
    ]
    _, report = run_validation(StrategyIntent.model_validate(data))
    assert report.is_valid
    assert report.clarification_questions == []


def test_llm_noise_questions_dropped_when_deterministic_exist():
    # 실측(2026-07-16): 4B가 "손절 기준?"·"비중 방식?" 등 선택 필드 잉여 질문을 관성 출력 —
    # 결정론 검증이 지적한 누락과 교차 확인된 질문만 채택한다
    data = _full_intent_dict(
        entry_conditions=[{"factor": "fundamental.operating_margin", "operator": ">=",
                           "value": None}],
    )
    data["clarification_questions"] = [
        {"field": "strategy.risk_management.stop_loss", "question": "손절 기준을 몇 %로?"},
    ] + [
        {"field": f"strategy.custom_{i}", "question": f"질문{i}?"} for i in range(4)
    ]
    _, report = run_validation(StrategyIntent.model_validate(data))
    assert not report.is_valid
    fields = {q.field for q in report.clarification_questions}
    assert "strategy.entry_conditions[0].value" in fields
    assert "strategy.risk_management.stop_loss" not in fields
    assert len(report.clarification_questions) <= 3


def test_llm_self_generated_questions_never_shown_uncorroborated():
    # 사고(2026-07-17): "이 전략에 이름을 붙여드릴까요?" 류 LLM 잉여 질문 노출 —
    # 결정론 검증이 지적한 누락 필드와 일치하지 않는 LLM 질문은 절대 노출하지 않는다.
    # 완결된 전략(READY)이면 질문 자체가 비워진다.
    data = _full_intent_dict()
    data["status"] = "NEEDS_CLARIFICATION"  # LLM이 스스로 모호하다고 주장해도
    data["clarification_questions"] = [
        {"field": "strategy.name", "question": "이 전략에 이름을 붙여드릴까요?"},
        {"field": "", "question": "요청을 정확히 이해했는지 확인해 주시겠어요?"},
    ]
    _, report = run_validation(StrategyIntent.model_validate(data))
    assert report.status == "READY"
    assert report.clarification_questions == []


def test_recommended_value_list_coerced_to_string():
    # 실측 드리프트(2026-07-16): 유니버스 질문 추천값에 ["KOSPI","KOSDAQ"] 리스트 출력
    data = _full_intent_dict()
    data["clarification_questions"] = [
        {"field": "strategy.universe.markets", "question": "어느 시장으로 할까요?",
         "recommended_value": ["KOSPI", "KOSDAQ"]}
    ]
    intent = StrategyIntent.model_validate(data)
    assert intent.clarification_questions[0].recommended_value == "KOSPI, KOSDAQ"


def test_backtest_period_days_mapped_to_bucket():
    # 실측 드리프트(2026-07-16): "10년간" → period=1080(일수) 숫자 출력
    for days, expected in ((300, "1y"), (1080, "3y"), (1825, "5y"), (3650, "full")):
        intent = StrategyIntent.model_validate(_full_intent_dict(
            backtest={"period": days},
        ))
        assert intent.strategy.backtest.period == expected, days


def test_ranking_condition_moved_out_of_entry():
    # 실측 드리프트(2026-07-16): 랭킹을 ranking 배열과 entry 조건에 중복 출력
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "ranking.return", "operator": ">=", "value": None}],
        ranking=[{"metric": "ranking.return", "lookback_days": 60}],
    ))
    validated, report = run_validation(intent)
    assert validated.strategy.entry_conditions == []
    assert len(validated.strategy.ranking) == 1
    assert report.is_valid, (report.errors, report.missing_fields)


def test_ranking_only_condition_promoted_to_ranking():
    # ranking 배열 없이 entry 조건으로만 출력한 경우 → 랭킹으로 승격
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "ranking.return", "operator": ">=", "value": None,
                           "parameters": {"lookback_days": 90}}],
        ranking=[],
    ))
    validated, report = run_validation(intent)
    assert validated.strategy.entry_conditions == []
    assert validated.strategy.ranking[0].lookback_days == 90


# ─── Registry ────────────────────────────────────────────────────────────────

def test_registry_resolves_aliases():
    assert resolve("PER").id == "fundamental.per"
    assert resolve("주가수익비율").id == "fundamental.per"
    assert resolve("골든크로스").id == "technical.ma_crossover"
    assert resolve("fundamental.roe_or_gpa").id == "fundamental.roe_or_gpa"


def test_registry_unsupported_and_unknown():
    assert resolve("FCF").supported == "UNSUPPORTED"
    assert resolve("존재하지않는지표") is None


def test_registry_resolves_new_negative_handling_metrics():
    """음수 재무데이터 처리 업그레이드로 추가된 5개 지표(EV/EBIT, EPS/EBITDA/영업현금흐름/
    잉여현금흐름 증가율)가 Registry에 정상 등록되어 있는지 확인."""
    assert resolve("EV/EBIT").id == "fundamental.ev_ebit"
    assert resolve("eps_growth").id == "fundamental.eps_growth"
    assert resolve("ebitda_growth").id == "fundamental.ebitda_growth"
    assert resolve("영업현금흐름증가율").id == "fundamental.ocf_growth"
    assert resolve("잉여현금흐름증가율").id == "fundamental.fcf_growth"
    # FCF 배율(밸류에이션 비율)은 여전히 미지원 — raw FCF 증가율만 지원 범위
    assert resolve("fcf_yield").supported == "UNSUPPORTED"


def test_registry_matches_engine_literals():
    # Registry의 엔진 바인딩이 실제 엔진 스키마 Literal과 어긋나지 않는지 (드리프트 가드)
    from engine.nl_parser import FundamentalFilter, TechnicalSignal

    fund_literals = set(
        FundamentalFilter.model_fields["metric"].annotation.__args__
    )
    tech_literals = set(
        TechnicalSignal.model_fields["indicator"].annotation.__args__
    )
    for spec in REGISTRY.values():
        if spec.engine_binding is None:
            continue
        kind, key = spec.engine_binding
        if kind == "fundamental_filter":
            assert key in fund_literals, f"{spec.id} → 엔진에 없는 metric {key}"
        elif kind == "technical_signal":
            assert key in tech_literals, f"{spec.id} → 엔진에 없는 indicator {key}"


# ─── 검증 파이프라인 ──────────────────────────────────────────────────────────

def test_valid_complete_strategy_is_ready():
    intent = StrategyIntent.model_validate(_full_intent_dict())
    validated, report = run_validation(intent)
    assert report.status == "READY"
    assert report.is_valid


def test_unknown_factor_rejected():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "미지의지표", "operator": ">=", "value": 1}],
    ))
    _, report = run_validation(intent)
    assert not report.is_valid
    assert "미지의지표" in report.unsupported_features


def test_unsupported_factor_suggests_alternative_without_substituting():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "unsupported.fcf_yield", "operator": ">=", "value": 5}],
    ))
    validated, report = run_validation(intent)
    assert not report.is_valid
    assert any("FCF" in f for f in report.unsupported_features)
    assert report.suggested_fixes  # 대체 제안은 하되
    # 조건이 다른 지표로 조용히 대체되지 않았다
    assert validated.strategy.entry_conditions[0].factor == "unsupported.fcf_yield"


def test_unresolvable_symbol_expression_surfaces_warning():
    """지정 종목 표현을 registry가 해석하지 못하면 조용히 버리지 않고 warning으로 알린다
    (계약 § 3 — LLM 패치 값 훼손('제주반도 semiconductor')이 무변경·무통보로 끝나던
    2026-07-26 사고). warning은 primary notices 채널로 사용자에게 노출된다."""
    intent = StrategyIntent.model_validate(_full_intent_dict(
        universe={"markets": ["KOSPI"], "sectors": [],
                  "symbols": ["005930", "제주반도 semiconductor"]},
    ))
    _, report = run_validation(intent)
    assert any("제주반도 semiconductor" in w for w in report.warnings)


def test_symbol_add_patch_compiles_to_target_union():
    """종목 추가 수정의 계약 경로 전체: 테마 지정 전략 → /universe/symbols/- 패치(문자열 값,
    프롬프트 규칙 10-1) → 검증 → 컴파일 = 기존 지정과의 합집합. LLM이 의미를 해석하고
    결정론은 형식 검증·registry 조회만 한다."""
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.interpreter.models import PatchOp

    prev = ParsedStrategy(
        description="이재명 관련주 투자 전략",
        target_symbols=["005930", "000660", "004310"],
    )
    draft = decompile_strategy(prev)
    patched = apply_patches(draft, [PatchOp(
        op="add", path="/universe/symbols/-", value="제주반도체",
        source_text="제주반도체도 추가해줘",
    )])
    validated, report = run_validation(
        StrategyIntent(intent="MODIFY_STRATEGY", strategy=patched, confidence=1.0)
    )
    assert report.is_valid, report.errors
    parsed = compile_strategy(validated, report, prev.description)
    assert parsed.target_symbols == ["005930", "000660", "004310", "080220"]


def test_symbol_add_patch_with_object_value_not_silently_lost():
    """패치 값이 조건형 객체로 오는 드리프트도 조용히 소실되지 않는다 — source_text가
    구제되어 해석되거나(정상 표기면 합류), 해석 불가면 warning으로 보고된다."""
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.interpreter.models import PatchOp

    draft = decompile_strategy(ParsedStrategy(
        description="테마 전략", target_symbols=["005930"],
    ))
    patched = apply_patches(draft, [PatchOp(
        op="add", path="/universe/symbols/-",
        value={"factor": None, "operator": None, "value": None, "source_text": "제주반도체"},
        source_text="제주반도체도 추가해줘",
    )])
    assert patched.universe.symbols == ["005930", "제주반도체"]
    validated, report = run_validation(
        StrategyIntent(intent="MODIFY_STRATEGY", strategy=patched, confidence=1.0)
    )
    parsed = compile_strategy(validated, report, "테마 전략")
    assert parsed.target_symbols == ["005930", "080220"]


def test_missing_threshold_generates_question_not_default():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "fundamental.operating_margin", "operator": ">=",
                           "value": None, "source_text": "영업이익률이 높은"}],
    ))
    validated, report = run_validation(intent)
    assert report.status == "NEEDS_CLARIFICATION"
    assert "strategy.entry_conditions[0].value" in report.missing_fields
    question = next(
        q for q in report.clarification_questions
        if q.field == "strategy.entry_conditions[0].value"
    )
    assert question.recommended_value == 10  # Registry 추천값 (확정값 아님)
    # 검증이 값을 임의로 채우지 않았다
    assert validated.strategy.entry_conditions[0].value is None


def test_missing_parameter_question_uses_friendly_label():
    # 사고(2026-07-20): "신고가 돌파의 lookback_period 기간을..." — 내부 파라미터
    # 이름이 되묻기 질문에 그대로 노출. 사용자 친화 라벨로 표시해야 한다.
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "technical.breakout", "operator": "crosses_above",
                           "parameters": {}}],
    ))
    _, report = run_validation(intent)
    assert report.status == "NEEDS_CLARIFICATION"
    question = next(
        q for q in report.clarification_questions
        if q.field == "strategy.entry_conditions[0].parameters.lookback_period"
    )
    assert "lookback_period" not in question.question
    assert "기준 기간" in question.question


def test_breakout_lookback_filled_from_source_not_reasked():
    # 사고(2026-07-21): 사용자가 "52주 신고가"라고 명시했는데 LLM 인터프리터가 '52주'를
    # lookback_period로 옮기지 못하고 빈 파라미터를 내보내, 완결성 검증이 이미 말한 값을
    # 되묻던 문제. 되묻기 전에 조건의 source_text(LLM 인용)에서 채운다(명시적 기간이 있을
    # 때만 — 2026-07-26 계약 전환으로 원문 폴백은 제거, LLM 출력만 읽는다).
    from strategy_conversation.primary import _fill_deterministic_condition_params

    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "technical.breakout", "operator": "crosses_above",
                           "parameters": {}, "source_text": "52주 신고가를 새로 만들고"}],
    ))
    _fill_deterministic_condition_params(intent)
    assert intent.strategy.entry_conditions[0].parameters.get("lookback_period") == 252
    _, report = run_validation(intent)
    assert not any(
        q.field == "strategy.entry_conditions[0].parameters.lookback_period"
        for q in report.clarification_questions
    )


def test_breakout_without_explicit_period_still_asks():
    # 기간 언급이 아예 없는 '신고가 돌파'는 조용히 기본값(60)으로 확정하지 않고 되묻는다.
    from strategy_conversation.primary import _fill_deterministic_condition_params

    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "technical.breakout", "operator": "crosses_above",
                           "parameters": {}, "source_text": "신고가 돌파 시 매수"}],
    ))
    _fill_deterministic_condition_params(intent)
    assert intent.strategy.entry_conditions[0].parameters.get("lookback_period") is None
    _, report = run_validation(intent)
    assert report.status == "NEEDS_CLARIFICATION"


def test_volume_surge_misclassified_as_trading_value_reclassified():
    # 사고(2026-07-21): '거래량이 최근 평균보다 늘어난'을 LLM이 trading_value(거래대금 절대
    # 임계 필요)로 오분류 → 거래대금 기준값을 되물음. 최종 전략은 volume_spike로 교정되므로
    # 질문만 헛것. 되묻기 전에 조건의 source_text(LLM 인용) 기준으로 volume_spike(임계값
    # 불필요)로 재분류한다(원문은 읽지 않는다).
    from strategy_conversation.primary import _fill_deterministic_condition_params

    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "technical.trading_value", "operator": ">",
                           "value": None, "source_text": "거래량이 최근 평균보다 늘어난"}],
    ))
    _fill_deterministic_condition_params(intent)
    assert intent.strategy.entry_conditions[0].factor == "technical.volume_spike"
    assert intent.strategy.entry_conditions[0].value is None
    _, report = run_validation(intent)
    assert not any(
        "거래대금" in q.question for q in report.clarification_questions
    )


def test_absolute_trading_value_threshold_not_reclassified():
    # '거래대금 100억 이상'은 정적 유동성 필터 — volume_spike로 바꾸지 않는다(급증 표현 아님).
    from strategy_conversation.primary import _fill_deterministic_condition_params

    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "technical.trading_value", "operator": ">=",
                           "value": 100, "source_text": "거래대금 100억 이상"}],
    ))
    _fill_deterministic_condition_params(intent)
    assert intent.strategy.entry_conditions[0].factor == "technical.trading_value"
    assert intent.strategy.entry_conditions[0].value == 100


def test_conflicting_conditions_detected():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[
            {"factor": "fundamental.per", "operator": "<=", "value": 10},
            {"factor": "fundamental.per", "operator": ">=", "value": 20},
        ],
    ))
    _, report = run_validation(intent)
    assert not report.is_valid
    assert any("모순" in e for e in report.errors)


def test_crossover_short_ge_long_detected():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "technical.ma_crossover", "operator": "crosses_above",
                           "parameters": {"short_period": 60, "long_period": 20}}],
    ))
    _, report = run_validation(intent)
    assert any("단기" in e for e in report.errors)


def test_rsi_value_out_of_range_detected():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "technical.rsi", "operator": "<=", "value": 150,
                           "parameters": {"period": 14}}],
    ))
    _, report = run_validation(intent)
    assert any("RSI" in e and "범위" in e for e in report.errors)


def test_rsi_period_too_small_detected():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "technical.rsi", "operator": "<=", "value": 30,
                           "parameters": {"period": 1}}],
    ))
    _, report = run_validation(intent)
    assert any("period=1" in e for e in report.errors)


def test_operator_not_allowed_detected():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "fundamental.per", "operator": "crosses_above",
                           "value": 10}],
    ))
    _, report = run_validation(intent)
    assert any("연산자" in e for e in report.errors)


def test_ranking_without_count_and_frequency_asks():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[],
        ranking=[{"metric": "ranking.return", "lookback_days": 60}],
        portfolio={"selection_count": None, "rebalance_frequency": None},
    ))
    _, report = run_validation(intent)
    assert report.status == "NEEDS_CLARIFICATION"
    fields = {q.field for q in report.clarification_questions}
    assert "strategy.portfolio.selection_count" in fields
    assert "strategy.portfolio.rebalance_frequency" in fields


def test_low_confidence_does_not_leak_to_user():
    # 사고(2026-07-17): "확신이 낮습니다 — 확인해 주시겠어요?"가 사용자에게 노출.
    # confidence는 텔레메트리 전용 — 상태 판정·경고·질문 어디에도 쓰지 않는다.
    data = _full_intent_dict()
    data["confidence"] = 0.0
    _, report = run_validation(StrategyIntent.model_validate(data))
    assert report.status == "READY"
    assert report.clarification_questions == []
    assert not any("신뢰도" in w or "확신" in w for w in report.warnings)


def test_sector_normalized_and_unknown_sector_rejected():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        universe={"markets": ["KOSPI", "KOSDAQ"], "sectors": ["반도체"]},
    ))
    validated, report = run_validation(intent)
    assert validated.strategy.universe.sectors == ["반도체"]

    intent2 = StrategyIntent.model_validate(_full_intent_dict(
        universe={"markets": ["KOSPI"], "sectors": ["우주광물채굴"]},
    ))
    _, report2 = run_validation(intent2)
    assert any("우주광물채굴" in e for e in report2.errors)


def test_multiple_sectors_normalized_with_spacing_drift():
    """복수 업종은 전부 정본화된다 — 4B의 글자 사이 공백 드리프트('2 차 전 지')도
    _sector_key가 흡수한다(실측 2026-07-25, 프롬프트 규칙 6-0 E2E 프로브)."""
    intent = StrategyIntent.model_validate(_full_intent_dict(
        universe={"markets": ["KOSPI", "KOSDAQ"], "sectors": ["반도체", "2 차 전 지"]},
    ))
    validated, report = run_validation(intent)
    assert validated.strategy.universe.sectors == ["반도체", "이차전지"]
    assert report.is_valid


def test_system_prompt_sector_rule_contract():
    """규칙 6-0 계약 가드 — 업종 제한은 지원 기능이며 universe.sectors에 채운다.

    실측 사고(2026-07-25): 4B가 규칙 3('목록에 없는 개념→unsupported')을 업종에도 적용해
    '업종/테마 기반 종목 선택 (반도체, 로봇)'을 unsupported_features로 분류하고 sectors를
    비운 채 되묻기를 냈다. 지표 목록은 조건용이지 유니버스용이 아님을 명시한다."""
    from strategy_conversation.interpreter.prompts import build_system_prompt

    prompt = build_system_prompt()
    assert "업종/테마 제한은 지원 기능" in prompt
    assert 'sectors=["반도체","로봇"]' in prompt
    assert "unsupported_features에 넣지 말고" in prompt


def test_rebalance_frequency_alias_normalized():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        portfolio={"selection_count": 10, "rebalance_frequency": "분기별"},
    ))
    validated, report = run_validation(intent)
    assert validated.strategy.portfolio.rebalance_frequency == "quarterly"
    assert report.is_valid


def test_non_strategy_intent_not_compiled():
    intent = StrategyIntent.model_validate(
        {"intent": "NON_STRATEGY_REQUEST", "confidence": 0.9}
    )
    _, report = run_validation(intent)
    assert not report.is_valid
    assert report.status == "REJECTED"


# ─── 컴파일러 ────────────────────────────────────────────────────────────────

def test_compile_full_strategy_to_parsed_strategy():
    intent = StrategyIntent.model_validate(_full_intent_dict())
    validated, report = run_validation(intent)
    parsed = compile_strategy(validated, report, "PER 10 이하 20종목 매월 리밸런싱 손절 8%")
    assert parsed.universe == ["KOSPI"]
    assert parsed.fundamental_filters[0].metric == "per"
    assert parsed.fundamental_filters[0].operator == "<="
    assert parsed.fundamental_filters[0].value == 10
    assert parsed.max_positions == 20
    assert parsed.rebalancing_period == "monthly"
    assert parsed.stop_loss_pct == 8.0
    assert parsed.backtest_period == "5y"  # 컴파일 단계 기본값


def test_compile_technical_and_ranking():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "technical.ma_crossover", "operator": "crosses_above",
                           "parameters": {"short_period": 20, "long_period": 60}}],
        exit_conditions=[{"factor": "technical.rsi", "operator": ">=", "value": 70,
                          "parameters": {"period": 14}}],
        ranking=[{"metric": "ranking.return", "lookback_days": 90}],
    ))
    validated, report = run_validation(intent)
    assert report.is_valid, (report.errors, report.missing_fields)
    parsed = compile_strategy(validated, report, "테스트")
    entry = parsed.entry_signals[0]
    assert entry.indicator == "ma_crossover"
    assert (entry.short_period, entry.long_period, entry.signal_type) == (20, 60, "buy")
    exit_sig = parsed.exit_signals[0]
    assert (exit_sig.indicator, exit_sig.signal_type, exit_sig.value) == ("rsi", "sell", 70)
    assert parsed.ranking_metric == "return"
    assert parsed.ranking_lookback_days == 90


def test_compile_refuses_invalid_report():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "fundamental.per", "operator": "<=", "value": None}],
    ))
    validated, report = run_validation(intent)
    assert not report.is_valid
    with pytest.raises(StrategyCompileError):
        compile_strategy(validated, report, "PER 낮은 종목")


def test_compile_partial_drops_pending_conditions_only():
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[
            {"factor": "fundamental.operating_margin", "operator": ">=", "value": None},
            {"factor": "fundamental.per", "operator": "<=", "value": 10},
        ],
    ))
    validated, report = run_validation(intent)
    assert not report.is_valid
    from strategy_conversation.compiler.strategy_compiler import compile_partial

    parsed, dropped = compile_partial(validated, report, "영업이익률 높고 PER 10 이하")
    assert [f.metric for f in parsed.fundamental_filters] == ["per"]
    assert dropped == ["영업이익률"]


# ─── Primary Mode (Phase 2) ──────────────────────────────────────────────────

class _StubPrimaryInterpreter:
    def __init__(self, intent_data):
        from strategy_conversation.interpreter.llm_strategy_interpreter import (
            InterpreterResult,
        )
        self._result = InterpreterResult(
            intent=StrategyIntent.model_validate(intent_data),
            raw_output="{}", repair_attempts=0, latency_ms=1.0, model_name="stub",
        )

    def interpret(self, user_input, draft=None):
        return self._result


def _run_primary_with(monkeypatch, intent_data, user_input="테스트"):
    from strategy_conversation import primary

    monkeypatch.setattr(primary, "_interpreter_singleton", _StubPrimaryInterpreter(intent_data))
    return primary.run_primary_parse(user_input)


def test_primary_ready_strategy_compiles_without_questions(monkeypatch):
    result = _run_primary_with(monkeypatch, _full_intent_dict())
    assert result is not None
    assert result["parsed"].fundamental_filters[0].metric == "per"
    assert result["clarification_question"] is None
    assert result["interpreter"]["validation_status"] == "READY"


def test_primary_needs_clarification_partial_compile_with_chips(monkeypatch):
    data = _full_intent_dict(
        entry_conditions=[
            {"factor": "fundamental.operating_margin", "operator": ">=", "value": None},
            {"factor": "fundamental.per", "operator": "<=", "value": 10},
        ],
    )
    result = _run_primary_with(monkeypatch, data, "영업이익률 높고 PER 10 이하")
    assert result is not None
    # 미확정 조건은 기본값으로 확정하지 않고 제외됐다
    assert [f.metric for f in result["parsed"].fundamental_filters] == ["per"]
    assert "영업이익률" in result["clarification_question"]
    assert "영업이익률 10% 이상" in (result["clarification_suggestions"] or [])


def test_primary_unsupported_features_noticed(monkeypatch):
    data = _full_intent_dict()
    data["unsupported_features"] = ["FCF Yield"]
    result = _run_primary_with(monkeypatch, data)
    assert result is not None
    assert any("FCF Yield" in n for n in result["notices"])


def test_primary_single_asset_target_from_llm_symbols(monkeypatch):
    """[회귀] FR-STR-068 — 지정 종목은 LLM이 universe.symbols로 넘기고 리졸버가 코드로 푼다.

    2026-07-26 계약 전환: 원문 정규식 추출(_apply_prompt_overrides)이 아니라 LLM 산출
    + universe_resolver가 담당한다(nl_interpretation_contract § 3-2). 종목명→코드 매핑은
    LLM이 대체할 수 없는 지식 조회이므로 결정론 코드가 맡되, 입력은 원문이 아닌 term이다.
    """
    data = _full_intent_dict(
        universe={"markets": ["KOSPI"], "sectors": [], "symbols": ["삼성전자"]},
        entry_conditions=[{"factor": "technical.ma_crossover", "source_text": "골든크로스",
                           "parameters": {"short_period": 5, "long_period": 20}}],
        exit_conditions=[],
        ranking=[],
        portfolio={"selection_count": 10},
        risk_management={},
    )
    result = _run_primary_with(monkeypatch, data, "삼성전자 골든크로스 테스트를 해보자")
    assert result is not None
    assert result["parsed"].target_symbols == ["005930"]
    # 청산 누락 질문은 억제된다 — 호출부 공유 보정(apply_single_asset_adjustments)이
    # 반대 신호 청산 추천+notice로 처리하는 영역이다.
    assert result["clarification_question"] is None


def test_primary_unknown_theme_sector_reaches_term_in_chain(monkeypatch):
    """[회귀] 2026-07-26 — capability validator는 정본 목록 밖 섹터 표현('이재명 관련주')을
    universe.sectors에서 제거한다. term-in 해석 체인(§ 11-3)은 검증 후 값이 아니라 검증 전
    LLM 산출 표현을 받아야 한다 — 검증 후 값을 읽으면 체인이 영원히 실행되지 못하고 테마가
    '지원되지 않아 반영되지 않았어요' 안내로 조용히 소실된다."""
    import engine.nl_parser as nl_parser

    monkeypatch.setenv("STRATEGY_PLANNER_MODE", "off")
    seen_terms: list = []

    def _fake_apply_theme(parsed, term):
        seen_terms.append(term)
        parsed.target_symbols = ["005930"]
        return "'이재명' 관련 상장사 1곳을 대상 종목으로 설정했어요."

    monkeypatch.setattr(nl_parser, "apply_theme_companies", _fake_apply_theme)
    data = _full_intent_dict(
        universe={"markets": ["KOSPI", "KOSDAQ"], "sectors": ["이재명 관련주"], "symbols": []},
    )
    result = _run_primary_with(monkeypatch, data, "이재명 관련주 투자 전략")
    assert result is not None
    assert seen_terms == ["이재명 관련주"]
    assert result["parsed"].target_symbols == ["005930"]
    # 반영된 테마에 검증기의 미지원 안내가 남으면 모순 — 지워져야 한다
    assert not any("이재명" in n and "지원되지 않아" in n for n in result["notices"])


def test_primary_universe_strategy_keeps_exit_question(monkeypatch):
    """지정 종목이 없으면 청산 누락 되묻기는 그대로 유지된다."""
    data = _full_intent_dict(
        entry_conditions=[{"factor": "technical.ma_crossover", "source_text": "골든크로스",
                           "parameters": {"short_period": 5, "long_period": 20}}],
        exit_conditions=[],
        ranking=[],
        portfolio={"selection_count": 10},
        risk_management={},
    )
    result = _run_primary_with(monkeypatch, data, "골든크로스 전략 테스트해줘")
    assert result is not None
    assert result["parsed"].target_symbols == []
    assert "청산 규칙이 없습니다" in (result["clarification_question"] or "")


def test_primary_compiled_entry_drops_entry_question(monkeypatch):
    """[회귀] 확정된 완성 전략을 다시 '어떤 조건으로 종목을 선택할까요?'로 되묻는 사고.

    컴파일된 parsed에 진입 조건이 있으면 진입 되묻기는 모순이므로 제거한다
    (_prune_clarifications_filled_by_overrides). 2026-07-26 전까지는 원문 정규식 보정이
    조건을 되살리는 경우가 트리거였고, 보정을 끈 뒤에는 LLM 산출이 그 자리를 대신한다.
    """
    data = _full_intent_dict(
        entry_conditions=[{"factor": "fundamental.eps", "operator": ">", "value": 0,
                           "source_text": "흑자 기업"}],
        ranking=[],
    )
    result = _run_primary_with(
        monkeypatch, data, "코스피 흑자 기업 매수, 손절 10% 익절 30%, 매월 리밸런싱"
    )
    assert result is not None
    assert any(f.metric == "eps" for f in result["parsed"].fundamental_filters)
    assert result["clarification_question"] is None


def test_primary_entry_restored_by_override_when_rolled_back(monkeypatch):
    """롤백 경로(STRATEGY_PROMPT_OVERRIDE_MODE=on)가 살아 있는지 지키는 가드.

    보정을 되살리면 LLM이 '흑자 기업'을 빠뜨려도 eps>0으로 복원된다 — 탈출구가 조용히
    썩지 않도록 계약을 고정한다(기본 경로는 off, 위 테스트).
    """
    monkeypatch.setenv("STRATEGY_PROMPT_OVERRIDE_MODE", "on")
    data = _full_intent_dict(entry_conditions=[], ranking=[])
    result = _run_primary_with(
        monkeypatch, data, "코스피 흑자 기업 매수, 손절 10% 익절 30%, 매월 리밸런싱"
    )
    assert result is not None
    assert any(f.metric == "eps" for f in result["parsed"].fundamental_filters)
    assert result["clarification_question"] is None


def test_primary_non_strategy_intent_falls_back(monkeypatch):
    data = {"intent": "NON_STRATEGY_REQUEST", "confidence": 0.9}
    assert _run_primary_with(monkeypatch, data) is None


def test_primary_interpreter_error_falls_back(monkeypatch):
    from strategy_conversation import primary
    from strategy_conversation.interpreter.llm_strategy_interpreter import InterpreterError

    class _Failing:
        def interpret(self, user_input, draft=None):
            raise InterpreterError("boom")

    monkeypatch.setattr(primary, "_interpreter_singleton", _Failing())
    assert primary.run_primary_parse("PER 10 이하") is None


def test_primary_mode_gated_by_env(monkeypatch):
    """2026-07-26 기본값 승격(로드맵 5번): env 미설정=primary, 명시적 off/shadow가 우선."""
    from strategy_conversation.primary import primary_enabled

    monkeypatch.delenv("STRATEGY_INTERPRETER_MODE", raising=False)
    assert primary_enabled()
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "off")
    assert not primary_enabled()
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "shadow")
    assert not primary_enabled()
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "primary")
    assert primary_enabled()


def test_apply_primary_meta_merges_into_result(monkeypatch):
    from strategy_conversation.primary import apply_primary_meta

    result = {
        "clarification_question": None,
        "clarification_suggestions": None,
        "notices": ["기존 안내"],
        "runtime": {"backend": "ollama"},
    }
    primary = {
        "clarification_question": "기준값을 얼마로 할까요?",
        "clarification_suggestions": ["영업이익률 10% 이상"],
        "notices": ["새 안내"],
        "interpreter": {"mode": "primary"},
    }
    apply_primary_meta(result, primary)
    assert result["clarification_question"] == "기준값을 얼마로 할까요?"
    assert result["notices"] == ["기존 안내", "새 안내"]
    assert result["runtime"]["interpreter"]["mode"] == "primary"


# ─── Decompiler / Modify Primary (Phase 2) ───────────────────────────────────

def _rich_parsed():
    from engine.nl_parser import ParsedStrategy

    return ParsedStrategy.model_validate({
        "description": "ROE 15% 이상, 20일선 60일선 골든크로스 매수, RSI 70 이상 매도",
        "universe": ["KOSPI", "KOSDAQ"],
        "sector": "반도체",
        "fundamental_filters": [
            {"metric": "roe_or_gpa", "operator": ">=", "value": 15},
            {"metric": "debt_ratio", "operator": "<=", "value": 100},
        ],
        "entry_signals": [
            {"indicator": "ma_crossover", "signal_type": "buy",
             "short_period": 20, "long_period": 60},
        ],
        "exit_signals": [
            {"indicator": "rsi", "signal_type": "sell", "period": 14,
             "operator": ">=", "value": 70},
        ],
        "max_positions": 15,
        "hold_period_days": 63,
        "rebalancing_period": "monthly",
        "stop_loss_pct": 8.0,
        "take_profit_pct": 20.0,
        "backtest_period": "3y",
        "initial_capital": 50_000_000.0,
        "fee_rate": 0.1,
        "slippage_rate": 0.1,
    })


def test_decompile_compile_roundtrip_preserves_strategy():
    from strategy_conversation.compiler.strategy_compiler import compile_strategy
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.interpreter.models import ValidationReport

    prev = _rich_parsed()
    spec = decompile_strategy(prev)
    intent = StrategyIntent(intent="CREATE_STRATEGY", strategy=spec, confidence=1.0)
    report = ValidationReport(is_valid=True, status="READY")
    roundtrip = compile_strategy(intent, report, prev.description)
    assert roundtrip.model_dump() == prev.model_dump()


def _stub_modify_interpreter(monkeypatch, intent_data):
    import engine.nl_parser as nl
    from strategy_conversation import primary

    monkeypatch.setattr(primary, "_interpreter_singleton", _StubPrimaryInterpreter(intent_data))
    # 결정적 fast-path 우선 게이트를 무력화해 인터프리터 메커니즘 자체를 검증한다 —
    # 룰 어휘가 확장돼 테스트 발화를 처리하게 되어도 이 테스트들이 흔들리지 않게.
    # 게이트 동작 자체는 test_modify_primary_deterministic_fast_path_skips_interpreter가 검증.
    monkeypatch.setattr(nl, "_modify_rule_based", lambda *a, **k: None)


def test_modify_primary_applies_patches(monkeypatch):
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY",
        "status": "READY",
        "confidence": 0.95,
        "patches": [
            {"op": "replace", "path": "/entry_conditions/0/value", "value": 20,
             "source_text": "ROE를 20%로"},
            {"op": "remove", "path": "/entry_conditions/1",
             "source_text": "부채비율 조건은 빼줘"},
        ],
    })
    prev = _rich_parsed()
    result = run_primary_modification("ROE를 20%로 올리고 부채비율 조건은 빼줘",
                                      prev.model_dump())
    assert result is not None
    parsed = result["parsed"]
    assert [(f.metric, f.value) for f in parsed.fundamental_filters] == [("roe_or_gpa", 20.0)]
    # 나머지 필드는 전부 보존
    assert parsed.entry_signals[0].short_period == 20
    assert parsed.stop_loss_pct == 8.0
    assert parsed.description == prev.description
    assert result["interpreter"]["mode"] == "primary_modify"


def test_modify_primary_rejects_full_strategy_output(monkeypatch):
    # patches 없이 전체 전략 재출력 → 필드 소실 위험이라 수락하지 않고 폴백
    from strategy_conversation.primary import run_primary_modification

    data = _full_intent_dict()
    data["intent"] = "MODIFY_STRATEGY"
    _stub_modify_interpreter(monkeypatch, data)
    assert run_primary_modification("종목 10개로", _rich_parsed().model_dump()) is None


def test_modify_primary_preserves_entry_filters_via_carry_over(monkeypatch):
    # StrategySpec 밖 필드(entry_filters)는 원본에서 이월 보존된다(목록형 필드 소실 방지)
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "READY", "confidence": 0.95,
        "patches": [{"op": "replace", "path": "/portfolio/selection_count", "value": 5}],
    })
    prev_data = _rich_parsed().model_dump()
    prev_data["entry_filters"] = [
        {"indicator": "ema", "signal_type": "buy", "mode": "above", "long_period": 60}
    ]
    prev = ParsedStrategy.model_validate(prev_data)
    result = run_primary_modification("종목 5개로", prev.model_dump())
    assert result is not None
    assert result["parsed"].max_positions == 5
    assert result["parsed"].entry_filters == prev.entry_filters


def test_modify_primary_roundtrip_guard_falls_back(monkeypatch):
    # StrategySpec이 표현 못 하는 신호(rsi rebound 모드)는 라운드트립 불일치로 이관 거부
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "READY", "confidence": 0.95,
        "patches": [{"op": "replace", "path": "/portfolio/selection_count", "value": 5}],
    })
    prev_data = _rich_parsed().model_dump()
    prev_data["exit_signals"] = [
        {"indicator": "rsi", "signal_type": "sell", "period": 14,
         "operator": ">=", "value": 70, "mode": "rebound"}
    ]
    prev = ParsedStrategy.model_validate(prev_data)
    assert run_primary_modification("종목 5개로", prev.model_dump()) is None


def test_modify_primary_target_symbol_from_patch(monkeypatch):
    """[FR-STR-068 회귀] 종목-only 수정("삼성전자 투자 하는 전략")이 조용히 무시되던 사고.

    2026-07-26 계약 전환: UniverseSpec.symbols가 생겨 인터프리터가 직접 표현하고,
    universe_resolver가 코드로 푼다. 이전에는 원문 정규식 추출이 구제하던 경로다.
    """
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "READY", "confidence": 0.9,
        "patches": [{"op": "replace", "path": "/universe/symbols", "value": ["삼성전자"]}],
    })
    prev = _rich_parsed().model_dump()
    prev["target_symbols"] = []
    result = run_primary_modification("삼성전자 투자 하는 전략", prev)
    assert result is not None
    assert result["parsed"].target_symbols == ["005930"]


def _provenance(patch, user_input: str) -> bool:
    from engine.nl_parser import _compact
    from strategy_conversation.primary import (
        _input_number_candidates,
        _patch_provenance_supported,
    )

    return _patch_provenance_supported(
        patch, _compact(user_input), _input_number_candidates(user_input)
    )


def test_modify_primary_rejects_hallucinated_symbol_patch(monkeypatch):
    """종목 패치는 키워드 큐가 아니라 **해석 가능성**으로 거른다(§ 3-2).

    종목명은 열린 집합이라 큐 목록으로 열거할 수 없고, 원문 스캔은 계약 위반이다.
    마스터에 없는 이름을 지어내면 거부된다.
    """
    from strategy_conversation.interpreter.models import PatchOp

    real = PatchOp(op="replace", path="/universe/symbols", value=["삼성전자"])
    fake = PatchOp(op="replace", path="/universe/symbols", value=["없는회사이름입니다"])
    clear = PatchOp(op="replace", path="/universe/symbols", value=[])

    assert _provenance(real, "손절을 10퍼센트로 바꿔줘") is True
    assert _provenance(fake, "손절을 10퍼센트로 바꿔줘") is False
    assert _provenance(clear, "종목 지정 풀어줘") is True


def test_patch_provenance_gate_is_reconciliation_not_vocabulary_scan():
    """환각 게이트는 대조(§ 3-1)다 — 어휘 스캔이 아니라 인용 실재·수치 일치로 판정한다.

    2026-07-26 계약 전환: 필드별 한국어 어휘 목록(_PATCH_FIELD_CUES)은 계약이 금지한
    발화 어휘 스캔이라 폐기. 판정 근거는 ① LLM 인용(source_text)이 입력에 실재,
    ② 패치 수치가 입력 수치와 일치(단위 환산 포함), ③ 종목 해석 가능성뿐이다.
    """
    from strategy_conversation.interpreter.models import PatchOp

    utter = "손절을 10퍼센트로 바꿔줘"
    # 수치 대조: 값 10이 입력의 '10'과 일치 → 인용 없어도 근거 있음
    assert _provenance(
        PatchOp(op="replace", path="/risk_management/stop_loss", value=10), utter) is True
    # 인용 대조: 무수치 패치도 인용이 실재하면 통과(표기 정규화 후 포함 — %↔퍼센트 흡수)
    assert _provenance(
        PatchOp(op="replace", path="/portfolio/rebalance_frequency", value="monthly",
                source_text="매월 리밸런싱으로"),
        "매월 리밸런싱으로 바꿔줘") is True
    # 지어낸 인용(입력에 없는 문구)은 거부
    assert _provenance(
        PatchOp(op="replace", path="/portfolio/rebalance_frequency", value="monthly",
                source_text="매월 리밸런싱으로"),
        "다른 예는 없어?") is False
    # 인용도 수치도 없는 패치는 환각으로 거부(QA 20-3)
    assert _provenance(
        PatchOp(op="replace", path="/portfolio/rebalance_frequency", value="monthly"),
        "다른 예는 없어?") is False
    # 단위 환산 대조: '1개월 보유'(21거래일)처럼 표기 변환된 수치도 근거로 인정
    assert _provenance(
        PatchOp(op="replace", path="/portfolio/hold_period_days", value=21),
        "1개월 보유로 바꿔줘") is True


def test_modify_primary_clarify_returns_question_with_strategy_intact(monkeypatch):
    # 2026-07-17 사고 재현: "pbr이 뭐야?"가 수정 경로로 흘러 인터프리터가 CLARIFY로
    # 정확히 판단했는데, 폴백이 질문을 버리고 기존 수정 LLM이 무변경 전략을 반환해
    # 동일한 전략 요약만 재렌더링됐다. CLARIFY(패치 없음)+질문은 전략을 그대로 유지한
    # 채 clarification 채널로 전달돼야 한다.
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "CLARIFY_STRATEGY", "status": "NEEDS_CLARIFICATION", "confidence": 0.9,
        "clarification_questions": [
            {"field": "", "question": "현재 전략 초안을 수정하시겠습니까? 아니면 PBR(주가순자산비율)에 대한 개념 설명을 원하시나요?"},
        ],
    })
    prev = _rich_parsed()
    result = run_primary_modification("pbr이 뭐야?", prev.model_dump())
    assert result is not None
    assert result["parsed"].model_dump() == prev.model_dump()  # 전략 무변경
    assert "PBR" in result["clarification_question"]
    assert result["interpreter"]["mode"] == "primary_modify_clarify"


def test_modify_primary_definition_question_answered_with_strategy_intact(monkeypatch):
    # 2026-07-17 사고 2차("pbr이 뭐야?"가 수정 경로로 오라우팅) — 인터프리터 LLM이
    # EXPLAIN_INDICATOR로 라벨하면 전략을 유지한 채 실제 설명(/query/general과 동일
    # 생성기)을 notices로 답한다(2026-07-19 교정 — "변경하지 않았어요" 안내만 주면
    # 질문이 답변되지 않음). 질문 판정은 LLM 라벨만 쓴다 — 과거의 결정적 cue
    # (is_definition_question, 원문 의도 분류)는 계약 위반이라 제거(2026-07-26).
    import api.intent_routes as intent_routes
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "EXPLAIN_INDICATOR", "status": "READY", "confidence": 0.9,
    })
    monkeypatch.setattr(
        intent_routes, "generate_general_answer",
        lambda query, history=None: "PBR은 주가를 주당순자산으로 나눈 값으로, 낮을수록 장부가치 대비 저평가로 봅니다.",
    )
    prev = _rich_parsed()
    result = run_primary_modification("pbr이 뭐야?", prev.model_dump())
    assert result is not None
    assert result["parsed"].model_dump() == prev.model_dump()  # 전략 무변경
    assert any("주당순자산" in n for n in result["notices"])  # 실제 설명이 전달됨
    assert result["interpreter"]["mode"] == "primary_modify_explain"


def test_modify_primary_unsupported_label_gets_notice_not_llm_guess(monkeypatch):
    # 계약 전환(2026-07-26): 인터프리터가 질문을 unsupported_features로만 보고하면(라벨 드리프트)
    # 원문 cue로 질문 여부를 재해석하지 않는다 — LLM 라벨이 해석의 최종 권한이므로
    # 전략 유지+미반영 안내로 응답한다. 드리프트 자체는 프롬프트 규칙 10이 담당.
    import api.intent_routes as intent_routes
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "UNSUPPORTED", "confidence": 0.9,
        "unsupported_features": ["PBR 개념 설명 요청"],
    })
    def _must_not_call(query, history=None):
        raise AssertionError("EXPLAIN_INDICATOR 라벨 없이 설명 LLM이 호출됨")
    monkeypatch.setattr(intent_routes, "generate_general_answer", _must_not_call)
    prev = _rich_parsed()
    result = run_primary_modification("pbr이 뭐야?", prev.model_dump())
    assert result is not None
    assert result["parsed"].model_dump() == prev.model_dump()  # 전략 무변경
    assert any("반영할 수 없어" in n for n in result["notices"])
    assert result["interpreter"]["mode"] == "primary_modify_unsupported"


def test_modify_primary_explain_indicator_falls_back_to_notice_without_llm(monkeypatch):
    # 프롬프트 1.2 계약(개념 질문=EXPLAIN_INDICATOR)에서 설명 LLM이 미가용이면
    # 침묵 대신 전략 유지+설명을 준비하지 못했다는 정직한 안내를 돌려준다.
    import api.intent_routes as intent_routes
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "EXPLAIN_INDICATOR", "status": "READY", "confidence": 0.9,
    })
    monkeypatch.setattr(
        intent_routes, "generate_general_answer", lambda query, history=None: None,
    )
    prev = _rich_parsed()
    result = run_primary_modification("PBR이 뭐야?", prev.model_dump())
    assert result is not None
    assert result["parsed"].model_dump() == prev.model_dump()
    assert any("설명" in n for n in result["notices"])
    assert result["interpreter"]["mode"] == "primary_modify_explain"


def test_modify_primary_unsupported_condition_returns_notice(monkeypatch):
    # 정의형 질문이 아닌 진짜 미지원 개념 수정 요청(패치 없음+unsupported_features)은
    # 설명 LLM을 부르지 않고 전략 유지+미반영 안내를 돌려준다.
    import api.intent_routes as intent_routes
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "UNSUPPORTED", "confidence": 0.9,
        "unsupported_features": ["FCF"],
    })
    def _must_not_call(query, history=None):
        raise AssertionError("미지원 조건 요청에 설명 LLM이 호출됨")
    monkeypatch.setattr(intent_routes, "generate_general_answer", _must_not_call)
    prev = _rich_parsed()
    result = run_primary_modification("FCF 조건 추가해줘", prev.model_dump())
    assert result is not None
    assert result["parsed"].model_dump() == prev.model_dump()
    assert any("FCF" in n and "반영할 수 없어" in n for n in result["notices"])
    assert result["interpreter"]["mode"] == "primary_modify_unsupported"


def test_modify_primary_deterministic_fast_path_skips_interpreter(monkeypatch):
    # **롤백 모드(fast_path_first) 전용 동작** — 결정적 fast-path가 완전히 해석하는 수정은
    # 인터프리터(LLM)를 호출하지 않고 폴백한다(LLM 왕복 지연·수치/날짜 드리프트 회피).
    # 기본 모드(llm_first)는 2026-07-26 계약 전환으로 fast-path를 상담하지 않는다 —
    # 원문 해석 권한은 LLM에만 있다.
    from strategy_conversation import primary

    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "fast_path_first")

    class _MustNotBeCalled:
        def interpret(self, user_input, draft=None):
            raise AssertionError("결정적 fast-path 처리 가능한 입력에 인터프리터가 호출됨")

    monkeypatch.setattr(primary, "_interpreter_singleton", _MustNotBeCalled())
    prev = _rich_parsed().model_dump()
    assert primary.run_primary_modification("손절 10%로 바꿔줘", prev) is None
    # 2026-07-17 사고 입력: 월 포함 명시 날짜 범위도 fast-path가 처리한다
    assert primary.run_primary_modification(
        "백테스트를 2020년 1월 부터 2025년 12월 까지 해줘", prev
    ) is None


def test_modify_primary_explicit_dates_from_patches(monkeypatch):
    # 수정 경로의 명시 날짜는 인터프리터 패치가 옮긴다(2026-07-26 계약 전환 — 이전에는
    # 결정적 추출이 최종 덮어썼다). 모델이 오늘 날짜를 몰라 '2025-12=미래'로 오판하던
    # 사고는 프롬프트 규칙 12 + build_user_prompt의 오늘 날짜 주입이 담당한다.
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "READY", "confidence": 0.9,
        "patches": [
            {"op": "replace", "path": "/backtest/start_date", "value": "2020-01-01"},
            {"op": "replace", "path": "/backtest/end_date", "value": "2025-12-31"},
        ],
    })
    result = run_primary_modification(
        "백테스트를 2020년 1월부터 2025년 12월까지로 하고 진입 조건도 다듬어줘",
        _rich_parsed().model_dump(),
    )
    assert result is not None
    assert result["parsed"].backtest_start_date == "2020-01-01"
    assert result["parsed"].backtest_end_date == "2025-12-31"


def test_primary_parse_explicit_dates_from_llm(monkeypatch):
    """명시 날짜는 LLM이 backtest.start_date/end_date로 산출하고 컴파일러가 그대로 옮긴다.

    2026-07-26 계약 전환: 이전에는 원문 정규식 추출이 최종 진실이었다. 모델이 오늘 날짜를
    몰라 종료일을 미래로 오판하던 사고는 프롬프트 규칙 12 + 오늘 날짜 주입이 담당한다.
    """
    data = _full_intent_dict(
        backtest={"start_date": "2020-01-01", "end_date": "2025-12-31"},
    )
    result = _run_primary_with(
        monkeypatch, data, "PER 10 이하, 백테스트는 2020년 1월부터 2025년 12월까지"
    )
    assert result is not None
    assert result["parsed"].backtest_start_date == "2020-01-01"
    assert result["parsed"].backtest_end_date == "2025-12-31"


def test_primary_parse_explicit_dates_override_when_rolled_back(monkeypatch):
    """롤백 경로 가드 — 보정을 켜면 LLM이 날짜를 비워도 원문 추출이 채운다."""
    monkeypatch.setenv("STRATEGY_PROMPT_OVERRIDE_MODE", "on")
    result = _run_primary_with(
        monkeypatch, _full_intent_dict(),
        "PER 10 이하, 백테스트는 2020년 1월부터 2025년 12월까지",
    )
    assert result is not None
    assert result["parsed"].backtest_start_date == "2020-01-01"
    assert result["parsed"].backtest_end_date == "2025-12-31"


def test_user_prompt_includes_today_grounding():
    # 인터프리터 사용자 프롬프트에 오늘 날짜가 항상 주입된다(과거/미래 오판 방지).
    from datetime import date
    from strategy_conversation.interpreter.prompts import build_user_prompt

    today = date.today().isoformat()
    assert today in build_user_prompt("백테스트 2025년까지")
    assert today in build_user_prompt("백테스트 2025년까지", draft={"portfolio": {}})


def test_modify_primary_clarify_without_questions_falls_back(monkeypatch):
    # CLARIFY인데 질문이 없으면 전달할 내용이 없으므로 기존대로 폴백한다.
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "CLARIFY_STRATEGY", "status": "NEEDS_CLARIFICATION", "confidence": 0.9,
    })
    assert run_primary_modification("음 그게", _rich_parsed().model_dump()) is None


def test_modify_primary_invalid_patch_falls_back(monkeypatch):
    # 출처 인용은 실재하지만(게이트 통과) 경로가 스키마 밖인 패치 → PatchError → 폴백.
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "READY", "confidence": 0.95,
        "patches": [{"op": "replace", "path": "/없는경로/x", "value": 1,
                     "source_text": "수정해줘"}],
    })
    assert run_primary_modification("수정해줘", _rich_parsed().model_dump()) is None


def test_modify_primary_groundless_patch_keeps_strategy_with_notice(monkeypatch):
    # 인용도 수치도 없는 패치("수정해줘"에 임의 값 패치)는 환각으로 전량 거부 —
    # 레거시 원문 파서로 폴백하지 않고 전략 유지+미해석 안내로 응답한다(계약 전환).
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "READY", "confidence": 0.95,
        "patches": [{"op": "replace", "path": "/risk_management/stop_loss", "value": 5}],
    })
    prev = _rich_parsed()
    result = run_primary_modification("수정해줘", prev.model_dump())
    assert result is not None
    assert result["parsed"].model_dump() == prev.model_dump()  # 전략 무변경
    assert any("해석하지 못해" in n for n in result["notices"])
    assert result["interpreter"]["mode"] == "primary_modify_rejected_patches"


def test_operator_token_drift_repaired():
    # 실측(2026-07-16, greedy 결정적): '"operator":">="' → '"operator">="' 붕괴
    broken = ('{"entry_conditions":[{"factor":"fundamental.roe_or_gpa","operator">="value":15},'
              '{"factor":"fundamental.per","operator"><=","value":10}]}')
    fixed = json.loads(extract_json_object(broken))
    assert fixed["entry_conditions"][0]["operator"] == ">="
    assert fixed["entry_conditions"][0]["value"] == 15
    assert fixed["entry_conditions"][1]["operator"] == "<="
    # 올바른 JSON에는 no-op(멱등)
    good = '{"operator":">=","value":15}'
    assert json.loads(extract_json_object(good)) == {"operator": ">=", "value": 15}


# ─── JSON Patch / Draft ──────────────────────────────────────────────────────

def _spec() -> StrategySpec:
    return StrategyIntent.model_validate(_full_intent_dict()).strategy


def test_patch_replace_and_remove():
    spec = _spec()
    patched = apply_patches(spec, [
        PatchOp(op="replace", path="/portfolio/rebalance_frequency", value="quarterly"),
        PatchOp(op="remove", path="/risk_management/stop_loss"),
    ])
    assert patched.portfolio.rebalance_frequency == "quarterly"
    assert patched.risk_management.stop_loss is None
    # 원본 불변
    assert spec.portfolio.rebalance_frequency == "monthly"


def test_patch_array_operations():
    spec = _spec()
    patched = apply_patches(spec, [
        PatchOp(op="add", path="/entry_conditions/-",
                value={"factor": "fundamental.roe_or_gpa", "operator": ">=", "value": 15}),
    ])
    assert len(patched.entry_conditions) == 2
    patched2 = apply_patches(patched, [PatchOp(op="remove", path="/entry_conditions/0")])
    assert len(patched2.entry_conditions) == 1
    assert patched2.entry_conditions[0].factor == "fundamental.roe_or_gpa"


def test_patch_replace_on_append_position_accepted():
    # 실측 드리프트(2026-07-17): 추가 의도를 {"op":"replace","path":".../-"}로 출력 —
    # "-"는 배열 끝이라 의미가 유일하므로 append로 수용
    spec = _spec()
    patched = apply_patches(spec, [
        PatchOp(op="replace", path="/entry_conditions/-",
                value={"factor": "fundamental.pbr", "operator": "<=", "value": 1}),
    ])
    assert patched.entry_conditions[-1].factor == "fundamental.pbr"


def test_patch_invalid_path_rejected():
    with pytest.raises(PatchError):
        apply_patches(_spec(), [PatchOp(op="replace", path="/없는필드/x", value=1)])


def test_patch_schema_violation_rejected():
    with pytest.raises(PatchError):
        apply_patches(_spec(), [
            PatchOp(op="replace", path="/universe/markets", value=["NASDAQ"]),
        ])


def test_draft_store_revision_and_patch():
    store = DraftStore()
    state = store.get_or_create("conv-1")
    state.replace_draft(_spec(), "PER 10 이하")
    assert state.revision == 1
    state.apply_patches(
        [PatchOp(op="replace", path="/portfolio/selection_count", value=5)], "5종목으로"
    )
    assert state.revision == 2
    assert state.current_strategy_draft.portfolio.selection_count == 5


# ─── 출력 복구 루프 (스텁 LLM) ───────────────────────────────────────────────

def test_interpreter_parses_valid_json():
    good = json.dumps(_full_intent_dict(), ensure_ascii=False)
    interp = StrategyInterpreter(chat_fn=lambda s, u: good, model="stub")
    result = interp.interpret("PER 10 이하")
    assert result.intent.intent == "CREATE_STRATEGY"
    assert result.repair_attempts == 0


def test_interpreter_repairs_once_on_bad_output():
    good = json.dumps(_full_intent_dict(), ensure_ascii=False)
    calls = []

    def chat(system, user):
        calls.append(user)
        return "이건 JSON이 아닙니다" if len(calls) == 1 else good

    result = StrategyInterpreter(chat_fn=chat, model="stub").interpret("PER 10 이하")
    assert result.repair_attempts == 1
    assert "잘못된 출력" in calls[1]  # 복구 요청에 실패 출력이 포함된다


def test_interpreter_fails_after_repair_budget():
    interp = StrategyInterpreter(chat_fn=lambda s, u: "no json here", model="stub")
    with pytest.raises(InterpreterError):
        interp.interpret("PER 10 이하")


def test_extract_json_object_from_codefence():
    raw = "```json\n{\"a\": {\"b\": 1}}\n```"
    assert json.loads(extract_json_object(raw)) == {"a": {"b": 1}}


def test_llm_roundtrip_logged_to_console(capsys):
    # LLM 원본 응답을 dev 콘솔에서 눈으로 확인할 수 있어야 한다(사용자 요청 2026-07-17)
    good = json.dumps(_full_intent_dict(), ensure_ascii=False)
    StrategyInterpreter(chat_fn=lambda s, u: good, model="stub").interpret("PER 10 이하")
    out = capsys.readouterr().out
    assert "[LLM-INTERPRETER] ▶ 요청" in out and "PER 10 이하" in out
    assert "[LLM-INTERPRETER] ◀ 원본 응답" in out and '"CREATE_STRATEGY"' in out
    assert "[LLM-INTERPRETER] ✓ 해석" in out


def test_llm_repair_round_logged(capsys):
    good = json.dumps(_full_intent_dict(), ensure_ascii=False)
    calls = []

    def chat(system, user):
        calls.append(user)
        return "깨진 출력" if len(calls) == 1 else good

    StrategyInterpreter(chat_fn=chat, model="stub").interpret("PER 10 이하")
    out = capsys.readouterr().out
    assert "⟳ 복구 요청(1회차)" in out
    assert "◀ 복구 응답(1회차)" in out


# ─── Shadow 러너 ─────────────────────────────────────────────────────────────

def test_shadow_records_diff_and_writes_log(tmp_path, monkeypatch):
    from strategy_conversation import shadow
    from strategy_conversation.interpreter.llm_strategy_interpreter import InterpreterResult

    log_path = tmp_path / "shadow.jsonl"
    monkeypatch.setenv("STRATEGY_INTERPRETER_SHADOW_LOG", str(log_path))

    intent = StrategyIntent.model_validate(_full_intent_dict())

    class _StubInterpreter:
        def interpret(self, user_input, draft=None):
            return InterpreterResult(
                intent=intent, raw_output="{}", repair_attempts=0,
                latency_ms=1.0, model_name="stub",
            )

    monkeypatch.setattr(shadow, "_get_interpreter", lambda: _StubInterpreter())

    legacy = {"universe": ["KOSPI200"], "max_positions": 10}
    record = shadow._run_shadow_sync("PER 10 이하", legacy, "req-test")
    assert record["validation_status"] == "READY"
    assert record["compiler_output"]["max_positions"] == 20
    assert record["field_diff"]["universe"] == {"legacy": ["KOSPI200"], "interpreter": ["KOSPI"]}
    assert log_path.exists()
    logged = json.loads(log_path.read_text().strip())
    assert logged["request_id"] == "req-test"


def test_shadow_disabled_by_default(monkeypatch):
    from strategy_conversation import shadow

    monkeypatch.delenv("STRATEGY_INTERPRETER_MODE", raising=False)
    assert not shadow.shadow_enabled()


# ─── 평가 지표 ───────────────────────────────────────────────────────────────

def test_metrics_false_assumption_and_missing_detection():
    from strategy_conversation.evaluation.metrics import aggregate, evaluate_case

    case = {
        "id": "c1", "category": "missing_value",
        "input": "영업이익률이 높은 기업",
        "expect": {"intent": "CREATE_STRATEGY",
                   "missing_value_factors": ["fundamental.operating_margin"]},
    }
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "fundamental.operating_margin", "operator": ">=",
                           "value": None}],
    ))
    _, report = run_validation(intent)
    outcome = {
        "intent_dump": intent.model_dump(),
        "report_dump": report.model_dump(),
        "latency_ms": 100, "repair_attempts": 0,
    }
    result = evaluate_case(case, outcome)
    assert result["checks"]["no_false_assumption"]
    assert result["checks"]["missing_detected"]
    summary = aggregate([result], [outcome])
    assert summary["false_assumption_rate"] == 0.0
    assert summary["missing_field_detection_recall"] == 1.0


# ─── ETF 유니버스 (2026-07-19) ────────────────────────────────────────────────


def test_etf_universe_markets_exclusive():
    """ETF는 주식 시장과 혼합하지 않는 독립 유니버스다 — LLM이 섞어 내도 단독 정규화."""
    intent = StrategyIntent.model_validate(_full_intent_dict(
        universe={"markets": ["KOSPI", "ETF"], "sectors": []},
        entry_conditions=[{"factor": "technical.rsi", "operator": "<=", "value": 30,
                           "source_text": "RSI 30 이하"}],
    ))
    assert intent.strategy.universe.markets == ["ETF"]


def test_etf_universe_rejects_fundamental_factor_with_alternative():
    """ETF × 기업 재무지표: 조용히 제거하지 않고 오류 + 기술 지표 대안 제안."""
    intent = StrategyIntent.model_validate(_full_intent_dict(
        universe={"markets": ["ETF"], "sectors": []},
    ))  # 기본 entry: fundamental.per
    _, report = run_validation(intent)
    assert any("재무지표" in e and "ETF" in e for e in report.errors)
    assert any("기술 지표" in f or "이동평균" in f for f in report.suggested_fixes)
    assert not report.is_valid


def test_etf_universe_accepts_technical_and_clears_sectors():
    """ETF + 기술 지표는 통과하고, 종목 섹터 분류는 비운다(테마는 etf_theme 담당)."""
    intent = StrategyIntent.model_validate(_full_intent_dict(
        universe={"markets": ["ETF"], "sectors": ["반도체"]},
        entry_conditions=[{"factor": "technical.rsi", "operator": "<=", "value": 30,
                           "source_text": "RSI 30 이하"}],
    ))
    validated, report = run_validation(intent)
    assert validated.strategy.universe.markets == ["ETF"]
    assert validated.strategy.universe.sectors == []
    # 드리프트로 sectors에 들어온 테마는 조용히 버리지 않고 etf_theme로 승격한다
    assert validated.strategy.universe.etf_theme == "반도체"
    assert not any("재무지표" in e for e in report.errors)


def test_etf_theme_is_not_unsupported_and_compiles_to_etf_theme():
    """ETF 테마('반도체 종목 ETF')는 미지원 개념이 아니라 etf_theme로 컴파일된다.

    회귀: LLM이 'ETF의 산업별 구성(반도체) 확인 불가'로 unsupported_features에 넣어
    테마가 전략에서 통째로 빠지던 버그(어순상 인접 추출도 놓치는 케이스).
    """
    intent = StrategyIntent.model_validate(_full_intent_dict(
        universe={"markets": ["ETF"], "etf_theme": "반도체"},
        entry_conditions=[{"factor": "technical.rsi", "operator": "<=", "value": 30,
                           "source_text": "RSI 30 이하"}],
    ))
    validated, report = run_validation(intent)
    assert not report.unsupported_features
    assert report.is_valid
    parsed = compile_strategy(validated, report, "반도체 종목 ETF를 골라줘")
    assert parsed.universe == ["ETF"]
    assert parsed.etf_theme == "반도체"
    assert parsed.sector is None


# ─── 섹터 보정 후 인터프리터 질문/미지원 안내 정리(FR-STR-069 파싱 경로) ────────────

def test_prune_sector_question_when_deterministic_sector_filled():
    """결정적 섹터 보정(검색 그라운딩 학습분 포함)이 채운 업종 질문은 제거된다.

    '마운자로 관련주' — 인터프리터 LLM은 업종을 몰라 universe.sectors 질문을 냈지만,
    오버라이드가 섹터를 채웠으면 같은 걸 다시 되묻지 않는다(다른 질문은 유지)."""
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.interpreter.models import (
        ClarificationQuestion,
        ValidationReport,
    )
    from strategy_conversation.primary import _prune_clarifications_filled_by_overrides

    def make_report():
        return ValidationReport(clarification_questions=[
            ClarificationQuestion(field="strategy.universe.sectors",
                                  question="어떤 업종을 대상으로 할까요?"),
            ClarificationQuestion(field="strategy.portfolio.selection_count",
                                  question="몇 종목을 보유할까요?"),
        ])

    filled = ParsedStrategy.model_validate({
        "description": "마운자로 관련주 전략", "universe": ["KOSPI", "KOSDAQ"],
        "sector": "바이오/제약",
    })
    report = make_report()
    _prune_clarifications_filled_by_overrides(report, filled)
    assert [q.field for q in report.clarification_questions] == [
        "strategy.portfolio.selection_count"
    ]

    # 섹터 미해석이면 업종 질문은 그대로 남는다
    unfilled = ParsedStrategy.model_validate({
        "description": "마운자로 관련주 전략", "universe": ["KOSPI", "KOSDAQ"],
    })
    report2 = make_report()
    _prune_clarifications_filled_by_overrides(report2, unfilled)
    assert len(report2.clarification_questions) == 2
