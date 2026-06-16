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


def test_learning_provider_prefers_parameter_near_samples_for_adjustments(tmp_path):
    summary = {
        "summary": {
            "best_indicator_combinations": {},
            "best_single_indicators": {},
        }
    }
    rows = [
        {
            "input": {
                "user_prompt": "RSI 30 이하, 손절 8%, 익절 15%, 20일 보유",
                "parsed_blocks": ["rsi", "stop_loss", "take_profit", "max_holding_days"],
                "extracted_parameters": {
                    "stop_loss_pct": 8,
                    "take_profit_pct": 15,
                    "hold_period_days": 20,
                    "max_positions": 10,
                },
            },
            "output": {
                "evidence": {
                    "median_cagr": 9.0,
                    "median_sharpe": 0.8,
                    "median_mdd": -12.0,
                    "median_profit_factor": 1.4,
                    "median_trades": 42,
                },
                "suggested_actions": ["MDD 확인"],
            },
        },
        {
            "input": {
                "user_prompt": "RSI 30 이하, 손절 12%, 익절 25%, 60일 보유",
                "parsed_blocks": ["rsi", "stop_loss", "take_profit", "max_holding_days"],
                "extracted_parameters": {
                    "stop_loss_pct": 12,
                    "take_profit_pct": 25,
                    "hold_period_days": 60,
                    "max_positions": 20,
                },
            },
            "output": {
                "evidence": {
                    "median_cagr": 2.0,
                    "median_sharpe": 0.2,
                    "median_mdd": -25.0,
                    "median_profit_factor": 0.9,
                    "median_trades": 15,
                },
                "suggested_actions": ["MDD 확인"],
            },
        },
    ]
    (tmp_path / "strategy_prompt_experiment_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "strategy_advisor_learning_dataset.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows),
        encoding="utf-8",
    )

    provider = ExperimentLearningProvider(tmp_path)
    insight = provider.build_insight({
        "entry_signals": [{"indicator": "rsi", "threshold": 30}],
        "max_positions": 10,
    })

    assert insight["similar_samples"][0]["extracted_parameters"]["stop_loss_pct"] == 8
    assert insight["similar_samples"][0]["parameter_similarity"] > insight["similar_samples"][1]["parameter_similarity"]
    assert insight["recommended_adjustments"][:3] == [
        "RSI 진입 기준 25/30/35 비교",
        "손절 8% 추가 버전 비교",
        "익절 15% 추가 버전 비교",
    ]


def test_learning_provider_separates_positive_and_negative_samples(tmp_path):
    summary = {
        "summary": {
            "best_indicator_combinations": {},
            "best_single_indicators": {},
        }
    }
    rows = [
        {
            "input": {
                "sample_id": "good_rsi_stop",
                "user_prompt": "RSI 30 이하, 손절 8%, 익절 15%",
                "parsed_blocks": ["rsi", "stop_loss", "take_profit"],
                "extracted_parameters": {
                    "stop_loss_pct": 8,
                    "take_profit_pct": 15,
                    "max_positions": 10,
                },
            },
            "output": {
                "evidence": {
                    "median_cagr": 10.0,
                    "median_sharpe": 0.9,
                    "median_mdd": -12.0,
                    "median_profit_factor": 1.6,
                    "median_trades": 35,
                },
            },
        },
        {
            "input": {
                "sample_id": "bad_rsi_stop",
                "user_prompt": "RSI 30 이하, 손절 20%, 익절 40%",
                "parsed_blocks": ["rsi", "stop_loss", "take_profit"],
                "extracted_parameters": {
                    "stop_loss_pct": 20,
                    "take_profit_pct": 40,
                    "max_positions": 10,
                },
            },
            "output": {
                "evidence": {
                    "median_cagr": -8.0,
                    "median_sharpe": -0.4,
                    "median_mdd": -38.0,
                    "median_profit_factor": 0.7,
                    "median_trades": 28,
                },
            },
        },
    ]
    (tmp_path / "strategy_prompt_experiment_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "strategy_advisor_learning_dataset.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows),
        encoding="utf-8",
    )

    provider = ExperimentLearningProvider(tmp_path)
    insight = provider.build_insight({
        "entry_signals": [{"indicator": "rsi", "threshold": 30}],
        "max_positions": 10,
    })

    assert insight["positive_samples"][0]["sample_id"] == "good_rsi_stop"
    assert insight["negative_samples"][0]["sample_id"] == "bad_rsi_stop"
    assert insight["negative_sample_count"] == 1
    assert insight["recommended_adjustments"][:3] == [
        "RSI 진입 기준 25/30/35 비교",
        "손절 8% 추가 버전 비교",
        "익절 15% 추가 버전 비교",
    ]
    assert any("유사 실패 패턴" in warning for warning in insight["warnings"])


