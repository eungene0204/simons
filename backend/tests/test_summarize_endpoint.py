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
    # Ollama 요약 경로 검증 (과거 MLX 경로는 제거됨)
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    def fake_summarize_ollama(prompt):
        return '{"total_summary":"요약 성공","strengths":["강점"],"weaknesses":["단점"],"improvements":["개선점"]}'

    monkeypatch.setattr("ai.summarize.summarize_ollama", fake_summarize_ollama)

    response = main.summarize_backtest(main.SummarizeRequest(metrics={}))

    assert response["summary"] == "요약 성공"
    assert response["strengths"] == ["강점"]
    assert response["weaknesses"] == ["단점"]
    assert response["improvements"] == ["개선점"]
    assert response["runtime"]["backend"] == "ollama"
    assert response["runtime"]["total_ms"] >= 0


def test_summarize_endpoint_uses_advisor_for_improvements_when_parsed_strategy(monkeypatch):
    """parsed_strategy 가 있으면 advisor 가 improvements/점수를 결정론적으로 채우고 LLM 출력을 덮어쓴다."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    def fake_summarize_ollama(prompt):
        # LLM 이 엉뚱한 improvements 를 내도 advisor 가 덮어써야 한다
        return '{"total_summary":"총평","strengths":["강점"],"weaknesses":["단점"],"improvements":["LLM환각개선"]}'

    monkeypatch.setattr("ai.summarize.summarize_ollama", fake_summarize_ollama)

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

    response = main.summarize_backtest(
        main.SummarizeRequest(
            metrics={"cagr": 16.0, "maxDrawdown": -11.0},
            parsed_strategy={"entry_signals": []},
            user_prompt="안정적인 전략",
        )
    )

    # advisor 결정론 결과로 덮어쓰기
    assert response["improvements"] == ["손절 8% 설정을 고려해보세요.", "손절 8~10% 비교 백테스트"]
    assert response["advisorScore"] == 64.0
    assert response["riskScore"] == 38.0
    assert response["overfitRisk"] == "medium"
    # LLM 서술은 유지
    assert response["summary"] == "총평"
    assert response["strengths"] == ["강점"]


def test_summarize_endpoint_falls_back_to_llm_only_when_advisor_fails(monkeypatch):
    """advisor 가 None 을 반환(실패)하면 LLM 단독 결과를 사용한다."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    def fake_summarize_ollama(prompt):
        return '{"total_summary":"폴백","strengths":["s"],"weaknesses":["w"],"improvements":["i"]}'

    monkeypatch.setattr("ai.summarize.summarize_ollama", fake_summarize_ollama)
    monkeypatch.setattr(main, "_run_advisor_for_report", lambda ps, up, m: None)

    response = main.summarize_backtest(
        main.SummarizeRequest(metrics={}, parsed_strategy={"entry_signals": []})
    )

    assert response["improvements"] == ["i"]
    assert "advisorScore" not in response


def test_summarize_endpoint_marks_degraded_when_llm_output_unparseable(monkeypatch):
    """LLM이 지시문 복창/미닫힘 <think>만 내놓으면 폴백 요약 + degraded=True를 반환해야 한다.

    프록시/프론트는 degraded 리포트를 캐시·저장하지 않고 재시도를 유도한다.
    """
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    def fake_summarize_ollama(prompt):
        return (
            "[중요] 위 JSON 규칙을 따르되, improvements 키는 절대 포함하지 마세요. "
            "<think> Analyze the Request: conflicting instructions..."
        )

    monkeypatch.setattr("ai.summarize.summarize_ollama", fake_summarize_ollama)

    response = main.summarize_backtest(main.SummarizeRequest(metrics={}))

    assert response["degraded"] is True
    assert "요약을 생성하지 못했습니다" in response["summary"]
    # 지시문/내부 추론이 총평으로 새지 않는다
    assert "[중요]" not in response["summary"]
    assert "<think>" not in response["summary"]


def test_summarize_endpoint_no_degraded_flag_on_success(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    def fake_summarize_ollama(prompt):
        return '{"total_summary":"정상 요약","strengths":["s"],"weaknesses":["w"],"improvements":["i"]}'

    monkeypatch.setattr("ai.summarize.summarize_ollama", fake_summarize_ollama)

    response = main.summarize_backtest(main.SummarizeRequest(metrics={}))

    assert "degraded" not in response
    assert response["summary"] == "정상 요약"


def test_summarize_endpoint_injects_corpus_comparison(monkeypatch):
    """코퍼스 비교가 계산되면 프롬프트에 주입되고 응답에 corpusComparison으로 포함된다."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    captured = {}

    def fake_summarize_ollama(prompt):
        captured["prompt"] = prompt
        return '{"total_summary":"비교군 중 상위 23%입니다.","strengths":["s"],"weaknesses":["w"],"improvements":["i"]}'

    monkeypatch.setattr("ai.summarize.summarize_ollama", fake_summarize_ollama)

    fake_cmp = {
        "cohort_label": "구조가 유사한 과거 전략 시뮬레이션 187개(전체 2000개 중)",
        "cohort_size": 187,
        "corpus_size": 2000,
        "lines": ["CAGR 13.80%는 비교군 중 상위 23% (비교군 중앙값 8.10%)."],
        "contrast_lines": [],
    }
    monkeypatch.setattr("advisor.corpus_insights.build_corpus_comparison", lambda ps, m: fake_cmp)

    response = main.summarize_backtest(main.SummarizeRequest(metrics={"cagr": 13.8}))

    assert "코퍼스 비교" in captured["prompt"]
    assert "상위 23%" in captured["prompt"]
    assert response["corpusComparison"] == fake_cmp


def test_summarize_endpoint_survives_corpus_comparison_failure(monkeypatch):
    """코퍼스 비교 계산이 죽어도 리포트는 기존 형태로 동작해야 한다."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    def fake_summarize_ollama(prompt):
        return '{"total_summary":"요약","strengths":["s"],"weaknesses":["w"],"improvements":["i"]}'

    monkeypatch.setattr("ai.summarize.summarize_ollama", fake_summarize_ollama)
    monkeypatch.setattr(
        "advisor.corpus_insights.build_corpus_comparison",
        lambda ps, m: (_ for _ in ()).throw(RuntimeError("corpus broken")),
    )

    response = main.summarize_backtest(main.SummarizeRequest(metrics={"cagr": 13.8}))

    assert response["summary"] == "요약"
    assert "corpusComparison" not in response
