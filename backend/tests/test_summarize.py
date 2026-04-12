import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from ai.summarize import (
    MLX_MODEL,
    OLLAMA_MODEL,
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

{"total_summary":"요약입니다.","strengths":["강점"],"risks":["리스크"]}"""

    assert parse_llm_output(text) == {
        "total_summary": "요약입니다.",
        "strengths": ["강점"],
        "risks": ["리스크"],
    }


def test_parse_llm_output_ignores_think_tags():
    text = """<think>
내부 추론
</think>

{"total_summary":"총평","strengths":[],"risks":[]}"""

    assert parse_llm_output(text) == {
        "total_summary": "총평",
        "strengths": [],
        "risks": [],
    }


def test_summarize_models_point_to_qwen35_4b():
    assert MLX_MODEL == "mlx-community/Qwen3.5-4B-OptiQ-4bit"
    assert OLLAMA_MODEL == "qwen3.5:4b"
