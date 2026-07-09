import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from ai.summarize import (
    build_advisor_grounded_prompt,
    build_report_from_advisor,
    to_advisor_backtest_summary,
)


# ── 단위 변환 (퍼센트 → 분수) ─────────────────────────────────────────────────

def test_to_advisor_backtest_summary_converts_percent_to_fraction():
    out = to_advisor_backtest_summary(
        {
            "cagr": 18.0,
            "maxDrawdown": -32.0,
            "winRate": 55.0,
            "profitFactor": 1.6,
            "sharpe": 1.2,
            "trades": 42,
        }
    )
    assert out["cagr"] == 0.18
    assert out["mdd"] == -0.32
    assert out["win_rate"] == 0.55
    assert out["profit_factor"] == 1.6
    assert out["sharpe"] == 1.2
    assert out["trade_count"] == 42


def test_to_advisor_backtest_summary_normalizes_positive_mdd_to_negative():
    # 프론트가 MDD 를 양수 절댓값으로 줄 수도 있다 → advisor 음수 컨벤션으로 변환
    out = to_advisor_backtest_summary({"maxDrawdown": 25.0})
    assert out["mdd"] == -0.25


def test_to_advisor_backtest_summary_handles_missing_and_bad_values():
    out = to_advisor_backtest_summary({"cagr": None, "trades": "x"})
    assert out["cagr"] is None
    assert out["trade_count"] is None
    assert out["win_rate"] is None


# ── advisor → 리포트 매핑 ─────────────────────────────────────────────────────

def test_build_report_from_advisor_maps_advice_to_improvements_sorted_by_severity():
    advisor = {
        "strategy_score": 64.0,
        "risk_score": 40.0,
        "overfit_risk": "medium",
        "advice": [
            {"severity": "low", "title": "낮은 우선순위", "body": "b1"},
            {
                "severity": "high",
                "title": "손절 추가",
                "body": "손절이 없습니다.",
                "proposed_change": {"description": "손절 8% 설정을 고려해보세요."},
            },
        ],
        "suggested_experiments": ["손절 8~10% 비교 백테스트"],
    }
    report = build_report_from_advisor(advisor)

    # high 가 먼저, proposed_change.description 우선
    assert report["improvements"][0] == "손절 8% 설정을 고려해보세요."
    assert "손절 8~10% 비교 백테스트" in report["improvements"]
    assert report["advisorScore"] == 64.0
    assert report["riskScore"] == 40.0
    assert report["overfitRisk"] == "medium"
    assert report["advice_titles"][0] == "손절 추가"


def test_build_report_from_advisor_limits_improvements_to_three():
    advisor = {
        "advice": [
            {"severity": "high", "title": f"t{i}", "body": f"b{i}"}
            for i in range(5)
        ],
        "suggested_experiments": ["exp1", "exp2"],
    }
    report = build_report_from_advisor(advisor)
    assert len(report["improvements"]) == 3


def test_build_report_from_advisor_empty_returns_none_marker():
    report = build_report_from_advisor({})
    assert report["improvements"] == ["없음"]
    assert report["advisorScore"] is None


# ── 근거 주입 프롬프트 ────────────────────────────────────────────────────────

def test_build_advisor_grounded_prompt_injects_diagnoses_and_omits_improvements():
    payload = {"metrics": {"cagr": 16.0, "maxDrawdown": -11.0}}
    report = {
        "advisorScore": 64,
        "riskScore": 40,
        "overfitRisk": "medium",
        "advice_titles": ["손절 추가", "거래대금 필터 추가"],
        "response_sections": [{"title": "위험 요소", "body": "손절 미설정으로 하방 위험이 큽니다."}],
    }
    prompt = build_advisor_grounded_prompt(payload, report)

    assert "advisor 진단 근거" in prompt
    assert "손절 추가" in prompt
    assert "과적합 위험: medium" in prompt
    # weaknesses 는 진단 근거에서만 도출하도록 지시
    assert "지어내지 마세요" in prompt
    # improvements 는 LLM 출력 스키마에서 제외
    assert '"improvements"' not in prompt.split("출력 형식 (JSON만 출력, improvements 키 없음)")[1]


def test_build_advisor_grounded_prompt_allows_fewer_than_three_weaknesses():
    """단점은 근거(진단·지표)가 있는 만큼만 쓰고, 없으면 빈 배열을 허용해야 한다.

    base 프롬프트의 '정확히 3개' 규칙과 '진단에서만 도출' 규칙이 충돌하면
    LLM이 없는 문제를 지어내는(환각) 쪽으로 밀리기 때문이다.
    """
    payload = {"metrics": {"cagr": 16.0}}
    report = {"advice_titles": ["손절 추가"], "response_sections": []}
    prompt = build_advisor_grounded_prompt(payload, report)

    assert "근거가 있는 만큼만 최대 3개" in prompt
    assert "빈 배열 []" in prompt


def test_build_advisor_grounded_prompt_has_no_conflicting_rules():
    """grounded 프롬프트는 base 규칙과 모순되는 지시(단점/개선 '정확히 3개')를 포함하면 안 된다.

    규칙 두 벌이 충돌하면 모델이 지시문을 복창하거나 내부 추론을 노출한다
    (2026-07-08 총평 지시문 누출 사고의 원인).
    """
    payload = {"metrics": {"cagr": 16.0}}
    report = {"advice_titles": ["손절 추가"], "response_sections": []}
    prompt = build_advisor_grounded_prompt(payload, report)

    assert "weaknesses는 정확히 3개" not in prompt
    assert "improvements는 정확히 3개" not in prompt
    # 출력 형식 블록은 단 한 번만 등장해야 한다
    assert prompt.count("출력 형식") == 1
