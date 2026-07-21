import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import main


class _DummyParsed:
    fundamental_filters = []
    entry_signals = []
    ranking_metric = None
    # 하한선 보정(enforce_strategy_minimums)이 읽는 필드들
    initial_capital = 10_000_000.0
    hold_period_days = None
    ranking_lookback_days = None
    stop_loss_pct = None
    take_profit_pct = None
    trailing_stop_pct = None
    max_mdd_limit_pct = None
    fee_rate = 0.015
    slippage_rate = 0.05
    backtest_start_date = None

    def model_dump(self):
        return {"universe": ["KOSPI200"]}


class _DummyParser:
    def __init__(self):
        self.parse_calls = 0

    def parse(self, _prompt, on_stage=None, on_validation=None, defer_validation=False):
        self.parse_calls += 1
        return _DummyParsed()


def test_parse_nl_strategy_reports_runtime_and_cache_hit(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")  # 테스트는 ollama 파서를 주입하므로 환경도 ollama로 고정
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


async def _collect_sse(response):
    """StreamingResponse 본문을 모아 SSE data 페이로드 리스트로 반환."""
    chunks = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunk = chunk.decode()
        chunks.append(chunk)
    text = "".join(chunks)
    return [
        block[len("data: "):].strip()
        for block in text.split("\n\n")
        if block.startswith("data: ")
    ]


@pytest.mark.asyncio
async def test_parse_stream_emits_parsing_stage_and_result(monkeypatch):
    """규칙 기반 경로: stage('parsing') → result → [DONE], thinking 없음."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    main._nl_parsers["ollama"] = _DummyParser()
    main._nl_parse_cache.clear()
    main._reset_ai_runtime_metrics_for_tests()

    import engine.strategy_converter as strategy_converter
    monkeypatch.setattr(strategy_converter, "to_backtest_request", lambda _p: {"symbols": ["005930"]})

    try:
        response = await main.parse_nl_strategy_stream(
            main.NLParseRequest(prompt="PBR 1 이하", backend="ollama")
        )
        payloads = await _collect_sse(response)
    finally:
        main._nl_parse_cache.clear()
        main._nl_parsers.pop("ollama", None)

    import json
    events = [json.loads(p) for p in payloads if p != "[DONE]"]
    stages = [e["stage"] for e in events if e["type"] == "stage"]
    assert stages == ["parsing"]
    assert payloads[-1] == "[DONE]"
    result = next(e for e in events if e["type"] == "result")
    assert result["data"]["parsed"] == {"universe": ["KOSPI200"]}


@pytest.mark.asyncio
async def test_parse_stream_emits_thinking_stage_when_parser_falls_back(monkeypatch):
    """파서가 on_stage('thinking')을 호출하면 스트림에 thinking 단계가 실린다."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    class _LLMFallbackParser:
        def parse(self, _prompt, on_stage=None, on_validation=None, defer_validation=False):
            if on_stage is not None:
                on_stage("thinking")
            return _DummyParsed()

    main._nl_parsers["ollama"] = _LLMFallbackParser()
    main._nl_parse_cache.clear()
    main._reset_ai_runtime_metrics_for_tests()

    import engine.strategy_converter as strategy_converter
    monkeypatch.setattr(strategy_converter, "to_backtest_request", lambda _p: {"symbols": ["005930"]})

    try:
        response = await main.parse_nl_strategy_stream(
            main.NLParseRequest(prompt="애매한 전략", backend="ollama")
        )
        payloads = await _collect_sse(response)
    finally:
        main._nl_parse_cache.clear()
        main._nl_parsers.pop("ollama", None)

    import json
    stages = [json.loads(p)["stage"] for p in payloads if p != "[DONE]" and json.loads(p)["type"] == "stage"]
    assert "parsing" in stages
    assert "thinking" in stages
    assert stages.index("thinking") > stages.index("parsing")


def test_forced_mlx_parse_requires_startup_loaded_model(monkeypatch):
    """LLM_BACKEND=mlx 로 명시 강제했는데 모델이 startup에 로드되지 않았으면 503.

    (강제가 아닌 일반 backend='mlx' 요청은 ollama로 강등된다 —
    test_nl_parser_status_isolation.test_unloaded_mlx_downgrades_to_ollama 참조.)
    """
    monkeypatch.setenv("LLM_BACKEND", "mlx")
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
    monkeypatch.setenv("LLM_BACKEND", "mlx")  # MLX 모드에서만 startup이 모델 로드 실패를 전파
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
