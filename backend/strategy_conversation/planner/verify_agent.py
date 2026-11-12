"""해석 자기 검증 에이전트 — 해석 결과를 요청 문장과 대조해 빠진 칸을 스스로 채운다.

고정 파이프라인이 만든 전략(검증 통과본)을 LLM이 요청 문장과 나란히 놓고 읽은 뒤,
도구를 불러 가며 '말했는데 빠진 것'을 채운다: 관찰 → 행동(지표 조회·채우기 시도) →
결과 관찰(검증기의 수락·거절 사유) → 다시 행동 → 종료. 의미 판단은 전부 LLM 레인이고
(대원칙 1), 안전 계약은 전부 결정론이다:

- 채우기만 한다 — 이미 값이 있는 칸의 교체·삭제는 적용하지 않는다. 두 번째 LLM이 맞는 값을
  뒤집은 실측(2026-10-23 EMA→SMA 8턴 중 6턴) 때문이다. 틀렸다고 본 칸은 finish의
  concerns로 Trace에만 남긴다(관측).
- quote는 요청 문장에 그대로 있어야 한다(출처 대조 — condition_recall ②와 같은 계약)
- 패치 값의 숫자는 quote에 적힌 숫자여야 한다(말하지 않은 값·환산값 확정 금지 —
  빈 값은 완결성 검증이 되묻는다)
- 경로는 조건·리스크·포트폴리오·백테스트 칸만(유니버스는 planner 소유)
- 이 턴의 앞 단계가 빼거나 보류한 조건(blocked)은 다시 넣지 못한다
- 채운 결과는 validate_intent를 다시 통과해야 한다(오류·미지원이 늘면 거절, 사유를 관찰로)
- 스텝 예산(config.verify_agent_max_steps)·동일 액션 반복 즉시 종료

실패(JSON 위반·예산 소진·예외)는 그때까지 수락된 채우기만 남긴다 — 각 채우기는 위 관문을
개별 통과했다. 하나도 없으면 None이고 호출부는 원래 결과를 그대로 쓴다.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

from pydantic import ValidationError

from strategy_conversation import config
from strategy_conversation.conversation.patch_applier import PatchError, apply_patches
from strategy_conversation.interpreter.models import PatchOp, StrategyIntent, ValidationReport
from strategy_conversation.planner.mini_planner import _extract_json
from strategy_conversation.registry.indicator_registry import resolve
from strategy_conversation.tools import call as call_tool

logger = logging.getLogger("strategy_interpreter.planner")

_PATCH_ROOTS = ("entry_conditions", "exit_conditions", "risk_management", "portfolio", "backtest")
_CONDITION_ROOTS = ("entry_conditions", "exit_conditions")
_LOOKUP_TERM_MAX = 40
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

_SYSTEM = """당신은 주식 백테스트 플랫폼의 해석 검수 에이전트입니다. 다른 해석기가 사용자 요청을
전략 JSON으로 옮겼습니다. 요청 문장이 분명히 말한 내용이 전략에 빠져 있는지 확인하고, 빠진 것만
도구로 채웁니다.

매 턴 JSON 객체 하나만 출력하세요:
- 지표 조회: {"action":"lookup","text":"<지표·개념 표현>"} — 쓸 수 있는 factor ID·연산자·파라미터 이름을 돌려줍니다
- 채우기 시도: {"action":"patch","quote":"<요청 문장에서 그대로 복사한 조각>","patches":[{"op":"add","path":"/entry_conditions/-","value":{"factor":"<ID>","operator":"<연산자>","value":null,"parameters":{}}}]}
- 종료: {"action":"finish","concerns":[{"path":"/...","quote":"<요청 조각>","reason":"<짧게>"}]}

규칙:
1. 요청에 없는 조건·값을 만들지 마세요. 전략이 요청을 이미 담고 있으면 바로 finish 하세요.
2. patch는 빈 칸(null·없는 항목)을 채우는 것만 됩니다. 이미 값이 있는 칸이 틀렸다고 판단하면
   고치지 말고 finish의 concerns에 적으세요. 삭제(remove)는 할 수 없습니다.
3. patch 값의 숫자는 quote에 적힌 숫자 그대로여야 합니다. 단위 환산·추정이 필요한 값은 넣지
   마세요 — 비워 두면 시스템이 사용자에게 묻습니다.
