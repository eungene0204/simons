"""LLM Strategy Interpreter — 사용자 자연어를 StrategyIntent JSON으로 변환.

자연어 이해의 주체는 인터프리터 LLM이다(STRATEGY_INTERPRETER_MODEL 전용 슬롯 —
2026-07-26부터 Qwen 3.5 9B, 미설정 시 NL_OLLAMA_MODEL 폴백). 이 모듈은:
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
from strategy_conversation.validation.recall_validator import (
    build_recall_repair_prompt,
    find_unreflected_numbers,
)

logger = logging.getLogger("strategy_interpreter")

# 대조 대상은 전략 본문을 만들어내는 intent뿐이다 — 설명 질문·비전략 요청은
# 수치가 출력에 없는 것이 정상이다.
_RECALL_CHECKED_INTENTS = ("CREATE_STRATEGY", "MODIFY_STRATEGY", "CLARIFY_STRATEGY")


def _recall_gap(user_input: str, intent) -> list[str]:
    if intent.intent not in _RECALL_CHECKED_INTENTS:
        return []
    return find_unreflected_numbers(user_input, intent)

ChatFn = Callable[[str, str], str]  # (system_prompt, user_message) -> raw text


def _log_llm(tag: str, text: str) -> None:
    """LLM 왕복을 dev 콘솔에서 눈으로 확인할 수 있게 출력한다([NL-PARSE]와 동일한 print 관례).

    uvicorn 로깅 설정과 무관하게 항상 보이도록 print를 쓴다. 원본 응답은 가공 없이 그대로.
    """
    print(f"[LLM-INTERPRETER] {tag} {text}", flush=True)


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

    # 공유 chat 계약은 (system_prompt, user_msg, *, max_tokens) -> str — term_grounding
    # 등 소비자가 max_tokens를 넘긴다(미수용 시 TypeError로 검색 그라운딩 전체가 침묵 실패).
    def chat(system_prompt: str, user_message: str, *, max_tokens: int | None = None) -> str:
        import urllib.request

        from engine.nl_parser import (
            _OLLAMA_NUM_CTX,
            _ollama_ensure_warm,
            _ollama_open_with_retry,
        )
        from llm_backend import OLLAMA_BASE_URL, is_local_ollama, ollama_auth_headers

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "think": False,
            "format": "json",
            "options": {"temperature": 0, "num_ctx": _OLLAMA_NUM_CTX,
                        "num_predict": max_tokens or 2048},
        }
        if is_local_ollama():
            # 로컬 dev 상주 유지 — Ollama는 마지막 요청의 keep_alive로 언로드 타이머를
            # 갱신하므로(기본 5분), startup preload(-1)만으론 첫 요청 후 다시 풀린다.
            # 원격(Modal)은 컨테이너 수명이 별도 관리라 기본값을 유지한다.
            payload["keep_alive"] = -1
        body = json.dumps(payload).encode()
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
        # 인터프리터 전용 모델 슬롯(SUMMARIZE_OLLAMA_MODEL 선례) — 파서·코치가 공유하는
        # NL_OLLAMA_MODEL과 분리해, 해석 품질을 위해 더 큰 모델을 쓰되 다른 경로의 지연에
        # 영향을 주지 않는다. 미설정 시 기존 동작(NL_OLLAMA_MODEL) 그대로.
        self.model_name = (
            model
            or os.environ.get("STRATEGY_INTERPRETER_MODEL")
            or os.environ.get("NL_OLLAMA_MODEL", "qwen3:8b")
        )
        self._chat = chat_fn or _default_ollama_chat(self.model_name)
        self._system_prompt = build_system_prompt()

    def interpret(self, user_input: str, draft: Optional[dict] = None) -> InterpreterResult:
        started = time.perf_counter()
        user_prompt = build_user_prompt(user_input, draft)
        _log_llm("▶ 요청", f"{user_input!r}" + (" (수정 모드 — 전략 초안 포함)" if draft else ""))
        raw = self._chat(self._system_prompt, user_prompt)
        _log_llm("◀ 원본 응답", raw.strip())

        attempts = 0
        last_error: Exception | None = None
        current_raw = raw
        recall_retried = False
        while True:
            try:
                intent = StrategyIntent.model_validate_json(extract_json_object(current_raw))
                # 문맥 보정(결정론): 기존 초안이 없으면 MODIFY/CLARIFY는 성립 불가 —
                # 4B가 단문 전략 서술을 MODIFY_STRATEGY로 오분류하는 드리프트 실측(2026-07-16).
                if draft is None and intent.intent in ("MODIFY_STRATEGY", "CLARIFY_STRATEGY") \
                        and intent.strategy is not None:
                    intent = intent.model_copy(update={"intent": "CREATE_STRATEGY"})
                # 수치 반영 대조(§ 3-1). 스키마는 통과했지만 사용자가 말한 수치가 통째로
                # 빠진 경우 — 값을 채우지 않고 모델에게 한 번 다시 시킨다. 재요청 예산은
                # 스키마 복구와 공유하며, 재생성 후에도 남으면 그대로 진행한다(누락은
                # 스키마 오류가 아니므로 요청을 실패시키지 않는다).
                if not recall_retried and config.recall_check_enabled():
                    missing = _recall_gap(user_input, intent)
                    if missing and attempts < config.MAX_REPAIR_ATTEMPTS:
                        recall_retried = True
                        attempts += 1
                        _log_llm("⟳ 수치 누락 재요청", f"미반영: {', '.join(missing)}")
                        current_raw = self._chat(
                            self._system_prompt,
                            build_recall_repair_prompt(user_input, missing, current_raw),
                        )
                        _log_llm("◀ 재요청 응답", current_raw.strip())
                        continue
                    if missing:
                        _log_llm("△ 수치 누락 잔존", f"미반영: {', '.join(missing)}")
                _log_llm("✓ 해석", (
                    f"intent={intent.intent} status={intent.status} "
                    f"patches={len(intent.patches)} repairs={attempts} "
                    f"({round((time.perf_counter() - started) * 1000)}ms)"
                ))
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
                _log_llm(f"⟳ 복구 요청({attempts}회차)", f"검증 오류: {str(exc)[:300]}")
                repair_prompt = build_repair_prompt(user_input, current_raw, str(exc), draft)
                current_raw = self._chat(self._system_prompt, repair_prompt)
                _log_llm(f"◀ 복구 응답({attempts}회차)", current_raw.strip())

        _log_llm("✗ 해석 실패", f"{attempts}회 복구 후에도 스키마 불만족: {str(last_error)[:200]}")
        raise InterpreterError(
            f"LLM 출력이 {attempts}회 복구 후에도 StrategyIntent 스키마를 만족하지 않습니다: "
            f"{str(last_error)[:500]}"
        )
