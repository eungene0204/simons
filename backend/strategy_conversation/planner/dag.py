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
from typing import Dict, List, Optional, Sequence, Set

_VALID_TYPES = ("tool", "ask", "finish")


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

    def call_key(self) -> str:
        """동일 도구+인자 판정용 정본 키(실행 중복 방지)."""
        return f"{self.tool}:{json.dumps(self.args, ensure_ascii=False, sort_keys=True)}"

    def immutable_snapshot(self) -> Dict:
        """done 불변성 비교 대상 — 의존 관계 재배선은 허용, 내용 변경은 위반."""
        return {"type": self.type, "tool": self.tool,
                "args": json.dumps(self.args, ensure_ascii=False, sort_keys=True)}


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
        nodes.append(DagNode(
            id=node_id.strip(), type=node_type, depends_on=list(depends_on),
            tool=raw.get("tool"), args=args, topic=raw.get("topic"),
            question=raw.get("question"), chips=chips,
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


def ready_nodes(nodes: Sequence[DagNode], done_ids: Set[str]) -> List[DagNode]:
    """의존이 전부 done인 미완료 노드(발행 순서 유지)."""
    return [n for n in nodes
            if n.id not in done_ids and all(d in done_ids for d in n.depends_on)]
