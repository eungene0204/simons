import json
import os
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))

from advisor.learning_builder import (
    build_advisor_learning_artifacts,
    build_advisor_learning_file_payloads,
    build_advisor_learning_artifacts_from_batch_export,
    build_advisor_learning_artifacts_from_prompt_experiment_result,
    normalize_batch_run_learning_results,
    serialize_learning_dataset_jsonl,
)
from advisor.sample_generator import generate_advisor_smoke_samples
from advisor.sample_generator import generate_advisor_paired_smoke_samples


def _result(sample_id: str, cagr: float, sharpe: float, mdd: float, trades: int = 20):
    return {
        "sample_id": sample_id,
        "metrics": {
            "cagr": cagr,
            "sharpe": sharpe,
            "mdd": mdd,
            "trade_count": trades,
        },
    }


def test_build_advisor_learning_artifacts_keeps_sample_result_alignment():
    samples = generate_advisor_smoke_samples(6)
    results = [
        {
            **_result(samples[0]["sample_id"], 8.0, 0.7, -12.0),
            "metrics": {
                "cagr": 8.0,
                "sharpe": 0.7,
                "mdd": -12.0,
                "profitFactor": 1.35,
                "tradeCount": 44,
            },
        },
        _result(samples[1]["sample_id"], -4.0, -0.2, -35.0),
    ]

    artifacts = build_advisor_learning_artifacts(samples, results)
    rows = artifacts["learning_dataset"]

    assert len(rows) == 2
    assert rows[0]["input"]["sample_id"] == samples[0]["sample_id"]
    assert rows[0]["input"]["parsed_blocks"] == samples[0]["parsed_blocks"]
    assert rows[0]["output"]["evidence"]["median_cagr"] == 8.0
    assert rows[0]["output"]["evidence"]["median_profit_factor"] == 1.35
    assert rows[0]["output"]["evidence"]["median_trades"] == 44.0
    assert rows[1]["output"]["evidence"]["median_mdd"] == -35.0
    assert "종목 수 분산 비교" in rows[1]["output"]["suggested_actions"]


def test_build_advisor_learning_artifacts_summarizes_combinations_and_singles():
    samples = generate_advisor_smoke_samples(12)
    first_blocks = samples[0]["parsed_blocks"]
    samples[6]["parsed_blocks"] = first_blocks
    results = [
        _result(samples[0]["sample_id"], 8.0, 0.7, -12.0),
        _result(samples[6]["sample_id"], 12.0, 0.9, -18.0),
    ]

    summary = build_advisor_learning_artifacts(samples, results)["summary"]["summary"]
    combo_key = "+".join(sorted(first_blocks))

    assert summary["total_samples"] == 2
    assert summary["best_indicator_combinations"][combo_key]["combination_count"] == 2
    assert summary["best_indicator_combinations"][combo_key]["median_cagr"] == 10.0
    assert summary["best_indicator_combinations"][combo_key]["median_sharpe"] == 0.8
    assert summary["best_indicator_combinations"][combo_key]["confidence"] == "low"
    assert first_blocks[0] in summary["best_single_indicators"]


