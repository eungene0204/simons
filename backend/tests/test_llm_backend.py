import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from llm_backend import resolve_llm_backend


def test_resolve_defaults_to_ollama(monkeypatch):
    """기본 백엔드는 Ollama (배포/개발 parity). LLM_BACKEND 미설정·preferred 없음 → ollama."""
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    assert resolve_llm_backend() == "ollama"
    assert resolve_llm_backend(preferred="ollama") == "ollama"


def test_resolve_env_force(monkeypatch):
    """LLM_BACKEND 환경변수가 명시적으로 백엔드를 강제한다."""
    monkeypatch.setenv("LLM_BACKEND", "mlx")
    assert resolve_llm_backend() == "mlx"
    assert resolve_llm_backend(preferred="ollama") == "mlx"  # 강제가 preferred보다 우선
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    assert resolve_llm_backend() == "ollama"


def test_resolve_preferred_mlx_only_when_available(monkeypatch):
    """preferred='mlx' 라도 MLX를 쓸 수 없으면 ollama로 강등."""
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setattr("llm_backend.mlx_available", lambda: False)
    assert resolve_llm_backend(preferred="mlx") == "ollama"
    monkeypatch.setattr("llm_backend.mlx_available", lambda: True)
    assert resolve_llm_backend(preferred="mlx") == "mlx"
