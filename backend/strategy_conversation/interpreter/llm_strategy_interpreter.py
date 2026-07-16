"""LLM Strategy Interpreter — 사용자 자연어를 StrategyIntent JSON으로 변환.

자연어 이해의 주체는 LLM(Qwen 3.5 4B)이다. 이 모듈은:
  ① Ollama /api/chat(format=json, think=false)로 구조화 출력을 요청하고
  ② JSON 추출 → Pydantic 검증 → 실패 시 오류와 함께 1회 자동 수정 요청
  ③ 다시 실패하면 InterpreterError를 던진다(호출부가 안전한 사용자 응답 담당).

transport(chat_fn)는 주입 가능해 테스트가 LLM 없이 스텁으로 검증할 수 있다.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Callable, Optional

from pydantic import ValidationError

from strategy_conversation import config
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.interpreter.output_repair import (
    build_repair_prompt,
    extract_json_object,
)
from strategy_conversation.interpreter.prompts import (
    PROMPT_VERSION,
    build_system_prompt,
    build_user_prompt,
)

logger = logging.getLogger("strategy_interpreter")

ChatFn = Callable[[str, str], str]  # (system_prompt, user_message) -> raw text


class InterpreterError(RuntimeError):
    """복구 재시도 후에도 유효한 StrategyIntent를 얻지 못한 경우."""


class InterpreterResult:
    def __init__(
        self,
        intent: StrategyIntent,
        raw_output: str,
        repair_attempts: int,
        latency_ms: float,
        model_name: str,
    ):
        self.intent = intent
        self.raw_output = raw_output
        self.repair_attempts = repair_attempts
        self.latency_ms = latency_ms
        self.model_name = model_name
        self.prompt_version = PROMPT_VERSION


def _default_ollama_chat(model: str) -> ChatFn:
    """기존 파서와 동일한 콜드스타트 내성 Ollama 호출(warm-up + 재시도 재사용)."""

    def chat(system_prompt: str, user_message: str) -> str:
        import urllib.request

        from engine.nl_parser import (
            _OLLAMA_NUM_CTX,
            _ollama_ensure_warm,
            _ollama_open_with_retry,
        )
        from llm_backend import OLLAMA_BASE_URL, ollama_auth_headers

        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "think": False,
            "format": "json",
            "options": {"temperature": 0, "num_ctx": _OLLAMA_NUM_CTX, "num_predict": 2048},
        }).encode()
        _ollama_ensure_warm()
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json", **ollama_auth_headers()},
            method="POST",
        )
        with _ollama_open_with_retry(req, timeout=120) as resp:
            data = json.loads(resp.read())
        return (data.get("message") or {}).get("content", "")

    return chat


class StrategyInterpreter:
    def __init__(self, chat_fn: Optional[ChatFn] = None, model: Optional[str] = None):
        self.model_name = model or os.environ.get("NL_OLLAMA_MODEL", "qwen3:8b")
        self._chat = chat_fn or _default_ollama_chat(self.model_name)
        self._system_prompt = build_system_prompt()

    def interpret(self, user_input: str, draft: Optional[dict] = None) -> InterpreterResult:
        started = time.perf_counter()
        user_prompt = build_user_prompt(user_input, draft)
        raw = self._chat(self._system_prompt, user_prompt)

        attempts = 0
        last_error: Exception | None = None
        current_raw = raw
        while True:
            try:
                intent = StrategyIntent.model_validate_json(extract_json_object(current_raw))
                # 문맥 보정(결정론): 기존 초안이 없으면 MODIFY/CLARIFY는 성립 불가 —
                # 4B가 단문 전략 서술을 MODIFY_STRATEGY로 오분류하는 드리프트 실측(2026-07-16).
                if draft is None and intent.intent in ("MODIFY_STRATEGY", "CLARIFY_STRATEGY") \
                        and intent.strategy is not None:
                    intent = intent.model_copy(update={"intent": "CREATE_STRATEGY"})
                return InterpreterResult(
                    intent=intent,
                    raw_output=current_raw,
                    repair_attempts=attempts,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    model_name=self.model_name,
                )
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempts >= config.MAX_REPAIR_ATTEMPTS:
                    break
                attempts += 1
                logger.warning(
                    "interpreter output invalid, requesting repair | attempt=%d err=%s",
                    attempts, str(exc)[:300],
                )
                repair_prompt = build_repair_prompt(user_input, current_raw, str(exc), draft)
                current_raw = self._chat(self._system_prompt, repair_prompt)

        raise InterpreterError(
            f"LLM 출력이 {attempts}회 복구 후에도 StrategyIntent 스키마를 만족하지 않습니다: "
            f"{str(last_error)[:500]}"
        )
