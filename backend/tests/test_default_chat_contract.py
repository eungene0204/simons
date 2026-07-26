"""_default_ollama_chat의 공유 chat 계약 회귀 — (system, user, *, max_tokens) -> str.

사고(2026-07-26): term_grounding이 chat(prompt, text, max_tokens=40)으로 호출하는데
_default_ollama_chat의 chat이 max_tokens를 안 받아 TypeError — strategy_conversation
레인(_ground_sector_term·planner ground_term 주입)의 검색 그라운딩 전체가 broad
except에 삼켜져 조용히 실패했다(fixed=즉시 되묻기, planner=폴백).
"""

import json

import pytest


class _FakeResp:
    def __init__(self, content: str):
        self._content = content

    def read(self):
        return json.dumps({"message": {"content": self._content}}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def captured_chat(monkeypatch):
    """네트워크 없이 chat 요청 본문을 캡처한다."""
    import engine.nl_parser as nl_parser

    captured = {}
    monkeypatch.setattr(nl_parser, "_ollama_ensure_warm", lambda: None)

    def _fake_open(req, timeout=None):
        captured["body"] = json.loads(req.data)
        return _FakeResp("{}")

    monkeypatch.setattr(nl_parser, "_ollama_open_with_retry", _fake_open)
    return captured


def test_chat_accepts_max_tokens_kwarg(captured_chat):
    """term_grounding 호출 형태(chat(..., max_tokens=40))가 TypeError 없이 동작한다."""
    from strategy_conversation.interpreter.llm_strategy_interpreter import (
        _default_ollama_chat,
    )

    chat = _default_ollama_chat("test-model")
    out = chat("system", "user", max_tokens=40)
    assert out == "{}"
    assert captured_chat["body"]["options"]["num_predict"] == 40


def test_chat_without_max_tokens_keeps_default(captured_chat):
    """인터프리터의 기존 호출(chat(system, user))은 기본 num_predict를 유지한다."""
    from strategy_conversation.interpreter.llm_strategy_interpreter import (
        _default_ollama_chat,
    )

    chat = _default_ollama_chat("test-model")
    chat("system", "user")
    assert captured_chat["body"]["options"]["num_predict"] == 2048
