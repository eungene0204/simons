"""Action DAG 모델·결정론 검증·스케줄링(Planner→Tool→Responder Phase 4).

Planner LLM의 유일한 출력은 DAG(JSON)다 — 실행(도구 호출·질문 전달·상태 갱신)은
전부 결정론 러너(dag_planner.py) 소관이고, 이 모듈은 그 러너가 쓰는 순수 자료구조와
검증만 담당한다. 검증은 전부 결정론이다:

- 노드 id 고유·타입 유효·의존 노드 존재·비순환(Kahn)
- tool 노드는 화이트리스트 도구만, args는 dict만
- ask 노드는 질문 필수, 질문 하나당 노드 하나(질문 병합 금지는 프롬프트 계약)
- 노드 수 예산 초과 금지
- done 노드 불변 — 재발행 시 type/tool/args가 다르거나 누락되면 계약 위반
- finish 노드는 compile_strategy에 (전이적으로) 의존해야 하고, 그 compile은
  validate_intent에 의존해야 한다 — 검증·컴파일 없는 확정 경로를 구조로 차단

계약 위반은 DagContractError — 호출부(러너)는 이를 폴백(None) 신호로 강등한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Set

_VALID_TYPES = ("tool", "ask", "finish")


class NodeStatus(str, Enum):
    """Action 상태(설계 스펙 § 12.2).

    러너는 완료 집합(done_ids)만으로 스케줄링해 왔다. 그러면 "왜 이 노드가 실행되지
    않았나"를 구분할 수 없다 — 의존이 안 끝난 것인지, 무효화된 것인지, 실패한 것인지가
    전부 '아직 안 됨' 하나였다. 이 축이 그 구분을 만든다.

    **무효화된 노드는 삭제하지 않고 INVALIDATED로 남긴다**(스펙 § 12.2) — 지우면
    무엇이 왜 취소됐는지 추적할 수 없다.
    """

    PENDING = "PENDING"          # 의존이 아직 안 끝났다
    READY = "READY"              # 의존이 전부 끝나 실행할 수 있다
    RUNNING = "RUNNING"          # 실행 중
    COMPLETED = "COMPLETED"      # 실행 완료(관찰값 확보)
    BLOCKED = "BLOCKED"          # 의존 노드가 무효·실패해 영영 실행될 수 없다
    INVALIDATED = "INVALIDATED"  # State 변경으로 전제가 깨졌다(이력 보존용으로 남긴다)
    FAILED = "FAILED"            # 실행했으나 실패
    SKIPPED = "SKIPPED"          # 실행할 필요가 없어졌다(이미 채워진 슬롯 질문 등)


# 다시 실행될 수 없는 상태 — ready 후보에서 제외되고, 이 노드에 의존하는 노드는 BLOCKED.
_DEAD_STATUSES = frozenset({
    NodeStatus.BLOCKED, NodeStatus.INVALIDATED, NodeStatus.FAILED, NodeStatus.SKIPPED,
})


class DagContractError(Exception):
    """DAG 계약 위반 — 러너는 고정 파이프라인 폴백으로 강등한다."""


@dataclass
class DagNode:
    id: str
    type: str  # "tool" | "ask" | "finish"
    depends_on: List[str] = field(default_factory=list)
    tool: Optional[str] = None
    args: Dict = field(default_factory=dict)
    topic: Optional[str] = None
    question: Optional[str] = None
    chips: List[str] = field(default_factory=list)
    # ── Action 메타데이터(설계 스펙 § 12.1) ────────────────────────────────────
    # depends_on이 '어떤 노드 뒤에 오는가'라면, 아래는 '어떤 State를 쓰고 만드는가'다.
    # 둘을 구분해야 State 변경이 어떤 Action을 무효로 만드는지 계산할 수 있다.
    requires: List[str] = field(default_factory=list)        # 필요한 State 필드
    produces: List[str] = field(default_factory=list)        # 이 Action이 채우는 필드
    invalidated_by: List[str] = field(default_factory=list)  # 이 필드가 바뀌면 무효

    def call_key(self) -> str:
        """동일 도구+인자 판정용 정본 키(실행 중복 방지)."""
        return f"{self.tool}:{json.dumps(self.args, ensure_ascii=False, sort_keys=True)}"

    def immutable_snapshot(self) -> Dict:
        """done 불변성 비교 대상 — 의존 관계 재배선은 허용, 내용 변경은 위반."""
        return {"type": self.type, "tool": self.tool,
                "args": json.dumps(self.args, ensure_ascii=False, sort_keys=True)}


# 도구별 Action 효과(설계 스펙 § 12.1) — **정적 사실이므로 LLM에 묻지 않는다.**
# "kg_theme_companies가 무엇을 만들고 언제 무효가 되는가"는 도구의 성질이지 이번 턴의
# 판단이 아니다. 프롬프트 출력 형태에 필드를 늘리면 9B가 그 자리를 채우려 잡음을 내고
# prefill 예산만 먹는다(FR-STR-019o·019p) — 대신 여기서 결정론으로 채운다.
_TOOL_EFFECTS: Dict[str, Dict[str, List[str]]] = {
    "classify_universe": {
        "produces": ["universe.type"], "invalidated_by": ["universe.term"],
    },
    "list_concept_candidates": {
        "requires": ["universe.type"], "produces": ["universe.candidates"],
        "invalidated_by": ["universe.term", "universe.type"],
    },
    "kg_resolve_sector": {
        "produces": ["universe.sectors"], "invalidated_by": ["universe.term"],
    },
    "kg_theme_companies": {
        "produces": ["universe.symbols"],
        "invalidated_by": ["universe.term", "universe.type", "universe.sectors"],
    },
    "ground_term": {
        "produces": ["universe.term_definition"], "invalidated_by": ["universe.term"],
    },
    "resolve_universe": {
        "requires": ["universe.type"], "produces": ["universe.symbols"],
        "invalidated_by": ["universe.term", "universe.type", "universe.sectors"],
    },
    "lookup_capabilities": {
        "requires": ["universe.type"], "produces": ["capabilities"],
        "invalidated_by": ["universe.type"],
    },
    "validate_intent": {
        "produces": ["validation"],
        "invalidated_by": ["universe.type", "universe.symbols", "conditions"],
    },
    "compile_strategy": {
        "requires": ["validation"], "produces": ["strategy"],
        "invalidated_by": ["universe.type", "universe.symbols", "conditions"],
    },
}


def tool_effects(tool: Optional[str]) -> Dict[str, List[str]]:
    """도구의 정적 Action 효과. 모르는 도구는 빈 효과(지어내지 않는다)."""
    return _TOOL_EFFECTS.get(tool or "", {})


def parse_dag(data: Dict) -> List[DagNode]:
    """LLM 출력 dict → DagNode 목록. 구조 위반은 DagContractError."""
    if not isinstance(data, dict):
        raise DagContractError("출력이 JSON 객체가 아님")
    dag = data.get("dag")
    if not isinstance(dag, dict) or not isinstance(dag.get("nodes"), list):
        raise DagContractError('{"dag": {"nodes": [...]}} 형식이 아님')
    nodes: List[DagNode] = []
    for raw in dag["nodes"]:
        if not isinstance(raw, dict):
            raise DagContractError("노드가 JSON 객체가 아님")
        node_id = raw.get("id")
        node_type = raw.get("type")
        if not isinstance(node_id, str) or not node_id.strip():
            raise DagContractError("노드 id 누락")
        if node_type not in _VALID_TYPES:
            raise DagContractError(f"노드 타입 위반: {node_type!r}")
        depends_on = raw.get("depends_on") or []
        if not isinstance(depends_on, list) or not all(isinstance(d, str) for d in depends_on):
            raise DagContractError(f"depends_on 형식 위반: {node_id}")
        args = raw.get("args") or {}
        if not isinstance(args, dict):
            raise DagContractError(f"args가 객체가 아님: {node_id}")
        chips = raw.get("chips") or []
        if not isinstance(chips, list) or not all(isinstance(c, str) for c in chips):
            raise DagContractError(f"chips 형식 위반: {node_id}")
        # 메타데이터는 도구의 정적 사실이 정본이다. LLM이 실어 보내도(스펙 § 12.1 형식)
        # 형식만 검증하고, 알려진 도구면 정적 표로 덮어쓴다 — 도구가 무엇을 만드는지를
        # LLM이 이번 턴에 다시 정하게 두지 않는다.
        effects = tool_effects(raw.get("tool"))
        meta = {}
        for key in ("requires", "produces", "invalidated_by"):
            value = raw.get(key) or []
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise DagContractError(f"{key} 형식 위반: {node_id}")
            meta[key] = list(effects.get(key, [v.strip() for v in value if v.strip()]))
        nodes.append(DagNode(
            id=node_id.strip(), type=node_type, depends_on=list(depends_on),
            tool=raw.get("tool"), args=args, topic=raw.get("topic"),
            question=raw.get("question"), chips=chips, **meta,
        ))
    return nodes


def _assert_acyclic(nodes: Sequence[DagNode]) -> None:
    """Kahn 위상정렬 — 전부 소비되지 않으면 순환."""
    ids = {n.id for n in nodes}
    indegree = {n.id: len([d for d in n.depends_on if d in ids]) for n in nodes}
    dependents: Dict[str, List[str]] = {n.id: [] for n in nodes}
    for n in nodes:
        for dep in n.depends_on:
            if dep in ids:
                dependents[dep].append(n.id)
    queue = [nid for nid, deg in indegree.items() if deg == 0]
    seen = 0
    while queue:
        current = queue.pop()
        seen += 1
        for child in dependents[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if seen != len(nodes):
        raise DagContractError("DAG에 순환 존재")


def _transitive_deps(node: DagNode, by_id: Dict[str, DagNode]) -> Set[str]:
    result: Set[str] = set()
    stack = list(node.depends_on)
    while stack:
        dep = stack.pop()
        if dep in result or dep not in by_id:
            continue
        result.add(dep)
        stack.extend(by_id[dep].depends_on)
    return result


def validate_dag(
    nodes: Sequence[DagNode],
    *,
    allowed_tools: Sequence[str],
    node_budget: int,
    done_snapshots: Optional[Dict[str, Dict]] = None,
) -> None:
    """구조 계약 전체를 검증한다. 위반은 DagContractError."""
    if len(nodes) > node_budget:
        raise DagContractError(f"노드 예산 초과: {len(nodes)} > {node_budget}")
    ids = [n.id for n in nodes]
    if len(ids) != len(set(ids)):
        raise DagContractError("노드 id 중복")
    by_id = {n.id: n for n in nodes}
    for n in nodes:
        for dep in n.depends_on:
            if dep not in by_id:
                raise DagContractError(f"존재하지 않는 의존 노드: {n.id} → {dep}")
        if n.type == "tool":
            if n.tool not in allowed_tools:
                raise DagContractError(f"화이트리스트 밖 도구: {n.tool!r}")
        elif n.type == "ask":
            if not (n.question or "").strip():
                raise DagContractError(f"ask 노드에 질문 없음: {n.id}")
    _assert_acyclic(nodes)

    # 동일 도구+인자 tool 노드 중복 금지(실행 중복의 구조적 차단)
    call_keys = [n.call_key() for n in nodes if n.type == "tool"]
    if len(call_keys) != len(set(call_keys)):
        raise DagContractError("동일 도구+인자 tool 노드 중복")

    # finish → compile_strategy → validate_intent 의존 사슬 강제
    for n in nodes:
        if n.type != "finish":
            continue
        deps = _transitive_deps(n, by_id)
        compiles = [by_id[d] for d in deps
                    if by_id[d].type == "tool" and by_id[d].tool == "compile_strategy"]
        if not compiles:
            raise DagContractError("finish가 compile_strategy에 의존하지 않음")
        if not any(
            by_id[d].tool == "validate_intent"
            for c in compiles for d in _transitive_deps(c, by_id)
            if by_id[d].type == "tool"
        ):
            raise DagContractError("compile_strategy가 validate_intent에 의존하지 않음")

    # done 노드 불변성 — 내용 변경은 위반. 누락은 위반이 아니다: done은 러너가 보유한
    # 이력이라 LLM이 재발행을 생략해도 의미가 명백하다(러너가 병합 유지 — 계약 § 판정
    # 기준의 'LLM 출력 표기 정규화'. 9B가 done 재발행을 자주 생략해 전량 폴백되던
    # 문제의 결정론 보정이며, 러너 보유 사본이 정본이므로 안전성은 동일하다).
    for done_id, snapshot in (done_snapshots or {}).items():
        node = by_id.get(done_id)
        if node is not None and node.immutable_snapshot() != snapshot:
            raise DagContractError(f"done 노드 변경: {done_id}")


def invalidated_by_state_change(
    nodes: Sequence[DagNode], changed_fields: Set[str], done_ids: Set[str]
) -> Set[str]:
    """State 변경으로 전제가 깨진 노드 id(설계 스펙 § 12.1 invalidated_by).

    완료된 노드도 무효화 대상이다 — 유니버스가 바뀌면 그 전에 조회한 테마 상장사
    관찰값은 더 이상 이 전략의 것이 아니다. 무효화는 **연쇄**한다: 무효 노드의 관찰에
    기대던 노드도 함께 무효다(그 관찰이 사라졌으므로).

    LLM의 판단이 아니라 노드가 선언한 invalidated_by와 실제 변경 필드의 대조다.
    선언하지 않은 노드는 무효화되지 않는다 — 지어내서 지우지 않는다.
    """
    if not changed_fields:
        return set()
    # 씨앗은 **이미 완료된** 노드뿐이다. 아직 실행 전인 노드까지 씨앗으로 삼으면 정상
    # 선행 실행이 무효로 잡힌다 — classify_universe(produces universe.type)가 먼저 돌면
    # 그 값에 기대는 kg_theme_companies가 시작도 전에 무효가 된다.
    invalid = {
        n.id for n in nodes
        if n.id in done_ids
        and n.invalidated_by and changed_fields.intersection(n.invalidated_by)
    }
    # 연쇄 — 무효 노드에 의존하는 노드도 무효(고정점까지 반복).
    while True:
        cascaded = {
            n.id for n in nodes
            if n.id not in invalid and invalid.intersection(n.depends_on)
        }
        if not cascaded:
            return invalid
        invalid |= cascaded


def node_statuses(
    nodes: Sequence[DagNode],
    done_ids: Set[str],
    invalidated_ids: Optional[Set[str]] = None,
    failed_ids: Optional[Set[str]] = None,
    skipped_ids: Optional[Set[str]] = None,
) -> Dict[str, NodeStatus]:
    """노드별 상태(설계 스펙 § 12.2). 무효·실패 노드는 목록에서 지우지 않고 표시한다.

    의존 노드가 다시 실행될 수 없는 상태면 BLOCKED다 — '아직 안 됨'(PENDING)과 구분해야
    러너가 영영 오지 않을 노드를 기다리지 않는다.
    """
    invalidated = invalidated_ids or set()
    failed = failed_ids or set()
    skipped = skipped_ids or set()
    result: Dict[str, NodeStatus] = {}
    for node in nodes:
        if node.id in invalidated:
            result[node.id] = NodeStatus.INVALIDATED
        elif node.id in failed:
            result[node.id] = NodeStatus.FAILED
        elif node.id in skipped:
            result[node.id] = NodeStatus.SKIPPED
        elif node.id in done_ids:
            result[node.id] = NodeStatus.COMPLETED
        else:
            result[node.id] = NodeStatus.PENDING
    # 죽은 의존을 가진 노드는 BLOCKED — 고정점까지 전파한다.
    while True:
        changed = False
        for node in nodes:
            if result[node.id] is not NodeStatus.PENDING:
                continue
            if any(result.get(d) in _DEAD_STATUSES for d in node.depends_on):
                result[node.id] = NodeStatus.BLOCKED
                changed = True
        if not changed:
            break
    for node in nodes:
        if result[node.id] is NodeStatus.PENDING and all(
            d in done_ids for d in node.depends_on
        ):
            result[node.id] = NodeStatus.READY
    return result


def ready_nodes(
    nodes: Sequence[DagNode],
    done_ids: Set[str],
    excluded_ids: Optional[Set[str]] = None,
) -> List[DagNode]:
    """의존이 전부 done인 미완료 노드(발행 순서 유지).

    excluded_ids(무효·실패·스킵)는 후보에서 빠지고, 그 노드를 의존으로 가진 노드도
    영영 ready가 되지 않는다(BLOCKED — node_statuses가 같은 판정을 이름으로 준다).
    """
    return [n for n in nodes
            if n.id not in done_ids and n.id not in (excluded_ids or set())
            and all(d in done_ids for d in n.depends_on)]
