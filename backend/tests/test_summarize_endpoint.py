import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import main


# 전략 검증 전문가 리포트(10섹션) — LLM 서술 8섹션 JSON 샘플.
_EXPERT_JSON = (
    '{"executive_summary":"핵심 요약","top_insights":["통찰1","통찰2"],'
    '"strengths":["강점"],"weaknesses":["약점"],"hidden_risks":["숨은 위험"],'
    '"overfitting_analysis":"과최적화 서술","strategy_profile_note":"성향 서술",'
    '"final_verdict":"최종 평가"}'
)

# DSL 수정(손절/익절 값·지표·파라미터·매수매도 조건) 문구가 개선안에 섞이면 안 된다.
_DSL_FORBIDDEN = ["손절", "익절", "지표를 추가", "파라미터를", "매수 조건", "매도 조건"]


def _fake_ollama(payload):
    # summarize_ollama(prompt, num_predict=...) 시그니처를 흡수한다.
    def _inner(prompt, *args, **kwargs):
        return payload
    return _inner


def test_summarize_endpoint_returns_expert_sections(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setattr("ai.summarize.summarize_ollama", _fake_ollama(_EXPERT_JSON))

    response = main.summarize_backtest(main.SummarizeRequest(metrics={}))

    assert response["summary"] == "핵심 요약"
    assert response["executiveSummary"] == "핵심 요약"
    assert response["topInsights"] == ["통찰1", "통찰2"]
    assert response["strengths"] == ["강점"]
    assert response["weaknesses"] == ["약점"]
    assert response["hiddenRisks"] == ["숨은 위험"]
    assert response["overfittingAnalysis"] == "과최적화 서술"
    assert response["finalVerdict"] == "최종 평가"
    # 검증 로드맵·개선 우선순위는 결정론으로 항상 채워진다.
    assert isinstance(response["validationRoadmap"], list) and response["validationRoadmap"]
    assert isinstance(response["improvements"], list) and response["improvements"]
    assert response["runtime"]["backend"] == "ollama"
    assert response["runtime"]["total_ms"] >= 0


def test_summarize_endpoint_improvements_are_validation_centric_not_dsl(monkeypatch):
    """parsed_strategy·advisor 가 있어도 개선안은 검증 중심이며 구체적 DSL 수정을 담지 않는다."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setattr("ai.summarize.summarize_ollama", _fake_ollama(_EXPERT_JSON))

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

    # advisor 점수·등급은 그대로 반영
    assert response["advisorScore"] == 64.0
    assert response["riskScore"] == 38.0
    assert response["overfitRisk"] == "medium"
    # LLM 서술은 유지
    assert response["summary"] == "핵심 요약"
    # 개선안은 검증 중심 — advisor 의 DSL 제안('손절 8% 설정')을 그대로 옮기지 않는다.
    joined = " ".join(response["improvements"])
    assert not any(tok in joined for tok in _DSL_FORBIDDEN)
    roadmap_titles = " ".join(i["title"] for i in response["validationRoadmap"])
    assert not any(tok in roadmap_titles for tok in _DSL_FORBIDDEN)


def test_summarize_endpoint_works_without_advisor(monkeypatch):
    """advisor 가 None(실패/미전달)이어도 결정론 섹션으로 리포트를 구성한다."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setattr("ai.summarize.summarize_ollama", _fake_ollama(_EXPERT_JSON))
    monkeypatch.setattr(main, "_run_advisor_for_report", lambda ps, up, m: None)

    response = main.summarize_backtest(
        main.SummarizeRequest(metrics={}, parsed_strategy={"entry_signals": []})
    )

    assert response["summary"] == "핵심 요약"
    assert response["improvements"]  # 점수 기반 결정론 개선안
    assert "advisorScore" not in response


def test_summarize_endpoint_marks_degraded_when_llm_output_unparseable(monkeypatch):
    """LLM이 지시문 복창/미닫힘 <think>만 내놓으면 폴백 요약 + degraded=True를 반환해야 한다."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setattr(
        "ai.summarize.summarize_ollama",
        _fake_ollama(
            "[중요] 위 JSON 규칙을 따르되, improvements 키는 절대 포함하지 마세요. "
            "<think> Analyze the Request: conflicting instructions..."
        ),
    )

    response = main.summarize_backtest(main.SummarizeRequest(metrics={}))

    assert response["degraded"] is True
    assert "요약을 생성하지 못했습니다" in response["summary"]
    # 지시문/내부 추론이 총평으로 새지 않는다
    assert "[중요]" not in response["summary"]
    assert "<think>" not in response["summary"]


def test_summarize_endpoint_no_degraded_flag_on_success(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setattr("ai.summarize.summarize_ollama", _fake_ollama(_EXPERT_JSON))

    response = main.summarize_backtest(main.SummarizeRequest(metrics={}))

    assert "degraded" not in response
    assert response["summary"] == "핵심 요약"


def test_summarize_endpoint_injects_corpus_comparison(monkeypatch):
    """코퍼스 비교가 계산되면 프롬프트에 주입되고 응답에 corpusComparison으로 포함된다."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    captured = {}

    def fake_summarize_ollama(prompt, *args, **kwargs):
        captured["prompt"] = prompt
        return _EXPERT_JSON

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
    monkeypatch.setattr("ai.summarize.summarize_ollama", _fake_ollama(_EXPERT_JSON))
    monkeypatch.setattr(
        "advisor.corpus_insights.build_corpus_comparison",
        lambda ps, m: (_ for _ in ()).throw(RuntimeError("corpus broken")),
    )

    response = main.summarize_backtest(main.SummarizeRequest(metrics={"cagr": 13.8}))

    assert response["summary"] == "핵심 요약"
    assert "corpusComparison" not in response
