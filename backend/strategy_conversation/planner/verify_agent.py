"""해석 자기 검증 에이전트 — 해석 결과를 요청 문장과 대조해 빠진 칸을 스스로 채운다.

고정 파이프라인이 만든 전략(검증 통과본)을 LLM이 요청 문장과 나란히 놓고 읽은 뒤,
도구를 불러 가며 '말했는데 빠진 것'을 채운다: 관찰 → 행동(지표 조회·채우기 시도) →
결과 관찰(검증기의 수락·거절 사유) → 다시 행동 → 종료. 의미 판단은 전부 LLM 레인이고
(대원칙 1), 안전 계약은 전부 결정론이다:

- 채우기만 한다 — 이미 값이 있는 칸의 교체·삭제는 적용하지 않는다. 두 번째 LLM이 맞는 값을
  뒤집은 실측(2026-10-23 EMA→SMA 8턴 중 6턴) 때문이다. 틀렸다고 본 칸은 finish의
  concerns로 남긴다. 그중 **숫자 한 칸**(손절·익절·트레일링·보유 종목 수·조건 기준값)이고
  요청 문장에 적힌 값이 관문을 통과하면 '값 확인' 후보(corrections)로 돌려준다 — 고치는 것은
  사용자다(호출부가 확인 질문으로 낸다, 2026-11-16 사용자 결정). 나머지는 Trace에만 남는다.
- quote는 요청 문장에 그대로 있어야 한다(출처 대조 — condition_recall ②와 같은 계약)
- 패치 값의 숫자는 quote에 적힌 숫자여야 한다(말하지 않은 값·환산값 확정 금지 —
  빈 값은 완결성 검증이 되묻는다)
- 경로는 조건·리스크·포트폴리오·백테스트 칸만(유니버스는 planner 소유)
- 이 턴의 앞 단계가 빼거나 보류한 조건(blocked)은 다시 넣지 못한다. 수정 턴에서는 사용자가 이번에
  지운 조건·비운 설정 칸(blocked_paths)도 같다 — "PER 조건은 빼줘"의 PER을 '빠진 것'으로 되살리면 안 된다
- 채운 결과는 validate_intent를 다시 통과해야 한다(오류·미지원이 늘면 거절, 사유를 관찰로)
- 스텝 예산(config.verify_agent_max_steps)·동일 액션 반복 즉시 종료

실패(JSON 위반·예산 소진·예외)는 그때까지 수락된 채우기만 남긴다 — 각 채우기는 위 관문을
개별 통과했다. 채운 것도 확인 후보도 없으면 None이고 호출부는 원래 결과를 그대로 쓴다.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
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
_LOOKUP_TERMS_MAX = 4
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

_SYSTEM = """당신은 주식 백테스트 플랫폼의 해석 검수 에이전트입니다. 다른 해석기가 사용자 요청을
전략 JSON으로 옮겼습니다. 요청 문장이 분명히 말한 내용이 전략에 빠져 있는지 확인하고, 빠진 것만
도구로 채웁니다.

매 턴 JSON 객체 하나만 출력하세요:
- 지표 조회: {"action":"lookup","terms":["<지표 이름>","<지표 이름>"]} — 지표 이름을 하나씩 따로 적으면(한 칸에 여러 지표·설명을 묶지 않습니다) 이름마다 쓸 수 있는 factor ID·연산자·파라미터 이름을 돌려줍니다
- 채우기 시도: {"action":"patch","quote":"<요청 문장에서 그대로 복사한 조각>","patches":[{"op":"add","path":"/entry_conditions/-","value":{"factor":"<ID>","operator":"<연산자>","value":null,"parameters":{}}}]}
- 종료: {"action":"finish","concerns":[{"path":"/...","quote":"<요청 문장에서 그대로 복사한 조각>","value":<그 조각에 적힌 값>,"reason":"<짧게>"}]}

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
8. 실행 기록의 거절(rejected) 사유를 읽고 같은 시도를 반복하지 마세요. 같은 조회·같은 채우기를
   두 번 내지 마세요 — 더 할 일이 없으면 finish 하세요.
