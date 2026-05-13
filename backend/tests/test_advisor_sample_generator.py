import json
import os
import sys
from collections import Counter

sys.path.append(os.path.join(os.getcwd(), "backend"))

from advisor.sample_generator import (
    FAMILY_PLANS,
    build_advisor_batch_run_payload,
    generate_advisor_smoke_samples,
    serialize_advisor_smoke_samples_jsonl,
)


def test_generate_advisor_smoke_samples_returns_balanced_300_samples():
    samples = generate_advisor_smoke_samples()

    assert len(samples) == 300
    assert len({sample["sample_id"] for sample in samples}) == 300
    assert Counter(sample["family"] for sample in samples) == {
        plan.family: 50
        for plan in FAMILY_PLANS
    }


def test_generated_samples_include_required_learning_and_backtest_fields():
    sample = generate_advisor_smoke_samples(6)[0]

    assert sample["sample_id"].startswith("advisor_smoke_")
    assert sample["family"]
    assert sample["hypothesis"]
    assert sample["parameter_bucket"]
    assert sample["validation_purpose"]
    assert sample["parsed_blocks"]

    strategy = sample["strategy_dsl"]
    assert strategy["universe"] == ["KOSPI200"]
    assert strategy["entry_signals"] or strategy["fundamental_filters"]
    assert strategy["max_positions"] in {3, 5, 10, 20}
    assert strategy["fee_rate"] > 0
    assert strategy["slippage_rate"] > 0

    settings = sample["backtest_settings"]
    assert settings["period"] == strategy["backtest_period"]
    assert settings["universe"] == strategy["universe"]
    assert settings["initial_capital"] == strategy["initial_capital"]


def test_generated_samples_cover_risk_controls_and_parameter_buckets():
    samples = generate_advisor_smoke_samples()
    buckets = {sample["parameter_bucket"] for sample in samples}

    assert "ma_cross_adx" in buckets
    assert "rsi_reversal" in buckets
    assert "pbr_per" in buckets
    assert any(sample["strategy_dsl"]["stop_loss_pct"] is not None for sample in samples)
    assert any(sample["strategy_dsl"]["take_profit_pct"] is not None for sample in samples)
    assert any(sample["strategy_dsl"]["hold_period_days"] is not None for sample in samples)
    assert any(sample["strategy_dsl"]["trailing_stop_pct"] is not None for sample in samples)


def test_serialize_advisor_smoke_samples_jsonl_round_trips():
    samples = generate_advisor_smoke_samples(6)
    payload = serialize_advisor_smoke_samples_jsonl(samples)
    rows = [json.loads(line) for line in payload.splitlines()]

    assert rows == samples
    assert len(rows) == 6


def test_generated_samples_convert_to_batch_run_payload_without_symbol_resolution():
    samples = generate_advisor_smoke_samples()
    payload = build_advisor_batch_run_payload(
        samples,
        run_id="advisor_smoke_test",
        concurrency=1,
        resolve_symbols=False,
    )

    assert payload["action"] == "run_backtest_requests"
    assert payload["runId"] == "advisor_smoke_test"
    assert len(payload["candidates"]) == 300
    assert all(candidate["id"].startswith("advisor_smoke_test__advisor_smoke_") for candidate in payload["candidates"])
    assert all(candidate["backtestRequest"]["strategy_id"] for candidate in payload["candidates"])
    assert all(candidate["backtestRequest"]["symbols"] == [] for candidate in payload["candidates"])
    assert all(candidate["backtestRequest"]["symbols_resolved"] is False for candidate in payload["candidates"])
    assert all(candidate["backtestRequest"]["entry"]["conditions"] for candidate in payload["candidates"])


def test_generated_batch_run_payload_uses_bounded_kospi200_universe():
    payload = build_advisor_batch_run_payload(
        generate_advisor_smoke_samples(12),
        run_id="advisor_smoke_test",
        concurrency=1,
        resolve_symbols=True,
    )

    symbol_counts = [
        len(candidate["backtestRequest"]["symbols"])
        for candidate in payload["candidates"]
    ]
    assert min(symbol_counts) >= 150
    assert max(symbol_counts) <= 250
    assert {candidate["backtestRequest"]["universe_id"] for candidate in payload["candidates"]} == {"kospi200"}
