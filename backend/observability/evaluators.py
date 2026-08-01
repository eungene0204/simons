"""결정론 Evaluator — Trace 하나를 읽고 구조적 성질만 채점한다(스펙 § Evaluation).

원칙 두 가지:

1. **LLM judge를 쓰지 않는다.** 채점이 비결정적이면 회귀 테스트로 쓸 수 없다. 여기
   있는 검사는 전부 같은 Trace에 대해 같은 점수를 낸다.
2. **판정할 수 없으면 None을 낸다.** 근거가 없는데 1점이나 0점을 주면 대시보드가
   거짓말을 한다. 예를 들어 planner가 폴백된 턴에는 "DAG가 올바른가"를 채점하지
   않는다 — DAG가 없는 것이지 나쁜 것이 아니다.

자연어 해석 계약: 이 모듈은 **사용자 원문의 의미를 판정하지 않는다.** 검사 입력은
Agent가 만든 구조화 출력(DAG·노드 상태·질문 문자열)과 Dataset이 사람 손으로 붙인
라벨뿐이다. 원문에서 지표·업종·의도를 추출하는 코드를 여기 추가해서는 안 된다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

# 채점 결과. score=None은 "이 턴에는 해당 없음"이며 집계에서 빠진다.
Result = Dict[str, Any]


def _result(key: str, score: Optional[float], comment: str) -> Result:
    return {"key": key, "score": score, "comment": comment}


# ── 1. Planner가 올바른 DAG를 생성했는가 ──────────────────────────────────────

def dag_well_formed(dag: Optional[Dict[str, Any]]) -> Result:
    """DAG 구조 계약 — 실행 계층의 validate_dag와 같은 성질을 사후에 다시 본다.

    러너가 이미 검증하므로 통과가 기본이다. 여기서 0이 나오면 **검증을 통과한 DAG가
    계약을 어겼다는 뜻**이라 러너 쪽 결함이다.
    """
    key = "dag_well_formed"
    if not dag or not dag.get("nodes"):
        return _result(key, None, "DAG 없음(planner 미사용 또는 폴백) — 채점 제외")
    nodes = dag["nodes"]
    ids = [n.get("id") for n in nodes]
    problems: List[str] = []
    if len(ids) != len(set(ids)):
        problems.append("노드 id 중복")
    known = set(ids)
    for node in nodes:
        for dep in node.get("depends_on") or []:
            if dep not in known:
                problems.append(f"존재하지 않는 의존: {node.get('id')} → {dep}")
    if _has_cycle(nodes):
        problems.append("순환 존재")
    finishes = [n for n in nodes if n.get("type") == "finish"]
    for finish in finishes:
        deps = _transitive(finish.get("id"), nodes)
        tools = {n.get("tool") for n in nodes if n.get("id") in deps}
        if "compile_strategy" not in tools:
            problems.append("finish가 compile_strategy에 의존하지 않음")
        elif "validate_intent" not in tools:
            problems.append("compile_strategy가 validate_intent에 의존하지 않음")
    return _result(key, 0.0 if problems else 1.0,
                   "; ".join(problems) if problems else f"정상 (노드 {len(nodes)}개)")


def _has_cycle(nodes: Sequence[Dict[str, Any]]) -> bool:
    ids = {n.get("id") for n in nodes}
    indegree = {n.get("id"): len([d for d in (n.get("depends_on") or []) if d in ids])
                for n in nodes}
    children: Dict[Any, List[Any]] = {n.get("id"): [] for n in nodes}
    for node in nodes:
        for dep in node.get("depends_on") or []:
            if dep in ids:
                children[dep].append(node.get("id"))
    queue = [nid for nid, deg in indegree.items() if deg == 0]
    seen = 0
    while queue:
        current = queue.pop()
        seen += 1
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return seen != len(nodes)


def _transitive(node_id: Any, nodes: Sequence[Dict[str, Any]]) -> set:
    by_id = {n.get("id"): n for n in nodes}
    result: set = set()
    stack = list((by_id.get(node_id) or {}).get("depends_on") or [])
    while stack:
        dep = stack.pop()
        if dep in result or dep not in by_id:
            continue
        result.add(dep)
        stack.extend(by_id[dep].get("depends_on") or [])
    return result


# ── 2. 불필요한 Action이 있었는가 ─────────────────────────────────────────────

def no_wasted_actions(
    dag: Optional[Dict[str, Any]], statuses: Optional[Dict[str, str]],
) -> Result:
    """계획됐지만 영영 쓰이지 못한 Action의 비율.

    BLOCKED·INVALIDATED는 낭비다(전제가 깨져 실행될 수 없다). SKIPPED는 낭비가 아니다 —
    이미 채워진 슬롯을 묻지 않고 건너뛴 것은 가드가 제대로 동작한 것이다.
    """
    key = "no_wasted_actions"
    if not dag or not dag.get("nodes") or not statuses:
        return _result(key, None, "DAG/상태 없음 — 채점 제외")
    wasted = [nid for nid, status in statuses.items()
              if status in ("BLOCKED", "INVALIDATED")]
    total = len(statuses)
    score = 1.0 - (len(wasted) / total) if total else None
    comment = (f"낭비 {len(wasted)}/{total}: {', '.join(sorted(wasted))}"
               if wasted else f"낭비 없음 ({total}개)")
    return _result(key, score, comment)


# ── 3. State가 올바르게 변경되었는가 ──────────────────────────────────────────

def state_change_declared(
    dag: Optional[Dict[str, Any]], changed_fields: Optional[Sequence[str]],
) -> Result:
    """실제로 바뀐 State 필드가 어떤 Action의 produces로 선언돼 있는가.

    선언되지 않은 필드가 바뀌었다면 계획 밖에서 State가 움직인 것이다 — DAG가 실행을
    설명하지 못한다는 뜻이라 추적 가능성이 깨진다.
    """
    key = "state_change_declared"
    if not dag or not dag.get("nodes") or changed_fields is None:
        return _result(key, None, "DAG/State 변경 기록 없음 — 채점 제외")
    declared: set = set()
    for node in dag["nodes"]:
        declared.update(node.get("produces") or [])
    if not changed_fields:
        return _result(key, 1.0, "State 변경 없음")
    # 점 표기 경로는 접두 일치로 본다(universe.symbols 선언 ↔ universe.symbols.0 변경).
    undeclared = [
        field for field in changed_fields
        if not any(field == d or field.startswith(f"{d}.") for d in declared)
    ]
    score = 1.0 - (len(undeclared) / len(changed_fields))
    return _result(key, score,
                   f"미선언 변경 {len(undeclared)}/{len(changed_fields)}: "
                   f"{', '.join(undeclared[:8])}" if undeclared else "전부 선언됨")


# ── 4. Tool 선택이 적절했는가 ─────────────────────────────────────────────────

def tool_selection_valid(
    called_tools: Optional[Sequence[str]], forbidden: Optional[Sequence[str]] = None,
) -> Result:
    """금지 도구를 부르지 않았는가 + 같은 도구를 중복 호출하지 않았는가."""
    key = "tool_selection_valid"
    if called_tools is None:
        return _result(key, None, "도구 호출 기록 없음 — 채점 제외")
    problems: List[str] = []
    banned = set(forbidden or [])
    hit = [t for t in called_tools if t in banned]
    if hit:
        problems.append(f"금지 도구 호출: {', '.join(sorted(set(hit)))}")
    duplicates = [t for t in set(called_tools) if called_tools.count(t) > 1]
    if duplicates:
        problems.append(f"중복 호출: {', '.join(sorted(duplicates))}")
    return _result(key, 0.0 if problems else 1.0,
                   "; ".join(problems) if problems else
                   f"정상 ({len(called_tools)}회 호출)")


# ── 5. 응답이 계약을 지켰는가 ─────────────────────────────────────────────────

def response_contract_kept(
    response: Optional[Dict[str, Any]], forbidden_terms: Optional[Sequence[str]] = None,
) -> Result:
    """응답 문구가 유니버스 계약을 어기지 않았는가.

    검사 대상은 **Agent가 생성한 문자열**(질문·칩)이지 사용자 원문이 아니다 —
    ETF 유니버스에 개별 기업 재무 지표 칩이 나오면 계약 위반이라는 판정은 표기만 보면
    결정 가능하다(자연어 해석 계약 § 판정 기준).
    """
    key = "response_contract_kept"
    if not response:
        return _result(key, None, "응답 없음 — 채점 제외")
    if not forbidden_terms:
        return _result(key, None, "이 예시엔 금지 표현 라벨 없음 — 채점 제외")
    surface = " ".join(filter(None, [
        response.get("clarification_question") or "",
        " ".join(response.get("clarification_suggestions") or []),
        " ".join((response.get("pending_ask") or {}).get("chips") or []),
    ]))
    hit = [term for term in forbidden_terms if term in surface]
    return _result(key, 0.0 if hit else 1.0,
                   f"금지 표현 노출: {', '.join(hit)}" if hit else "정상")


# ── 6. 사용자 요청이 진전되었는가 ─────────────────────────────────────────────

def turn_made_progress(response: Optional[Dict[str, Any]]) -> Result:
    """이 턴이 대화를 앞으로 보냈는가.

    **되묻기는 실패가 아니다** — 말하지 않은 값을 묻는 것이 Agent의 계약이다. 실패는
    아무것도 확정하지 못하고 질문도 못 한 턴이다.
    """
    key = "turn_made_progress"
    if response is None:
        return _result(key, 0.0, "응답 없음(예외 종료)")
    if response.get("clarification_question"):
        return _result(key, 1.0, "되묻기로 진전(정상 동작)")
    if response.get("outcome") == "answer":
        return _result(key, 1.0, "전략 확정")
    return _result(key, 0.0, "확정도 질문도 없음")


# ── 집계 ──────────────────────────────────────────────────────────────────────

def evaluate_trace(observed: Dict[str, Any], labels: Optional[Dict[str, Any]] = None,
                   ) -> List[Result]:
    """Trace 하나의 관찰값 묶음을 전부 채점한다.

    observed 키: dag, node_statuses, changed_fields, called_tools, response
    labels(Dataset metadata) 키: forbidden_tools, forbidden_terms
    """
    labels = labels or {}
    return [
        dag_well_formed(observed.get("dag")),
        no_wasted_actions(observed.get("dag"), observed.get("node_statuses")),
        state_change_declared(observed.get("dag"), observed.get("changed_fields")),
        tool_selection_valid(observed.get("called_tools"), labels.get("forbidden_tools")),
        response_contract_kept(observed.get("response"), labels.get("forbidden_terms")),
        turn_made_progress(observed.get("response")),
    ]


def summarize(results: Sequence[Result]) -> Dict[str, Any]:
    """채점 결과 요약. score=None은 집계에서 빠진다(판정 불가 ≠ 0점)."""
    scored = [r for r in results if r.get("score") is not None]
    return {
        "scored": len(scored),
        "skipped": len(results) - len(scored),
        "mean": round(sum(r["score"] for r in scored) / len(scored), 3) if scored else None,
        "failed": [r["key"] for r in scored if r["score"] < 1.0],
    }
