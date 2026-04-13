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
        return '{"total_summary":"요약 성공","strengths":["강점"],"risks":["리스크"]}'

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
    assert response["risks"] == ["리스크"]