def test_build_advisor_learning_artifacts_attaches_paired_deltas():
    samples = generate_advisor_paired_smoke_samples(6)[:4]
    results = [
        {
            **_result(samples[0]["sample_id"], 4.0, 0.4, -20.0, trades=30),
            "metrics": {
                "cagr": 4.0,
                "sharpe": 0.4,
                "mdd": -20.0,
                "profitFactor": 1.0,
                "tradeCount": 30,
            },
        },
        {
            **_result(samples[1]["sample_id"], 7.0, 0.7, -12.0, trades=35),
            "metrics": {
                "cagr": 7.0,
                "sharpe": 0.7,
                "mdd": -12.0,
                "profitFactor": 1.3,
                "tradeCount": 35,
            },
        },
    ]

    artifacts = build_advisor_learning_artifacts(samples, results)
    candidate_row = next(row for row in artifacts["learning_dataset"] if row["input"]["sample_id"] == samples[1]["sample_id"])
    paired_delta = candidate_row["output"]["paired_delta"]

    assert paired_delta["baseline_sample_id"] == samples[0]["sample_id"]
    assert paired_delta["change_axis"] == "stop_loss"
    assert paired_delta["cagr_delta"] == 3.0
    assert paired_delta["sharpe_delta"] == 0.3
    assert paired_delta["mdd_delta"] == 8.0
    assert paired_delta["profit_factor_delta"] == 0.3
    assert paired_delta["trade_delta"] == 5.0
    assert paired_delta["improves_risk_adjusted"] is True
    assert artifacts["summary"]["summary"]["paired_deltas"]["stop_loss"]["median_mdd_delta"] == 8.0


def test_serialize_learning_dataset_jsonl_round_trips():
    samples = generate_advisor_smoke_samples(6)
    artifacts = build_advisor_learning_artifacts(samples, [_result(samples[0]["sample_id"], 1.0, 0.1, -5.0)])

    payload = serialize_learning_dataset_jsonl(artifacts["learning_dataset"])
    rows = [json.loads(line) for line in payload.splitlines()]

    assert rows == artifacts["learning_dataset"]


def test_normalize_batch_run_learning_results_keeps_only_completed_rows():
    payload = {
        "results": [
            {
                "sample_id": "run_1__advisor_smoke_0001",
                "candidate_id": "candidate-1",
                "strategy_id": "hash_momentum",
                "status": "computed",
                "metrics": {"cagr": 8.5, "sharpe": 0.7, "maxDrawdown": -14.0},
            },
            {
                "sample_id": "advisor_smoke_0002",
                "status": "failed",
                "metrics": {"cagr": 99.0},
            },
            {
                "sample_id": "advisor_smoke_0003",
                "status": "cache_hit",
                "metrics": None,
            },
        ]
    }

    rows = normalize_batch_run_learning_results(payload)

    assert rows == [
        {
            "sample_id": "advisor_smoke_0001",
            "candidate_id": "candidate-1",
            "strategy_id": "hash_momentum",
            "metrics": {"cagr": 8.5, "sharpe": 0.7, "maxDrawdown": -14.0},
        }
    ]


def test_normalize_batch_run_learning_results_accepts_five_digit_sample_ids():
    rows = normalize_batch_run_learning_results({
        "results": [
            {
                "sample_id": "advisor_smoke_kospi200_10000__advisor_smoke_10000",
                "candidate_id": "candidate-10000",
                "strategy_id": "hash_final",
                "status": "cache_hit",
                "metrics": {"cagr": 3.2},
            },
        ]
    })

    assert rows == [
        {
            "sample_id": "advisor_smoke_10000",
            "candidate_id": "candidate-10000",
            "strategy_id": "hash_final",
            "metrics": {"cagr": 3.2},
        }
    ]


def test_normalize_batch_run_learning_results_accepts_paired_sample_ids():
    rows = normalize_batch_run_learning_results({
        "results": [
            {
                "sample_id": "advisor_paired_smoke_0120__advisor_pair_0001_stop_loss_pct",
                "candidate_id": "candidate-paired",
                "strategy_id": "hash_pair",
                "status": "computed",
                "metrics": {"cagr": 5.5},
            },
        ]
    })

    assert rows == [
        {
            "sample_id": "advisor_pair_0001_stop_loss_pct",
            "candidate_id": "candidate-paired",
            "strategy_id": "hash_pair",
            "metrics": {"cagr": 5.5},
        }
    ]


