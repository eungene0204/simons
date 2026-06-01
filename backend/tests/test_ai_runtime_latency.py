import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import main


class _DummyParsed:
    fundamental_filters = []
    entry_signals = []

    def model_dump(self):
        return {"universe": ["KOSPI200"]}


class _DummyParser:
    def __init__(self):
        self.parse_calls = 0

    def parse(self, _prompt):
        self.parse_calls += 1
        return _DummyParsed()


def test_parse_nl_strategy_reports_runtime_and_cache_hit(monkeypatch):
    parser = _DummyParser()
    main._nl_parsers["ollama"] = parser
    main._nl_parse_cache.clear()
    main._reset_ai_runtime_metrics_for_tests()

    import engine.strategy_converter as strategy_converter

    monkeypatch.setattr(
        strategy_converter,
        "to_backtest_request",
        lambda _parsed: {"symbols": ["005930"]},
    )

    try:
        request = main.NLParseRequest(prompt="PBR 1 이하", backend="ollama")
        first = main.parse_nl_strategy(request)
        second = main.parse_nl_strategy(request)
    finally:
        main._nl_parse_cache.clear()
        main._nl_parsers.pop("ollama", None)

    assert first["runtime"]["cache_hit"] is False
    assert first["runtime"]["backend"] == "ollama"
    assert first["runtime"]["parse_ms"] >= 0
    assert first["runtime"]["convert_ms"] >= 0
    assert second["runtime"]["cache_hit"] is True
    assert parser.parse_calls == 1

    metrics = main.get_ai_runtime_metrics()
    parse_metrics = metrics["stages"]["parse"]
    assert parse_metrics["count"] == 2
    assert parse_metrics["cache_hits"] == 1
    assert parse_metrics["cache_misses"] == 1
    assert parse_metrics["avg_total_ms"] >= 0


def test_mlx_parse_requires_startup_loaded_model():
    existing = main._nl_parsers.pop("mlx", None)
    main._nl_parse_cache.clear()
    try:
        with pytest.raises(Exception) as exc_info:
            main.parse_nl_strategy(main.NLParseRequest(prompt="RSI 전략", backend="mlx"))
    finally:
        main._nl_parse_cache.clear()
        if existing is not None:
            main._nl_parsers["mlx"] = existing

    assert getattr(exc_info.value, "status_code", None) == 503
    assert "not loaded at startup" in str(exc_info.value.detail)


def test_preload_nl_parser_fails_startup_when_model_load_fails(monkeypatch):
    class _FailingParser:
        def __init__(self, backend="mlx"):
            self.backend = backend

        def _init_mlx(self):
            raise RuntimeError("model unavailable")

    existing = main._nl_parsers.pop("mlx", None)
    main._nl_parser_status["status"] = "loading"
    main._nl_parser_status["error"] = None
    monkeypatch.setattr("engine.nl_parser.NLStrategyParser", _FailingParser)

    try:
        with pytest.raises(RuntimeError, match="model unavailable"):
            main.preload_nl_parser()
    finally:
        main._nl_parsers.pop("mlx", None)
        if existing is not None:
            main._nl_parsers["mlx"] = existing

    assert main._nl_parser_status["status"] == "failed"
    assert "model unavailable" in str(main._nl_parser_status["error"])


@pytest.mark.asyncio
async def test_lifespan_preloads_nl_parser_before_serving(monkeypatch):
    calls = []

    async def _startup():
        calls.append("startup")

    async def _shutdown():
        calls.append("shutdown")

    def _preload_nl_parser():
        calls.append("preload_nl_parser")

    def _preload_summarize_model():
        calls.append("preload_summarize_model")

    def _log_universe_status_on_startup():
        calls.append("log_universe_status_on_startup")

    def _start_news_llm_preload_thread():
        calls.append("start_news_llm_preload_thread")

    monkeypatch.setattr(main, "startup", _startup)
    monkeypatch.setattr(main, "shutdown", _shutdown)
    monkeypatch.setattr(main, "preload_nl_parser", _preload_nl_parser)
    monkeypatch.setattr(main, "preload_summarize_model", _preload_summarize_model)
    monkeypatch.setattr(main, "log_universe_status_on_startup", _log_universe_status_on_startup)
    monkeypatch.setattr(main, "_start_news_llm_preload_thread", _start_news_llm_preload_thread)

    async with main.lifespan(main.app):
        assert calls[:4] == [
            "preload_nl_parser",
            "preload_summarize_model",
            "startup",
            "log_universe_status_on_startup",
        ]

    assert calls[-1] == "shutdown"


def test_ai_runtime_metrics_reset_endpoint():
    main._record_ai_runtime("summary", {"cache_hit": False, "total_ms": 12.5})
    assert main.get_ai_runtime_metrics()["stages"]["summary"]["count"] == 1

    assert main.reset_ai_runtime_metrics() == {"ok": True}
    assert main.get_ai_runtime_metrics()["stages"] == {}
