"""Mini-Planner — 테마/유니버스 해석 구간 한정 동적 도구 계획(Planner→Tool→Responder Phase 3).

LLM(전략 인터프리터와 같은 슬롯)이 미해석 테마·업종 표현에 대해 어떤 도구를 어떤
순서로 부를지 결정한다: 지식그래프 조회 → (부족하면) 검색 그라운딩 → (그래도 안 되면)
되묻기 결정. 고정 체인(term_grounding.resolve_sector)과 달리 순서·중단을 LLM이 정하지만,
안전 계약은 전부 결정론이다:

- 도구는 화이트리스트(_ALLOWED_TOOLS)만 — 그 밖의 요청은 즉시 실패
- 스텝 예산(config.planner_max_steps) 초과·동일 호출 반복(루프) 즉시 실패
- JSON 파싱 실패·계약 위반 액션 즉시 실패
- **finish의 sector·companies는 LLM 주장값이 아니라 도구 관찰값에서만 채택한다**
  (LLM이 지어낸 섹터·종목이 관문 없이 확정되는 경로를 구조적으로 차단)
- planner가 만든 되묻기 질문도 출력 관문(output_guard)을 통과한다

실패는 전부 None 반환 — 호출부의 고정 파이프라인이 그대로 담당한다(planner는 어떤
경우에도 단독 실패 지점이 아니다).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from strategy_conversation import config
from strategy_conversation.response.output_guard import guard_text
from strategy_conversation.tools import ToolError, call as call_tool, get_tool

logger = logging.getLogger("strategy_interpreter.planner")

# 유니버스 해석 구간 한정 — 이 밖의 도구(컴파일·검증 등)는 planner 소관이 아니다.
_ALLOWED_TOOLS = ("kg_resolve_sector", "kg_theme_companies", "ground_term")


@dataclass
class PlannerStep:
    action: str
    tool: Optional[str] = None
    args: Dict[str, Any] = field(default_factory=dict)
    observation: Optional[Dict[str, Any]] = None


@dataclass
class PlannerResult:
    outcome: str  # "resolved" | "clarify"
    sector: Optional[str]
    companies: List[dict]
    question: Optional[str]
    steps: List[PlannerStep]
    latency_ms: int


def _system_prompt() -> str:
    tool_lines = "\n".join(
        f'- {name}: {get_tool(name).description} — 인자 {{"text": "<표현>"}}'
        for name in _ALLOWED_TOOLS
    )
    return (
        "당신은 주식 백테스트 플랫폼의 유니버스 해석 플래너입니다. 사용자가 말한 "
        "테마/업종 표현을 정본 섹터 또는 관련 상장사 목록으로 해석하기 위해 도구 호출 "
        "순서를 결정합니다.\n\n"
        f"사용 가능한 도구:\n{tool_lines}\n\n"
        "매 턴 JSON 객체 하나만 출력하세요:\n"
        '- 도구 호출: {"action": "tool", "tool": "<이름>", "args": {"text": "<표현>"}}\n'
        '- 해석 종료: {"action": "finish"} — 지금까지의 관찰로 충분할 때\n'
        '- 되묻기: {"action": "clarify", "question": "<사용자에게 물을 질문>"}\n\n'
        "규칙:\n"
        "1. 같은 도구를 같은 인자로 반복 호출하지 마세요.\n"
        "2. 관찰(observation)에서 sector가 나오면 finish 하세요.\n"
        "3. 검색(ground_term)은 비용이 크므로 지식그래프 관찰이 비었을 때만 쓰세요.\n"
        "4. 어떤 도구로도 해석되지 않으면 clarify로 사용자에게 물으세요 — 섹터나 "
        "종목을 지어내지 마세요.\n"
        "5. 투자 추천·시장 전망 표현을 쓰지 마세요."
    )


def _render_state(term: str, steps: List[PlannerStep]) -> str:
    lines = [f"해석 대상 표현: {json.dumps(term, ensure_ascii=False)}"]
    if steps:
        lines.append("지금까지의 실행 기록:")
        for i, step in enumerate(steps, 1):
            lines.append(json.dumps(
                {"step": i, "tool": step.tool, "args": step.args,
                 "observation": step.observation},
                ensure_ascii=False,
            ))
    else:
        lines.append("실행 기록: 없음 (첫 턴)")
    lines.append("다음 액션 JSON:")
    return "\n".join(lines)


def _extract_json(raw: str) -> Optional[dict]:
    """LLM 출력에서 JSON 객체 경계만 추출한다(형식 처리 — 의미 판단 없음)."""
    if not raw:
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _observed_resolution(steps: List[PlannerStep]) -> tuple[Optional[str], List[dict]]:
    """관찰값에서만 sector·companies를 채택한다 — LLM finish 주장값은 쓰지 않는다."""
    sector: Optional[str] = None
    companies: List[dict] = []
    for step in steps:
        obs = step.observation or {}
        if sector is None and obs.get("sector"):
            sector = obs["sector"]
        if not companies and obs.get("companies"):
            companies = obs["companies"]
    return sector, companies


def plan_universe_resolution(
    term: str, chat_fn: Callable[[str, str], str], max_steps: Optional[int] = None,
) -> Optional[PlannerResult]:
    """미해석 표현 하나를 planner 루프로 해석한다. 실패(폴백 필요) 시 None."""
    if not (term or "").strip():
        return None
    budget = max_steps if max_steps is not None else config.planner_max_steps()
    steps: List[PlannerStep] = []
    seen_calls: set = set()
    system_prompt = _system_prompt()
    start = time.monotonic()

    def _elapsed_ms() -> int:
        return int((time.monotonic() - start) * 1000)

    for _ in range(budget):
        decision = _extract_json(chat_fn(system_prompt, _render_state(term, steps)))
        if decision is None:
            logger.info("planner JSON 파싱 실패 — 고정 파이프라인 폴백 | term=%r", term)
            return None
        action = decision.get("action")

        if action == "finish":
            sector, companies = _observed_resolution(steps)
            if sector is None and not companies:
                # 관찰 근거 없는 finish는 해석이 아니다 — 지어내기 차단, 폴백
                logger.info("planner 근거 없는 finish — 폴백 | term=%r", term)
                return None
            return PlannerResult("resolved", sector, companies, None, steps, _elapsed_ms())

        if action == "clarify":
            question = guard_text((decision.get("question") or "").strip() or None)
            if not question:
                return None
            return PlannerResult("clarify", None, [], question, steps, _elapsed_ms())

        if action == "tool":
            tool_name = decision.get("tool")
            if tool_name not in _ALLOWED_TOOLS:
                logger.info("planner 화이트리스트 밖 도구 요청 거부 | tool=%r", tool_name)
                return None
            args = decision.get("args") or {}
            text = (args.get("text") or term) if isinstance(args, dict) else term
            call_key = (tool_name, text)
            if call_key in seen_calls:
                logger.info("planner 동일 호출 반복(루프) — 폴백 | %r", call_key)
                return None
            seen_calls.add(call_key)
            payload: Dict[str, Any] = {"text": text}
            if tool_name == "ground_term":
                payload["chat"] = chat_fn
            try:
                observation = call_tool(tool_name, **payload).model_dump()
            except ToolError as exc:
                logger.info("planner 도구 계약 위반 — 폴백 | %s", exc)
                return None
            except Exception:  # noqa: BLE001 — 도구 장애는 planner 실패로 강등(폴백)
                logger.warning("planner 도구 실행 실패 — 폴백 | tool=%s", tool_name,
                               exc_info=True)
                return None
            steps.append(PlannerStep("tool", tool_name, {"text": text}, observation))
            continue

        logger.info("planner 계약 밖 액션 — 폴백 | action=%r", action)
        return None

    logger.info("planner 스텝 예산 소진(%d) — 폴백 | term=%r", budget, term)
    return None
