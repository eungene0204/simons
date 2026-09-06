"""LLM 전송 어댑터(llm_chat) — Ollama 형태 payload ↔ OpenRouter(OpenAI 호환) 변환.

계약: 호출부는 Ollama /api/chat 형태만 알고, 프로바이더 차이는 어댑터가 흡수한다.
LLM_PROVIDER 기본(ollama)에서는 요청·응답이 종전과 바이트 단위로 같아야 하고,
openrouter에서는 형식 번역 + thinking 소프트 스위치(/no_think)가 반드시 들어간다
(2026-09-06 실측: 일부 프로바이더가 reasoning.enabled=false를 무시해 content가 빈 채 왔다).
"""

from __future__ import annotations

import io
import json

import pytest

import llm_backend
import llm_chat


PAYLOAD = {
    "model": "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M",
    "messages": [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "RSI 30 이하 매수"},
    ],
    "stream": False,
    "think": False,
    "format": "json",
    "keep_alive": -1,
    "options": {"temperature": 0, "num_ctx": 32768, "num_predict": 1024, "top_p": 0.9},
}


@pytest.fixture
def openrouter_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("OPENROUTER_MODEL", "qwen/qwen3-32b")


@pytest.fixture
def ollama_env(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("MODAL_KEY", raising=False)
    monkeypatch.delenv("MODAL_SECRET", raising=False)


# ── 프로바이더 결정 ────────────────────────────────────────────────────────────

def test_default_provider_is_ollama(ollama_env):
    assert llm_backend.llm_provider() == "ollama"
    assert llm_backend.is_openrouter() is False


def test_openrouter_disables_local_ollama_runner_management(openrouter_env, monkeypatch):
    """OpenRouter 레인에서는 OLLAMA_HOST가 localhost여도 로컬 러너 관리 경로가 꺼져야 한다 —
    preload·prefill·num_ctx 정합 가드·연결거부 fast-fail은 모두 로컬 Ollama 전용이다."""
    monkeypatch.setattr(llm_backend, "OLLAMA_BASE_URL", "http://localhost:11434")
    assert llm_backend.is_local_ollama() is False


def test_openrouter_without_key_fails_fast(monkeypatch):
    """키가 없으면 조용히 로컬 Ollama로 떨어지지 않고 즉시 실패한다(운영과 다른 모델로
    검증하고도 통과한 것처럼 보이는 사고 방지)."""
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        llm_chat.chat_request(PAYLOAD)


# ── 요청 변환 ─────────────────────────────────────────────────────────────────

def test_ollama_request_is_unchanged(ollama_env, monkeypatch):
    """기본 레인은 종전과 동일 — URL /api/chat, 본문은 payload 그대로."""
    monkeypatch.setattr(llm_backend, "OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(llm_chat, "OLLAMA_BASE_URL", "http://localhost:11434")
    req = llm_chat.chat_request(PAYLOAD)
    assert req.full_url == "http://localhost:11434/api/chat"
    assert json.loads(req.data) == PAYLOAD
    assert "Authorization" not in req.headers


def test_openrouter_request_translates_shape(openrouter_env):
    req = llm_chat.chat_request(PAYLOAD)
    assert req.full_url == "https://openrouter.ai/api/v1/chat/completions"
    assert req.get_header("Authorization") == "Bearer sk-or-test"
    body = json.loads(req.data)
    assert body["model"] == "qwen/qwen3-32b"          # Ollama 슬롯명이 아니라 OPENROUTER_MODEL
    assert body["temperature"] == 0
    assert body["top_p"] == 0.9
    assert body["max_tokens"] == 1024                  # num_predict → max_tokens
    assert body["response_format"] == {"type": "json_object"}  # format=json
    assert body["reasoning"] == {"enabled": False, "exclude": True}
    assert body["stream"] is False
    # Ollama 전용 키는 새지 않는다
    for key in ("options", "num_ctx", "keep_alive", "think", "format"):
        assert key not in body


def test_openrouter_think_false_appends_no_think_soft_switch(openrouter_env):
    """thinking을 끄는 정본은 /no_think 소프트 스위치다 — reasoning.enabled=false만 보내면
    DeepInfra 등 일부 프로바이더가 무시해 thinking이 max_tokens를 태우고 content가 빈다."""
    body = llm_chat.to_openrouter_payload(PAYLOAD)
    assert body["messages"][-1]["role"] == "user"
    assert body["messages"][-1]["content"].endswith(" /no_think")
    assert body["messages"][0]["content"] == "sys"     # system은 건드리지 않는다
    # 원본 payload는 변형되지 않는다(호출부가 재사용·로그에 남길 수 있다)
    assert PAYLOAD["messages"][-1]["content"] == "RSI 30 이하 매수"


def test_openrouter_no_think_is_qwen_only(openrouter_env, monkeypatch):
    """/no_think는 Qwen 전용 토큰 — Nemotron 등에는 reasoning 파라미터만 보낸다(실측 정상 반영)."""
    monkeypatch.setenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    body = llm_chat.to_openrouter_payload(PAYLOAD)
    assert body["reasoning"] == {"enabled": False, "exclude": True}
    assert "/no_think" not in body["messages"][-1]["content"]


def test_openrouter_model_defaults_to_free_nemotron(openrouter_env, monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    assert llm_backend.openrouter_model() == "nvidia/nemotron-3-super-120b-a12b:free"


def test_openrouter_no_think_is_idempotent(openrouter_env):
    payload = {**PAYLOAD, "messages": [{"role": "user", "content": "질문 /no_think"}]}
    body = llm_chat.to_openrouter_payload(payload)
    assert body["messages"][0]["content"] == "질문 /no_think"


def test_openrouter_think_unset_keeps_reasoning_default(openrouter_env):
    payload = {k: v for k, v in PAYLOAD.items() if k != "think"}
    body = llm_chat.to_openrouter_payload(payload)
    assert "reasoning" not in body
    assert "/no_think" not in body["messages"][-1]["content"]


def test_openrouter_stream_requests_usage(openrouter_env):
    body = llm_chat.to_openrouter_payload({**PAYLOAD, "stream": True})
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}


def test_probe_request_per_provider(openrouter_env, monkeypatch):
    assert llm_chat.probe_request().full_url == "https://openrouter.ai/api/v1/key"
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr(llm_chat, "OLLAMA_BASE_URL", "http://localhost:11434")
    assert llm_chat.probe_request().full_url == "http://localhost:11434/api/tags"


# ── 응답 변환 ─────────────────────────────────────────────────────────────────

OR_RESPONSE = {
    "id": "gen-1", "model": "qwen/qwen3-32b", "provider": "SiliconFlow",
    "choices": [{"index": 0, "finish_reason": "stop",
                 "message": {"role": "assistant", "content": '{"a": 1}', "reasoning": None}}],
    "usage": {"prompt_tokens": 43, "completion_tokens": 13, "total_tokens": 56,
              "completion_tokens_details": {"reasoning_tokens": 0}},
}


def test_openrouter_response_normalizes_to_ollama_shape(openrouter_env):
    data = llm_chat.read_chat_response(json.dumps(OR_RESPONSE).encode())
    assert data["message"]["content"] == '{"a": 1}'
    assert data["done"] is True
    assert data["done_reason"] == "stop"
    # observability.agent_trace.ollama_usage가 읽는 필드명으로 실린다
    assert data["prompt_eval_count"] == 43
    assert data["eval_count"] == 13
    assert data["reasoning_eval_count"] == 0     # thinking 누수 진단 필드(OpenRouter 전용)
    from observability.agent_trace import ollama_usage
    assert ollama_usage(data) == {"input_tokens": 43, "output_tokens": 13, "total_tokens": 56}


def test_ollama_response_passes_through(ollama_env):
    raw = {"message": {"role": "assistant", "content": "x"}, "done": True, "eval_count": 3}
    assert llm_chat.read_chat_response(json.dumps(raw).encode()) == raw


def test_openrouter_200_with_error_body_raises(openrouter_env):
    body = {"error": {"message": "This model is unavailable for free.", "code": 404}}
    with pytest.raises(RuntimeError, match="404"):
        llm_chat.read_chat_response(json.dumps(body).encode())


def test_openrouter_stream_yields_ollama_chunks(openrouter_env):
    def chunk(delta=None, finish=None, usage=None):
        obj = {"id": "gen-1", "model": "qwen/qwen3-32b", "provider": "DeepInfra",
               "choices": [{"index": 0, "delta": {"content": delta, "reasoning": None},
                            "finish_reason": finish}]}
        if usage:
            obj["usage"] = usage
        return f"data: {json.dumps(obj)}\n"

    sse = (
        ": OPENROUTER PROCESSING\n\n"
        + chunk("RSI")
        + chunk("는 지표")
        + chunk("", finish="stop")
        + chunk(None, usage={"prompt_tokens": 10, "completion_tokens": 4})
        + "data: [DONE]\n"
    )
    chunks = list(llm_chat.iter_chat_stream(io.BytesIO(sse.encode())))
    deltas = [c["message"]["content"] for c in chunks if not c["done"]]
    assert deltas == ["RSI", "는 지표"]
    final = chunks[-1]
    assert final["done"] is True
    assert final["done_reason"] == "stop"
    assert final["prompt_eval_count"] == 10 and final["eval_count"] == 4


def test_ollama_stream_passes_through_ndjson(ollama_env):
    ndjson = (
        json.dumps({"message": {"content": "a"}, "done": False}) + "\n"
        + "\n"
        + json.dumps({"message": {"content": ""}, "done": True, "eval_count": 1}) + "\n"
    )
    chunks = list(llm_chat.iter_chat_stream(io.BytesIO(ndjson.encode())))
    assert [c["message"]["content"] for c in chunks] == ["a", ""]
    assert chunks[-1]["done"] is True


# ── 호출부 결속: 인터프리터·검증기·리포트가 어댑터를 지나는가 ──────────────────

def test_interpreter_chat_goes_through_adapter_on_openrouter(openrouter_env, monkeypatch):
    """인터프리터 기본 chat이 OpenRouter 요청을 만들고 Ollama 형태로 돌려받는다."""
    from strategy_conversation.interpreter import llm_strategy_interpreter as mod
    from engine import nl_parser

    captured = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        return _Resp(json.dumps(OR_RESPONSE).encode())

    monkeypatch.setattr(nl_parser, "_ollama_open_with_retry", fake_open)
    chat = mod._default_ollama_chat("hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M")  # 슬롯명(무시됨)
    out = chat("sys", "RSI 30 이하 매수", max_tokens=512)
    assert out == '{"a": 1}'
    assert captured["url"].endswith("/chat/completions")
    assert captured["body"]["model"] == "qwen/qwen3-32b"
    assert captured["body"]["max_tokens"] == 512
    assert captured["body"]["messages"][-1]["content"].endswith("/no_think")
    assert "keep_alive" not in captured["body"]


def test_ensure_warm_is_noop_on_openrouter(openrouter_env, monkeypatch):
    """원격 API에는 깨울 콜드 컨테이너가 없다 — GET /api/tags를 치지 않는다."""
    import urllib.request
    from engine import nl_parser

    def boom(*a, **k):
        raise AssertionError("openrouter 레인에서 /api/tags 워밍업이 호출됐다")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    nl_parser._ollama_ensure_warm(budget_s=1)
