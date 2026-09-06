"""LLM chat 전송 어댑터 — Ollama /api/chat 형태의 payload를 현재 프로바이더 요청으로 바꾼다.

호출부(파서·인터프리터·검증기·코치·AI 리포트)는 종전처럼 **Ollama /api/chat 형태**의
payload(model·messages·stream·think·format·options)를 만들고, 응답도 Ollama 형태
(`message.content`, `done`, `prompt_eval_count`, `eval_count`)로 읽는다. 프로바이더 차이는
이 모듈이 흡수한다:

- ollama     : payload 그대로 `{OLLAMA_BASE_URL}/api/chat`(+Modal proxy-auth 헤더).
- openrouter : OpenAI 호환 `/chat/completions`로 번역한다.
    · model            → OPENROUTER_MODEL(전 슬롯 단일 모델)
    · options.temperature/top_p → temperature/top_p, options.num_predict → max_tokens
    · options.num_ctx·keep_alive → 버림(원격 API는 컨텍스트를 서버가 정한다)
    · format="json"    → response_format {"type": "json_object"}
    · think=False      → reasoning {"enabled": false, "exclude": true}. **Qwen 계열이면**
                         마지막 user 메시지에 소프트 스위치 ` /no_think` 도 붙인다 —
                         2026-09-06 실측: DeepInfra 등 일부 프로바이더는 Qwen3에 대해
                         `reasoning.enabled=false`·`chat_template_kwargs`를 무시해 thinking이
                         max_tokens를 전부 태우고 content가 빈 채 돌아왔고, `/no_think`만
                         동작했다. 스위치는 Qwen 전용 토큰이라 다른 모델(Nemotron 등)에는
                         붙이지 않는다(그쪽은 reasoning 파라미터가 정상 반영됨을 실측).
    · stream=True      → stream_options.include_usage 로 마지막 청크에 usage를 받는다.

이 모듈은 전송 형식만 다룬다. 자연어 해석·프롬프트·재시도 정책은 호출부 소관이다.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Iterator

from llm_backend import (
    OLLAMA_BASE_URL,
    OPENROUTER_BASE_URL,
    is_openrouter,
    ollama_auth_headers,
    openrouter_headers,
    openrouter_model,
)

logger = logging.getLogger(__name__)

# Qwen3 계열의 thinking 소프트 스위치 — 사용자 원문을 해석하는 것이 아니라 LLM에 보내는
# 메시지 끝에 붙이는 제어 토큰이다(프롬프트 계층).
_NO_THINK_SWITCH = " /no_think"


# ── 요청 ─────────────────────────────────────────────────────────────────────

def chat_request(payload: dict[str, Any]) -> urllib.request.Request:
    """Ollama /api/chat 형태 payload → 현재 프로바이더의 HTTP POST 요청."""
    if is_openrouter():
        body = json.dumps(to_openrouter_payload(payload)).encode()
        return urllib.request.Request(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", **openrouter_headers()},
            method="POST",
        )
    return urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **ollama_auth_headers()},
        method="POST",
    )


def probe_request() -> urllib.request.Request:
    """본문 없는 GET 도달 가능성 확인 요청. ollama=/api/tags, openrouter=/key(인증 확인)."""
    if is_openrouter():
        return urllib.request.Request(
            f"{OPENROUTER_BASE_URL}/key", headers=openrouter_headers(), method="GET"
        )
    return urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/tags", headers=ollama_auth_headers(), method="GET"
    )


def to_openrouter_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Ollama /api/chat payload → OpenAI 호환 chat/completions body(순수 변환, 네트워크 없음)."""
    options = payload.get("options") or {}
    messages = [dict(m) for m in payload.get("messages") or []]
    out: dict[str, Any] = {
        "model": openrouter_model(),
        "messages": messages,
        "stream": bool(payload.get("stream", False)),
    }
    if "temperature" in options:
        out["temperature"] = options["temperature"]
    if "top_p" in options:
        out["top_p"] = options["top_p"]
    if "num_predict" in options:
        out["max_tokens"] = options["num_predict"]
    if payload.get("format") == "json":
        out["response_format"] = {"type": "json_object"}
    if payload.get("think") is False:
        out["reasoning"] = {"enabled": False, "exclude": True}
        if "qwen" in out["model"].lower():
            _append_no_think(messages)
    if out["stream"]:
        out["stream_options"] = {"include_usage": True}
    return out


def _append_no_think(messages: list[dict[str, Any]]) -> None:
    """마지막 user 메시지에 ` /no_think` 를 붙인다(이미 있으면 그대로)."""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content") or ""
            if "/no_think" not in content:
                m["content"] = content + _NO_THINK_SWITCH
            return


