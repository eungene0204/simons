"""DAG Planner Shadow(Phase 4) — 초기 파스와 병행 관측 실행하고 JSONL을 남긴다.

STRATEGY_DAG_PLANNER_MODE=shadow일 때만 동작한다. 사용자 응답은 기존 파이프라인
결과 그대로이며, DAG planner는 백그라운드 스레드에서 실행되어 로그만 남긴다 —
planner/shadow.py(Phase 3 mini-planner shadow)와 같은 승격 판정 패턴.

로그 스키마: ts, user_input(축약), outcome(ask/finish/none), question, chips,
node_count, nodes[{id,type,tool,topic,status}], executed_tools, auto_steps,
sector, companies_count, llm_turns, latency_ms, error
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Callable, Optional

from strategy_conversation import config

logger = logging.getLogger("strategy_interpreter.planner.dag_shadow")


def dag_shadow_enabled() -> bool:
    return config.dag_planner_mode() == "shadow"


def _append_log(record: dict) -> None:
    path = config.dag_planner_shadow_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _run(user_input: str, chat_fn: Optional[Callable[[str, str], str]],
         trace_parent=None) -> None:
    """관찰 부모를 복원한 뒤 본체를 돌린다.

    관찰 계층은 contextvar로 부모 span을 찾는데 contextvar는 스레드를 건너지 않는다 —
    복원하지 않으면 shadow planner의 span이 고아 Trace가 되어 계층이 끊긴다.
    """
    from observability import use_parent

    with use_parent(trace_parent):
        _run_shadow(user_input, chat_fn)


def _run_shadow(user_input: str, chat_fn: Optional[Callable[[str, str], str]]) -> None:
    record: dict = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "user_input": user_input[:300], "outcome": "none", "error": None}
    started = time.monotonic()
    try:
        from strategy_conversation.planner.dag_planner import plan_strategy_dag
        from strategy_conversation.planner.shadow import _default_chat

        result = plan_strategy_dag(user_input, chat_fn or _default_chat())
        if result is not None:
            record.update({
                "outcome": result.outcome,
                "question": result.question,
                "chips": result.chips,
                "node_count": len(result.nodes),
                "nodes": [
                    {"id": n.id, "type": n.type, "tool": n.tool, "topic": n.topic,
                     "status": "done" if n.id in result.executed else "pending"}
                    for n in result.nodes
                ],
                "executed_tools": [e.node.tool for e in result.executed.values()],
                "auto_steps": [{"tool": s["tool"], "args": s["args"]}
                               for s in result.auto_steps],
                "sector": result.sector,
                "companies_count": len(result.companies),
                "llm_turns": result.llm_turns,
            })
    except Exception as exc:  # noqa: BLE001 — 관측 실패는 기록으로만
        record["error"] = repr(exc)[:300]
    record["latency_ms"] = int((time.monotonic() - started) * 1000)
    try:
        _append_log(record)
    except Exception:  # noqa: BLE001
        logger.warning("dag planner shadow 로그 기록 실패", exc_info=True)


def maybe_shadow_plan_dag(
    user_input: str,
    chat_fn: Optional[Callable[[str, str], str]] = None,
) -> Optional[threading.Thread]:
    """shadow 모드면 DAG planner를 비차단 실행한다. 시작한 스레드 반환."""
    if not dag_shadow_enabled() or not (user_input or "").strip():
        return None
    from observability import current_parent

    thread = threading.Thread(
        target=_run, args=(user_input, chat_fn, current_parent()), daemon=True,
        name="dag-planner-shadow",
    )
    thread.start()
    return thread
