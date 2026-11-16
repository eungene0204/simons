"""해석 에이전트(실험 레인) — 해석의 진행을 LLM이 쥔다.

고정 파이프라인은 인터프리터 초안 뒤에 정해진 순서의 보조 판정(조건 누락 대조·인용 대조·
의미 정합 보정·자기 검증 등)을 차례로 돌린다. 이 레인은 그 자리를 하나의 루프로 바꾼다:
초안과 검증기 결과를 LLM에게 보여 주고, LLM이 **무엇을 확인하고 무엇을 고칠지 스스로 골라**
(지표 조회·추가·교체·삭제) 끝났다고 판단할 때 종료한다. 의미 판단은 전부 LLM 레인이고
(대원칙 1), 안전 계약은 결정론이다:

- 인용(quote)은 요청 문장에 그대로 있어야 한다(출처 대조). 삭제만 하는 편집은 인용이 없어도 된다
- 추가·교체하는 값의 숫자는 인용에 적힌 숫자여야 한다(말하지 않은 값·환산값 확정 금지)
- 경로는 조건·랭킹·리스크·포트폴리오·백테스트 칸만(유니버스는 초안·검증기가 정한다)
- 편집 결과가 검증 오류·미지원을 늘리면 거절하고 사유를 관찰로 돌려준다
- 스텝 예산·같은 행동 반복 2회에서 종료. 어떻게 끝나든 그때까지 수락된 편집만 남는다

기본 off(`STRATEGY_INTERPRETATION_AGENT_MODE=primary`로 켠다). 한국 레인 생성 턴 한정이고,
업종·테마 유니버스 해석(대화 플래너)은 이 레인에 아직 없다 — 고정 파이프라인과의 비교 실험용이다.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import ValidationError

from strategy_conversation.conversation.patch_applier import PatchError, apply_patches
from strategy_conversation.interpreter.models import PatchOp, StrategyIntent, ValidationReport
from strategy_conversation.planner.mini_planner import _extract_json
from strategy_conversation.planner.verify_agent import _NUMBER_RE, _compact, _lookup
from strategy_conversation.tools import call as call_tool

logger = logging.getLogger("strategy_interpreter.planner")

_EDIT_ROOTS = ("entry_conditions", "exit_conditions", "ranking", "risk_management",
               "portfolio", "backtest")
_CONDITION_ROOTS = ("entry_conditions", "exit_conditions")
DEFAULT_MAX_STEPS = 6

_SYSTEM = """당신은 주식 백테스트 플랫폼의 전략 해석 에이전트입니다. 사용자 요청(utterance)을 전략
JSON(strategy)으로 옮기는 일을 끝까지 책임집니다. 첫 초안과 검증기 결과(validation)가 주어집니다.
요청이 말한 것이 전략에 정확히 들어 있고 말하지 않은 것이 들어 있지 않을 때까지, 도구로 확인하고
고친 뒤 종료하세요.

매 턴 JSON 객체 하나만 출력하세요:
- 지표 조회: {"action":"lookup","terms":["<지표 이름>","<지표 이름>"]} — 이름마다 쓸 수 있는 factor ID·연산자·파라미터 이름을 돌려줍니다
- 고치기: {"action":"edit","quote":"<요청 문장에서 그대로 복사한 조각>","patches":[{"op":"add|replace|remove","path":"/...","value":...}]}
- 종료: {"action":"finish"}

일하는 순서:
1. 요청을 구절로 나누고, 구절마다 전략의 어느 칸에 어떤 값으로 들어갔는지 대조합니다.
2. 빠진 구절은 add, 요청과 다른 값·연산자·기간은 replace, 요청에 없는데 들어간 조건은 remove 합니다.
3. 더 고칠 것이 없으면 finish 합니다. 초안이 이미 요청과 같으면 바로 finish 하세요.

규칙:
1. 요청에 없는 조건·값을 만들지 마세요.
2. add·replace 값의 숫자는 quote에 적힌 숫자 그대로여야 합니다. 단위 환산·추정이 필요한 값은
   넣지 마세요 — 비워 두면 시스템이 사용자에게 묻습니다.
3. 조건을 추가하기 전에 lookup으로 factor ID를 확인하세요. 조회 결과가 비면 추가하지 마세요.
4. 경로: /entry_conditions/-, /entry_conditions/<번호>, /entry_conditions/<번호>/<칸>,
   /exit_conditions/…, /ranking/-, /risk_management/<칸>, /portfolio/<칸>, /backtest/<칸>.
   조건 한 개의 모양: {"factor":"<ID>","operator":"<연산자>","value":<숫자|null>,"parameters":{}}