def test_learning_provider_surfaces_paired_delta_adjustments(tmp_path):
    summary = {
        "summary": {
            "best_indicator_combinations": {},
            "best_single_indicators": {},
        }
    }
    row = {
        "input": {
            "user_prompt": "RSI 30 이하에 손절 8%만 추가",
            "parsed_blocks": ["rsi", "stop_loss"],
            "extracted_parameters": {"stop_loss_pct": 8, "max_positions": 10},
        },
        "output": {
            "evidence": {
                "median_cagr": 7.0,
                "median_sharpe": 0.7,
                "median_mdd": -12.0,
                "median_profit_factor": 1.3,
                "median_trades": 35,
            },
            "paired_delta": {
                "pair_id": "advisor_pair_0001",
                "baseline_sample_id": "advisor_pair_0001_baseline",
                "change_axis": "stop_loss",
                "changed_parameter": {"stop_loss_pct": 8},
                "cagr_delta": 3.0,
                "sharpe_delta": 0.3,
                "mdd_delta": 8.0,
                "profit_factor_delta": 0.3,
                "trade_delta": 5.0,
                "improves_risk_adjusted": True,
            },
        },
    }
    (tmp_path / "strategy_prompt_experiment_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "strategy_advisor_learning_dataset.jsonl").write_text(json.dumps(row), encoding="utf-8")

    provider = ExperimentLearningProvider(tmp_path)
    insight = provider.build_insight({
        "entry_signals": [{"indicator": "rsi", "threshold": 30}],
        "max_positions": 10,
    })

    assert insight["recommended_adjustments"][0] == "손절 8% 추가 버전 비교(CAGR +3.00%p, Sharpe +0.30, MDD +8.00%p, PF +0.30)"


def test_learning_provider_prefers_paired_delta_over_missing_exit_rule(tmp_path):
    summary = {
        "summary": {
            "best_indicator_combinations": {},
            "best_single_indicators": {},
        }
    }
    rules = {
        "rules": [
            {
                "id": "rule_missing_exit_rule",
                "condition": "missing stop_loss_pct, take_profit_pct, trailing_stop_pct, and max_holding_days",
                "suggested_actions": ["손절 8% 추가", "익절 15% 추가"],
            }
        ]
    }
    row = {
        "input": {
            "user_prompt": "RSI 30 이하에 손절 8%만 추가",
            "parsed_blocks": ["rsi", "stop_loss"],
            "extracted_parameters": {"stop_loss_pct": 8, "max_positions": 10},
        },
        "output": {
            "evidence": {
                "median_cagr": 7.0,
                "median_sharpe": 0.7,
                "median_mdd": -12.0,
            },
            "paired_delta": {
                "change_axis": "stop_loss",
                "changed_parameter": {"stop_loss_pct": 8},
                "cagr_delta": 3.0,
                "sharpe_delta": 0.3,
                "mdd_delta": 8.0,
                "improves_risk_adjusted": True,
            },
        },
    }
    (tmp_path / "strategy_prompt_experiment_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "strategy_advisor_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (tmp_path / "strategy_advisor_learning_dataset.jsonl").write_text(json.dumps(row), encoding="utf-8")

    provider = ExperimentLearningProvider(tmp_path)
    insight = provider.build_insight({
        "entry_signals": [{"indicator": "rsi", "threshold": 30}],
        "max_positions": 10,
    })

    assert insight["matched_rules"]
    assert insight["recommended_adjustments"][0].startswith("손절 8% 추가 버전 비교(CAGR +3.00%p")


def test_learning_provider_uses_strategy_specific_adjustments_before_generic_params(tmp_path):
    summary = {
        "summary": {
            "best_indicator_combinations": {},
            "best_single_indicators": {},
        }
    }
    row = {
        "input": {
            "user_prompt": "공통 리스크 후보",
            "parsed_blocks": ["max_positions", "stop_loss"],
            "extracted_parameters": {"stop_loss_pct": 12, "max_positions": 20},
        },
        "output": {
            "evidence": {
                "median_cagr": 5.0,
                "median_sharpe": 0.5,
                "median_mdd": -15.0,
            },
        },
    }
    (tmp_path / "strategy_prompt_experiment_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "strategy_advisor_learning_dataset.jsonl").write_text(json.dumps(row), encoding="utf-8")

    provider = ExperimentLearningProvider(tmp_path)
    rsi = provider.build_insight({
        "entry_signals": [{"indicator": "rsi", "threshold": 30}],
        "max_positions": 10,
    })
    breakout = provider.build_insight({
        "entry_signals": [{"indicator": "breakout"}, {"indicator": "volume_spike"}],
        "max_positions": 10,
    })
    value = provider.build_insight({
        "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
        "max_positions": 10,
    })
    macd_volume = provider.build_insight({
        "entry_signals": [{"indicator": "macd"}, {"indicator": "volume_spike"}],
        "max_positions": 10,
    })

    assert rsi["recommended_adjustments"][0] == "RSI 진입 기준 25/30/35 비교"
    assert breakout["recommended_adjustments"][:2] == [
        "신고가 기간 120일/252일 비교",
        "거래량 급증 기준 1.5배/2배 비교",
    ]
    assert value["recommended_adjustments"][0] == "PBR 기준 0.8배/1.0배 비교"
    assert macd_volume["recommended_adjustments"][:2] == [
        "MACD 확인 조건 신호선 교차/0선 돌파 비교",
        "거래량 급증 기준 1.5배/2배 비교",
    ]
    assert len({
        rsi["recommended_adjustments"][0],
        breakout["recommended_adjustments"][0],
        value["recommended_adjustments"][0],
        macd_volume["recommended_adjustments"][0],
    }) == 4


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
    # 코치가 그대로 복창하면 사용자에게 새는 내부 지시문/매달린 접속어를 advice에 넣지 않는다.
    assert "내부 참고용" not in result.advice[0].body
    assert "판단하면" not in result.advice[0].body
    assert "비슷한 전략들의 과거 사례를 보면" in result.advice[0].body
    assert "현재 전략은 먼저 같은 기간과 비용 조건으로 백테스트" in result.advice[0].body
    assert "백테스트 학습 사례" not in result.advice[0].body
    assert "중앙값" not in result.advice[0].body


def test_advisor_primary_advice_combines_learning_and_memory_evidence(tmp_path):
    _write_learning_files(tmp_path)
    agent = StrategyAdvisorAgent(learning_provider=ExperimentLearningProvider(tmp_path))

    parsed_strategy = {
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi"}],
        "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
        "stop_loss_pct": 8.0,
        "take_profit_pct": 15.0,
        "max_positions": 10,
        "initial_capital": 10_000_000,
    }

    result = agent.review(AdvisorRequest(
        user_prompt="PBR 1 이하, RSI 30 이하, 손절 8%로 검증해줘",
        parsed_strategy=parsed_strategy,
        memory_strategy_cases=[
            {
                "strategy_id": "case_pbr_rsi",
                "user_prompt": "PBR 1 이하 RSI 평균회귀",
                "strategy_summary": "PBR + RSI + 손절",
                "strategy_dsl": parsed_strategy,
            }
        ],
        memory_experiences=[
            {
                "strategy_id": "case_pbr_rsi",
                "before_backtest": {"cagr": 0.04, "mdd": -0.24, "sharpe": 0.4},
                "after_backtest": {"cagr": 0.08, "mdd": -0.16, "sharpe": 0.8},
                "evaluation": {"advice_success": True},
                "lesson": "PBR + RSI 조합은 손절과 보유기간을 함께 비교해야 한다.",
            }
        ],
    ))

    assert result.advice[0].title == "전략 실험 근거 기반 개선"
    assert "내부 참고용" not in result.advice[0].body
    assert "판단하면" not in result.advice[0].body
    assert "비슷한 전략들의 과거 사례를 보면" in result.advice[0].body
    assert "유사 전략 경험까지 보면" in result.advice[0].body
    assert "조정 후" in result.advice[0].body
    assert "백테스트 학습 사례" not in result.advice[0].body
    assert "중앙값" not in result.advice[0].body
    assert any(item.title == "유사 전략 경험 기반 점검" for item in result.advice)


def test_advisor_injects_negative_experiment_warning(tmp_path):
    summary = {
        "summary": {
            "best_indicator_combinations": {},
            "best_single_indicators": {},
        }
    }
    row = {
        "input": {
            "sample_id": "bad_rsi_only",
            "user_prompt": "RSI 30 이하만 사용",
            "parsed_blocks": ["rsi"],
            "extracted_parameters": {"rsi_threshold": 30, "max_positions": 10},
        },
        "output": {
            "evidence": {
                "median_cagr": -12.0,
                "median_sharpe": -0.6,
                "median_mdd": -42.0,
                "median_trades": 30,
            },
        },
    }
    (tmp_path / "strategy_prompt_experiment_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "strategy_advisor_learning_dataset.jsonl").write_text(json.dumps(row), encoding="utf-8")

    agent = StrategyAdvisorAgent(learning_provider=ExperimentLearningProvider(tmp_path))
    result = agent.review(AdvisorRequest(
        user_prompt="RSI 30 이하 전략을 검토해줘",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "threshold": 30}],
            "fundamental_filters": [],
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
    ))

    assert result.strategy_experiment_learning is not None
    assert result.strategy_experiment_learning["negative_sample_count"] == 1
    assert "유사 실패 패턴" in result.advice[0].body
    assert "제안 주신 전략과 비슷한 전략의 결과" not in result.advice[0].body
    assert "이 전략에서" not in result.advice[0].body
    assert "각각 바꿔 테스트" not in result.advice[0].body
    assert "MDD와 Sharpe가 동시에 좋아지는 설정만 남기세요" not in result.advice[0].body
    assert "중앙값" not in result.advice[0].body
    assert "confidence" not in result.advice[0].body
    assert "근거 수준" not in result.advice[0].body
    assert "확신하기 어렵" not in result.advice[0].body
    assert "가까운 샘플도 파라미터" not in result.advice[0].body
    assert "delta만 비교" not in result.advice[0].body
    assert "stop_loss" not in result.advice[0].body
    assert "max_holding_days" not in result.advice[0].body


def test_flat_experiment_evidence_is_described_as_weak_signal(tmp_path):
    summary = {
        "summary": {
            "best_indicator_combinations": {
                "ma_crossover+max_positions+trading_value": {
                    "combination_count": 40,
                    "median_cagr": 0.0,
                    "median_sharpe": 0.0,
                    "median_mdd": 0.0,
                    "confidence": "high",
                    "recommended_guidance": "거래대금 + 이동평균 조합은 기본 성과가 확인됐습니다.",
                }
            },
            "best_single_indicators": {},
        }
    }
    (tmp_path / "strategy_prompt_experiment_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "strategy_advisor_learning_dataset.jsonl").write_text("", encoding="utf-8")

    agent = StrategyAdvisorAgent(learning_provider=ExperimentLearningProvider(tmp_path))
    result = agent.review(AdvisorRequest(
        user_prompt="거래대금 100억 이상 종목 중 10일선이 60일선을 돌파하면 매수",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "ma_cross"}],
            "fundamental_filters": [{"metric": "trading_value", "operator": ">=", "value": 10_000_000_000}],
            "max_positions": 10,
            "initial_capital": 30_000_000,
        },
    ))

    assert result.strategy_experiment_learning["confidence"] == "low"
    assert "성과 신호가 약하므로" in result.advice[0].body
    assert "한 번에 하나씩만 비교하세요" in result.advice[0].body
    assert "성과 신호가 거의 없었습니다" not in result.advice[0].body
    assert "현재안을 그대로 반복하지 말고" not in result.advice[0].body
    assert "중앙값" not in result.advice[0].body
    assert "근거 수준" not in result.advice[0].body
    assert "확신하기 어렵" not in result.advice[0].body
    assert "가까운 샘플도 파라미터" not in result.advice[0].body
    assert "delta만 비교" not in result.advice[0].body
    assert "기본 성과가 확인" not in result.advice[0].body


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
