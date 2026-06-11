import os
import sys
import types

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import main


class _DummyTokenizer:
    chat_template = "dummy-template"

    def __init__(self):
        self.kwargs = None

    def apply_chat_template(self, messages, **kwargs):
        self.kwargs = kwargs
        return "FORMATTED_PROMPT"


def test_summarize_endpoint_disables_thinking_on_mlx(monkeypatch):
    tokenizer = _DummyTokenizer()
    original_model = main._summarize_model["model"]
    original_tokenizer = main._summarize_model["tokenizer"]
    main._summarize_model["model"] = object()
    main._summarize_model["tokenizer"] = tokenizer

    fake_mlx_lm = types.ModuleType("mlx_lm")

    def fake_generate(model, tokenizer_arg, prompt, max_tokens, verbose):  # pragma: no cover - assertions below validate call
        assert tokenizer_arg is tokenizer
        assert prompt == "FORMATTED_PROMPT"
        return '{"total_summary":"요약 성공","strengths":["강점"],"weaknesses":["단점"],"improvements":["개선점"]}'

    fake_mlx_lm.generate = fake_generate
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_mlx_lm)
    monkeypatch.setattr("platform.system", lambda: "Darwin")

    try:
        response = main.summarize_backtest(main.SummarizeRequest(metrics={}))
    finally:
        main._summarize_model["model"] = original_model
        main._summarize_model["tokenizer"] = original_tokenizer

    assert tokenizer.kwargs is not None
    assert tokenizer.kwargs.get("enable_thinking") is False
    assert response["summary"] == "요약 성공"
    assert response["strengths"] == ["강점"]
    assert response["weaknesses"] == ["단점"]
    assert response["improvements"] == ["개선점"]
    assert response["runtime"]["backend"] == "mlx"
    assert response["runtime"]["total_ms"] >= 0


def test_summarize_endpoint_uses_advisor_for_improvements_when_parsed_strategy(monkeypatch):
    """parsed_strategy 가 있으면 advisor 가 improvements/점수를 결정론적으로 채우고 LLM 출력을 덮어쓴다."""
    tokenizer = _DummyTokenizer()
    original_model = main._summarize_model["model"]
    original_tokenizer = main._summarize_model["tokenizer"]
    main._summarize_model["model"] = object()
    main._summarize_model["tokenizer"] = tokenizer

    fake_mlx_lm = types.ModuleType("mlx_lm")

    captured = {}

    def fake_generate(model, tokenizer_arg, prompt, max_tokens, verbose):
        captured["prompt"] = prompt
        # LLM 이 엉뚱한 improvements 를 내도 advisor 가 덮어써야 한다
        return '{"total_summary":"총평","strengths":["강점"],"weaknesses":["단점"],"improvements":["LLM환각개선"]}'

    fake_mlx_lm.generate = fake_generate
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_mlx_lm)
    monkeypatch.setattr("platform.system", lambda: "Darwin")

    # advisor 호출을 가짜 응답으로 대체 (DB/모델 의존 제거)
    fake_advisor_resp = {
        "strategy_score": 64.0,
        "risk_score": 38.0,
        "overfit_risk": "medium",
        "advice": [
            {
                "severity": "high",
                "title": "손절 추가",
                "body": "손절이 없습니다.",
                "proposed_change": {"description": "손절 8% 설정을 고려해보세요."},
            }
        ],
        "suggested_experiments": ["손절 8~10% 비교 백테스트"],
        "response_sections": [{"title": "위험 요소", "body": "하방 위험이 큽니다."}],
    }
    monkeypatch.setattr(main, "_run_advisor_for_report", lambda ps, up, m: fake_advisor_resp)

    try:
        response = main.summarize_backtest(
            main.SummarizeRequest(
                metrics={"cagr": 16.0, "maxDrawdown": -11.0},
                parsed_strategy={"entry_signals": []},
                user_prompt="안정적인 전략",
            )
        )
    finally:
        main._summarize_model["model"] = original_model
        main._summarize_model["tokenizer"] = original_tokenizer

    # advisor 결정론 결과로 덮어쓰기
    assert response["improvements"] == ["손절 8% 설정을 고려해보세요.", "손절 8~10% 비교 백테스트"]
    assert response["advisorScore"] == 64.0
    assert response["riskScore"] == 38.0
    assert response["overfitRisk"] == "medium"
    # LLM 서술은 유지
    assert response["summary"] == "총평"
    assert response["strengths"] == ["강점"]
    # tokenizer 가 포맷팅한 프롬프트(근거 주입 포함)를 사용
    assert captured["prompt"] == "FORMATTED_PROMPT"
    assert tokenizer.kwargs is not None


def test_summarize_endpoint_falls_back_to_llm_only_when_advisor_fails(monkeypatch):
    """advisor 가 None 을 반환(실패)하면 기존 LLM 단독 경로로 폴백한다."""
    tokenizer = _DummyTokenizer()
    original_model = main._summarize_model["model"]
    original_tokenizer = main._summarize_model["tokenizer"]
    main._summarize_model["model"] = object()
    main._summarize_model["tokenizer"] = tokenizer

    fake_mlx_lm = types.ModuleType("mlx_lm")
    fake_mlx_lm.generate = lambda model, tokenizer_arg, prompt, max_tokens, verbose: (
        '{"total_summary":"폴백","strengths":["s"],"weaknesses":["w"],"improvements":["i"]}'
    )
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_mlx_lm)
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr(main, "_run_advisor_for_report", lambda ps, up, m: None)

    try:
        response = main.summarize_backtest(
            main.SummarizeRequest(metrics={}, parsed_strategy={"entry_signals": []})
        )
    finally:
        main._summarize_model["model"] = original_model
        main._summarize_model["tokenizer"] = original_tokenizer

    assert response["improvements"] == ["i"]
    assert "advisorScore" not in response
