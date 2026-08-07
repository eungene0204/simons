"""클래스(분류) 발화 되묻기 — Phase B (프롬프트 2.9 계약).

사용자가 "모멘텀 지표 하나"처럼 계열만 말하면 LLM이 온톨로지 분류 ID(class.*)를
factor로 출력하고, 시스템이 구체 지표를 대신 고르지 않고 선택지를 들어 되묻는다.
분류 조건은 오류·미지원이 아니라 **선택 대기**다(값 대기 조건과 같은 축):
capability 통과 → completeness가 .factor 누락+질문 → compile_partial이
pending_conditions로 제외 → 답변은 수정 인터프리터 레인이 처리(칩 없음 —
지표 선택 칩은 값 결속 계약이 성립하지 않아 노출 금지).
"""

from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.registry.concept_ontology import class_choice, is_class_id
from strategy_conversation.validation.field_state import slot_status_overrides
from strategy_conversation.validation.pipeline import run_validation


def _class_intent(factor="class.oscillator", source_text="모멘텀 지표", **strategy_overrides):
    strategy = {
        "universe": {"markets": ["KOSPI"], "sectors": []},
        "entry_conditions": [
            {"factor": factor, "operator": None, "value": None, "source_text": source_text}
        ],
        "exit_conditions": [],
        "ranking": [],
        "portfolio": {"selection_count": 10, "rebalance_frequency": "monthly"},
        "risk_management": {"stop_loss": 8},
        "backtest": {},
    }
    strategy.update(strategy_overrides)
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 0.9, "strategy": strategy,
    })


# ─── 온톨로지 헬퍼 ──────────────────────────────────────────────────────────────

def test_is_class_id():
    assert is_class_id("class.oscillator")
    assert not is_class_id("technical.rsi")
    assert not is_class_id("class.없는분류")
    assert not is_class_id(None)
    assert not is_class_id("")


def test_class_choice_direct_leaves():
    """직속 지원 잎이 있는 분류 — 잎 표시명(괄호 설명 제거) 목록."""
    name, options = class_choice("class.oscillator")
    assert name == "모멘텀/오실레이터"
    assert "RSI" in options and "스토캐스틱" in options
    assert all("(" not in o for o in options)


def test_class_choice_parent_descends_to_child_classes():
    """중간 분류(직속 잎 없음) — 지원 잎을 품은 자식 분류명 목록."""
    name, options = class_choice("class.technical")
    assert name == "기술 지표"
    assert "이동평균" in options and "모멘텀/오실레이터" in options
    # 지원 잎이 없는 분기는 선택지에 없어야 한다(고를 수 없는 선택지 노출 금지)
    assert options  # 비어 있지 않음


def test_class_choice_unknown_returns_none():
    assert class_choice("technical.rsi") is None


# ─── 검증 레인 ──────────────────────────────────────────────────────────────────

def test_capability_keeps_class_factor_without_error():
    """분류 발화는 '알 수 없는 지표' 오류·미지원이 아니다 — 선택 대기."""
    validated, report = run_validation(_class_intent())
    assert not any("class.oscillator" in e for e in report.errors)
    assert "class.oscillator" not in report.unsupported_features
    # 조건은 보존된다(조용한 드롭 금지)
    assert validated.strategy.entry_conditions[0].factor == "class.oscillator"


def test_completeness_asks_indicator_choice_with_options():
    """되묻기 질문에 사용자 원문 인용 + 분류명 + 선택지가 실린다."""
    _, report = run_validation(_class_intent())
    assert any(f.endswith("entry_conditions[0].factor") for f in report.missing_fields)
    q = next(
        q for q in report.clarification_questions if q.field.endswith(".factor")
    )
    assert "'모멘텀 지표'" in q.question
    # 역할(진입/청산)이 질문에 명시된다 — 답변 패치의 배열 귀속 근거(규칙 10-4)
    assert "진입 조건에" in q.question
    assert "모멘텀/오실레이터" in q.question
    assert "RSI" in q.question
    # 구체 지표를 대신 확정하지 않는다 — 추천값 없음
    assert q.recommended_value is None


def test_completeness_question_without_source_text():
    _, report = run_validation(_class_intent(source_text=None))
    q = next(
        q for q in report.clarification_questions if q.field.endswith(".factor")
    )
    assert q.question.startswith("진입 조건에 어떤 ")


def test_compile_partial_excludes_class_condition_as_pending():
    """분류 조건은 컴파일에서 제외되고 pending_conditions에 실린다(라벨=원문)."""
    validated, report = run_validation(_class_intent())
    parsed, dropped, pending = compile_partial(validated, report, "모멘텀 지표 하나로 매수")
    assert "모멘텀 지표" in dropped
    assert any(p["label"] == "모멘텀 지표" and p["role"] == "entry" for p in pending)
    # 컴파일 결과에는 들어가지 않는다
    assert not parsed.entry_signals
    assert not parsed.fundamental_filters


def test_pending_label_falls_back_to_class_korean_name():
    """source_text가 없으면 내부 식별자(oscillator) 대신 한글 분류명을 라벨로 쓴다."""
    validated, report = run_validation(_class_intent(source_text=None))
    _, dropped, pending = compile_partial(validated, report, "지표 전략")
    assert "모멘텀/오실레이터 지표" in dropped
    assert not any("oscillator" == p["label"] for p in pending)


def test_field_state_class_factor_is_not_invalid():
    """분류 발화 조건은 INVALID(엔진 실행 불가)로 강등되지 않는다 — 선택 대기 축."""
    validated, report = run_validation(_class_intent())
    overrides = slot_status_overrides(validated.strategy, report)
    assert "entry_signals" not in overrides


def test_leaf_factor_flow_unchanged():
    """잎 지표 경로 회귀 가드 — 분류 분기 추가가 기존 값 되묻기를 바꾸지 않는다."""
    intent = _class_intent(
        entry_conditions=[{"factor": "technical.rsi", "operator": "<=", "value": None,
                           "source_text": "RSI가 낮은"}],
    )
    _, report = run_validation(intent)
    assert any(f.endswith("entry_conditions[0].value") for f in report.missing_fields)
    assert not any(f.endswith(".factor") for f in report.missing_fields)


# ─── 프롬프트 계약 ──────────────────────────────────────────────────────────────

def test_prompt_declares_class_output_rule():
    """2.9 — 계열 발화는 class.* 출력, 구체 지표 발화는 잎 ID(과사용 금지) 계약."""
    from strategy_conversation.interpreter.prompts import PROMPT_VERSION, build_system_prompt

    assert PROMPT_VERSION >= "2.9"
    prompt = build_system_prompt()
    assert "계열만" in prompt
    assert '"factor":"class.oscillator"' in prompt  # 예시 1-1
    assert "구체 지표를 대신 골라 확정하지 마세요" in prompt
    # 규칙 10-4 — 되묻기 답변은 잎 ID 패치(class.* 금지, 임의 임계값 금지)
    assert "구체 지표를 고르는 되묻기" in prompt