# ── 응답 ─────────────────────────────────────────────────────────────────────

def read_chat_response(raw: bytes) -> dict[str, Any]:
    """비스트리밍 응답 본문 → Ollama /api/chat 형태 dict."""
    data = json.loads(raw)
    if not is_openrouter():
        return data
    return from_openrouter_response(data)


def from_openrouter_response(data: dict[str, Any]) -> dict[str, Any]:
    """OpenAI 호환 chat.completion → Ollama 형태(순수 변환)."""
    _raise_if_error(data)
    choices = data.get("choices") or []
    message = (choices[0].get("message") if choices else None) or {}
    content = message.get("content") or ""
    if not content and message.get("reasoning"):
        # thinking이 예산을 전부 태운 경우 — 조용히 빈 응답으로 넘기지 않고 로그에 남긴다.
        logger.warning(
            "openrouter 응답 content 비어 있음 — reasoning만 %d자 (provider=%s)",
            len(message.get("reasoning") or ""), data.get("provider"),
        )
    out: dict[str, Any] = {
        "model": data.get("model"),
        "provider": data.get("provider"),
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": (choices[0].get("finish_reason") if choices else None),
    }
    out.update(_usage_fields(data.get("usage")))
    _log_usage(out)
    return out


def iter_chat_stream(resp) -> Iterator[dict[str, Any]]:
    """스트리밍 응답 → Ollama NDJSON과 같은 형태의 청크 dict 반복.

    각 청크는 `{"message": {"content": delta}, "done": False}`, 마지막 청크는
    `done=True`에 usage(prompt_eval_count/eval_count)를 싣는다.
    """
    if not is_openrouter():
        for line in resp:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
        return

    usage: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    finish_reason = None
    for line in resp:
        line = line.decode("utf-8", "replace").strip() if isinstance(line, bytes) else line.strip()
        if not line.startswith("data:"):
            continue  # SSE 주석(": OPENROUTER PROCESSING")·빈 줄
        chunk = line[5:].strip()
        if chunk == "[DONE]":
            break
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        _raise_if_error(obj)
        meta.setdefault("model", obj.get("model"))
        meta.setdefault("provider", obj.get("provider"))
        if obj.get("usage"):
            usage = obj["usage"]
        for choice in obj.get("choices") or []:
            delta = (choice.get("delta") or {}).get("content") or ""
            if delta:
                yield {"message": {"role": "assistant", "content": delta}, "done": False}
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]
    final: dict[str, Any] = {
        **meta,
        "message": {"role": "assistant", "content": ""},
        "done": True,
        "done_reason": finish_reason,
    }
    final.update(_usage_fields(usage))
    _log_usage(final)
    yield final


def _usage_fields(usage: dict[str, Any] | None) -> dict[str, Any]:
    """OpenAI usage → Ollama 토큰 카운트 필드명(observability.agent_trace.ollama_usage가 읽는다).

    reasoning_eval_count(thinking 토큰)는 OpenRouter 전용 진단 필드다 — completion_tokens에
    포함돼 과금·지연을 만들지만 content에는 없어, 이 값이 커지면 /no_think가 무시된 것이다.
    """
    if not isinstance(usage, dict):
        return {}
    out: dict[str, Any] = {}
    if isinstance(usage.get("prompt_tokens"), int):
        out["prompt_eval_count"] = usage["prompt_tokens"]
    if isinstance(usage.get("completion_tokens"), int):
        out["eval_count"] = usage["completion_tokens"]
    details = usage.get("completion_tokens_details")
    if isinstance(details, dict) and isinstance(details.get("reasoning_tokens"), int):
        out["reasoning_eval_count"] = details["reasoning_tokens"]
    return out


def _log_usage(data: dict[str, Any]) -> None:
    """호출 1건의 프로바이더·종료 사유·토큰 수를 한 줄로 남긴다 — 잘림(length)과
    thinking 누수(reasoning_eval_count>0)는 이 로그로만 잡힌다."""
    logger.info(
        "openrouter chat | model=%s provider=%s finish=%s prompt_tokens=%s completion_tokens=%s "
        "reasoning_tokens=%s",
        data.get("model"), data.get("provider"), data.get("done_reason"),
        data.get("prompt_eval_count"), data.get("eval_count"), data.get("reasoning_eval_count", 0),
    )


def _raise_if_error(data: dict[str, Any]) -> None:
    """OpenRouter는 HTTP 200 본문(또는 스트림 중간)에 error 객체를 실어 보낼 수 있다."""
    err = data.get("error") if isinstance(data, dict) else None
    if err:
        raise RuntimeError(
            f"openrouter error {err.get('code')}: {err.get('message')}"
            if isinstance(err, dict) else f"openrouter error: {err}"
        )
