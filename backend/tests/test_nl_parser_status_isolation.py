"""NL 파서 로드 상태가 코치/검증 모듈 주입 실패와 분리되는지 회귀 검증.

버그: preload_nl_parser가 코치 파서 주입(`api.coach_routes.set_parser`)을 NL 파서
상태 결정 try 블록 안에서 수행해, 검증 에이전트 교체 등으로 coach_routes import가
깨지면 NL 모델이 멀쩡한데도 status="failed"로 찍혀 "AI 모델 로드 실패" 배너가 떴다.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import main


class _DummyParser:
    ollama_model = "dummy-model"

    def _init_ollama(self):
        pass


def _reset_status():
    main._nl_parser_status["status"] = "loading"
    main._nl_parser_status["error"] = None


def test_coach_injection_failure_does_not_fail_nl_parser(monkeypatch):
    _reset_status()
    monkeypatch.setattr("llm_backend.resolve_llm_backend", lambda: "ollama")
    monkeypatch.setattr("engine.nl_parser.NLStrategyParser", lambda backend: _DummyParser())
    monkeypatch.setattr(main, "_kick_ollama_warmup", lambda: None)
    monkeypatch.setattr(main, "_kick_local_ollama_model_preload", lambda _model: None)

    # 코치 파서 주입이 깨져도(검증 에이전트 교체 중 import 오류 등) NL 상태는 ok여야 한다.
    def _boom(_parser):
        raise ImportError("coach_routes import broke")

    monkeypatch.setattr("api.coach_routes.set_parser", _boom)

    main.preload_nl_parser()

    assert main._nl_parser_status["status"] == "ok"
    assert main._nl_parser_status["error"] is None


def test_nl_parser_load_failure_still_reports_failed(monkeypatch):
    _reset_status()
    monkeypatch.setattr("llm_backend.resolve_llm_backend", lambda: "ollama")

    def _broken_parser(backend):
        raise RuntimeError("model load failed")

    monkeypatch.setattr("engine.nl_parser.NLStrategyParser", _broken_parser)

    main.preload_nl_parser()

    assert main._nl_parser_status["status"] == "failed"
    assert "model load failed" in (main._nl_parser_status["error"] or "")


def test_unloaded_mlx_downgrades_to_ollama(monkeypatch):
    """버그: resolve_llm_backend는 mlx_lm 임포트 가능 여부만 봐서, 라이브러리는 있지만
    startup에 mlx 모델이 로드되지 않은 로컬 dev에서 backend='mlx' 요청이 503을 냈다.
    강제(LLM_BACKEND=mlx)가 아니면 ollama로 강등돼야 한다."""
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setattr(main, "_nl_parsers", {"ollama": _DummyParser()})
    assert main._downgrade_unloaded_mlx("mlx") == "ollama"
    # ollama 요청은 그대로 둔다.
    assert main._downgrade_unloaded_mlx("ollama") == "ollama"


def test_loaded_mlx_is_not_downgraded(monkeypatch):
    """mlx 모델이 실제로 로드돼 있으면 강등하지 않는다."""
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setattr(main, "_nl_parsers", {"mlx": _DummyParser()})
    assert main._downgrade_unloaded_mlx("mlx") == "mlx"


def test_forced_mlx_is_not_downgraded(monkeypatch):
    """LLM_BACKEND=mlx 로 강제하면 미로드여도 강등하지 않는다(명시적 의도 존중)."""
    monkeypatch.setenv("LLM_BACKEND", "mlx")
    monkeypatch.setattr(main, "_nl_parsers", {})
    assert main._downgrade_unloaded_mlx("mlx") == "mlx"


def test_llm_connection_error_classified_through_cause_chain():
    # instructor가 APIConnectionError를 InstructorRetryException으로 감싸 raise하는 형태.
    try:
        try:
            raise ValueError("APIConnectionError('Connection error.')")
        except ValueError as inner:
            raise RuntimeError("InstructorRetryException") from inner
    except RuntimeError as exc:
        assert main._is_llm_connection_error(exc) is True


def test_non_connection_error_not_classified_as_connection():
    assert main._is_llm_connection_error(ValueError("invalid strategy field")) is False
