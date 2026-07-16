"""Shadow Mode (Phase 1) — 기존 규칙 파서와 LLM Interpreter를 병행 실행하고 diff를 기록.

STRATEGY_INTERPRETER_MODE=shadow일 때만 동작한다. 실제 사용자에게는 기존 결과만
제공되며, 신규 파이프라인(해석→검증→컴파일)은 백그라운드 스레드에서 실행되어
관측 로그(JSONL)만 남긴다 — 응답 지연에 영향을 주지 않는다.

로그 스키마(관측성 계약):
  request_id, user_input, llm_raw_output, parsed_intent, validation_*,
  compiler_output, legacy_output, field_diff, model_name, prompt_version,
  schema_version, latency_ms, error
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, Optional

from strategy_conversation import config

logger = logging.getLogger("strategy_interpreter.shadow")

_interpreter = None
_interpreter_lock = threading.Lock()


def shadow_enabled() -> bool:
    return config.interpreter_mode() == "shadow"


def _get_interpreter():
    global _interpreter
    with _interpreter_lock:
        if _interpreter is None:
            from strategy_conversation.interpreter.llm_strategy_interpreter import (
                StrategyInterpreter,
            )
            _interpreter = StrategyInterpreter()
        return _interpreter


def _field_diff(legacy: Dict[str, Any], compiled: Dict[str, Any]) -> Dict[str, Any]:
    diff: Dict[str, Any] = {}
    for key in sorted(set(legacy) | set(compiled)):
        lv, cv = legacy.get(key), compiled.get(key)
        if lv != cv:
            diff[key] = {"legacy": lv, "interpreter": cv}
    return diff


def _append_jsonl(record: Dict[str, Any]) -> None:
    path = os.path.abspath(config.shadow_log_path())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _run_shadow_sync(user_input: str, legacy_parsed: Optional[dict], request_id: str) -> Dict[str, Any]:
    from strategy_conversation.compiler.strategy_compiler import (
        StrategyCompileError,
        compile_strategy,
    )
    from strategy_conversation.validation.pipeline import run_validation

    started = time.perf_counter()
    record: Dict[str, Any] = {
        "request_id": request_id,
        "user_input": user_input,
        "schema_version": "1.0",
        "legacy_output": legacy_parsed,
    }
    try:
        result = _get_interpreter().interpret(user_input)
        record.update({
            "llm_raw_output": result.raw_output,
            "parsed_intent": result.intent.model_dump(),
            "repair_attempts": result.repair_attempts,
            "model_name": result.model_name,
            "prompt_version": result.prompt_version,
        })
        validated, report = run_validation(result.intent)
        record.update({
            "validation_status": report.status,
            "validation_errors": report.errors,
            "validation_warnings": report.warnings,
            "missing_fields": report.missing_fields,
            "unsupported_features": report.unsupported_features,
            "clarification_questions": [q.model_dump() for q in report.clarification_questions],
        })
        if report.is_valid:
            try:
                compiled = compile_strategy(validated, report, user_input)
                compiled_dump = compiled.model_dump()
                record["compiler_output"] = compiled_dump
                if legacy_parsed is not None:
                    record["field_diff"] = _field_diff(legacy_parsed, compiled_dump)
            except StrategyCompileError as exc:
                record["compile_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 — shadow는 어떤 실패도 본선을 건드리면 안 된다
        record["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    try:
        _append_jsonl(record)
    except OSError as exc:
        logger.warning("shadow log write failed | err=%r", exc)
    return record


def maybe_run_shadow(user_input: str, legacy_parsed: Optional[dict]) -> None:
    """모드가 shadow면 백그라운드 스레드로 신규 파이프라인을 실행한다(비차단)."""
    if not shadow_enabled():
        return
    request_id = uuid.uuid4().hex[:12]
    thread = threading.Thread(
        target=_run_shadow_sync,
        args=(user_input, legacy_parsed, request_id),
        name=f"interpreter-shadow-{request_id}",
        daemon=True,
    )
    thread.start()