4. 조건을 추가하기 전에 lookup으로 factor ID를 확인하세요. 조회 결과가 비면 더 짧은 지표 이름으로
   한 번 더 조회하고, 그래도 없으면 추가하지 마세요.
5. 채울 수 있는 경로: /entry_conditions/-, /exit_conditions/-, /entry_conditions/<번호>/<칸>,
   /risk_management/<칸>, /portfolio/<칸>, /backtest/<칸>. 유니버스는 대상이 아닙니다.
6. validation.questions(값이 없어 사용자에게 물을 항목)는 결함이 아닙니다. 사용자가 그 값을
   말했는데 빠졌을 때만 채우세요.
7. excluded에 있는 조건은 다른 검사가 뺀 것입니다. 다시 넣지 마세요.
8. 실행 기록의 거절(rejected) 사유를 읽고 같은 시도를 반복하지 마세요."""


def _compact(text: str) -> str:
    return "".join((text or "").split())


def _canonical(factor: Any) -> Any:
    spec = resolve(factor) if isinstance(factor, str) else None
    return spec.id if spec is not None else factor


def _filled_numbers(before: Any, after: Any) -> List[float]:
    """적용 전후로 달라진 잎에 실린 숫자 — 스키마 정규화 뒤의 값을 본다.

    원시 패치 값이 아니라 정규화 뒤를 보는 이유: 숫자를 문자열("5%"·"3y")로 내면 스키마가 수로
    바꿔 확정하므로, 패치 표기만 대조하면 인용에 없는 값이 통과한다.
    """
    if isinstance(after, dict):
        prior = before if isinstance(before, dict) else {}
        return [n for key, value in after.items() if key != "value_source"
                for n in _filled_numbers(prior.get(key), value)]
    if isinstance(after, list):
        prior = before if isinstance(before, list) else []
        return [n for i, value in enumerate(after)
                for n in _filled_numbers(prior[i] if i < len(prior) else None, value)]
    if after == before or isinstance(after, bool):
        return []
    if isinstance(after, (int, float)):
        return [abs(float(after))]
    return [float(n) for n in _NUMBER_RE.findall(after)] if isinstance(after, str) else []


def _only_fills(before: Any, after: Any) -> bool:
    """after가 before의 빈 칸만 채웠는가 — 값이 있던 칸은 그대로, 목록은 뒤에 붙이기만."""
    if before in (None, [], {}):
        return True
    if isinstance(before, dict):
        # value_source는 값을 채우면 따라 바뀌는 파생 칸이다(MISSING → USER_PROVIDED).
        return isinstance(after, dict) and all(
            key == "value_source" or (key in after and _only_fills(value, after[key]))
            for key, value in before.items())
    if isinstance(before, list):
        return (isinstance(after, list) and len(after) >= len(before)
                and all(_only_fills(b, a) for b, a in zip(before, after)))
    return before == after


def _render_state(utterance: str, intent: StrategyIntent, report: ValidationReport,
                  blocked: FrozenSet[Tuple[str, str]], steps: List[Dict[str, Any]]) -> str:
    return json.dumps({
        "utterance": utterance,
        "strategy": intent.strategy.model_dump(mode="json"),
        "validation": {
            "questions": [q.question for q in report.clarification_questions],
            "unsupported_features": report.unsupported_features,
        },
        "excluded": [{"role": role, "factor": factor} for role, factor in sorted(blocked)],
        "steps": steps,
    }, ensure_ascii=False)


def _try_patch(decision: dict, intent: StrategyIntent, report: ValidationReport, utterance: str,
               blocked: FrozenSet[Tuple[str, str]],
               ) -> Tuple[Dict[str, Any], Optional[Tuple[StrategyIntent, ValidationReport]]]:
    """채우기 시도 하나를 관문에 통과시킨다. (관찰, 수락 시 새 (intent, report))."""
    quote = decision.get("quote")
    if not isinstance(quote, str) or not _compact(quote) or _compact(quote) not in _compact(utterance):
        return {"rejected": "quote가 요청 문장에 그대로 있지 않습니다"}, None
    try:
        patches = [PatchOp.model_validate(p) for p in decision.get("patches") or []]
    except ValidationError:
        return {"rejected": "patches 형식이 맞지 않습니다({op,path,value})"}, None
    if not patches:
        return {"rejected": "patches가 비어 있습니다"}, None
    quoted_numbers = {float(n) for n in _NUMBER_RE.findall(quote.replace(",", ""))}
    for patch in patches:
        root = patch.path.split("/")[1] if patch.path.startswith("/") else ""
        if patch.op == "remove" or root not in _PATCH_ROOTS:
            return {"rejected": f"채울 수 없는 경로·연산입니다: {patch.op} {patch.path}"}, None
        if root in _CONDITION_ROOTS and isinstance(patch.value, dict) and "factor" in patch.value:
            if (root, _canonical(patch.value["factor"])) in blocked:
                return {"rejected": "excluded 조건은 다시 넣을 수 없습니다"}, None
            patch.value = {**patch.value, "source_text": quote}
    try:
        spec = apply_patches(intent.strategy, patches)
    except PatchError as exc:
        return {"rejected": str(exc)[:200]}, None
    for condition in spec.entry_conditions + spec.exit_conditions:
        if condition.value is not None and condition.value_source == "MISSING":
            condition.value_source = "USER_PROVIDED"
    before, after = intent.strategy.model_dump(mode="json"), spec.model_dump(mode="json")
    if not _only_fills(before, after):
        return {"rejected": "이미 값이 있는 칸은 바꿀 수 없습니다 — finish의 concerns에 적으세요"}, None
    unquoted = [n for n in _filled_numbers(before, after) if n not in quoted_numbers]
    if unquoted:
        return {"rejected": f"숫자 {unquoted[0]:g}이(가) quote에 없습니다 — 말하지 않은 값·환산값은 비워 두세요"}, None
    checked = call_tool("validate_intent", intent=intent.model_copy(update={"strategy": spec}))
    new_errors = [e for e in checked.report.errors if e not in report.errors]
    new_unsupported = [f for f in checked.report.unsupported_features
                       if f not in report.unsupported_features]
    if new_errors or new_unsupported:
        return {"rejected": "검증을 통과하지 못했습니다",
                "errors": new_errors[:3], "unsupported": new_unsupported[:3]}, None
    return {"accepted": True}, (checked.intent, checked.report)


def verify_interpretation(
    intent: StrategyIntent, report: ValidationReport, utterance: str,
    chat_fn: Callable[..., str], blocked: FrozenSet[Tuple[str, str]] = frozenset(),
    max_steps: Optional[int] = None,
) -> Optional[Tuple[StrategyIntent, ValidationReport]]:
    """검증 통과본을 요청 문장과 대조해 빠진 칸을 채운다. 채운 것이 없으면 None."""
    from observability import span

    if intent.strategy is None or not callable(chat_fn):
        return None
    budget = max_steps if max_steps is not None else config.verify_agent_max_steps()
    steps: List[Dict[str, Any]] = []
    seen: set = set()
    filled = 0
    outcome, concerns = "budget_exhausted", []
    with span("Agent · 해석 자기 검증", "planner", inputs={"utterance": utterance}) as trace:
        try:
            for _ in range(budget):
                decision = _extract_json(
                    chat_fn(_SYSTEM, _render_state(utterance, intent, report, blocked, steps),
                            max_tokens=768))
                action = decision.get("action") if decision else None
                key = json.dumps(decision, ensure_ascii=False, sort_keys=True)
                if action == "finish":
                    outcome, concerns = "finish", decision.get("concerns") or []
                    break
                if action not in ("lookup", "patch") or key in seen:
                    outcome = "contract_violation"
                    break
                seen.add(key)
                if action == "lookup":
                    term = str(decision.get("text") or "")
                    # 조회 입력은 짧은 지표 표현이다 — 문장을 통째로 넘기면 원문 스캔이 된다.
                    observation = (
                        call_tool("lookup_indicator", term=term).model_dump()
                        if len(term) <= _LOOKUP_TERM_MAX
                        else {"rejected": "지표 이름만 짧게 넣으세요"})
                else:
                    observation, accepted = _try_patch(decision, intent, report, utterance, blocked)
                    if accepted is not None:
                        intent, report = accepted
                        filled += 1
                steps.append({**decision, "observation": observation})
        except Exception:  # noqa: BLE001 — 보조 에이전트 장애가 해석 턴을 깨면 안 된다
            logger.warning("verify agent 실행 실패 — 수락된 채우기만 유지", exc_info=True)
            outcome = "error"
        trace.output(outcome=outcome, filled=filled, concerns=concerns, steps=steps)
    return (intent, report) if filled else None
