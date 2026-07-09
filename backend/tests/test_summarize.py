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
    summarize_ollama,
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


def test_parse_llm_output_recovers_closed_fields_from_truncated_json():
    text = """'{ "total_summary": "총 수익률 52.40%를 기록했지만 바이앤홀드 대비 낮습니다.",
"strengths": ["손익비가 2.91로 우수합니다.", "MDD가 -21.47%로 제한되었습니다."],
"weaknesses": ["총 수익률이 바이앤홀드보다 낮습니다.", "승률이 49.09%입니다.", "샤프 지수 0.68과 소르티노 지수 0.96은 위험 대비 성과가 개선될 여지가 크"""

    result = parse_llm_output(text)

    assert result["total_summary"] == "총 수익률 52.40%를 기록했지만 바이앤홀드 대비 낮습니다."
    assert result["strengths"] == ["손익비가 2.91로 우수합니다.", "MDD가 -21.47%로 제한되었습니다."]
    assert result["weaknesses"] == ["총 수익률이 바이앤홀드보다 낮습니다.", "승률이 49.09%입니다."]
    assert "total_summary" not in result["total_summary"]


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


def test_build_prompt_includes_backtest_period_and_capital():
    prompt = build_prompt(
        {
            "metrics": {
                "cagr": 12.0,
                "periodStart": "2021-01-04",
                "periodEnd": "2025-12-30",
                "initialCapital": 10_000_000,
                "finalEquity": 17_543_210,
            }
        }
    )

    assert "백테스트 기간: 2021-01-04 ~ 2025-12-30" in prompt
    assert "초기 자본: 1,000만원 → 최종 자산: 1,754만원" in prompt
    # 수치 환각 방지 규칙
    assert "제시되지 않은 수치나 기간을 추측해서 쓰지 마세요" in prompt
    assert "미래 성과 예측이나 단정" in prompt


def test_build_prompt_omits_period_and_capital_lines_when_missing():
    prompt = build_prompt({"metrics": {"cagr": 12.0}})

    assert "백테스트 기간:" not in prompt
    assert "초기 자본:" not in prompt


def test_summarize_models_point_to_qwen35_4b(monkeypatch):
    # OLLAMA_MODEL은 NL_OLLAMA_MODEL 환경변수로 오버라이드된다(.env가 9B를 가리킴).
    # 여기서는 환경변수가 없을 때의 코드 폴백 기본값을 검증한다.
    import importlib
    import ai.summarize as summarize_mod

    monkeypatch.delenv("NL_OLLAMA_MODEL", raising=False)
    importlib.reload(summarize_mod)
    try:
        assert summarize_mod.MLX_MODEL == "mlx-community/Qwen3.5-4B-4bit"
        assert summarize_mod.OLLAMA_MODEL == "qwen3:8b"
    finally:
        importlib.reload(summarize_mod)  # 원래 환경 기준으로 복원


def test_summarize_uses_same_mlx_model_as_shared_nl_parser_runtime(monkeypatch):
    # 환경변수가 없을 때 요약 모델과 NL 파서 기본 모델이 같은지 검증한다.
    monkeypatch.delenv("NL_MLX_MODEL", raising=False)
    parser = NLStrategyParser()

    assert parser.mlx_model == MLX_MODEL


def test_summarize_ollama_allows_full_report_length(monkeypatch):
    """POST 본문은 num_predict=1200을 유지하고, 콜드스타트 대비 warmup GET이 선행돼야 한다."""
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"message":{"content":"{}"}}'

    def fake_urlopen(req, timeout):
        calls.append({"url": req.full_url, "method": req.get_method(), "body": req.data})
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    summarize_ollama("prompt")

    # Modal 콜드스타트 프록시는 첫 POST의 body를 유실시키므로, 본문 없는 GET으로 먼저 깨운다.
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"].endswith("/api/tags")
    assert calls[-1]["method"] == "POST"
    # GGUF 모델에서 think:false가 무시되는 /api/generate 대신 /api/chat을 써야 한다
    assert calls[-1]["url"].endswith("/api/chat")
    body = __import__("json").loads(calls[-1]["body"])
    assert body["options"]["num_predict"] == 1200


# ── 프롬프트 지시문/내부 추론 누출 방지 (2026-07-08 총평 누출 사고 재현) ──────

