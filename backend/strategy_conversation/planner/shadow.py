"""Planner Shadow — mini-planner를 관측 전용으로 병행 실행하고 JSONL을 남긴다.

STRATEGY_PLANNER_MODE=shadow일 때만 동작한다. 사용자 응답은 기존 고정 파이프라인
결과 그대로이며, planner는 백그라운드 스레드에서 실행되어 로그만 남긴다 —
interpreter shadow(strategy_conversation/shadow.py)와 같은 승격 판정 패턴.

로그 스키마: ts, term, outcome(resolved/clarify/none), sector, question,
steps[{tool,args,observation}], baseline_sector(고정 체인 학습 후 결정적 재조회),
latency_ms, error
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Callable, List, Optional

from strategy_conversation import config

logger = logging.getLogger("strategy_interpreter.planner.shadow")


def planner_shadow_enabled() -> bool:
    return config.planner_mode() == "shadow"


def _default_chat() -> Callable[[str, str], str]:
    """인터프리터와 같은 모델 슬롯(STRATEGY_INTERPRETER_MODEL, 9B)의 Ollama chat."""
    from strategy_conversation.interpreter.llm_strategy_interpreter import (
        _default_ollama_chat,
    )

    model = (
        os.environ.get("STRATEGY_INTERPRETER_MODEL")
        or os.environ.get("NL_OLLAMA_MODEL", "qwen3:8b")
    )
    return _default_ollama_chat(model)


def _append_log(record: dict) -> None:
    path = config.planner_shadow_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _run(term: str, chat_fn: Optional[Callable[[str, str], str]]) -> None:
    record: dict = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "term": term,
                    "outcome": "none", "error": None}
    started = time.monotonic()
    try:
        from strategy_conversation.planner.mini_planner import plan_universe_resolution

        result = plan_universe_resolution(term, chat_fn or _default_chat())
        if result is not None:
            record.update({
                "outcome": result.outcome,
                "sector": result.sector,
                "question": result.question,
                "companies_count": len(result.companies),
                "steps": [
                    {"tool": s.tool, "args": s.args, "observation": s.observation}
                    for s in result.steps
                ],
            })
        # 고정 체인이 같은 턴에 학습했다면 결정적 재조회에 잡힌다 — 승격 판정 비교 기준
        from strategy_conversation.registry.universe_resolver import resolve_sectors

        baseline, _ = resolve_sectors([term])
        record["baseline_sector"] = baseline
    except Exception as exc:  # noqa: BLE001 — 관측 실패는 기록으로만
        record["error"] = repr(exc)[:300]
    record["latency_ms"] = int((time.monotonic() - started) * 1000)
    try:
        _append_log(record)
    except Exception:  # noqa: BLE001
        logger.warning("planner shadow 로그 기록 실패", exc_info=True)


def maybe_shadow_plan(
    unresolved_terms: List[str],
    chat_fn: Optional[Callable[[str, str], str]] = None,
) -> Optional[threading.Thread]:
    """미해석 표현이 있고 shadow 모드면 planner를 비차단 실행한다. 시작한 스레드 반환."""
    if not planner_shadow_enabled() or not unresolved_terms:
        return None
    term = unresolved_terms[0]
    thread = threading.Thread(
        target=_run, args=(term, chat_fn), daemon=True, name="planner-shadow",
    )
    thread.start()
    return thread