5. validation.errors는 고쳐야 할 문제입니다. validation.questions는 값이 없어 사용자에게 물을
   항목이라 결함이 아닙니다 — 사용자가 그 값을 말했는데 빠졌을 때만 채우세요.
6. 실행 기록의 거절(rejected) 사유를 읽고 같은 시도를 반복하지 마세요."""


def _numbers_in(value: Any) -> List[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [abs(float(value))]
    if isinstance(value, str):
        return [float(n) for n in _NUMBER_RE.findall(value)]
    if isinstance(value, dict):
        return [n for key, item in value.items() if key != "source_text" for n in _numbers_in(item)]
    if isinstance(value, list):
        return [n for item in value for n in _numbers_in(item)]
    return []


def _render_state(utterance: str, intent: StrategyIntent, report: ValidationReport,
                  steps: List[Dict[str, Any]]) -> str:
    return json.dumps({
        "utterance": utterance,
        "strategy": intent.strategy.model_dump(mode="json", exclude_none=True),
        "validation": {
            "errors": report.errors,
            "questions": [q.question for q in report.clarification_questions],
            "unsupported_features": report.unsupported_features,
        },
        "steps": steps,
    }, ensure_ascii=False)


def _try_edit(decision: dict, intent: StrategyIntent, report: ValidationReport, utterance: str,
              ) -> Tuple[Dict[str, Any], Optional[Tuple[StrategyIntent, ValidationReport]]]:
    """편집 하나를 관문에 통과시킨다. (관찰, 수락 시 새 (intent, report))."""
    try:
        patches = [PatchOp.model_validate(p) for p in decision.get("patches") or []]
    except ValidationError:
        return {"rejected": "patches 형식이 맞지 않습니다({op,path,value})"}, None
    if not patches:
        return {"rejected": "patches가 비어 있습니다"}, None
    writes = [p for p in patches if p.op != "remove"]
    quote = decision.get("quote")
    if writes and (not isinstance(quote, str) or not _compact(quote)
                   or _compact(quote) not in _compact(utterance)):
        return {"rejected": "quote가 요청 문장에 그대로 있지 않습니다"}, None
    quoted = ({float(n) for n in _NUMBER_RE.findall(quote.replace(",", ""))}
              if isinstance(quote, str) else set())
    for patch in patches:
        root = patch.path.split("/")[1] if patch.path.startswith("/") else ""
        if root not in _EDIT_ROOTS:
            return {"rejected": f"고칠 수 없는 경로입니다: {patch.path}"}, None
        if patch.op == "remove":
            continue
        unquoted = [n for n in _numbers_in(patch.value) if n not in quoted]
        if unquoted:
            return {"rejected": f"숫자 {unquoted[0]:g}이(가) quote에 없습니다 — 말하지 않은 값·환산값은 비워 두세요"}, None
        if root in _CONDITION_ROOTS and isinstance(patch.value, dict) and "factor" in patch.value:
            patch.value = {**patch.value, "source_text": quote}
    try:
        spec = apply_patches(intent.strategy, patches)
    except (PatchError, ValidationError, ValueError) as exc:
        return {"rejected": str(exc)[:200]}, None
    for condition in spec.entry_conditions + spec.exit_conditions:
        if condition.value is not None and condition.value_source == "MISSING":
            condition.value_source = "USER_PROVIDED"
    if spec.model_dump(mode="json") == intent.strategy.model_dump(mode="json"):
        return {"rejected": "바뀐 것이 없습니다 — 고칠 것이 없으면 finish 하세요"}, None
    checked = call_tool("validate_intent", intent=intent.model_copy(update={"strategy": spec}))
    new_errors = [e for e in checked.report.errors if e not in report.errors]
    new_unsupported = [f for f in checked.report.unsupported_features
                       if f not in report.unsupported_features]
    if new_errors or new_unsupported:
        return {"rejected": "검증을 통과하지 못했습니다",
                "errors": new_errors[:3], "unsupported": new_unsupported[:3]}, None
    return {"accepted": True}, (checked.intent, checked.report)


def run_interpretation_agent(
    intent: StrategyIntent, report: ValidationReport, utterance: str,
    chat_fn: Callable[..., str], max_steps: int = DEFAULT_MAX_STEPS,
) -> Tuple[StrategyIntent, ValidationReport, Dict[str, Any]]:
    """초안을 요청 문장과 대조해 LLM이 고쳐 나간다. (전략, 검증 보고, 실행 요약)을 돌려준다."""
    from observability import span

    steps: List[Dict[str, Any]] = []
    seen: set = set()
    edits, repeated, outcome = 0, False, "budget_exhausted"
    with span("Agent · 해석", "planner", inputs={"utterance": utterance}) as trace:
        try:
            for _ in range(max_steps):
                decision = _extract_json(chat_fn(
                    _SYSTEM, _render_state(utterance, intent, report, steps), max_tokens=768))
                action = decision.get("action") if decision else None
                if action == "finish":
                    outcome = "finish"
                    break
                if action not in ("lookup", "edit"):
                    outcome = "contract_violation"
                    break
                key = json.dumps(decision, ensure_ascii=False, sort_keys=True)
                if key in seen:
                    if repeated:
                        outcome = "stalled"
                        break
                    repeated = True
                    steps.append({**decision, "observation": {
                        "rejected": "이미 한 행동입니다 — 위 결과를 쓰고, 더 할 일이 없으면 finish 하세요"}})
                    continue
                seen.add(key)
                if action == "lookup":
                    observation = _lookup(decision)
                else:
                    observation, accepted = _try_edit(decision, intent, report, utterance)
                    if accepted is not None:
                        intent, report = accepted
                        edits += 1
                steps.append({**decision, "observation": observation})
        except Exception:  # noqa: BLE001 — 에이전트 장애는 그때까지의 전략으로 끝낸다
            logger.warning("interpretation agent 실행 실패 — 수락된 편집만 유지", exc_info=True)
            outcome = "error"
        summary = {"outcome": outcome, "edits": edits, "steps": len(steps)}
        trace.output(**summary, trace=steps)
    return intent, report, summary


def run_agent_parse(user_input: str, previous_explicit_fields: Optional[List[str]] = None,
                    ) -> Optional[Dict[str, Any]]:
    """생성 턴을 해석 에이전트로 처리한다 — run_primary_parse와 같은 모양의 결과(실패 시 None)."""
    from strategy_conversation import primary
    from strategy_conversation.compiler.strategy_compiler import StrategyCompileError
    from strategy_conversation.interpreter.llm_strategy_interpreter import (
        InterpreterError, StrategyInterpreter)

    interpreter = primary._get_interpreter(StrategyInterpreter)
    try:
        result = interpreter.interpret(user_input)
    except InterpreterError as exc:
        logger.warning("agent lane interpreter failed | err=%s", str(exc)[:200])
        return None
    if result.intent.intent not in primary._STRATEGY_INTENTS or result.intent.strategy is None:
        return None
    validation = call_tool("validate_intent", intent=result.intent)
    validated, report = validation.intent, validation.report
    if validated.strategy is None:
        return None
    summary: Dict[str, Any] = {"outcome": "skipped", "edits": 0, "steps": 0}
    chat = getattr(interpreter, "_chat", None)
    if callable(chat):
        validated, report, summary = run_interpretation_agent(validated, report, user_input, chat)
    try:
        compiled = call_tool("compile_strategy", intent=validated, report=report,
                             user_input=user_input, partial=not report.is_valid)
    except StrategyCompileError as exc:
        logger.warning("agent lane compile failed | err=%s", exc)
        return None
    parsed = compiled.parsed
    question, chips, topic = primary._build_clarification(report, validated)
    pending_ask = primary._pending_ask_payload(question, chips, topic, parsed)
    explicit = primary._explicit_fields(validated.strategy, previous_explicit_fields)
    declined = list(getattr(validated.strategy, "declined", None) or [])
    return primary.finalize_user_response({
        "parsed": parsed,
        "clarification_question": question,
        "clarification_suggestions": (pending_ask or {}).get("chips") or None,
        "clarification_priority": None,
        "pending_ask": pending_ask,
        "explicit_fields": explicit,
        **({"declined_fields": declined} if declined else {}),
        "pending_conditions": list(compiled.pending_conditions),
        "field_states": primary._field_states(parsed, validated.strategy, report, explicit),
        "notices": primary.initial_validation_notices(report) + primary._preparing_notice(report),
        "interpreter": {
            "mode": "agent", "model_name": result.model_name,
            "prompt_version": result.prompt_version, "repair_attempts": result.repair_attempts,
            "llm_latency_ms": result.latency_ms, "validation_status": report.status,
            "confidence": validated.confidence, "agent": summary,
        },
    })
