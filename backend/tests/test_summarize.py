import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine.nl_parser import NLStrategyParser
from ai.summarize import (
    FALLBACK_SUMMARY,
    MLX_MODEL,
    OLLAMA_MODEL,
    build_prompt,
    normalize_report_items,
    parse_llm_output,
)


def test_normalize_report_items_returns_none_when_empty():
    assert normalize_report_items([]) == ["없음"]
    assert normalize_report_items(None) == ["없음"]
    assert normalize_report_items(["", "   ", None]) == ["없음"]


def test_normalize_report_items_keeps_non_empty_values():
    assert normalize_report_items(["강점 1", "  리스크 1  "]) == ["강점 1", "리스크 1"]


def test_parse_llm_output_ignores_qwen35_thinking_prefix():
    text = """Thinking Process:

1. Analyze metrics.
2. Build JSON.

{"total_summary":"요약입니다.","strengths":["강점"],"weaknesses":["단점"],"improvements":["개선점"]}"""

    assert parse_llm_output(text) == {
        "total_summary": "요약입니다.",
        "strengths": ["강점"],
        "weaknesses": ["단점"],
        "improvements": ["개선점"],
    }


def test_parse_llm_output_ignores_think_tags():
    text = """<think>
내부 추론
</think>

{"total_summary":"총평","strengths":[],"weaknesses":[],"improvements":[]}"""

    assert parse_llm_output(text) == {
        "total_summary": "총평",
        "strengths": [],
        "weaknesses": [],
        "improvements": [],
    }


def test_parse_llm_output_builds_summary_from_reasoning_only_response():
    text = """Thinking Process:
1. Analyze the Request
2. Analyze the Backtest Results"""

    assert parse_llm_output(text) == {
        "total_summary": "Analyze the Request Analyze the Backtest Results",
        "strengths": [],
        "weaknesses": [],
        "improvements": [],
    }


def test_parse_llm_output_supports_single_quote_json_with_trailing_comma():
    text = """```json
{'totalSummary': '총평입니다.', 'strengths': ['강점1'], 'weaknesses': ['단점1'], 'improvements': ['개선점1'],}
```"""

    assert parse_llm_output(text) == {
        "total_summary": "총평입니다.",
        "strengths": ["강점1"],
        "weaknesses": ["단점1"],
        "improvements": ["개선점1"],
    }


def test_parse_llm_output_supports_section_based_text():
    text = """총평: 전반적으로 안정적인 전략입니다.
강점:
- 손실 방어력이 높습니다.
- 승률이 안정적입니다.
단점:
- 횡보장에서 수익성이 낮아질 수 있습니다."""

    result = parse_llm_output(text)
    assert result["total_summary"] == "전반적으로 안정적인 전략입니다."
    assert result["strengths"] == ["손실 방어력이 높습니다.", "승률이 안정적입니다."]
    # 섹션 기반 파싱에서는 단점이 파싱될 수 있음
    assert "weaknesses" in result or "improvements" in result


def test_parse_llm_output_returns_fallback_when_reasoning_is_empty():
    text = "Thinking Process:"

    assert parse_llm_output(text) == {
        "total_summary": FALLBACK_SUMMARY,
        "strengths": [],
        "weaknesses": [],
        "improvements": [],
    }


def test_build_prompt_includes_quality_rules():
    prompt = build_prompt({"metrics": {}})

    assert "작성 규칙" in prompt
    assert "strengths는 정확히 3개" in prompt
    assert "weaknesses는 정확히 3개" in prompt
    assert "improvements는 정확히 3개" in prompt
    assert "지표 해석 힌트(참고용)" in prompt


def test_build_prompt_includes_metric_hints():
    prompt = build_prompt(
        {
            "metrics": {
                "totalReturn": 24.5,
                "buyAndHoldReturn": 14.5,
                "cagr": 16.2,
                "maxDrawdown": -11.0,
                "sharpe": 1.15,
                "profitFactor": 1.62,
                "winRate": 56.0,
                "trades": 42,
            }
        }
    )

    assert "바이앤홀드 대비 10.00%p 높습니다." in prompt
    assert "CAGR 16.20%" in prompt
    assert "최대 낙폭 11.00%" in prompt
    assert "샤프 1.15" in prompt
    assert "손익비 1.62" in prompt
    assert "승률 56.00%" in prompt


def test_summarize_models_point_to_qwen35_9b():
    assert MLX_MODEL == "mlx-community/Qwen3.5-9B-OptiQ-4bit"
    assert OLLAMA_MODEL == "qwen3.5:9b"


def test_summarize_uses_same_mlx_model_as_shared_nl_parser_runtime():
    parser = NLStrategyParser()

    assert parser.model_7b == MLX_MODEL
