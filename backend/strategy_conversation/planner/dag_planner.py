"""DAG Planner — 대화 턴 전체 Action DAG 계획(Planner→Tool→Responder Phase 4).

Planner LLM의 유일한 출력은 Action DAG(JSON)다. 실행은 전부 이 모듈의 결정론
러너가 수행한다: DAG 구조 검증(dag.py) → ready tool 노드 실행 → 관찰 기록 →
관찰을 다음 LLM 턴에 제시. ask 노드는 새 관찰이 없는 턴에만 표면화한다 —
도구 관찰이 질문을 불필요하게 만들 수 있으므로 LLM에게 수정 기회를 한 턴 준다.

mini_planner(Phase 3)의 안전 계약을 DAG로 확장한 것이다:

- DAG 구조 검증은 전부 결정론(dag.validate_dag) — 위반 즉시 폴백
- LLM 턴 예산(config.dag_planner_max_turns) 초과·무진전 동일 발행 즉시 폴백
- 동일 도구+인자는 한 번만 실행(관찰 재사용) — 루프의 구조적 차단
- validate_intent·compile_strategy는 DAG 구조상 허용하되 이 단계(shadow)에선
  실행하지 않는다(러너 보유 intent 상태가 필요 — primary 승격 시 배선)
- **확정값은 도구 관찰값에서만 채택한다** — finish·ask 문구의 LLM 주장값 무시
- 표면화되는 ask 질문은 출력 관문(output_guard)을 통과한다
- ground_term 학습 성공 후 테마 재조회는 판단이 아니라 절차 — LLM 턴 없이
  결정론 에필로그로 실행한다(고정 체인·mini_planner와 같은 계약)

실패는 전부 None 반환 — 고정 파이프라인이 그대로 담당한다(planner는 어떤
경우에도 단독 실패 지점이 아니다).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from strategy_conversation import config
from strategy_conversation.planner.dag import (
    DagContractError,
    DagNode,
    parse_dag,
    invalidated_by_state_change,
    ready_nodes,
    validate_dag,
)
from strategy_conversation.planner.dag import node_statuses
from strategy_conversation.response.output_guard import guard_text
from strategy_conversation.tools import ToolError, call as call_tool, get_tool

from observability import span
from observability.agent_trace import dag_ascii, dag_snapshot, node_status_counts

logger = logging.getLogger("strategy_interpreter.planner.dag")

# DAG 구조에 등장할 수 있는 도구 전체(화이트리스트).
_ALLOWED_TOOLS = (
    "classify_universe", "list_concept_candidates",
    "kg_resolve_sector", "kg_theme_companies", "ground_term", "resolve_universe",
    "lookup_capabilities", "validate_intent", "compile_strategy",
)
# 러너가 실제 실행하는 도구 — validate/compile은 러너 보유 intent 상태가 필요해
# 레인(primary.py)이 결정론으로 실행한다(구조상 노드로는 허용 — finish 사슬 계약).
_EXECUTABLE_TOOLS = (
    "classify_universe", "list_concept_candidates",
    "kg_resolve_sector", "kg_theme_companies", "ground_term", "resolve_universe",
    "lookup_capabilities",
)

_OBSERVATION_RENDER_LIMIT = 600  # LLM 상태 제시용 관찰 축약(로그에는 전문 보존)


@dataclass
class ExecutedNode:
    node: DagNode
    observation: Optional[Dict[str, Any]]


@dataclass
class DagPlanResult:
    outcome: str  # "ask" | "finish"
    question: Optional[str]
    chips: List[str]
    sector: Optional[str]          # 도구 관찰값에서만 채택
    companies: List[dict]          # 도구 관찰값에서만 채택
    nodes: List[DagNode]           # 마지막 발행 DAG
    topic: Optional[str] = None    # 표면화된 ask 노드의 슬롯(칩 답변 귀속 근거)
    executed: Dict[str, ExecutedNode] = field(default_factory=dict)
    auto_steps: List[dict] = field(default_factory=list)
    llm_turns: int = 0
    latency_ms: int = 0


def _system_prompt() -> str:
    tool_lines = "\n".join(
        f"- {name}: {get_tool(name).description}" for name in _ALLOWED_TOOLS
    )
    return (
        "당신은 널스탁(NullStock) Strategy Planner입니다. 널스탁은 투자 연구·백테스트 "
        "시뮬레이션 플랫폼이며 투자 자문·추천·전망·개인 맞춤형 조언을 제공하지 않습니다. "
        "당신의 유일한 출력은 Action DAG입니다 — 사용자가 말한 전략 조건을 구조화된 "
        "전략 정의로 완성하기까지 필요한 Action들과 의존관계를 DAG로 발행·수정합니다. "
        "전략의 우열·적합성 판단, 종목·전략 추천, 시장 전망은 어떤 경우에도 하지 않습니다.\n"
        "당신은 Action을 직접 실행하지 않습니다. 실행은 결정론 러너가 수행하고, 당신은 "
        "관찰(observation)을 보고 DAG를 수정할 뿐입니다.\n\n"
        "## 출력 계약 — 매 턴 JSON 객체 하나만 출력\n"
        '{"dag": {"nodes": [\n'
        '  {"id": "<고유 id — 턴이 바뀌어도 유지>", "type": "tool" | "ask" | "finish",\n'
        '   "depends_on": ["<선행 노드 id>"],\n'
        '   "tool": "<도구명>", "args": {...},          // type=tool\n'
        '   "topic": "<수집 정보>", "question": "<질문>",\n'
        '   "chips": ["<옵션>"]                          // type=ask\n'
        "  }]}}\n\n"
        "노드 타입:\n"
        "- tool: 러너가 실행할 도구 호출. 결과는 observation으로 돌아옵니다.\n"
        "- ask: 사용자에게 물을 질문 하나. 한 노드에 여러 질문 금지. chips는 클릭 시 "
        "그대로 메시지로 재전송되므로 칩 텍스트만으로 의미가 완전해야 합니다"
        "(예: \"모멘텀 3개월\", \"손절 -5%\" — \"3개월\", \"5%\" 단독 금지).\n"
        "- finish: 전략 정의 완성 선언 — 반드시 validate_intent에 의존하는 "
        "compile_strategy tool 노드에 의존해야 합니다.\n\n"
        f"## 도구 화이트리스트\n{tool_lines}\n"
        '조회 도구 인자는 {"text": "<표현>"}입니다. validate_intent·compile_strategy는 '
        "인자 없이 노드만 배치하세요(러너가 수집된 State를 공급합니다).\n\n"
        "## DAG 규칙 (러너가 결정론으로 검증 — 위반은 즉시 폴백)\n"
        "1. 비순환. depends_on은 존재하는 노드 id만.\n"
        "2. 같은 노드는 턴이 바뀌어도 같은 id를 유지합니다.\n"
        "3. done 노드는 불변 — 재발행을 생략해도 됩니다(러너가 유지하며, 새 노드의 "
        "depends_on에서 그 id를 계속 쓸 수 있습니다). 재발행한다면 내용을 바꾸지 마세요.\n"
        "4. pending 노드는 자유롭게 추가·수정·삭제 — 사용자가 조건을 바꾸면 영향받는 "
        "노드만 고칩니다. DAG를 처음부터 다시 만들지 마세요.\n"
        "5. 동일 도구+동일 인자 tool 노드를 중복 생성하지 마세요.\n"
        "6. 이미 결정된 정보(관찰·State에 있는 것)를 다시 묻는 ask 노드는 계약 위반입니다.\n"
        "7. 사용자의 최신 입력은 직전 질문에 대한 답이 아닐 수 있습니다 — State 요약이 "
        "그 입력을 반영한 정본이니, 새로 채워진 슬롯의 ask는 삭제하고 영향받는 pending "
        "노드만 수정하세요. 질문과 다른 답변이라는 이유로 오류 처리하지 않습니다.\n"
        "8. 사용자에게 묻지 않고 도구로 해결할 수 있는 정보는 도구를 먼저 사용합니다 — "
        "사용자 선택(선호)이 반드시 필요한 정보만 질문합니다.\n\n"
        "## 유니버스 우선(Universe-first) — 모든 계획의 첫 Action\n"
        "State에 유니버스가 아직 없으면, 다른 어떤 ask보다 먼저 유니버스를 결정합니다:\n"
        "1. 사용자 요청에서 유니버스 표현을 뽑아 classify_universe tool 노드를 만드세요"
        '(예: "보안주 관련 투자 전략" → args={"text": "보안주"}). 유니버스 표현이 전혀 '
        "없으면 이 단계를 건너뛰고 골격 순서대로 진행합니다(시장 선택은 되묻지 않습니다).\n"
        "2. 관찰의 universe_type이 MARKET·SECTOR·SINGLE_STOCK·ETF면 추가 해석이 필요 "
        "없습니다 — 다음 슬롯으로 진행하세요.\n"
        "3. universe_type이 CONCEPT면 **먼저 list_concept_candidates로 범위 후보를 "
        "조회**하세요.\n"
        "   - 후보가 2개 이상: 범위가 갈리는 표현입니다 — kg 해석으로 조용히 확정하지 "
        '말고 ask(topic은 반드시 "유니버스", chips는 관찰의 후보 term 표기 그대로)로 '
        "범위를 물으세요. 후보 표기를 바꾸거나 지어내면 안 됩니다.\n"
        "   - 후보가 1개: 그 표기를 chips 하나로 제시해 확인받으세요(자동 확정 금지).\n"
        "   - 후보가 0개: kg_resolve_sector·kg_theme_companies로 해석하고, 미해석이면 "
        "ground_term(검색 학습)을 시도하세요. 그래도 미해석이면 ask로 물으세요.\n"
        "4. 매수/매도 조건 등 모든 ask 노드는 유니버스 해석 노드(tool 또는 유니버스 ask)에 "
        "depends_on으로 의존해야 합니다 — 유니버스가 조건보다 선행 결정 사항입니다.\n\n"
        "## 진행 골격 — 모든 전략의 공통 줄기(8슬롯)\n"
        "전략은 다음 슬롯을 순서대로 채우면 완성됩니다:\n"
        "유니버스 → 매수 조건 → 매도 조건 → 최대 보유 → 리밸런싱 → 리스크 관리"
        "(손절/익절) → 백테스트 기간 → 초기 자본\n"
        "- ask 노드는 이 슬롯의 **공백에만** 만듭니다. State의 filled_slots에 나열된 "
        "슬롯은 이미 채워진 것이니 절대 다시 묻지 마세요(예: ranking_metric=기간 수익률 "
        "상위 랭킹이 있으면 매수 조건 슬롯은 충족 — filled_slots가 판정의 정본입니다). "
        "한 슬롯당 ask 하나, 골격 순서대로 depends_on을 걸어 한 번에 하나씩 진행합니다.\n"
        "- 슬롯 밖의 질문을 만들지 않습니다. 특정 전략 유형의 파라미터(모멘텀 기간·"
        "추세 조건·거래량 기준 등)는 **사용자가 그 개념을 말한 경우에만** 묻습니다. "
        "언급 없는 매수/매도 조건 공백은 열린 질문(\"어떤 조건에서 매수할까요?\")+"
        "유니버스에 맞는 옵션 칩으로 묻고, 특정 유형을 전제하지 마세요.\n"
        "- 사용자가 말하지 않은 값을 질문 없이 기본값으로 확정하는 경로를 만들지 "
        "않습니다 — 묻거나, chips로 제시해 확인받습니다.\n"
        "- 지원하지 않는 개념(뉴스·공시 기반 조건 등)은 ask로 채우지 말고 미지원 "
        "안내로 종결합니다. 지원 여부의 정본은 도구 관찰값입니다.\n\n"
        "## 유니버스별 디테일 (큰 줄기는 같고 디테일만 다릅니다)\n"
        "① 코스피/코스닥/업종·테마: 8슬롯 전부. 매수 조건 칩은 재무 지표(PER·ROE 등)와 "
        "기술 지표 모두 가능. 미해석 테마·업종 표현은 ask보다 먼저 해석 tool 체인"
        "(kg_resolve_sector·kg_theme_companies → 미해석 시 ground_term)을 넣으세요. "
        "검색이 소진되면 종결 안내 또는 ask.\n"
        "② ETF: 8슬롯 전부, 단 개별 기업 재무정보 사용 불가 — 매수/매도 조건의 질문·"
        "칩에 PER·PBR·ROE·EPS·영업이익·순이익·매출·재무 성장률을 넣으면 계약 위반. "
        "칩은 가격·거래량 기반 기술 지표(이동평균 크로스·RSI·돌파·거래량·기간 수익률 "
        "상위 등)로 구성하세요. ETF는 단독 유니버스(개별 주식과 혼합 불가 — 섞이면 ask).\n"
        "③ 단일종목/지정 종목: 종목이 이미 정해져 있으므로 **유니버스·최대 보유·"
        "리밸런싱 슬롯을 스킵**합니다(종목 수·동일가중/시가총액가중·정렬 질문 생성은 "
        "계약 위반). 매수/매도 조건·리스크 관리·백테스트 기간·초기 자본만 진행하며, "
        "크로스오버 진입이면 반대 신호 청산을 chips 옵션으로 제시합니다(확정은 사용자).\n\n"
        "## 모호성 처리\n"
        "복수 해석이 가능한 표현(예: \"삼성전자 관련 ETF\" — 편입 비중 상위/삼성그룹/"
        "반도체)은 해석 도구로 범위를 좁히는 tool 노드를 ask보다 먼저 두세요. 도구로도 "
        "하나로 확정할 수 없고 전략 결과가 크게 달라지면 ask+chips로 범위를 질문합니다 — "
        "추천이 아니라 선택지 제시입니다. 명확한 나머지 정보의 진행은 막지 않습니다.\n\n"
        "## 금지\n"
        "- 섹터·종목·전략 필드 값을 지어내지 마세요 — 확정값은 도구 관찰값에서만 "
        "채택됩니다.\n"
        "- 질문·문구에 투자 추천·우열·전망·수익 보장 표현을 쓰지 마세요.\n\n"
        "## 예시 — \"반도체 etf 투자 전략\" (유니버스는 State에 이미 결정: ETF/반도체)\n"
        "매수 조건을 사용자가 말하지 않았으므로 특정 유형(모멘텀 등)을 전제하지 않고 "
        "열린 질문+ETF에 맞는 기술 지표 칩으로 묻습니다. 이후 슬롯도 골격 순서대로:\n"
        '{"dag": {"nodes": [\n'
        '  {"id": "ask_entry", "type": "ask", "topic": "매수조건", '
        '"question": "어떤 조건에서 매수할까요?", '
        '"chips": ["골든크로스(5일/20일) 발생 시 매수", "RSI 30 이하에서 매수", '
        '"20일 고점 돌파 시 매수", "최근 3개월 수익률 상위 매수"], "depends_on": []},\n'
        '  {"id": "ask_exit", "type": "ask", "topic": "매도조건", '
        '"question": "어떤 조건에서 매도할까요?", '
        '"chips": ["데드크로스(5일/20일) 발생 시 매도", "RSI 70 이상에서 매도", '
        '"20일 보유 후 청산"], "depends_on": ["ask_entry"]},\n'
        '  {"id": "ask_positions", "type": "ask", "topic": "최대보유", '
        '"question": "최대 몇 종목을 보유할까요?", '
        '"chips": ["최대 5종목", "최대 10종목"], "depends_on": ["ask_exit"]},\n'
        '  {"id": "ask_rebalance", "type": "ask", "topic": "리밸런싱", '
        '"question": "리밸런싱 주기는 어떻게 할까요?", '
        '"chips": ["매월 리밸런싱", "분기마다 리밸런싱"], "depends_on": ["ask_positions"]},\n'
        '  {"id": "ask_risk", "type": "ask", "topic": "리스크관리", '
        '"question": "손절·익절 기준을 정할까요?", '
        '"chips": ["손절 -8%", "익절 20%", "손절 -8% 익절 20%"], '
        '"depends_on": ["ask_rebalance"]},\n'
        '  {"id": "validate", "type": "tool", "tool": "validate_intent", "args": {}, '
        '"depends_on": ["ask_risk"]},\n'
        '  {"id": "compile", "type": "tool", "tool": "compile_strategy", "args": {}, '
        '"depends_on": ["validate"]},\n'
        '  {"id": "done", "type": "finish", "depends_on": ["compile"]}\n'
        "]}}\n"
        "미해석 테마가 있는 유니버스라면 위 ask들보다 먼저 해석 tool 노드"
        "(kg_resolve_sector 등)를 두고 첫 ask가 그에 의존하게 하세요."
    )


def _render_state(
    user_input: str,
    nodes: Optional[List[DagNode]],
    executed: Dict[str, ExecutedNode],
    auto_steps: List[dict],
    state_summary: Optional[Dict[str, Any]] = None,
) -> str:
    lines = [f"사용자 요청: {json.dumps(user_input, ensure_ascii=False)}"]
    if state_summary:
        # 파이프라인이 이미 확정한 전략 State — 여기 있는 정보를 다시 묻는 ask 노드는
        # 계약 위반이다(프롬프트 DAG 규칙 6). 값은 결정론 파이프라인 산출물이다.
        lines.append(
            "이미 결정된 전략 State(다시 묻기 금지): "
            + json.dumps(state_summary, ensure_ascii=False, default=str)
        )
    if nodes is None:
        lines.append("현재 DAG: 없음 (첫 턴 — 새 DAG를 발행하세요)")
    else:
        lines.append("현재 DAG와 실행 상태:")
        for n in nodes:
            entry: Dict[str, Any] = {"id": n.id, "type": n.type,
                                     "status": "done" if n.id in executed else "pending"}
            if n.type == "tool":
                entry.update({"tool": n.tool, "args": n.args})
                observed = executed.get(n.id)
                if observed is not None and observed.observation is not None:
                    rendered = json.dumps(observed.observation, ensure_ascii=False)
                    entry["observation"] = rendered[:_OBSERVATION_RENDER_LIMIT]
            elif n.type == "ask":
                entry.update({"topic": n.topic, "question": n.question})
            lines.append(json.dumps(entry, ensure_ascii=False))
        for step in auto_steps:
            rendered = json.dumps(step.get("observation"), ensure_ascii=False)
            lines.append(json.dumps(
                {"id": step["id"], "type": "tool(runner 자동 실행)",
                 "tool": step["tool"], "args": step["args"], "status": "done",
                 "observation": rendered[:_OBSERVATION_RENDER_LIMIT]},
                ensure_ascii=False,
            ))
    lines.append("다음 DAG JSON:")
    return "\n".join(lines)


def _balance_braces(fragment: str) -> Optional[str]:
    """닫는 괄호가 부족한 JSON 조각을 결정론으로 보정한다(형식 처리 — 의미 판단 없음).

    9B가 긴 DAG JSON에서 마지막 닫는 중괄호를 빠뜨리는 실측 결함의 보정이다.
    문자열 리터럴 밖의 괄호 스택을 스캔해 부족한 닫힘만 덧붙인다 — 짝이 어긋난
    출력(교차 닫힘·문자열 미종결)은 보정하지 않는다(None).
    """
    stack: List[str] = []
    in_string = False
    escaped = False
    for ch in fragment:
        if escaped:
            escaped = False
            continue
        if in_string:
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack or (stack.pop(), ch) not in (("{", "}"), ("[", "]")):
                return None
    if in_string:
        return None
    return fragment + "".join("}" if c == "{" else "]" for c in reversed(stack))


def _extract_json(raw: str) -> Optional[dict]:
    """LLM 출력에서 JSON 객체 경계만 추출한다(형식 처리 — 의미 판단 없음)."""
    if not raw:
        return None
    start = raw.find("{")
    if start < 0:
        return None
    candidates = []
    end = raw.rfind("}")
    if end > start:
        candidates.append(raw[start:end + 1])
    balanced = _balance_braces(raw[start:].rstrip().rstrip("`"))
    if balanced is not None:
        candidates.append(balanced)
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _observed_resolution(
    executed: Dict[str, ExecutedNode], auto_steps: List[dict]
) -> tuple[Optional[str], List[dict]]:
    """관찰값에서만 sector·companies를 채택한다 — LLM 주장값은 쓰지 않는다."""
    sector: Optional[str] = None
    companies: List[dict] = []
    observations = [e.observation for e in executed.values()]
    observations.extend(step.get("observation") for step in auto_steps)
    for obs in observations:
        if not obs:
            continue
        if sector is None and obs.get("sector"):
            sector = obs["sector"]
        if not companies and obs.get("companies"):
            companies = obs["companies"]
    return sector, companies


def plan_strategy_dag(
    user_input: str,
    chat_fn: Callable[..., str],  # 공유 chat 계약 (system, user, *, max_tokens) -> str
    max_turns: Optional[int] = None,
    node_budget: Optional[int] = None,
    state_summary: Optional[Dict[str, Any]] = None,
) -> Optional[DagPlanResult]:
    """사용자 요청 하나를 DAG planner로 계획한다. 실패(폴백 필요) 시 None.

    state_summary: 파이프라인이 이미 확정한 전략 필드 요약(재질문 방지 근거).

    본체는 _plan_strategy_dag다 — 이 함수는 관찰 span만 연다(비활성 시 no-op).
    계획·실행·폴백 판정은 전부 본체 소관이며 여기서 아무것도 바꾸지 않는다.
    """
    with span(
        "Planner · Action DAG", "planner",
        inputs={"user_input": user_input, "state_summary": state_summary},
        metadata={"max_turns": max_turns if max_turns is not None
                  else config.dag_planner_max_turns(),
                  "node_budget": node_budget if node_budget is not None
                  else config.dag_planner_node_budget()},
    ) as trace:
        result = _plan_strategy_dag(
            user_input, chat_fn, max_turns, node_budget, state_summary, trace,
        )
        if result is None:
            # 폴백은 예외가 아니라 반환값이다 — Trace에서 "왜 planner가 안 쓰였나"가
            # 보이도록 원인 종류를 남긴다(원인 문자열은 본체가 이미 기록했다).
            trace.output(outcome="fallback")
        else:
            trace.output(
                outcome=result.outcome, question=result.question, chips=result.chips,
                topic=result.topic, sector=result.sector,
                company_count=len(result.companies),
            )
            trace.meta(llm_turns=result.llm_turns, planner_latency_ms=result.latency_ms,
                       executed_nodes=len(result.executed),
                       auto_steps=len(result.auto_steps))
        return result


def _plan_strategy_dag(
    user_input: str,
    chat_fn: Callable[..., str],
    max_turns: Optional[int],
    node_budget: Optional[int],
    state_summary: Optional[Dict[str, Any]],
    trace: Any,
) -> Optional[DagPlanResult]:
    if not (user_input or "").strip():
        trace.error("EmptyInput", "빈 사용자 입력 — 계획 없음")
        return None
    turns = max_turns if max_turns is not None else config.dag_planner_max_turns()
    budget = node_budget if node_budget is not None else config.dag_planner_node_budget()
    system_prompt = _system_prompt()
    start = time.monotonic()

    executed: Dict[str, ExecutedNode] = {}
    # 무효화된 노드 id(설계 스펙 § 12.2) — 목록에서 지우지 않고 여기 모아 둔다.
    # 지우면 무엇이 왜 취소됐는지 추적할 수 없고, LLM이 같은 노드를 다시 발행한다.
    invalidated: set = set()
    call_cache: Dict[str, Optional[Dict[str, Any]]] = {}
    auto_steps: List[dict] = []
    nodes: Optional[List[DagNode]] = None
    prev_fingerprint: Optional[str] = None
    llm_turns = 0

    def _result(outcome: str, *, question: Optional[str] = None,
                chips: Optional[List[str]] = None,
                topic: Optional[str] = None) -> DagPlanResult:
        sector, companies = _observed_resolution(executed, auto_steps)
        return DagPlanResult(
            outcome=outcome, question=question, chips=chips or [],
            sector=sector, companies=companies, nodes=nodes or [], topic=topic,
            executed=executed, auto_steps=auto_steps, llm_turns=llm_turns,
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    def _execute(node: DagNode) -> bool:
        """tool 노드 하나를 실행(중복은 관찰 재사용). 새 실행 발생 시 True."""
        # Action span — Tool span(tools/base.call)의 부모다. 둘을 분리해야 "Action은
        # 계획됐는데 도구가 안 불렸다"(캐시 재사용)를 Trace에서 구분할 수 있다.
        with span(
            f"Action · {node.id}", "action",
            inputs={"tool": node.tool, "args": node.args},
            metadata={"node_id": node.id, "node_type": node.type,
                      "requires": node.requires, "produces": node.produces,
                      "invalidated_by": node.invalidated_by,
                      "depends_on": node.depends_on},
        ) as action_trace:
            key = node.call_key()
            if key in call_cache:
                executed[node.id] = ExecutedNode(node, call_cache[key])
                action_trace.meta(cache_hit=True)
                action_trace.output(status="COMPLETED", reused_observation=True)
                return False
            payload: Dict[str, Any] = dict(node.args)
            if node.tool == "ground_term":
                payload["chat"] = chat_fn  # 비결정론 도구 — 공유 LLM 주입 계약
            observation = call_tool(node.tool, **payload).model_dump()
            action_trace.meta(cache_hit=False)
            action_trace.output(status="COMPLETED", observation=observation)
        call_cache[key] = observation
        executed[node.id] = ExecutedNode(node, observation)
        if node.tool == "ground_term":
            # 검색 학습이 테마 앵커를 새로 만들 수 있다 — 학습 후 테마 재조회는
            # 판단이 아니라 절차라 LLM 턴 없이 결정론 에필로그로 수행한다.
            text = node.args.get("text")
            requery = DagNode(id=f"auto:{len(auto_steps)}", type="tool",
                              tool="kg_theme_companies", args={"text": text})
            requery_key = requery.call_key()
            if text and requery_key not in call_cache:
                try:
                    requery_obs = call_tool("kg_theme_companies", text=text).model_dump()
                    call_cache[requery_key] = requery_obs
                    auto_steps.append({"id": requery.id, "tool": requery.tool,
                                       "args": requery.args, "observation": requery_obs})
                except Exception:  # noqa: BLE001 — 재조회 실패는 관찰 없음으로 계속
                    logger.debug("dag planner 학습 후 테마 재조회 실패", exc_info=True)
        return True

    for _ in range(turns):
        # 공유 chat 계약의 max_tokens — DAG JSON은 미니플래너 한 줄 액션보다 커서
        # 기본 상한(2048)에 잘려 JSON이 깨진다(실측: 한글 칩 다수 DAG가 ~1.3k자에서 절단).
        raw = chat_fn(system_prompt,
                      _render_state(user_input, nodes, executed, auto_steps, state_summary),
                      max_tokens=4096)
        llm_turns += 1
        data = _extract_json(raw)
        if data is None:
            logger.info("dag planner JSON 파싱 실패 — 폴백")
            trace.error("PlannerOutputParseError",
                        f"turn={llm_turns} DAG JSON 경계 추출 실패 | raw={raw[:400]}")
            return None
        try:
            emitted = parse_dag(data)
            # done 노드 병합 — LLM이 재발행을 생략한 done 노드는 러너 보유 사본(불변
            # 정본)으로 채운다(재발행 생략 허용 계약). 동일 도구+인자를 새 id로 다시
            # 낸 경우는 병합하지 않는다(call_cache가 관찰을 재사용).
            emitted_ids = {n.id for n in emitted}
            emitted_keys = {n.call_key() for n in emitted if n.type == "tool"}
            for done_id, entry in executed.items():
                if done_id not in emitted_ids and entry.node.call_key() not in emitted_keys:
                    emitted.append(entry.node)
            validate_dag(
                emitted, allowed_tools=_ALLOWED_TOOLS, node_budget=budget,
                done_snapshots={nid: e.node.immutable_snapshot()
                                for nid, e in executed.items()},
            )
        except DagContractError as exc:
            logger.info("dag planner 계약 위반 — 폴백 | %s", exc)
            trace.error("DagContractError", f"turn={llm_turns} {exc}")
            return None
        nodes = emitted
        # 이번 턴에 확정된 DAG(스펙 § 3). 턴마다 덮어써 마지막 발행이 남는다 —
        # 중간 발행은 각 LLM span의 출력에 원문이 그대로 있다.
        trace.output(action_dag=dag_snapshot(nodes), action_dag_ascii=dag_ascii(nodes))

        # ready인 실행 가능 tool 노드를 전부 실행한다(전이적 — 관찰이 다음 ready를 연다)
        progressed = False
        while True:
            done_ids = set(executed)
            batch = [n for n in ready_nodes(nodes, done_ids, excluded_ids=invalidated)
                     if n.type == "tool" and n.tool in _EXECUTABLE_TOOLS]
            if not batch:
                break
            for node in batch:
                try:
                    if _execute(node):
                        progressed = True
                        # 이 도구가 채운 State 필드가 이미 완료된 노드의 전제를 깼는가
                        # (설계 스펙 § 12.1). 무효 노드는 목록에서 지우지 않고 표시만
                        # 한다 — 지우면 무엇이 왜 취소됐는지 추적할 수 없다(§ 12.2).
                        newly_invalid = invalidated_by_state_change(
                            nodes, set(node.produces), set(executed) - {node.id},
                        )
                        if newly_invalid - invalidated:
                            logger.info(
                                "dag planner 노드 무효화 | 원인=%s(%s) 무효=%s",
                                node.id, ", ".join(node.produces),
                                ", ".join(sorted(newly_invalid - invalidated)),
                            )
                            # State 변경이 어떤 Action을 무효로 만들었나(스펙 § 6).
                            # 별도 span으로 남겨야 무효화가 언제·왜 일어났는지 순서대로 읽힌다.
                            with span(
                                "State · 무효화", "state",
                                inputs={"cause_node": node.id,
                                        "changed_fields": list(node.produces)},
                            ) as state_trace:
                                state_trace.output(
                                    invalidated_nodes=sorted(newly_invalid - invalidated),
                                )
                            invalidated |= newly_invalid
                except ToolError as exc:
                    logger.info("dag planner 도구 계약 위반 — 폴백 | %s", exc)
                    trace.error("ToolContractError", f"node={node.id} tool={node.tool} {exc}")
                    return None
                except Exception as exc:  # noqa: BLE001 — 도구 장애는 폴백으로 강등
                    logger.warning("dag planner 도구 실행 실패 — 폴백 | tool=%s",
                                   node.tool, exc_info=True)
                    trace.error("ToolError",
                                f"node={node.id} tool={node.tool} "
                                f"{type(exc).__name__}: {exc}")
                    return None

        if progressed:
            # 새 관찰이 생겼다 — ask 표면화 전에 LLM에게 DAG 수정 기회를 한 턴 준다
            # (관찰이 질문을 불필요하게 만들 수 있다: 테마 해석 후 업종 질문 등).
            prev_fingerprint = None
            continue

        done_ids = set(executed)
        # 재질문 결정론 가드 — State 요약의 filled_slots(결정론 판정)에 있는 슬롯의 ask는
        # 표면화하지 않는다. "채워진 슬롯은 절대 다시 묻지 않는다"는 프롬프트 지시를 9B가
        # 어기고 풀 골격(ask_entry부터)을 재발행하는 실측 드리프트(2026-07-29 매수 조건
        # 재질문 사고)의 출력측 차단이다. 판정은 topic↔슬롯 라벨의 공백 무시 비교뿐이다
        # (표기 정규화 — 의미 판단 없음). 이미 답이 있는 ask는 충족으로 흡수해 그에
        # 의존하는 다음 빈 슬롯 ask를 연다(전부 충족이면 아래 무진전 폴백).
        filled_slots = {
            str(slot).replace(" ", "")
            for slot in (state_summary or {}).get("filled_slots") or []
        }
        answered: set = set()
        while True:
            already_answered = [
                n for n in ready_nodes(nodes, done_ids | answered,
                                       excluded_ids=invalidated)
                if n.type == "ask" and (n.topic or "").replace(" ", "") in filled_slots
            ]
            if not already_answered:
                break
            for node in already_answered:
                logger.info("dag planner 재질문 가드 — 채워진 슬롯 ask 건너뜀 | id=%s topic=%s",
                            node.id, node.topic)
            answered.update(n.id for n in already_answered)

        for node in ready_nodes(nodes, done_ids | answered,
                                excluded_ids=invalidated):
            if node.type == "ask":
                question = guard_text((node.question or "").strip() or None)
                if not question:
                    logger.info("dag planner ask 질문 관문 전체 제거 — 폴백 | id=%s", node.id)
                    trace.error("OutputGuardRejected",
                                f"node={node.id} ask 질문이 출력 관문에서 전부 제거됨")
                    return None
                _trace_final_statuses(trace, nodes, set(executed), invalidated, answered)
                return _result("ask", question=question, chips=list(node.chips),
                               topic=node.topic)
            if node.type == "finish":
                _trace_final_statuses(trace, nodes, set(executed), invalidated, answered)
                return _result("finish")

        fingerprint = json.dumps(
            [n.__dict__ for n in nodes], ensure_ascii=False, sort_keys=True, default=str,
        )
        if fingerprint == prev_fingerprint:
            logger.info("dag planner 무진전 동일 발행 — 폴백")
            trace.error("NoProgress", f"turn={llm_turns} 직전과 동일한 DAG 재발행")
            return None
        prev_fingerprint = fingerprint

    logger.info("dag planner 턴 예산 소진(%d) — 폴백", turns)
    trace.error("TurnBudgetExhausted", f"LLM 턴 예산 {turns} 소진 — 결론 미도달")
    return None


def _trace_final_statuses(
    trace: Any, nodes: List[DagNode], done_ids: set, invalidated: set, answered: set,
) -> None:
    """종결 시점의 노드별 상태(스펙 § 4 Action 실행 로그).

    상태 판정은 dag.node_statuses — 실행 계층이 쓰는 바로 그 함수다. 관찰 계층이
    자기 판정을 따로 만들면 Trace가 실제 실행과 어긋난다.
    """
    try:
        statuses = node_statuses(nodes, done_ids, invalidated_ids=invalidated,
                                 skipped_ids=answered)
        trace.output(node_statuses={k: v.value for k, v in statuses.items()},
                     status_counts=node_status_counts(statuses))
    except Exception:  # noqa: BLE001 — 관찰값 산출 실패가 계획 결과를 바꾸지 않는다
        logger.debug("dag planner 상태 관찰 실패", exc_info=True)