9. pending_question이 있으면 요청 문장은 그 질문에 대한 답입니다."""


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
                  blocked: FrozenSet[Tuple[str, str]], steps: List[Dict[str, Any]],
                  pending_question: Optional[str] = None) -> str:
    return json.dumps({
        "utterance": utterance,
        **({"pending_question": pending_question} if pending_question else {}),
        "strategy": intent.strategy.model_dump(mode="json"),
        "validation": {
            "questions": [q.question for q in report.clarification_questions],
            "unsupported_features": report.unsupported_features,
        },
        "excluded": [{"role": role, "factor": factor} for role, factor in sorted(blocked)],
        "steps": steps,
    }, ensure_ascii=False)


def _lookup(decision: dict) -> Dict[str, Any]:
    """지표 이름마다 따로 조회한다 — 여러 지표를 한 표현에 묶으면 등록부 대조가 빈손이 된다
    (2026-11-15 실측: "볼린저밴드 하단, 볼린저밴드 중심선, 종가")."""
    terms = decision.get("terms")
    if isinstance(terms, str):
        terms = [terms]
    if not isinstance(terms, list) or not terms or not all(isinstance(t, str) for t in terms):
        return {"rejected": 'terms에 지표 이름을 목록으로 넣으세요(예: ["RSI","거래대금"])'}
    results = []
    for term in terms[:_LOOKUP_TERMS_MAX]:
        # 조회 입력은 짧은 지표 표현이다 — 문장을 통째로 넘기면 원문 스캔이 된다.
        results.append({"term": term, **(
            call_tool("lookup_indicator", term=term).model_dump(exclude_none=True)
            if len(term) <= _LOOKUP_TERM_MAX
            else {"rejected": "지표 이름만 짧게 넣으세요"})})
    return {"results": results}


def _try_patch(decision: dict, intent: StrategyIntent, report: ValidationReport, utterance: str,
               blocked: FrozenSet[Tuple[str, str]], blocked_paths: FrozenSet[str] = frozenset(),
               ) -> Tuple[Dict[str, Any], Optional[Tuple[StrategyIntent, ValidationReport, List[PatchOp]]]]:
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
        if patch.path in blocked_paths:
            return {"rejected": "이번 요청이 비운 칸은 다시 채울 수 없습니다"}, None
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
    if before == after:
        return {"rejected": "바뀐 것이 없습니다 — 채울 것이 없으면 finish 하세요"}, None
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
    return {"accepted": True}, (checked.intent, checked.report, patches)


# 값 확인 후보로 올릴 수 있는 칸 — 사용자에게 이름을 붙여 물을 수 있는 숫자 한 칸뿐이다.
_CORRECTABLE_SCALARS = ("/risk_management/stop_loss", "/risk_management/take_profit",
                        "/risk_management/trailing_stop", "/portfolio/selection_count")


@dataclass
class VerifyOutcome:
    intent: StrategyIntent
    report: ValidationReport
    filled: int = 0
    # 수락된 채우기 패치 — 수정 턴 호출부가 '이번 턴이 바꾼 칸'(명시 필드) 판정에 쓴다
    patches: List[PatchOp] = field(default_factory=list)
    # [{"path","quote","current","proposed"}] — 관문을 통과한 값 확인 후보(적용하지 않았다)
    corrections: List[Dict[str, Any]] = field(default_factory=list)


def _current_value(strategy: Any, path: str) -> Any:
    node: Any = strategy
    for part in path.strip("/").split("/"):
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                return None
            node = node[int(part)]
        else:
            node = getattr(node, part, None)
        if node is None:
            return None
    return node


def _correction(concern: Any, intent: StrategyIntent, report: ValidationReport,
                utterance: str) -> Optional[Dict[str, Any]]:
    """concern 하나가 값 확인 후보 자격이 있는가 — 전부 결정론 관문이다(적용은 하지 않는다)."""
    if not isinstance(concern, dict):
        return None
    path, quote, proposed = concern.get("path"), concern.get("quote"), concern.get("value")
    if not isinstance(path, str) or not isinstance(quote, str):
        return None
    if isinstance(proposed, bool) or not isinstance(proposed, (int, float)):
        return None
    parts = path.strip("/").split("/")
    is_condition_value = (len(parts) == 3 and parts[0] in _CONDITION_ROOTS
                          and parts[1].isdigit() and parts[2] == "value")
    if path not in _CORRECTABLE_SCALARS and not is_condition_value:
        return None
    if not _compact(quote) or _compact(quote) not in _compact(utterance):
        return None
    current = _current_value(intent.strategy, path)
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        return None
    quoted = {float(n) for n in _NUMBER_RE.findall(quote.replace(",", ""))}
    # 인용에 요청값만 있고 지금 값은 없어야 한다 — 둘 다 적힌 인용은 어느 쪽 칸인지 가릴 수 없다.
    if abs(float(proposed)) not in quoted or abs(float(current)) in quoted:
        return None
    try:
        spec = apply_patches(intent.strategy, [PatchOp(op="replace", path=path, value=proposed)])
    except (PatchError, ValidationError):
        return None
    checked = call_tool("validate_intent", intent=intent.model_copy(update={"strategy": spec}))
    if ([e for e in checked.report.errors if e not in report.errors]
            or [f for f in checked.report.unsupported_features
                if f not in report.unsupported_features]):
        return None
    return {"path": path, "quote": quote, "current": current, "proposed": proposed}


def verify_interpretation(
    intent: StrategyIntent, report: ValidationReport, utterance: str,
    chat_fn: Callable[..., str], blocked: FrozenSet[Tuple[str, str]] = frozenset(),
    max_steps: Optional[int] = None, pending_question: Optional[str] = None,
    blocked_paths: FrozenSet[str] = frozenset(),
) -> Optional[VerifyOutcome]:
    """검증 통과본을 요청 문장과 대조해 빠진 칸을 채운다. 채운 것도 확인 후보도 없으면 None."""
    from observability import span

    if intent.strategy is None or not callable(chat_fn):
        return None
    budget = max_steps if max_steps is not None else config.verify_agent_max_steps()
    steps: List[Dict[str, Any]] = []
    seen: set = set()
    filled = 0
    outcome, concerns = "budget_exhausted", []
    corrections: List[Dict[str, Any]] = []
    repeated = False
    accepted_patches: List[PatchOp] = []
    with span("Agent · 해석 자기 검증", "planner", inputs={"utterance": utterance}) as trace:
        try:
            for _ in range(budget):
                decision = _extract_json(
                    chat_fn(_SYSTEM, _render_state(utterance, intent, report, blocked, steps,
                                                   pending_question),
                            max_tokens=768))
                action = decision.get("action") if decision else None
                key = json.dumps(decision, ensure_ascii=False, sort_keys=True)
                if action == "finish":
                    outcome, concerns = "finish", decision.get("concerns") or []
                    break
                if action not in ("lookup", "patch"):
                    outcome = "contract_violation"
                    break
                if key in seen:
                    # 같은 행동의 반복은 한 번 사유를 돌려주고 잇는다 — 바로 끊으면 채울 것이 없는
                    # 턴이 '규칙 위반'으로 끝난다(2026-11-16 실측 10턴 중 8턴이 같은 조회 반복).
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
                    observation, accepted = _try_patch(decision, intent, report, utterance, blocked,
                                                       blocked_paths)
                    if accepted is not None:
                        intent, report = accepted[0], accepted[1]
                        accepted_patches.extend(accepted[2])
                        filled += 1
                steps.append({**decision, "observation": observation})
        except Exception:  # noqa: BLE001 — 보조 에이전트 장애가 해석 턴을 깨면 안 된다
            logger.warning("verify agent 실행 실패 — 수락된 채우기만 유지", exc_info=True)
            outcome = "error"
        if isinstance(concerns, list):
            for concern in concerns:
                candidate = _correction(concern, intent, report, utterance)
                if candidate is not None:
                    corrections.append(candidate)
        trace.output(outcome=outcome, filled=filled, concerns=concerns,
                     corrections=corrections, steps=steps)
    if not filled and not corrections:
        return None
    return VerifyOutcome(intent=intent, report=report, filled=filled, patches=accepted_patches,
                         corrections=corrections)
