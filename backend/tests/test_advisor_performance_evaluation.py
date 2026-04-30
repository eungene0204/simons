import json
import os
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))

from advisor.agent import StrategyAdvisorAgent
from advisor.performance_evaluation import (
    AdvisorPerformanceEvaluator,
    NullLearningProvider,
    case_to_parsed_strategy,
    load_advisor_cases,
    report_to_dict,
    score_response,
)
from advisor.schemas import AdvisorRequest


def _write_evaluation_files(tmp_path):
    summary = {
        "summary": {
            "best_indicator_combinations": {
                "pbr+rsi+stop_loss": {
                    "combination_count": 18,
                    "median_cagr": 6.2,
                    "median_sharpe": 0.7,
                    "median_mdd": -19.5,
                    "median_profit_factor": 1.4,
                    "median_trades": 50,
                    "median_quality_score": 0.35,
                    "confidence": "medium",
                    "recommended_guidance": "RSI + PBR + 손절 조합은 MDD를 줄이는 경향이 있어 손절 범위를 검증하세요.",
                    "warnings": [],
                }
            },
            "best_single_indicators": {},
        }
    }
    rules = {"rules": []}
    rows = [
        {
            "input": {
                "user_prompt": "KOSPI200에서 RSI 30 이하 PBR 1 이하 손절 8%",
                "parsed_blocks": ["rsi", "pbr", "stop_loss"],
                "risk_profile": "moderate",
                "category": "hybrid_value_technical",
                "extracted_parameters": {"rsi_threshold": 30, "stop_loss_pct": 8},
            },
            "output": {"evidence": {"similar_strategy_count": 18}},
        },
        {
            "input": {
                "user_prompt": "KOSPI200에서 RSI 25 이하 PBR 1 이하 손절 10%",
                "parsed_blocks": ["rsi", "pbr", "stop_loss"],
                "risk_profile": "conservative",
                "category": "hybrid_value_technical",
                "extracted_parameters": {"rsi_threshold": 25, "stop_loss_pct": 10},
            },
            "output": {"evidence": {"similar_strategy_count": 18}},
        },
    ]
    (tmp_path / "strategy_prompt_experiment_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "strategy_advisor_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (tmp_path / "strategy_advisor_learning_dataset.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_load_cases_and_convert_to_parsed_strategy(tmp_path):
    _write_evaluation_files(tmp_path)

    cases = load_advisor_cases(tmp_path)
    parsed = case_to_parsed_strategy(cases[0])

    assert len(cases) == 2
    assert parsed["entry_signals"][0]["indicator"] == "rsi"
    assert parsed["fundamental_filters"][0]["metric"] == "pbr"
    assert parsed["stop_loss_pct"] == 8


def test_score_response_rewards_experiment_evidence(tmp_path):
    _write_evaluation_files(tmp_path)
    case = load_advisor_cases(tmp_path, limit=1)[0]
    parsed = case_to_parsed_strategy(case)

    baseline = StrategyAdvisorAgent(learning_provider=NullLearningProvider()).review(
        AdvisorRequest(user_prompt=case.user_prompt, parsed_strategy=parsed)
    )
    learned = StrategyAdvisorAgent().review(
        AdvisorRequest(user_prompt=case.user_prompt, parsed_strategy=parsed)
    )
    learned.strategy_experiment_learning = {
        "similar_strategy_count": 18,
        "median_cagr": 6.2,
        "median_sharpe": 0.7,
        "median_mdd": -19.5,
        "recommended_adjustments": ["손절 8% 추가"],
    }

    assert score_response(learned).total > score_response(baseline).total


def test_evaluator_reports_positive_learning_uplift(tmp_path):
    _write_evaluation_files(tmp_path)

    report = AdvisorPerformanceEvaluator(tmp_path).evaluate()
    payload = report_to_dict(report)

    assert report.total_cases == 2
    assert report.learned_average_score > report.baseline_average_score
    assert report.absolute_improvement > 0
    assert report.evidence_coverage_rate == 1.0
    assert report.safety_pass_rate == 1.0
    assert "cases" not in payload