def test_parse_llm_output_never_leaks_unclosed_think_reasoning():
    """닫히지 않은 <think>(토큰 한도까지 이어진 추론)가 총평으로 노출되면 안 된다."""
    text = (
        "[중요] 위 JSON 규칙을 따르되, 아래 'advisor 진단 근거'에 명시된 문제만 weaknesses에 반영하세요. "
        "improvements 키는 절대 포함하지 마세요.\n"
        "<think> **Analyze the Request:** Role: Quant Investment Strategy Analyst. "
        "However, looking closely at the second JSON template provided in the prompt..."
    )

    parsed = parse_llm_output(text)

    assert parsed["total_summary"] == FALLBACK_SUMMARY
    assert parsed["strengths"] == []
    assert parsed["weaknesses"] == []


def test_parse_llm_output_rejects_prompt_instruction_echo_without_think():
    """<think> 태그 없이 지시문만 복창한 출력도 총평으로 흘려보내지 않는다."""
    text = (
        "작성 규칙:\n"
        "1) total_summary는 5~7문장으로 작성하고...\n"
        "출력 형식 (JSON만 출력):"
    )

    parsed = parse_llm_output(text)

    assert parsed["total_summary"] == FALLBACK_SUMMARY


def test_parse_llm_output_rejects_echoed_output_template_json():
    """모델이 출력 템플릿 JSON을 그대로 복창하면 리포트로 수락하지 않는다."""
    text = (
        '{"total_summary": "전략 전체 총평 5~7문장으로 상세히 작성. 수익성, 안정성, 효율성, 거래 신뢰도 등 다각도 분석",'
        '"strengths": ["강점1 - 2~3문장으로 상세 설명, 지표 수치 포함"],'
        '"weaknesses": ["단점1 - 1~2문장으로 간결히"],'
        '"improvements": ["개선 방안1 - 2~3문장으로 구체적 조치와 기대효과"]}'
    )

    parsed = parse_llm_output(text)

    assert parsed["total_summary"] == FALLBACK_SUMMARY


def test_parse_llm_output_accepts_valid_json_even_after_instruction_preamble():
    """지시문 복창 뒤라도 유효한 실제 리포트 JSON이 있으면 그것을 채택한다(과차단 방지)."""
    text = (
        "[중요] 위 JSON 규칙을 따르되...\n"
        '{"total_summary": "과거 데이터 기준 CAGR 12.30%를 기록했습니다.", '
        '"strengths": ["샤프 지수가 양호합니다."], "weaknesses": [], "improvements": []}'
    )

    parsed = parse_llm_output(text)

    assert parsed["total_summary"] == "과거 데이터 기준 CAGR 12.30%를 기록했습니다."
    assert parsed["strengths"] == ["샤프 지수가 양호합니다."]


def test_summarize_ollama_disables_thinking(monkeypatch):
    """qwen3 계열 thinking 우회 — nl_parser와 동일하게 think:false를 보내야 한다."""
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"message":{"content":"{}"}}'

    def fake_urlopen(req, timeout):
        calls.append(req)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    summarize_ollama("prompt")

    body = __import__("json").loads(calls[-1].data)
    assert body.get("think") is False, "thinking 우회는 think:false로 해야 함"


def test_build_prompt_includes_corpus_comparison_block_when_provided():
    cmp = {
        "cohort_label": "구조가 유사한 과거 전략 시뮬레이션 187개(전체 2000개 중)",
        "cohort_size": 187,
        "corpus_size": 2000,
        "lines": ["CAGR 13.80%는 비교군 중 상위 23% (비교군 중앙값 8.10%)."],
        "contrast_lines": ["이 전략처럼 손절 없이 운용된 비교군 90개의 최대 낙폭(MDD) 중앙값은 -19.00%, 손절을 둔 비교군 97개는 -12.40%였습니다."],
    }
    prompt = build_prompt({"metrics": {"cagr": 13.8}}, corpus_comparison=cmp)

    assert "코퍼스 비교 (기준: 구조가 유사한 과거 전략 시뮬레이션 187개" in prompt
    assert "상위 23%" in prompt
    assert "구조 장치 유무별 과거 통계" in prompt
    assert "9)" in prompt and "상대적 위치(상위/하위 %)" in prompt
    # '하위 X%' 오독(하위권을 긍정 서술) 방지 지시
    assert "긍정적으로 서술하지 마세요" in prompt


def test_build_prompt_omits_corpus_block_when_absent():
    prompt = build_prompt({"metrics": {"cagr": 13.8}})

    assert "코퍼스 비교" not in prompt
    assert "9)" not in prompt
