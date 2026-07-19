"""Primary Mode (Phase 2) — LLM Interpreter를 초기 파스의 기본 경로로 승격.

STRATEGY_INTERPRETER_MODE=primary일 때 main.py 초기 파스가 이 모듈을 먼저 시도한다.
None을 반환하면 호출부가 기존 규칙 파서 경로(하이브리드)로 폴백한다:
  - LLM 호출/JSON 복구 실패
  - 전략 파이프라인 대상이 아닌 intent(비전략·설명·추천 요청 — 상류 분류기 소관)
  - strategy 본문 없음 / 컴파일 실패

READY면 전체 컴파일, NEEDS_CLARIFICATION이면 **미확정 조건을 제외한 부분 컴파일**
(조용한 기본값 확정 금지) + 되묻기 질문·추천값 칩을 기존 clarification 채널로 전달.
칩 텍스트("영업이익률 10% 이상")는 클릭 시 일반 수정 메시지로 재전송되어 기존
modify 경로(결정적 병합)가 조건을 채운다 — condition_builder와 동일한 무상태 패턴.

수정(modify) 경로는 Phase 2에서 기존 하이브리드를 유지한다(QA 실측 26/26 경로 보존,
대화 상태는 기존 아키텍처대로 프론트의 previous_parsed가 소유).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from strategy_conversation import config
from strategy_conversation.interpreter.llm_strategy_interpreter import _log_llm
from strategy_conversation.interpreter.models import StrategyIntent, ValidationReport
from strategy_conversation.registry.indicator_registry import REGISTRY

logger = logging.getLogger("strategy_interpreter.primary")

_STRATEGY_INTENTS = ("CREATE_STRATEGY", "MODIFY_STRATEGY", "CLARIFY_STRATEGY")


def primary_enabled() -> bool:
    return config.interpreter_mode() == "primary"


def _build_clarification(
    report: ValidationReport, intent: StrategyIntent
) -> tuple[Optional[str], Optional[List[str]]]:
    """검증 리포트의 질문들을 기존 clarification 채널(질문 텍스트 + 칩)로 변환한다."""
    if not report.clarification_questions:
        return None, None
    lines: List[str] = []
    chips: List[str] = []
    strategy = intent.strategy
    conditions_by_field: Dict[str, Any] = {}
    if strategy is not None:
        for path, conds in (("entry_conditions", strategy.entry_conditions),
                            ("exit_conditions", strategy.exit_conditions)):
            for i, cond in enumerate(conds):
                conditions_by_field[f"strategy.{path}[{i}].value"] = cond
    for q in report.clarification_questions:
        line = q.question
        if q.recommended_value is not None and q.recommendation_reason:
            line += f" ({q.recommendation_reason})"
        lines.append(line)
        # 조건 임계값 질문 → "영업이익률 10% 이상" 칩(수정 메시지로 재전송 가능한 형태)
        cond = conditions_by_field.get(q.field)
        if cond is not None and q.recommended_value is not None:
            spec = REGISTRY.get(cond.factor)
            if spec is not None:
                unit = {"percent": "%", "ratio": "배", "억원": "억원"}.get(spec.value_type or "", "")
                direction = "이하" if (cond.operator or "").startswith("<") else "이상"
                # display_name의 괄호 설명은 칩에서 제거해 수정 파서 어휘와 맞춘다
                name = spec.display_name.split("(")[0]
                chips.append(f"{name} {q.recommended_value:g}{unit} {direction}")
    return "\n".join(lines), (chips or None)


def _override_explicit_dates(parsed, user_input: str):
    """명시적 백테스트 날짜 범위를 결정적으로 덮어쓴다(레거시 _apply_prompt_overrides와 동형).

    "2020년 1월부터 2025년 12월까지"처럼 사용자가 못박은 날짜는 LLM이 놓치거나 오판해도
    (오늘 날짜를 모르는 모델이 과거 연도를 미래로 오판해 종료일을 누락하는 사고 등) 보장돼야
    한다. 언급이 없으면 기존 값을 유지한다.
    """
    from engine.nl_parser import _extract_backtest_dates

    start, end = _extract_backtest_dates(user_input)
    updates: Dict[str, Any] = {}
    if start is not None:
        updates["backtest_start_date"] = start
    if end is not None:
        updates["backtest_end_date"] = end
    return parsed.model_copy(update=updates) if updates else parsed


def _override_target_symbols(parsed, user_input: str):
    """지정 종목(FR-STR-068)을 결정적으로 채운다(레거시 _apply_prompt_overrides와 동형).

    StrategySpec에는 지정 종목 개념이 없어 "삼성전자 골든크로스"가 유니버스 전략으로
    조용히 넓어진다 — 종목명→코드 해석은 LLM에 맡기지 않고 결정적 추출이 보장한다.
    '~가 속한 업종'류 문맥 가드는 _extract_target_symbols가 이미 적용하며,
    언급이 없으면 기존 값을 유지한다.
    """
    from engine.nl_parser import _extract_target_symbols

    refs = _extract_target_symbols(user_input)
    if not refs:
        return parsed
    return parsed.model_copy(update={"target_symbols": [ref.symbol for ref in refs]})


def run_primary_parse(user_input: str, on_stage=None) -> Optional[Dict[str, Any]]:
    """LLM Interpreter 기본 경로 실행. 성공 시 결과 dict, 폴백 필요 시 None.

    반환: {"parsed": ParsedStrategy, "clarification_question": str|None,
           "clarification_suggestions": [str]|None, "notices": [str],
           "interpreter": 관측 메타}
    """
    from strategy_conversation.compiler.strategy_compiler import (
        StrategyCompileError,
        compile_partial,
        compile_strategy,
    )
    from strategy_conversation.interpreter.llm_strategy_interpreter import (
        InterpreterError,
        StrategyInterpreter,
    )
    from strategy_conversation.validation.pipeline import run_validation

    if on_stage is not None:
        on_stage("thinking")
    try:
        interpreter = _get_interpreter(StrategyInterpreter)
        result = interpreter.interpret(user_input)
    except InterpreterError as exc:
        logger.warning("interpreter primary failed, falling back to rule parser | err=%s",
                       str(exc)[:200])
        return None
    except Exception as exc:  # noqa: BLE001 — 연결 실패 등도 폴백(기존 경로가 503 처리)
        logger.warning("interpreter primary transport error, falling back | err=%r", exc)
        return None

    validated, report = run_validation(result.intent)
    _log_llm("✓ 검증", (
        f"status={report.status} 오류={len(report.errors)} 누락={len(report.missing_fields)} "
        f"질문={len(report.clarification_questions)} 미지원={report.unsupported_features or '[]'}"
    ))
    if validated.intent not in _STRATEGY_INTENTS or validated.strategy is None:
        _log_llm("↩ 폴백", f"전략 파이프라인 대상이 아닌 intent={validated.intent} — 규칙 파서로")
        logger.info("interpreter primary non-strategy intent=%s, falling back",
                    validated.intent)
        return None

    notices: List[str] = list(report.warnings)
    try:
        if report.is_valid:
            parsed = compile_strategy(validated, report, user_input)
            dropped: List[str] = []
        else:
            parsed, dropped = compile_partial(validated, report, user_input)
    except StrategyCompileError as exc:
        logger.warning("interpreter primary compile failed, falling back | err=%s", exc)
        return None
    parsed = _override_explicit_dates(parsed, user_input)
    parsed = _override_target_symbols(parsed, user_input)
    if parsed.target_symbols:
        # 지정 종목 전략의 청산 누락은 호출부 공유 보정(apply_single_asset_adjustments)이
        # 반대 신호 청산 추천/기간 종료 보유 안내(비차단 notices)로 처리한다(FR-STR-068) —
        # 정기 리밸런싱을 추천하는 유니버스형 되묻기 질문은 지정 종목에 맞지 않아 제거한다.
        report.clarification_questions = [
            q for q in report.clarification_questions
            if q.field != "strategy.exit_conditions"
        ]

    clarification_question, clarification_suggestions = _build_clarification(report, validated)
    if report.unsupported_features:
        features = ", ".join(dict.fromkeys(report.unsupported_features))
        notices.append(
            f"'{features}' 조건은 현재 지원되지 않아 전략에 반영되지 않았어요."
            + (" " + " ".join(report.suggested_fixes) if report.suggested_fixes else "")
        )
    # 제외됐지만 질문/미지원 안내가 다루지 않는 조건이 있으면 정직하게 알린다
    unexplained_drops = [d for d in dropped if d not in " ".join(
        [clarification_question or ""] + notices
    )]
    if unexplained_drops:
        notices.append(
            f"'{', '.join(unexplained_drops)}' 조건은 값 확인 전까지 전략에 반영되지 않았어요."
        )

    return {
        "parsed": parsed,
        "clarification_question": clarification_question,
        "clarification_suggestions": clarification_suggestions,
        "notices": notices,
        "interpreter": {
            "mode": "primary",
            "model_name": result.model_name,
            "prompt_version": result.prompt_version,
            "repair_attempts": result.repair_attempts,
            "llm_latency_ms": result.latency_ms,
            "validation_status": report.status,
            "confidence": validated.confidence,
        },
    }


def run_primary_modification(user_input: str, previous_parsed: dict, on_stage=None) -> Optional[Dict[str, Any]]:
    """수정 요청의 LLM Interpreter 기본 경로. 성공 시 결과 dict, 폴백 필요 시 None.

    안전 장치(전부 결정론):
    ① 라운드트립 가드 — 기존 전략을 decompile→재compile(+이월)했을 때 원본과 1비트라도
       다르면 StrategySpec이 표현 못 하는 전략(rsi rebound/macd zero 모드 등)이므로 이관을
       거부하고 기존 modify 경로로 폴백한다(목록형 필드 소실 사고 방지의 구조적 보장).
    ② patches 필수 — LLM이 전체 전략을 재출력하면(필드 소실 위험) 수락하지 않는다.
       예외: CLARIFY_STRATEGY(패치 없음)+질문이 있고 결정적 fast-path도 처리 못 하는
       입력이면, 폴백해 질문을 버리는 대신 전략을 그대로 유지한 채 질문을 clarification
       채널로 전달한다(무변경 요약만 재렌더링되던 2026-07-17 사고 방지).
       예외 2: 패치 없이 EXPLAIN_INDICATOR거나 unsupported_features만 보고된 경우도
       폴백하지 않고 전략을 유지한다(같은 사고의 2차 — 인터프리터가 질문 대신
       unsupported_features=["PBR 개념 설명 요청"]으로 보고). 정의형 질문(결정적 cue)이면
       /query/general과 같은 LLM 설명을 notices로 실제 답변하고, 아니면 미반영을 알린다.
    ③ 패치 적용 후 검증 READY일 때만 컴파일. 아니면 폴백(임계값 없는 조건 추가 등은
       상류 clarification_for_add가 이미 가로챈다).
    description·execution_timing·entry_filters는 StrategySpec 밖이므로 원본에서 이월.
    """
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.compiler.strategy_compiler import (
        StrategyCompileError,
        compile_strategy,
    )
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.conversation.patch_applier import PatchError, apply_patches
    from strategy_conversation.interpreter.llm_strategy_interpreter import (
        InterpreterError,
        StrategyInterpreter,
    )
    from strategy_conversation.interpreter.models import StrategyIntent as _Intent
    from strategy_conversation.validation.pipeline import run_validation

    try:
        prev = ParsedStrategy.model_validate(previous_parsed)
    except Exception:  # noqa: BLE001 — 비정상 previous는 기존 경로가 처리
        return None

    # 결정적 fast-path가 완전히 해석하는 수정("손절 10%로", 명시적 백테스트 기간 등)은
    # 인터프리터를 건너뛴다 — 폴백 경로(parse_modification)의 첫 단계가 같은 fast-path라
    # 즉시 확정된다. LLM 왕복 지연과 수치·날짜 드리프트(오늘 날짜를 모르는 모델이
    # 과거 연도를 미래로 오판해 종료일을 누락하는 사고 등)를 원천 회피한다
    # (핵심은 결정적, 긴 꼬리는 LLM).
    from engine.nl_parser import _modify_rule_based
    if _modify_rule_based(user_input, previous_parsed) is not None:
        _log_llm("↩ 폴백", "결정적 fast-path 처리 가능 — 인터프리터 생략")
        logger.info("modify primary skipped, deterministic fast-path handles input")
        return None

    def _carry_over(parsed):
        return parsed.model_copy(update={
            "description": prev.description,
            "execution_timing": prev.execution_timing,
            "entry_filters": prev.entry_filters,
        })

    draft_spec = decompile_strategy(prev)
    ready_report = ValidationReport(is_valid=True, status="READY")
    try:
        roundtrip = _carry_over(compile_strategy(
            _Intent(intent="CREATE_STRATEGY", strategy=draft_spec, confidence=1.0),
            ready_report, prev.description,
        ))
    except StrategyCompileError:
        return None
    if roundtrip.model_dump() != prev.model_dump():
        _log_llm("↩ 폴백", "라운드트립 불일치(표현 불가 전략) — 기존 수정 경로로")
        logger.info("modify primary roundtrip mismatch, falling back to legacy modify")
        return None

    if on_stage is not None:
        on_stage("thinking")
    try:
        result = _get_interpreter(StrategyInterpreter).interpret(
            user_input, draft=draft_spec.model_dump()
        )
    except InterpreterError as exc:
        logger.warning("modify primary interpreter failed, falling back | err=%s", str(exc)[:200])
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("modify primary transport error, falling back | err=%r", exc)
        return None

    intent = result.intent
    if intent.intent == "CLARIFY_STRATEGY" and not intent.patches and intent.clarification_questions:
        # 되묻기 의도를 폴백으로 버리면 기존 수정 LLM이 무변경 전략을 정상 응답처럼
        # 반환해 질문이 사라진다(2026-07-17 "pbr이 뭐야?" 사고). 결정적 fast-path가
        # 처리할 수 있는 입력은 상단 게이트가 이미 폴백시켰으므로, 여기 도달한 되묻기는
        # 단순 수정을 가로막을 수 없다 — 전략을 유지한 채 질문을 채널로 전달한다.
        question, chips = _build_clarification(
            ValidationReport(clarification_questions=intent.clarification_questions),
            intent,
        )
        _log_llm("✓ 되묻기", (
            f"질문={len(intent.clarification_questions)} — 전략 유지, clarification 채널로"
        ))
        return {
            "parsed": prev,
            "clarification_question": question,
            "clarification_suggestions": chips,
            "notices": [],
            "interpreter": {
                "mode": "primary_modify_clarify",
                "model_name": result.model_name,
                "prompt_version": result.prompt_version,
                "repair_attempts": result.repair_attempts,
                "llm_latency_ms": result.latency_ms,
                "patch_count": 0,
                "confidence": intent.confidence,
            },
        }
    if not intent.patches and (
        intent.intent == "EXPLAIN_INDICATOR" or intent.unsupported_features
    ):
        # 개념 설명 질문·미지원 개념 요청을 폴백으로 버리면 기존 수정 LLM이 무변경 전략을
        # 정상 응답처럼 반환해 요청이 조용히 사라진다(2026-07-17 "pbr이 뭐야?" 사고 2차 —
        # 인터프리터가 질문을 내지 않고 unsupported_features로만 보고한 케이스). 전략은
        # 그대로 유지하되, 정의형 질문이면 /query/general과 같은 LLM 답변을 생성해 notices로
        # 실제 설명을 전달한다("변경하지 않았어요" 안내만 주던 2026-07-19 교정). 질문 판정은
        # 4B 라벨이 아니라 결정적 cue(is_definition_question)가 기준 — 같은 발화를 4B가
        # EXPLAIN_INDICATOR로도 unsupported_features로도 내는 실측 대응.
        from api.intent_routes import generate_general_answer
        from intent.classifier import is_definition_question

        is_question = (
            intent.intent == "EXPLAIN_INDICATOR" or is_definition_question(user_input)
        )
        answer = generate_general_answer(user_input) if is_question else None
        if answer:
            notices = [answer]
        elif is_question:
            notices = ["용어·지표 설명 질문으로 이해했지만 지금은 설명을 준비하지 못했어요. "
                       "전략은 변경하지 않았어요."]
        else:
            features = ", ".join(dict.fromkeys(intent.unsupported_features))
            notices = [f"'{features}'은(는) 전략 조건으로 반영할 수 없어 전략을 변경하지 않았어요."]
        _log_llm("✓ 설명/미반영", (
            f"intent={intent.intent} 질문={is_question} 답변={'있음' if answer else '없음'} "
            f"미지원={intent.unsupported_features or '[]'} — 전략 유지, notices 채널로"
        ))
        return {
            "parsed": prev,
            "clarification_question": None,
            "clarification_suggestions": None,
            "notices": notices,
            "interpreter": {
                "mode": "primary_modify_explain" if is_question else "primary_modify_unsupported",
                "model_name": result.model_name,
                "prompt_version": result.prompt_version,
                "repair_attempts": result.repair_attempts,
                "llm_latency_ms": result.latency_ms,
                "patch_count": 0,
                "confidence": intent.confidence,
            },
        }
    if intent.intent not in ("MODIFY_STRATEGY", "CLARIFY_STRATEGY") or not intent.patches:
        _log_llm("↩ 폴백", f"patches 미출력(intent={intent.intent}) — 기존 수정 경로로")
        logger.info("modify primary without patches (intent=%s), falling back", intent.intent)
        return None
    try:
        patched_spec = apply_patches(draft_spec, intent.patches)
    except PatchError as exc:
        _log_llm("↩ 폴백", f"패치 거부: {str(exc)[:150]} — 기존 수정 경로로")
        logger.warning("modify primary patch rejected, falling back | err=%s", exc)
        return None

    validated, report = run_validation(_Intent(
        intent="MODIFY_STRATEGY", strategy=patched_spec,
        confidence=intent.confidence, unsupported_features=intent.unsupported_features,
    ))
    _log_llm("✓ 검증", (
        f"status={report.status} patches={len(intent.patches)} "
        f"오류={len(report.errors)} 미지원={report.unsupported_features or '[]'}"
    ))
    if not report.is_valid:
        _log_llm("↩ 폴백", f"패치 적용 후 검증 미통과(status={report.status}) — 기존 수정 경로로")
        logger.info("modify primary not READY after patch (status=%s), falling back",
                    report.status)
        return None
    try:
        parsed = _carry_over(compile_strategy(validated, report, prev.description))
    except StrategyCompileError as exc:
        logger.warning("modify primary compile failed, falling back | err=%s", exc)
        return None
    parsed = _override_explicit_dates(parsed, user_input)

    return {
        "parsed": parsed,
        "clarification_question": None,
        "clarification_suggestions": None,
        "notices": list(report.warnings),
        "interpreter": {
            "mode": "primary_modify",
            "model_name": result.model_name,
            "prompt_version": result.prompt_version,
            "repair_attempts": result.repair_attempts,
            "llm_latency_ms": result.latency_ms,
            "patch_count": len(intent.patches),
            "confidence": intent.confidence,
        },
    }


_interpreter_singleton = None


def _get_interpreter(cls):
    global _interpreter_singleton
    if _interpreter_singleton is None:
        _interpreter_singleton = cls()
    return _interpreter_singleton


def apply_primary_meta(result: dict, primary: Dict[str, Any]) -> None:
    """_build_parse_result 산출물에 primary 경로의 질문/안내/메타를 병합한다.

    인터프리터의 질문이 기존 detect_missing_entry_clarification 질문보다 구체적이므로
    있으면 우선한다. notices는 뒤에 덧붙인다(하한선 보정 안내가 앞).
    """
    if primary["clarification_question"]:
        result["clarification_question"] = primary["clarification_question"]
        result["clarification_suggestions"] = primary["clarification_suggestions"]
    elif primary["interpreter"]["mode"] in ("primary_modify_explain", "primary_modify_unsupported"):
        # 전략 무변경 + 설명/미반영 안내 응답 — 프롬프트의 지표 언급("pbr이 뭐야?")에 반응한
        # 기존 되묻기("PBR은 몇 이하로 할까요?")는 설명·안내와 모순되므로 억제한다.
        result["clarification_question"] = None
        result["clarification_suggestions"] = None
    if primary["notices"]:
        result["notices"] = list(result.get("notices") or []) + primary["notices"]
    result["runtime"]["interpreter"] = primary["interpreter"]
