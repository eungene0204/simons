"""관찰 라벨용 실제 모델명(active_chat_model) — span 이름이 Ollama 슬롯명으로 찍혀
OpenRouter 모델의 드리프트를 로컬 9B 회귀로 오독한 사고(2026-09-07)의 회귀 테스트."""
import time

import llm_backend


def test_active_model_is_payload_model_on_ollama_lane(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert llm_backend.active_chat_model("slot-model") == "slot-model"


def test_active_model_is_openrouter_model_on_openrouter_lane(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    llm_backend.resume_openrouter()
    assert llm_backend.active_chat_model("slot-model") == "nvidia/nemotron-3-super-120b-a12b:free"


def test_active_model_falls_back_to_slot_while_openrouter_paused(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    llm_backend.pause_openrouter_until(time.time() + 60)
    try:
        assert llm_backend.active_chat_model("slot-model") == "slot-model"
    finally:
        llm_backend.resume_openrouter()
