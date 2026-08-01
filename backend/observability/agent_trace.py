"""Agent 구조(Action DAG · State · 응답)를 Trace 관찰값으로 옮기는 어댑터.

tracing.py는 어떤 도메인도 모르는 파사드이고, 이 모듈이 **널스탁 Agent의 자료구조를
읽어** 관찰값 형태로 바꾼다. 읽기 전용이다 — DagNode·ParsedStrategy·report 어느 것도
수정하지 않는다.

strategy_conversation을 import하지 않는다(덕타이핑). 관찰 계층이 실행 계층을 import하면
의존 방향이 뒤집혀, 나중에 실행 계층이 관찰을 import할 때 순환이 된다.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger("observability.agent_trace")


def dag_snapshot(
    nodes: Optional[Sequence[Any]],
    *,
    statuses: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Action DAG 전체를 관찰값으로(스펙 § 3 Action DAG).

    statuses는 dag.node_statuses()의 산출물 — 있으면 노드별 상태를 함께 싣는다.
    없으면 구조만 싣는다(상태를 여기서 다시 계산하지 않는다 — 판정은 실행 계층 소관).
    """
    if not nodes:
        return {"nodes": [], "edges": [], "node_count": 0}
    rendered: List[Dict[str, Any]] = []
    edges: List[str] = []
    for node in nodes:
        entry: Dict[str, Any] = {
            "id": getattr(node, "id", None),
            "type": getattr(node, "type", None),
        }
        status = (statuses or {}).get(entry["id"])
        if status is not None:
            entry["status"] = getattr(status, "value", str(status))
        if entry["type"] == "tool":
            entry["tool"] = getattr(node, "tool", None)
            entry["args"] = getattr(node, "args", None)
        elif entry["type"] == "ask":
            entry["topic"] = getattr(node, "topic", None)
            entry["question"] = getattr(node, "question", None)
            entry["chips"] = list(getattr(node, "chips", None) or [])
        for axis in ("requires", "produces", "invalidated_by"):
            values = list(getattr(node, axis, None) or [])
            if values:
                entry[axis] = values
        deps = list(getattr(node, "depends_on", None) or [])
        if deps:
            entry["depends_on"] = deps
            edges.extend(f"{dep} → {entry['id']}" for dep in deps)
        rendered.append(entry)
    return {"nodes": rendered, "edges": edges, "node_count": len(rendered)}


def dag_ascii(nodes: Optional[Sequence[Any]]) -> str:
    """DAG를 사람이 읽는 한 덩어리로(스펙 § 3의 표기).

    Trace UI에서 노드 배열을 펼치지 않고도 흐름을 보기 위한 것이다.
    """
    if not nodes:
        return "(빈 DAG)"
    label: Dict[str, str] = {}
    for node in nodes:
        nid = getattr(node, "id", "?")
        ntype = getattr(node, "type", "?")
        if ntype == "tool":
            label[nid] = f"{getattr(node, 'tool', '?')}"
        elif ntype == "ask":
            label[nid] = f"Ask({getattr(node, 'topic', None) or nid})"
        else:
            label[nid] = ntype.capitalize()
    lines: List[str] = []
    for node in nodes:
        nid = getattr(node, "id", "?")
        deps = list(getattr(node, "depends_on", None) or [])
        prefix = ", ".join(label.get(d, d) for d in deps)
        lines.append(f"{prefix} ↓ {label.get(nid, nid)}" if prefix else label.get(nid, nid))
    return "\n".join(lines)


