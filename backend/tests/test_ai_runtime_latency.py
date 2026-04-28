import os
import sys

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


def test_ai_runtime_metrics_reset_endpoint():
    main._record_ai_runtime("summary", {"cache_hit": False, "total_ms": 12.5})
    assert main.get_ai_runtime_metrics()["stages"]["summary"]["count"] == 1

    assert main.reset_ai_runtime_metrics() == {"ok": True}
    assert main.get_ai_runtime_metrics()["stages"] == {}
