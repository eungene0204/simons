"""검증 파이프라인 — LLM 출력(StrategyIntent) 이후의 결정론 검증 계층을 순서대로 실행.

  1. (JSON 파싱·Pydantic 스키마 검증은 interpreter가 수행)
  2. Intent 검증
  3. Indicator Registry / Capability 검증 (factor canonical 정규화 포함)
  4. Parameter/단위 범위 검증
  5. 논리 충돌 검증
  6. Completeness 검증 (누락 필수값 → 되묻기 질문)

규제 정책 게이팅(추천/전망 차단)은 상류 intent 분류(intent/scope.py 등)가 담당한다 —
이 파이프라인은 '실행 가능한 전략 서술'만 다룬다.

confidence는 상태 판정·사용자 노출에 쓰지 않는다(4B가 자주 누락해 0.0이 되는
신뢰 불가 신호) — 텔레메트리로만 남긴다. 검증은 confidence와 무관하게 항상 수행.
"""

from __future__ import annotations

from typing import Tuple

from strategy_conversation.interpreter.models import StrategyIntent, ValidationReport
from strategy_conversation.validation.capability_validator import validate_capability
from strategy_conversation.validation.completeness_validator import validate_completeness
from strategy_conversation.validation.conflict_validator import validate_conflicts
from strategy_conversation.validation.parameter_validator import validate_parameters

_STRATEGY_INTENTS = ("CREATE_STRATEGY", "MODIFY_STRATEGY", "CLARIFY_STRATEGY")


def run_validation(intent: StrategyIntent) -> Tuple[StrategyIntent, ValidationReport]:
    """검증을 실행하고 (정규화된 intent, 통합 리포트)를 반환한다.

    intent.strategy의 factor/주기 등은 canonical 형태로 제자리 정규화된다.
    """
    intent = intent.model_copy(deep=True)
    report = ValidationReport()

    # ── Intent 검증
    if intent.intent not in _STRATEGY_INTENTS:
        # 전략 파이프라인 대상이 아닌 의도 — 유효하지만 컴파일 대상 아님
        report.is_valid = False
        report.status = "UNSUPPORTED" if intent.intent == "UNSUPPORTED_REQUEST" else "REJECTED"
        return intent, report
    if intent.intent == "CREATE_STRATEGY" and intent.strategy is None:
        report.errors.append("CREATE_STRATEGY 의도인데 strategy가 없습니다")
    if intent.intent == "MODIFY_STRATEGY" and intent.strategy is None and not intent.patches:
        report.errors.append("MODIFY_STRATEGY 의도인데 strategy도 patches도 없습니다")

    # ── Capability / Registry
    cap_errors, cap_warnings, unsupported, fixes = validate_capability(intent)
    report.errors.extend(cap_errors)
    report.warnings.extend(cap_warnings)
    report.unsupported_features.extend(unsupported)
    report.suggested_fixes.extend(fixes)

    # LLM이 스스로 보고한 unsupported_features도 합친다(중복 제거)
    for feat in intent.unsupported_features:
        if feat not in report.unsupported_features:
            report.unsupported_features.append(feat)

    # ── 유니버스 지정 종목 해석 가능성 — 컴파일러의 registry 해석이 실패할 표현을 조용히
    # 흘려보내지 않는다(계약 § 3: 해석 실패는 반환·기록). 실행을 막지는 않으므로 warning
    # (→ primary notices 채널)으로 알린다. 업종/테마 미해석은 별도 그라운딩 체인
    # (sector_unresolved 되묻기·검색 학습)이 소유하므로 여기서 다루지 않는다.
    if intent.strategy is not None and intent.strategy.universe.symbols:
        from strategy_conversation.registry.universe_resolver import resolve_symbols

        _, unresolved_symbols = resolve_symbols(intent.strategy.universe.symbols)
        for term in unresolved_symbols:
            report.warnings.append(
                f"'{term}'은(는) 종목으로 인식되지 않아 전략에 반영하지 못했어요. "
                "정확한 종목명이나 6자리 종목코드로 다시 말씀해 주세요."
            )

    # ── Parameter 범위/단위
    report.errors.extend(validate_parameters(intent))

    # ── 논리 충돌
    conflict_errors, conflict_warnings = validate_conflicts(intent)
    report.errors.extend(conflict_errors)
    report.warnings.extend(conflict_warnings)

    # ── Completeness (누락 → 질문)
    missing, questions = validate_completeness(intent)
    report.missing_fields.extend(missing)
    report.clarification_questions.extend(questions)
    # LLM이 스스로 생성한 질문은 결정론 검증이 지적한 누락 필드와 일치할 때만 채택한다 —
    # "전략 이름 붙여드릴까요?"·"확신이 낮은데 확인해 주시겠어요?" 류의 잉여/자기회의 질문을
    # 사용자에게 노출하지 않는다(사고 2026-07-17). 의도 해석 책임은 시스템에 있고, 사용자에게
    # 묻는 건 실행에 필요한 값이 실제로 비었을 때뿐이다.
    known_fields = {q.field for q in report.clarification_questions}
    for q in intent.clarification_questions:
        if q.field and q.field in report.missing_fields and q.field not in known_fields:
            report.clarification_questions.append(q)
            known_fields.add(q.field)

    # ── 최종 상태 판정. confidence는 사용자 노출/상태 판정에 쓰지 않는다 — 4B가 자주
    # 누락해 0.0이 되는 신뢰 불가 신호다. 텔레메트리(runtime.interpreter 메타)로만 남긴다.
    if report.unsupported_features and not report.missing_fields and not report.errors:
        report.status = "UNSUPPORTED"
    elif report.errors or report.missing_fields:
        report.status = "NEEDS_CLARIFICATION"
    else:
        report.status = "READY"

    report.is_valid = report.status == "READY"
    # READY면 되묻을 것이 없다 — LLM이 관성으로 낸 잉여 질문(전략 이름 등)을 제거한다.
    # NEEDS_CLARIFICATION이면 병합된 질문 전체에 턴당 상한을 적용한다.
    if report.is_valid:
        report.clarification_questions = []
    else:
        from strategy_conversation.validation.completeness_validator import (
            MAX_QUESTIONS_PER_TURN,
        )
        report.clarification_questions = report.clarification_questions[:MAX_QUESTIONS_PER_TURN]
    return intent, report