def _flatten(value: Any, prefix: str = "", out: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """중첩 dict를 점 표기 경로로 편다 — State diff의 입력."""
    out = {} if out is None else out
    if isinstance(value, dict):
        for key, item in value.items():
            _flatten(item, f"{prefix}.{key}" if prefix else str(key), out)
    else:
        out[prefix] = value
    return out


def state_diff(before: Any, after: Any) -> Dict[str, Any]:
    """State 전후 차이(스펙 § 6). 어떤 필드가 무엇에서 무엇으로 바뀌었는지.

    before/after는 dict거나 model_dump()를 가진 pydantic 모델이면 된다.
    """
    def _as_dict(value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if hasattr(value, "model_dump"):
            try:
                return value.model_dump()
            except Exception:  # noqa: BLE001
                return {}
        return dict(value) if isinstance(value, dict) else {}

    try:
        flat_before = _flatten(_as_dict(before))
        flat_after = _flatten(_as_dict(after))
    except Exception:  # noqa: BLE001 — 진단용 값이 실행을 깨지 않는다
        logger.debug("state diff 계산 실패", exc_info=True)
        return {}

    changed: Dict[str, Any] = {}
    for key in set(flat_before) | set(flat_after):
        old, new = flat_before.get(key), flat_after.get(key)
        if old != new:
            changed[key] = {"before": _short(old), "after": _short(new)}
    return {
        "changed_fields": sorted(changed),
        "changed_count": len(changed),
        "diff": dict(list(changed.items())[:60]),
    }


def _short(value: Any, limit: int = 200) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[:limit] + "…"


def responder_payload(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """사용자에게 실제로 나간 것(스펙 § 8 최종 응답).

    전략 전문이 아니라 **사용자가 보는 것**과 되묻기 상태를 싣는다 — Trace를 열었을 때
    "이 턴이 무엇을 물었고 무엇을 확정했나"가 한눈에 보여야 한다.
    """
    if not result:
        return {"delivered": None}
    payload: Dict[str, Any] = {
        "clarification_question": result.get("clarification_question"),
        "clarification_suggestions": result.get("clarification_suggestions"),
        "clarification_priority": result.get("clarification_priority"),
        "notices": result.get("notices"),
        "explicit_fields": result.get("explicit_fields"),
        "symbol_count": result.get("symbol_count"),
    }
    pending = result.get("pending_ask")
    if pending:
        payload["pending_ask"] = pending
    payload["outcome"] = "ask" if payload["clarification_question"] else "answer"
    return {k: v for k, v in payload.items() if v is not None}


def ask_binding_gate(
    *,
    question: Optional[str],
    priority: Optional[str],
    chips_offered: Optional[Sequence[str]],
    pending_ask: Optional[Dict[str, Any]],
    planner_mode_primary: bool,
    planner_ran: bool,
    ask_reason: Optional[str] = None,
    lane: str = "parse",
) -> Dict[str, Any]:
    """되묻기 질문↔답변 결속(pending_ask)이 **어느 게이트에서 끊겼나**.

    pending_ask는 "이 답이 저 질문의 답"이라는 유일한 결정론 근거다. 없으면 다음 턴의
    사용자 답변은 일반 의도 분류 레인으로 떨어져 새 발화로 읽힌다. 그런데 발행까지
    통과해야 하는 게이트가 여러 개인데다 **실패가 전부 조용한 폴백**이라, Trace에
    pending_ask 유무만 실으면 "왜 없는지"를 알 수 없다(responder_payload의 한계).

    이 함수는 판정을 새로 하지 않는다 — 이미 실행 계층이 내린 결과(질문·칩·pending_ask)를
    읽어 어느 단계에서 끊겼는지만 이름 붙인다.

    gate 값:
      ok                   결속 성립(다음 턴 답변 귀속 가능)
      no_question          되묻기 없는 턴 — 결속 대상이 없다(정상)
      planner_off          STRATEGY_DAG_PLANNER_MODE != primary
      path_without_binding 결속을 발행하지 않는 질문 경로(sector/symbol 미해결)
      planner_failed       planner 실행 실패·예산 소진 → 고정 파이프라인 질문
      ask_rejected:<사유>  planner ask를 결정론 게이트가 채택하지 않음
      no_chips             질문은 있으나 칩이 없어 결속 대상이 없다
      chip_binding_failed  칩은 있었으나 전부 값 결속에 실패해 탈락

    lane: "parse"(초기 파스) | "modify"(수정). **수정 레인은 설계상 플래너를 돌리지
    않으므로 플래너 관련 게이트를 적용하지 않는다** — 적용하면 정상 동작이 전부
    planner_failed로 잡혀 Trace가 없는 원인을 가리킨다.
    """
    offered = [c for c in (chips_offered or []) if c]
    bound = [c for c in ((pending_ask or {}).get("chips") or []) if c]
    planner_lane = lane != "modify"

    if not question:
        gate = "no_question"
    elif pending_ask:
        gate = "ok"
    elif planner_lane and not planner_mode_primary:
        gate = "planner_off"
    elif priority == "sector_unresolved":
        gate = "path_without_binding"
    elif planner_lane and not planner_ran:
        gate = "planner_failed"
    elif ask_reason:
        gate = f"ask_rejected:{ask_reason}"
    elif not offered:
        gate = "no_chips"
    else:
        gate = "chip_binding_failed"

    verdict: Dict[str, Any] = {
        "gate": gate,
        "bound": gate == "ok",
        "lane": lane,
        "priority": priority,
        "topic": (pending_ask or {}).get("topic"),
        "chips_offered": len(offered),
        "chips_bound": len(bound),
    }
    dropped = [c for c in offered if c not in bound]
    if dropped:
        # 어떤 문구가 결속에 실패했는지가 수정 대상이다 — 개수만으로는 못 고친다.
        verdict["chips_dropped"] = dropped[:20]
    return verdict


def tool_observation(output: Any) -> Any:
    """도구 산출물 → 관찰값. pydantic 모델이면 dict로 편다."""
    if hasattr(output, "model_dump"):
        try:
            return output.model_dump()
        except Exception:  # noqa: BLE001
            return repr(output)
    return output


def node_status_counts(statuses: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """상태별 노드 수 — '어디서 멈췄나'를 Trace 목록에서 바로 거르기 위한 요약."""
    counts: Dict[str, int] = {}
    for status in (statuses or {}).values():
        key = getattr(status, "value", str(status))
        counts[key] = counts.get(key, 0) + 1
    return counts


def ollama_usage(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Ollama /api/chat 응답의 토큰·지연 지표(스펙 § 7).

    self-hosted라 단가가 없으므로 Cost는 싣지 않는다 — 지어낸 비용은 관찰이 아니다.
    """
    if not isinstance(payload, dict):
        return {}
    usage: Dict[str, Any] = {}
    for source, target in (
        ("prompt_eval_count", "input_tokens"),
        ("eval_count", "output_tokens"),
    ):
        value = payload.get(source)
        if isinstance(value, int):
            usage[target] = value
    if "input_tokens" in usage and "output_tokens" in usage:
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    for source, target in (
        ("total_duration", "ollama_total_ns"),
        ("load_duration", "ollama_load_ns"),
    ):
        value = payload.get(source)
        if isinstance(value, int):
            usage[target] = value
    return usage


def dedupe(values: Iterable[Any]) -> List[Any]:
    """관찰값 목록의 중복 제거(순서 유지)."""
    seen: set = set()
    out: List[Any] = []
    for value in values:
        key = repr(value)
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out
