import json
import os
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))

from advisor.agent import StrategyAdvisorAgent
from advisor.experiment_learning import ExperimentLearningProvider, extract_strategy_blocks
from advisor.schemas import AdvisorRequest, NewsArticleSignal, NewsContext


def _write_learning_files(tmp_path):
    summary = {
        "experiment_id": "test_exp",
        "summary": {
            "best_indicator_combinations": {
                "pbr+rsi+stop_loss": {
                    "combination_count": 18,
                    "median_cagr": 7.2,
                    "median_sharpe": 0.81,
                    "median_mdd": -18.4,
                    "median_profit_factor": 1.5,
                    "median_trades": 64,
                    "median_quality_score": 0.42,
                    "confidence": "medium",
                    "recommended_guidance": "RSI + PBR + 손절 조합은 MDD를 줄이는 경향이 있어 손절 범위를 함께 검증하세요.",
                    "warnings": [],
                }
            },
            "best_single_indicators": {
                "rsi": {
                    "count": 30,
                    "median_cagr": 4.1,
                    "median_sharpe": 0.5,
                    "median_mdd": -22.0,
                    "median_quality_score": 0.25,
                    "confidence": "medium",
                }
            },
        },
        "advisor_guidance": {},
    }
    rules = {
        "rules": [
            {
                "id": "rule_missing_exit_rule",
                "condition": "missing stop_loss_pct, take_profit_pct, trailing_stop_pct, and max_holding_days",
                "evidence": {"confidence": "medium"},
                "advice": "청산 조건이 부족하면 실험 근거와 함께 MDD 확대 가능성을 먼저 설명합니다.",
                "suggested_actions": ["손절 8% 추가", "익절 15% 추가"],
                "confidence": "medium",
            }
        ]
    }
    sample = {
        "input": {
            "user_prompt": "PBR 1 이하 RSI 30 이하 손절 8%",
            "parsed_blocks": ["pbr", "rsi", "stop_loss"],
            "risk_profile": "moderate",
            "category": "hybrid_value_technical",
            "extracted_parameters": {"stop_loss_pct": 8},
        },
        "output": {
            "evidence": {
                "similar_strategy_count": 18,
                "median_cagr": 7.2,
                "median_sharpe": 0.81,
                "median_mdd": -18.4,
                "confidence": "medium",
            },
            "recommended_advice": "전략 검증 관점에서 손절 범위를 비교하세요.",
            "suggested_actions": ["손절 8% 추가"],
        },
    }
    (tmp_path / "strategy_prompt_experiment_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "strategy_advisor_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (tmp_path / "strategy_advisor_learning_dataset.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")


def test_extract_strategy_blocks_from_parsed_strategy():
    blocks = extract_strategy_blocks({
        "entry_signals": [{"indicator": "rsi"}],
        "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
        "stop_loss_pct": 8.0,
        "max_positions": 10,
    })

    assert blocks == ["max_positions", "pbr", "rsi", "stop_loss"]


def test_learning_provider_returns_evidence(tmp_path):
    _write_learning_files(tmp_path)
    provider = ExperimentLearningProvider(tmp_path)

    insight = provider.build_insight({
        "entry_signals": [{"indicator": "rsi"}],
        "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
        "stop_loss_pct": 8.0,
    })

    assert insight["confidence"] == "medium"
    assert insight["similar_strategy_count"] == 18
    assert insight["median_mdd"] == -18.4
    assert insight["matched_patterns"][0]["pattern_key"] == "pbr+rsi+stop_loss"
    assert "RSI + PBR + 손절" in insight["recommended_advice"][0]


def test_advisor_injects_experiment_learning_advice(tmp_path):
    _write_learning_files(tmp_path)
    agent = StrategyAdvisorAgent(learning_provider=ExperimentLearningProvider(tmp_path))

    result = agent.review(AdvisorRequest(
        user_prompt="PBR 1 이하, RSI 30 이하, 손절 8%로 검증해줘",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi"}],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
            "stop_loss_pct": 8.0,
            "take_profit_pct": 15.0,
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
    ))

    assert result.strategy_experiment_learning is not None
    assert result.strategy_experiment_learning["similar_strategy_count"] == 18
    assert result.advice[0].title == "전략 실험 근거 기반 개선"
    assert "비슷한 18개 실험" in result.advice[0].body
    assert "투자 추천이 아니라 전략 검증/리스크 관리 근거" in result.advice[0].body


def test_high_news_risk_takes_priority_over_learning(tmp_path):
    _write_learning_files(tmp_path)
    agent = StrategyAdvisorAgent(learning_provider=ExperimentLearningProvider(tmp_path))

    result = agent.review(AdvisorRequest(
        user_prompt="PBR 1 이하, RSI 30 이하, 손절 8%로 검증해줘",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi"}],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
            "stop_loss_pct": 8.0,
            "take_profit_pct": 15.0,
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
        news_context=[
            NewsContext(
                symbol="005930",
                risk_alert_level="high",
                articles=[
                    NewsArticleSignal(
                        event_type="regulatory_probe",
                        sentiment="negative",
                        impact_direction="down",
                        impact_score=-0.8,
                        confidence_score=0.9,
                    )
                ],
            )
        ],
    ))

    assert result.advice[0].title.startswith("하나 이상의 종목에서 높은 뉴스 리스크")
    assert result.strategy_experiment_learning is not None
    assert "뉴스 리스크가 high" in result.strategy_experiment_learning["warnings"][0]
