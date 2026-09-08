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


# ── 무료 한도 폴백: OpenRouter 429(per-day) → 같은 요청을 Ollama 레인으로 ────────────

QUOTA_429 = (b'{"error":{"message":"Rate limit exceeded: free-models-per-day. Add 10 credits",'
             b'"code":429,"metadata":{"headers":{"X-RateLimit-Reset":"4102444800000"}}}}')


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def ollama_host(monkeypatch):
    monkeypatch.setattr(llm_backend, "OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(llm_chat, "OLLAMA_BASE_URL", "http://localhost:11434")


def test_open_chat_falls_back_to_ollama_on_daily_quota(openrouter_env, ollama_host, monkeypatch):
    """한도 소진 429를 받은 그 요청부터 Ollama 레인으로 다시 보내고, 프로세스는 리셋 시각까지
    Ollama로 전환된다(사용자 지시 2026-09-06: 무료 소진 시 예전 로컬 LLM으로)."""
    import urllib.error
    import urllib.request
    from engine import nl_parser

    monkeypatch.setattr(nl_parser, "_ollama_align_runner_num_ctx", lambda: False)
    monkeypatch.setattr(nl_parser, "_ollama_ensure_warm", lambda *a, **k: None)
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, json.loads(req.data)))
        if "openrouter.ai" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(QUOTA_429))
        return _Resp(json.dumps({"message": {"role": "assistant", "content": "ollama says hi"}, "done": True}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with llm_chat.open_chat(PAYLOAD, timeout=30) as resp:
        data = llm_chat.read_chat_response(resp.read())
    assert data["message"]["content"] == "ollama says hi"
    assert [u for u, _ in calls] == [
        "https://openrouter.ai/api/v1/chat/completions",
        "http://localhost:11434/api/chat",
    ]
    assert calls[1][1] == PAYLOAD                      # Ollama 레인은 원본 payload 그대로
    assert llm_backend.openrouter_fallback_active() is True
    # 다음 요청은 OpenRouter를 건드리지 않고 곧장 Ollama로 간다
    calls.clear()
    with llm_chat.open_chat(PAYLOAD, timeout=30) as resp:
        resp.read()
    assert [u for u, _ in calls] == ["http://localhost:11434/api/chat"]
    assert llm_chat.probe_request().full_url == "http://localhost:11434/api/tags"
    # 리셋 시각이 지나면 자동 복귀
    llm_backend.pause_openrouter_until(0.0)
    assert llm_backend.is_openrouter() is True


def test_open_chat_no_retry_lane_also_falls_back(openrouter_env, ollama_host, monkeypatch):
    """검증기(retry=False, 단발 urlopen)도 같은 폴백을 탄다."""
    import urllib.error
    import urllib.request
    from engine import nl_parser

    monkeypatch.setattr(nl_parser, "_ollama_ensure_warm", lambda *a, **k: None)
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if "openrouter.ai" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(QUOTA_429))
        return _Resp(b'{"message":{"content":"ok"},"done":true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with llm_chat.open_chat(PAYLOAD, timeout=5, retry=False) as resp:
        assert llm_chat.read_chat_response(resp.read())["message"]["content"] == "ok"
    assert calls == ["https://openrouter.ai/api/v1/chat/completions", "http://localhost:11434/api/chat"]


def test_per_minute_429_does_not_trigger_fallback(openrouter_env):
    """분당 한도 429는 일시적이다 — 폴백을 켜지 않고 그대로 둔다(호출부 재시도)."""
    import urllib.error

    err = urllib.error.HTTPError("https://openrouter.ai/x", 429, "Too Many Requests", {},
                                 io.BytesIO(b'{"error":{"message":"free-models-per-min","code":429}}'))
    llm_chat.check_openrouter_quota(err)  # raise 없음
    assert llm_backend.openrouter_fallback_active() is False


def test_quota_without_reset_header_pauses_for_an_hour(openrouter_env, monkeypatch):
    import urllib.error

    monkeypatch.setattr(llm_chat.time, "time", lambda: 1000.0)
    err = urllib.error.HTTPError("https://openrouter.ai/x", 429, "Too Many Requests", {},
                                 io.BytesIO(b'{"error":{"message":"free-models-per-day","code":429}}'))
    with pytest.raises(llm_chat.OpenRouterQuotaExhausted):
        llm_chat.check_openrouter_quota(err)
    assert llm_backend._openrouter_paused_until == 1000.0 + 3600.0


# ── 응답 형태 자동 판별(전환 순간의 레이스 방지) ───────────────────────────────

def test_read_chat_response_detects_shape_regardless_of_lane(openrouter_env):
    """OpenRouter 레인이어도 Ollama 형태 응답(폴백 직후)은 그대로 통과한다."""
    raw = {"message": {"role": "assistant", "content": "x"}, "done": True, "eval_count": 3}
    assert llm_chat.read_chat_response(json.dumps(raw).encode()) == raw
    # 반대로 ollama 레인에서 OpenAI 형태가 오면 정규화한다
    llm_backend.pause_openrouter_until(4102444800.0)
    assert llm_chat.read_chat_response(json.dumps(OR_RESPONSE).encode())["message"]["content"] == '{"a": 1}'


def test_iter_chat_stream_detects_ndjson_on_openrouter_lane(openrouter_env):
    ndjson = json.dumps({"message": {"content": "a"}, "done": False}) + "\n" + \
        json.dumps({"message": {"content": ""}, "done": True}) + "\n"
    chunks = list(llm_chat.iter_chat_stream(io.BytesIO(ndjson.encode())))
    assert [c["message"]["content"] for c in chunks] == ["a", ""]


# ── 레인·모델 로그(2026-09-07 사용자 요청: 로컬 모델인지 외부 API인지, 어떤 모델인지) ──

def _capture(caplog):
    """console_logger는 propagate=False라 caplog 기본 수집(root)에 안 잡힌다 — 핸들러를 직접 단다."""
    llm_chat.logger.addHandler(caplog.handler)
    return lambda: llm_chat.logger.removeHandler(caplog.handler)


def test_describe_lane_openrouter_names_external_api_and_model(openrouter_env):
    line = llm_chat.describe_lane(PAYLOAD)
    assert "openrouter(외부 API)" in line
    assert "model=qwen/qwen3-32b" in line          # Ollama 슬롯명이 아니라 OPENROUTER_MODEL
    assert "url=https://openrouter.ai/api/v1" in line


def test_describe_lane_local_ollama(ollama_env, ollama_host):
    line = llm_chat.describe_lane(PAYLOAD)
    assert "ollama-local(로컬 모델)" in line
    assert f"model={PAYLOAD['model']}" in line
    assert "url=http://localhost:11434" in line
    assert "폴백" not in line


def test_describe_lane_remote_ollama_is_modal(ollama_env, monkeypatch):
    monkeypatch.setattr(llm_backend, "OLLAMA_BASE_URL", "https://x--ollama.modal.run")
    monkeypatch.setattr(llm_chat, "OLLAMA_BASE_URL", "https://x--ollama.modal.run")
    line = llm_chat.describe_lane(PAYLOAD)
    assert "ollama-remote(원격 Ollama·Modal)" in line
    assert "url=https://x--ollama.modal.run" in line


def test_open_chat_logs_lane_and_fallback(openrouter_env, ollama_host, monkeypatch, caplog):
    """요청마다 [LLM] 줄이 남고, 한도 소진 폴백이면 Ollama 레인 줄에 폴백 표기가 붙는다."""
    import urllib.error
    import urllib.request
    from engine import nl_parser

    monkeypatch.setattr(nl_parser, "_ollama_ensure_warm", lambda *a, **k: None)

    def fake_urlopen(req, timeout):
        if "openrouter.ai" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(QUOTA_429))
        return _Resp(b'{"message":{"content":"ok"},"done":true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    undo = _capture(caplog)
    try:
        with llm_chat.open_chat(PAYLOAD, timeout=5, retry=False) as resp:
            resp.read()
    finally:
        undo()
        llm_backend.resume_openrouter()
    lanes = [r.getMessage() for r in caplog.records if r.getMessage().startswith("chat → ")]
    assert len(lanes) == 2
    assert "lane=openrouter(외부 API) model=qwen/qwen3-32b" in lanes[0]
    assert "lane=ollama-local(로컬 모델)[OpenRouter 한도 소진 폴백]" in lanes[1]
    assert f"model={PAYLOAD['model']}" in lanes[1]


# ── 상류 일시 오류 재시도(2026-09-08) ─────────────────────────────────────────
# OpenRouter가 HTTP 200 본문에 `{"error":{"code":502,"message":"Upstream error from Nvidia:
# Service temporarily overloaded"}}`를 실어 보내던 실측 — 분류기가 이를 빈 응답으로 삼켜
# "해석하지 못했어요"가 나갔다(대화 종료 직후처럼 진행 중인 전략이 없을 때).

UPSTREAM_502 = json.dumps({
    "error": {"code": 502, "message": "Upstream error from Nvidia: Service temporarily overloaded"},
    "user_id": "user_x",
}).encode()
OK_BODY = json.dumps({
    "choices": [{"message": {"role": "assistant", "content": '{"intent":"STRATEGY_ADVICE"}'}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
}).encode()


@pytest.fixture
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(llm_chat.time, "sleep", lambda s: slept.append(s))
    return slept


def _openrouter_sequence(monkeypatch, bodies):
    """OpenRouter로 가는 urlopen이 bodies를 순서대로 HTTP 200으로 돌려준다."""
    import urllib.request

    calls = []
    queue = list(bodies)

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        body = queue.pop(0) if len(queue) > 1 else queue[0]
        resp = _Resp(body)
        resp.status = 200
        resp.headers = {}
        return resp

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def test_transient_error_code_is_pure_shape_check():
    assert llm_chat.transient_error_code(UPSTREAM_502) == 502
    assert llm_chat.transient_error_code(OK_BODY) is None
    assert llm_chat.transient_error_code(b'{"error":{"code":400,"message":"bad request"}}') is None
    assert llm_chat.transient_error_code(b'{"error":{"code":"nope"}}') is None
    assert llm_chat.transient_error_code(b"not json") is None


def test_open_chat_retries_in_body_upstream_502(openrouter_env, monkeypatch, no_sleep):
    calls = _openrouter_sequence(monkeypatch, [UPSTREAM_502, UPSTREAM_502, OK_BODY])
    with llm_chat.open_chat(PAYLOAD, timeout=5, retry=False) as resp:
        data = llm_chat.read_chat_response(resp.read())
    assert data["message"]["content"] == '{"intent":"STRATEGY_ADVICE"}'
    assert len(calls) == 3
    assert no_sleep == [0.5, 1.0]


def test_open_chat_falls_back_to_ollama_after_retry_budget(openrouter_env, ollama_host, monkeypatch, no_sleep):
    """재시도를 다 써도 상류 502면 요청을 죽이지 않고 **이 요청만** Ollama 레인으로 다시 보낸다.

    2026-09-08 사고: 무료 Nemotron 상류가 4회 연속 502를 주면 요청 전체가 예외로 끝나
    "요청을 전략 조건으로 해석하지 못했어요"가 나갔다(정상 해석되던 문장인데도). 한도
    소진과 달리 프로세스 전역은 전환하지 않는다 — 다음 요청은 다시 OpenRouter로 간다."""
    import urllib.request
    from engine import nl_parser

    monkeypatch.setattr(nl_parser, "_ollama_ensure_warm", lambda *a, **k: None)
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if "openrouter.ai" in req.full_url:
            resp = _Resp(UPSTREAM_502)
            resp.status = 200
            resp.headers = {}
            return resp
        return _Resp(json.dumps({"message": {"role": "assistant", "content": "ollama says hi"}, "done": True}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with llm_chat.open_chat(PAYLOAD, timeout=5, retry=False) as resp:
        data = llm_chat.read_chat_response(resp.read())
    assert data["message"]["content"] == "ollama says hi"
    openrouter_calls = [u for u in calls if "openrouter.ai" in u]
    assert len(openrouter_calls) == 1 + len(llm_chat._TRANSIENT_RETRY_BACKOFF_S)
    assert calls[-1] == "http://localhost:11434/api/chat"
    assert no_sleep == list(llm_chat._TRANSIENT_RETRY_BACKOFF_S)
    assert llm_backend.request_forced_to_ollama() is False  # 응답 핸들을 연 뒤 원래 레인 복귀
    # 프로세스 전역 전환은 아니다 — 다음 요청은 다시 OpenRouter부터 간다
    assert llm_backend.openrouter_fallback_active() is False
    assert llm_backend.is_openrouter() is True
    calls.clear()
    with llm_chat.open_chat(PAYLOAD, timeout=5, retry=False) as resp:
        resp.read()
    assert calls[0] == "https://openrouter.ai/api/v1/chat/completions"


def test_upstream_fallback_logs_its_own_lane_tag(openrouter_env, ollama_host, monkeypatch, no_sleep, caplog):
    """상류 오류 폴백은 한도 소진 폴백과 다른 표기로 남는다(운영 콘솔에서 원인 구분)."""
    import urllib.request
    from engine import nl_parser

    monkeypatch.setattr(nl_parser, "_ollama_ensure_warm", lambda *a, **k: None)

    def fake_urlopen(req, timeout):
        if "openrouter.ai" in req.full_url:
            resp = _Resp(UPSTREAM_502)
            resp.status = 200
            resp.headers = {}
            return resp
        return _Resp(json.dumps({"message": {"role": "assistant", "content": "x"}, "done": True}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    undo = _capture(caplog)
    try:
        with llm_chat.open_chat(PAYLOAD, timeout=5, retry=False) as resp:
            resp.read()
    finally:
        undo()
    lanes = [r.getMessage() for r in caplog.records if r.getMessage().startswith("chat → ")]
    assert len(lanes) == 2
    assert "lane=openrouter(외부 API)" in lanes[0]
    assert "lane=ollama-local(로컬 모델)[OpenRouter 상류 오류 폴백]" in lanes[1]


def test_retry_and_fallback_show_retrying_stage_then_restore(openrouter_env, ollama_host, monkeypatch, no_sleep):
    """재시도가 시작되면 결속된 진행 holder가 'retrying'이 되고(프론트 '재확인 중...'), 재시도 중
    폴백까지 끝나 응답 핸들이 열리면 이전 단계로 되돌아간다(사용자 지시 2026-09-08)."""
    import urllib.request
    import llm_progress
    from engine import nl_parser

    monkeypatch.setattr(nl_parser, "_ollama_ensure_warm", lambda *a, **k: None)
    holder = {"stage": "universe"}
    seen = []  # (호출 URL, 그 시점의 stage)

    def fake_urlopen(req, timeout):
        seen.append((req.full_url, holder["stage"]))
        if "openrouter.ai" in req.full_url:
            resp = _Resp(UPSTREAM_502)
            resp.status = 200
            resp.headers = {}
            return resp
        return _Resp(json.dumps({"message": {"role": "assistant", "content": "x"}, "done": True}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with llm_progress.bind(holder):
        with llm_chat.open_chat(PAYLOAD, timeout=5, retry=False) as resp:
            resp.read()
    stages = [stage for _, stage in seen]
    assert stages[0] == "universe"                       # 첫 시도는 재시도가 아니다
    assert all(st == "retrying" for st in stages[1:])    # 재시도·Ollama 폴백 호출 모두 '재시도 중'
    assert seen[-1][0] == "http://localhost:11434/api/chat"
    assert holder["stage"] == "universe"                 # 응답 핸들이 열리면 이전 단계 복귀


def test_successful_retry_restores_stage(openrouter_env, monkeypatch, no_sleep):
    import llm_progress

    holder = {"stage": "entry"}
    calls = _openrouter_sequence(monkeypatch, [UPSTREAM_502, OK_BODY])
    with llm_progress.bind(holder):
        with llm_chat.open_chat(PAYLOAD, timeout=5, retry=False) as resp:
            llm_chat.read_chat_response(resp.read())
    assert len(calls) == 2
    assert holder["stage"] == "entry"


def test_upstream_exhaustion_raises_typed_error_from_retry_loop(openrouter_env, monkeypatch, no_sleep):
    """재시도 루프 자체는 예산 소진을 형식 있는 예외로 올린다(open_chat이 폴백 판단)."""
    calls = _openrouter_sequence(monkeypatch, [UPSTREAM_502])
    import urllib.request

    with pytest.raises(llm_chat.OpenRouterUpstreamUnavailable) as info:
        llm_chat._open_buffered_with_transient_retry(
            lambda req: urllib.request.urlopen(req, timeout=5), PAYLOAD)
    assert info.value.code == 502
    assert len(calls) == 1 + len(llm_chat._TRANSIENT_RETRY_BACKOFF_S)


def test_open_chat_does_not_retry_permanent_in_body_error(openrouter_env, monkeypatch, no_sleep):
    bad = b'{"error":{"code":400,"message":"Invalid model"}}'
    calls = _openrouter_sequence(monkeypatch, [bad])
    with llm_chat.open_chat(PAYLOAD, timeout=5, retry=False) as resp:
        raw = resp.read()
    with pytest.raises(RuntimeError, match="openrouter error 400"):
        llm_chat.read_chat_response(raw)
    assert len(calls) == 1
    assert no_sleep == []


# ── 스트리밍 재시도(2026-09-08 사고 2) ────────────────────────────────────────
# 인터프리터 본 호출은 스트리밍이라 재시도 관문 밖이었다 — 상류 502가 `data: {"error":…}`
# 한 줄로 오면 iter_chat_stream이 예외를 올려 요청이 통째로 실패했다(실서버 재현).

def _sse(*deltas, finish="stop"):
    lines = [": OPENROUTER PROCESSING\n", "\n"]
    for d in deltas:
        lines.append("data: " + json.dumps({"choices": [{"delta": {"content": d}, "finish_reason": None}]}) + "\n")
    lines.append("data: " + json.dumps({"choices": [{"delta": {"content": ""}, "finish_reason": finish}],
                                        "usage": {"prompt_tokens": 1, "completion_tokens": 1}}) + "\n")
    lines.append("data: [DONE]\n")
    return "".join(lines).encode()


SSE_502 = (": OPENROUTER PROCESSING\n\n" + "data: " + UPSTREAM_502.decode() + "\n").encode()


def test_open_chat_streaming_retries_in_stream_upstream_502(openrouter_env, monkeypatch, no_sleep):
    calls = _openrouter_sequence(monkeypatch, [SSE_502, SSE_502, _sse("RSI", "는 지표")])
    with llm_chat.open_chat({**PAYLOAD, "stream": True}, timeout=5, retry=False) as resp:
        chunks = list(llm_chat.iter_chat_stream(resp))
    assert [c["message"]["content"] for c in chunks if not c["done"]] == ["RSI", "는 지표"]
    assert chunks[-1]["done"] is True
    assert len(calls) == 3
    assert no_sleep == [0.5, 1.0]


def test_open_chat_streaming_replays_peeked_lines_intact(openrouter_env, monkeypatch, no_sleep):
    """정상 스트림은 peek로 읽은 주석·첫 이벤트를 포함해 원문 그대로 흘러간다(재시도 없음)."""
    calls = _openrouter_sequence(monkeypatch, [_sse("a", "b", "c")])
    with llm_chat.open_chat({**PAYLOAD, "stream": True}, timeout=5, retry=False) as resp:
        chunks = list(llm_chat.iter_chat_stream(resp))
    assert [c["message"]["content"] for c in chunks if not c["done"]] == ["a", "b", "c"]
    assert len(calls) == 1
    assert no_sleep == []


def test_open_chat_streaming_falls_back_to_ollama_after_retry_budget(openrouter_env, ollama_host, monkeypatch, no_sleep):
    """스트림도 예산을 다 쓰면 이 요청만 Ollama 레인(NDJSON 스트림)으로 다시 보낸다."""
    import urllib.request
    from engine import nl_parser

    monkeypatch.setattr(nl_parser, "_ollama_ensure_warm", lambda *a, **k: None)
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if "openrouter.ai" in req.full_url:
            resp = _Resp(SSE_502)
            resp.status = 200
            resp.headers = {}
            return resp
        return _Resp(b'{"message":{"role":"assistant","content":"ol"},"done":false}\n'
                     b'{"message":{"role":"assistant","content":""},"done":true}\n')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with llm_chat.open_chat({**PAYLOAD, "stream": True}, timeout=5, retry=False) as resp:
        chunks = list(llm_chat.iter_chat_stream(resp))
    assert [c["message"]["content"] for c in chunks if not c["done"]] == ["ol"]
    assert len([u for u in calls if "openrouter.ai" in u]) == 1 + len(llm_chat._TRANSIENT_RETRY_BACKOFF_S)
    assert calls[-1] == "http://localhost:11434/api/chat"
    assert llm_backend.is_openrouter() is True  # 요청 단위 폴백 — 전역 전환 아님


def test_open_chat_streaming_permanent_error_is_not_retried(openrouter_env, monkeypatch, no_sleep):
    bad = b'data: {"error":{"code":400,"message":"Invalid model"}}\n'
    calls = _openrouter_sequence(monkeypatch, [bad])
    with llm_chat.open_chat({**PAYLOAD, "stream": True}, timeout=5, retry=False) as resp:
        with pytest.raises(RuntimeError, match="openrouter error 400"):
            list(llm_chat.iter_chat_stream(resp))
    assert len(calls) == 1
    assert no_sleep == []


def test_open_chat_retry_honors_cancellation(openrouter_env, monkeypatch, no_sleep):
    """'대화 종료'로 끊긴 요청은 다시 보내지 않는다."""
    import cancellation

    calls = _openrouter_sequence(monkeypatch, [UPSTREAM_502])
    token = cancellation.CancelToken()
    token.cancel()
    with cancellation.bind(token):
        with pytest.raises(cancellation.OperationCancelled):
            llm_chat.open_chat(PAYLOAD, timeout=5, retry=False)
    assert len(calls) == 1
