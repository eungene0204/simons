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
    from strategy_conversation.primary import primary_enabled

    monkeypatch.delenv("STRATEGY_INTERPRETER_MODE", raising=False)
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
    from strategy_conversation import primary

    monkeypatch.setattr(primary, "_interpreter_singleton", _StubPrimaryInterpreter(intent_data))


def test_modify_primary_applies_patches(monkeypatch):
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY",
        "status": "READY",
        "confidence": 0.95,
        "patches": [
            {"op": "replace", "path": "/entry_conditions/0/value", "value": 20},
            {"op": "remove", "path": "/entry_conditions/1"},
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


def test_modify_primary_invalid_patch_falls_back(monkeypatch):
    from strategy_conversation.primary import run_primary_modification

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "READY", "confidence": 0.95,
        "patches": [{"op": "replace", "path": "/없는경로/x", "value": 1}],
    })
    assert run_primary_modification("수정해줘", _rich_parsed().model_dump()) is None


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