def test_build_learning_artifacts_from_batch_export_uses_next_export_shape():
    samples = generate_advisor_smoke_samples(6)
    payload = {
        "runId": "batch_run_learning",
        "results": [
            {
                "sample_id": samples[0]["sample_id"],
                "candidate_id": samples[0]["sample_id"],
                "strategy_id": "hash_momentum",
                "status": "computed",
                "metrics": {"cagr": 8.5, "sharpe": 0.7, "maxDrawdown": -14.0, "trades": 22},
            },
            {
                "sample_id": samples[1]["sample_id"],
                "candidate_id": samples[1]["sample_id"],
                "strategy_id": "hash_value",
                "status": "cache_hit",
                "metrics": {"cagr": -3.0, "sharpeRatio": -0.1, "mdd": -31.0, "tradeCount": 8},
            },
        ],
    }

    artifacts = build_advisor_learning_artifacts_from_batch_export(samples, payload)
    rows = artifacts["learning_dataset"]

    assert len(rows) == 2
    assert rows[0]["input"]["sample_id"] == samples[0]["sample_id"]
    assert rows[0]["output"]["evidence"]["median_mdd"] == -14.0
    assert rows[1]["output"]["evidence"]["median_sharpe"] == -0.1
    assert rows[1]["output"]["evidence"]["median_mdd"] == -31.0
    assert artifacts["summary"]["summary"]["total_samples"] == 2


def test_build_learning_file_payloads_returns_deployable_artifact_contents():
    samples = generate_advisor_smoke_samples(6)
    payload = {
        "results": [
            {
                "sample_id": samples[0]["sample_id"],
                "candidate_id": samples[0]["sample_id"],
                "strategy_id": "hash_momentum",
                "status": "computed",
                "metrics": {"cagr": 8.5, "sharpe": 0.7, "maxDrawdown": -14.0},
            }
        ],
    }

    files = build_advisor_learning_file_payloads(samples, payload)
    dataset_rows = [
        json.loads(line)
        for line in files["strategy_advisor_learning_dataset.jsonl"].splitlines()
    ]
    summary = json.loads(files["strategy_prompt_experiment_summary.json"])

    assert set(files) == {
        "strategy_advisor_learning_dataset.jsonl",
        "strategy_prompt_experiment_summary.json",
    }
    assert dataset_rows[0]["input"]["sample_id"] == samples[0]["sample_id"]
    assert summary["summary"]["total_samples"] == 1


def test_build_learning_artifacts_from_prompt_experiment_result_uses_candidate_metrics():
    result = {
        "experiment_id": "prompt_exp",
        "candidates": [
            {
                "id": "prompt_001",
                "prompt_id": "prompt_001",
                "prompt": "RSI 30 이하 손절 8%",
                "category": "technical_mean_reversion",
                "risk_profile": "moderate",
                "status": "computed",
                "extracted_blocks": ["rsi", "stop_loss"],
                "extracted_parameters": {"stop_loss_pct": 8},
                "parsed_strategy": {"entry_signals": [{"indicator": "rsi"}]},
                "metrics": {"cagr": 6.4, "sharpe": 0.6, "max_drawdown": -12.0},
            },
            {
                "id": "prompt_002",
                "prompt_id": "prompt_002",
                "prompt": "실패 후보",
                "category": "technical_mean_reversion",
                "risk_profile": "moderate",
                "status": "failed",
                "extracted_blocks": ["rsi"],
                "metrics": {"cagr": 99.0},
            },
        ],
    }

    artifacts = build_advisor_learning_artifacts_from_prompt_experiment_result(result)
    rows = artifacts["learning_dataset"]

    assert len(rows) == 1
    assert rows[0]["input"]["sample_id"] == "prompt_001"
    assert rows[0]["input"]["parsed_blocks"] == ["rsi", "stop_loss"]
    assert rows[0]["input"]["category"] == "technical_mean_reversion"
    assert rows[0]["output"]["evidence"]["median_cagr"] == 6.4
    assert rows[0]["output"]["evidence"]["median_mdd"] == -12.0
    assert artifacts["summary"]["summary"]["total_samples"] == 1
