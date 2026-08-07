"""합성 개념 결정적 전개 — Phase C (프롬프트 3.0 계약).

LLM은 관용 표현을 개념 ID로만 착지시키고(골든크로스 → concept.golden_cross),
연산자·정본 기간(5/20)의 조립은 capability_validator가 온톨로지 선언대로 물질화한다.
연산자 표기 드리프트("golden_cross"·"above")와 파라미터 드리프트(2026-07-30 사고류)를
LLM 손에서 떼어내는 단계다. 사용자가 말한 기간은 전개 기본값보다 우선한다.
"""

from strategy_conversation.compiler.strategy_compiler import compile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation


def _intent(entry=None, exit_=None):
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 0.9,
        "strategy": {
            "universe": {"markets": ["KOSPI"], "sectors": []},
            "entry_conditions": entry or [],
            "exit_conditions": exit_ or [],
            "ranking": [],
            "portfolio": {"selection_count": 10, "rebalance_frequency": "monthly"},
            "risk_management": {"stop_loss": 8},
            "backtest": {},
        },
    })


def test_parameterless_golden_cross_expands_to_canonical():
    """기간 없는 골든크로스 → ma_crossover crosses_above 5/20 물질화, 되묻기 없음."""
    validated, report = run_validation(_intent(
        entry=[{"factor": "concept.golden_cross", "operator": None, "value": None,
                "source_text": "골든크로스 매수"}],
    ))
    cond = validated.strategy.entry_conditions[0]
    assert cond.factor == "technical.ma_crossover"
    assert cond.operator == "crosses_above"
    assert cond.parameters["short_period"] == 5
    assert cond.parameters["long_period"] == 20
    assert report.status == "READY"
    parsed = compile_strategy(validated, report, "골든크로스 매수 전략")
    assert len(parsed.entry_signals) == 1


def test_user_periods_override_expansion_defaults():
    """사용자가 말한 기간(20/60)이 정본 기본값(5/20)보다 우선한다."""
    validated, _ = run_validation(_intent(
        entry=[{"factor": "concept.golden_cross", "operator": None, "value": None,
                "parameters": {"short_period": 20, "long_period": 60},
                "source_text": "20일선이 60일선을 골든크로스"}],
    ))
    cond = validated.strategy.entry_conditions[0]
    assert cond.factor == "technical.ma_crossover"
    assert cond.parameters == {"short_period": 20, "long_period": 60}


def test_declared_operator_overrides_llm_drift():
    """전개 연산자는 선언이 정본 — LLM이 엉뚱한 연산자를 내도 덮어쓴다(드리프트 정규화)."""
    validated, _ = run_validation(_intent(
        entry=[{"factor": "concept.golden_cross", "operator": "crosses_below",
                "value": None, "source_text": "골든크로스"}],
    ))
    assert validated.strategy.entry_conditions[0].operator == "crosses_above"


def test_dead_cross_exit_passes_exit_role_rule():
    """청산의 데드크로스 전개는 technical_signal이라 청산 역할 규칙을 통과한다."""
    validated, report = run_validation(_intent(
        entry=[{"factor": "concept.golden_cross", "operator": None, "value": None,
                "source_text": "골든크로스 매수"}],
        exit_=[{"factor": "concept.dead_cross", "operator": None, "value": None,
                "source_text": "데드크로스 매도"}],
    ))
    cond = validated.strategy.exit_conditions[0]
    assert cond.factor == "technical.ma_crossover"
    assert cond.operator == "crosses_below"
    assert report.status == "READY"
    parsed = compile_strategy(validated, report, "골든크로스 매수 데드크로스 매도")
    assert len(parsed.exit_signals) == 1


def test_partial_user_period_fills_only_missing():
    """기간 절반만 말한 경우 — 말한 값 보존, 빈 자리만 정본으로 채운다."""
    validated, _ = run_validation(_intent(
        entry=[{"factor": "concept.golden_cross", "operator": None, "value": None,
                "parameters": {"long_period": 120}, "source_text": "골든크로스"}],
    ))
    cond = validated.strategy.entry_conditions[0]
    assert cond.parameters["long_period"] == 120
    assert cond.parameters["short_period"] == 5


def test_macd_golden_cross_expands_without_params():
    """MACD 골든크로스 → technical.macd crosses_above, 파라미터 없음(12/26/9 고정)."""
    validated, report = run_validation(_intent(
        entry=[{"factor": "concept.macd_golden_cross", "operator": None, "value": None,
                "source_text": "MACD 골든크로스"}],
    ))
    cond = validated.strategy.entry_conditions[0]
    assert cond.factor == "technical.macd"
    assert cond.operator == "crosses_above"
    assert cond.parameters == {}
    assert report.status == "READY"


def test_macd_echoed_fixed_params_dropped_silently():
    """9B가 고정 기본값(12/26/9)을 습관적으로 echo하는 드리프트(2.7부터 실측) —
    의미 손실 0이므로 조용히 정리하고 안내·오류를 내지 않는다(질문 없는
    NEEDS_CLARIFICATION 사고의 해소)."""
    validated, report = run_validation(_intent(
        entry=[{"factor": "concept.macd_golden_cross", "operator": None, "value": None,
                "parameters": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
                "source_text": "MACD 골든크로스"}],
    ))
    assert validated.strategy.entry_conditions[0].parameters == {}
    assert report.status == "READY"
    assert not report.errors
    assert not any("커스텀" in w for w in report.warnings)


def test_macd_custom_periods_dropped_with_notice():
    """사용자가 커스텀 기간을 말한 경우(고정값과 다름) — 조용히 버리지 않고 안내한다."""
    validated, report = run_validation(_intent(
        entry=[{"factor": "concept.macd_golden_cross", "operator": None, "value": None,
                "parameters": {"fast_period": 5, "slow_period": 35, "signal_period": 5},
                "source_text": "MACD 5/35/5 골든크로스"}],
    ))
    assert validated.strategy.entry_conditions[0].parameters == {}
    assert not report.errors
    assert any("커스텀이 지원되지 않아" in w for w in report.warnings)


def test_macd_dead_cross_exit_expands():
    validated, report = run_validation(_intent(
        entry=[{"factor": "concept.golden_cross", "operator": None, "value": None,
                "source_text": "골든크로스 매수"}],
        exit_=[{"factor": "concept.macd_dead_cross", "operator": None, "value": None,
                "source_text": "MACD 데드크로스 매도"}],
    ))
    cond = validated.strategy.exit_conditions[0]
    assert cond.factor == "technical.macd"
    assert cond.operator == "crosses_below"
    assert report.status == "READY"


def test_unknown_concept_id_still_errors():
    """온톨로지에 없는 concept.* 표기는 전개 없이 기존 '알 수 없는 지표' 경로."""
    _, report = run_validation(_intent(
        entry=[{"factor": "concept.없는개념", "operator": None, "value": None}],
    ))
    assert any("concept.없는개념" in e for e in report.errors)
