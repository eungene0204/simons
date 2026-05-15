"""
Build advisor learning artifacts from designed samples and backtest results.

This module is intentionally pure: callers provide generated samples and result
rows, and receive JSON-serializable learning artifacts. It does not run
backtests and does not write files.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence


METRIC_KEYS = {
    "cagr": ("cagr", "median_cagr"),
    "sharpe": ("sharpe", "sharpe_ratio", "sharpeRatio", "median_sharpe"),
    "mdd": ("mdd", "maxDrawdown", "max_drawdown", "median_mdd"),
    "profit_factor": ("profit_factor", "profitFactor", "median_profit_factor"),
    "trade_count": ("trade_count", "tradeCount", "trades", "median_trades"),
}
SAMPLE_ID_PATTERN = re.compile(r"(advisor_smoke_\d{4,5}|advisor_pair_\d{4}_(?:baseline|stop_loss_pct|take_profit_pct|hold_period_days)|prompt_\d{3,})")


def _metric(payload: Dict[str, Any], name: str) -> Optional[float]:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else payload
    for key in METRIC_KEYS[name]:
        value = metrics.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _median(values: Sequence[Optional[float]]) -> Optional[float]:
    numeric = [value for value in values if isinstance(value, (int, float))]
    return float(median(numeric)) if numeric else None


def _confidence(sample_count: int) -> str:
    if sample_count >= 30:
        return "high"
    if sample_count >= 10:
        return "medium"
    return "low"


def _normalize_sample_id(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    match = SAMPLE_ID_PATTERN.search(text)
    return match.group(1) if match else text


def _quality_score(metrics: Dict[str, Optional[float]]) -> Optional[float]:
    cagr = metrics.get("median_cagr")
    sharpe = metrics.get("median_sharpe")
    mdd = metrics.get("median_mdd")
    if cagr is None and sharpe is None and mdd is None:
        return None

    cagr_component = (cagr or 0.0) / 100.0
    sharpe_component = (sharpe or 0.0) * 0.25
    mdd_component = (mdd or 0.0) / 100.0
    return round(cagr_component + sharpe_component + mdd_component, 4)


def _combo_key(blocks: Sequence[str]) -> str:
    return "+".join(sorted(str(block) for block in blocks if block))


def _recommended_guidance(combo: str, metrics: Dict[str, Optional[float]]) -> str:
    cagr = metrics.get("median_cagr")
    sharpe = metrics.get("median_sharpe")
    mdd = metrics.get("median_mdd")
    combo_text = combo.replace("+", " + ") or "해당 조건"

    if (mdd is not None and mdd <= -30) or (sharpe is not None and sharpe < 0):
        return f"{combo_text} 조합은 손실 또는 변동성 부담이 컸습니다. 손절, 보유기간, 종목 수 조건을 분리해 비교하세요."
    if cagr is not None and cagr > 0 and sharpe is not None and sharpe > 0:
        return f"{combo_text} 조합은 기본 성과가 확인됐습니다. 비용 반영 후에도 MDD가 유지되는지 검증하세요."
    return f"{combo_text} 조합은 성과 방향이 뚜렷하지 않습니다. 동일 조건 반복보다 리스크 조건별 비교를 우선하세요."


def _suggested_actions(sample: Dict[str, Any], metrics: Dict[str, Optional[float]]) -> List[str]:
    actions = ["MDD 확인", "Sharpe 확인"]
    strategy = sample.get("strategy_dsl") or {}
    if strategy.get("stop_loss_pct") is None and strategy.get("trailing_stop_pct") is None:
        actions.append("손절 조건 비교")
    if strategy.get("hold_period_days") is None:
        actions.append("보유기간 제한 비교")
    if metrics.get("median_mdd") is not None and metrics["median_mdd"] <= -30:
        actions.append("종목 수 분산 비교")
    return list(dict.fromkeys(actions))[:4]


def _learning_row(sample: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    metrics = {
        "median_cagr": _metric(result, "cagr"),
        "median_sharpe": _metric(result, "sharpe"),
        "median_mdd": _metric(result, "mdd"),
        "median_profit_factor": _metric(result, "profit_factor"),
        "median_trades": _metric(result, "trade_count"),
    }
    input_payload = {
        "sample_id": sample["sample_id"],
        "user_prompt": sample["hypothesis"],
        "parsed_blocks": sample["parsed_blocks"],
        "risk_profile": sample["parameter_bucket"],
        "category": sample["family"],
        "validation_purpose": sample["validation_purpose"],
        "extracted_parameters": {
            key: value
            for key, value in (sample.get("strategy_dsl") or {}).items()
            if key in {"stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "hold_period_days", "max_positions"}
            and value is not None
        },
    }
    paired_experiment = sample.get("paired_experiment")
    if isinstance(paired_experiment, dict):
        input_payload["paired_experiment"] = paired_experiment

    return {
        "input": {
            **input_payload,
        },
        "output": {
            "analysis": "백테스트 결과를 기반으로 전략 검증과 리스크 관리 관점에서 평가합니다.",
            "evidence": {
                "similar_strategy_count": 1,
                **metrics,
                "confidence": "low",
            },
            "recommended_advice": _recommended_guidance(_combo_key(sample["parsed_blocks"]), metrics),
            "suggested_actions": _suggested_actions(sample, metrics),
        },
    }


def build_advisor_learning_artifacts(
    samples: Sequence[Dict[str, Any]],
    results: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    result_by_sample = {
        str(result.get("sample_id")): result
        for result in results
        if result.get("sample_id")
    }
    rows = [
        _learning_row(sample, result_by_sample[sample["sample_id"]])
        for sample in samples
        if sample.get("sample_id") in result_by_sample
    ]
    _attach_pair_deltas(rows)

    grouped: dict[str, list[dict]] = defaultdict(list)
    single_grouped: dict[str, list[dict]] = defaultdict(list)
    paired_grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        blocks = row["input"]["parsed_blocks"]
        grouped[_combo_key(blocks)].append(row)
        for block in blocks:
            single_grouped[str(block)].append(row)
        paired_delta = row["output"].get("paired_delta")
        if isinstance(paired_delta, dict):
            paired_grouped[str(paired_delta.get("change_axis") or "unknown")].append(row)

    summary = {
        "experiment_id": "advisor_smoke_backtest_learning",
        "summary": {
            "total_samples": len(rows),
            "best_indicator_combinations": _summarize_groups(grouped),
            "best_single_indicators": _summarize_groups(single_grouped),
            "paired_deltas": _summarize_paired_deltas(paired_grouped),
        },
    }
    return {
        "learning_dataset": rows,
        "summary": summary,
    }


def normalize_batch_run_learning_results(batch_export: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert Next.js batch-run export payload into learning result rows."""
    rows: List[Dict[str, Any]] = []
    raw_results = batch_export.get("results") if isinstance(batch_export, dict) else None
    if not isinstance(raw_results, list):
        return rows

    for item in raw_results:
        if not isinstance(item, dict):
            continue
        if item.get("status") not in {"computed", "cache_hit"}:
            continue
        metrics = item.get("metrics")
        if not isinstance(metrics, dict):
            continue
        sample_id = _normalize_sample_id(
            item.get("sample_id") or item.get("candidate_id") or metrics.get("sample_id")
        )
        if not sample_id:
            continue
        rows.append({
            "sample_id": str(sample_id),
            "metrics": metrics,
            "candidate_id": item.get("candidate_id"),
            "strategy_id": item.get("strategy_id"),
        })
    return rows


def build_advisor_learning_artifacts_from_batch_export(
    samples: Sequence[Dict[str, Any]],
    batch_export: Dict[str, Any],
) -> Dict[str, Any]:
    return build_advisor_learning_artifacts(
        samples,
        normalize_batch_run_learning_results(batch_export),
    )


def build_advisor_learning_artifacts_from_prompt_experiment_result(
    experiment_result: Dict[str, Any],
) -> Dict[str, Any]:
    raw_candidates = experiment_result.get("candidates") if isinstance(experiment_result, dict) else None
    if not isinstance(raw_candidates, list):
        return build_advisor_learning_artifacts([], [])

    samples: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("status") not in {"computed", "cache_hit"}:
            continue
        metrics = candidate.get("metrics")
        if not isinstance(metrics, dict):
            continue

        sample_id = str(candidate.get("prompt_id") or candidate.get("id") or "")
        if not sample_id:
            continue
        parsed_blocks = candidate.get("extracted_blocks") or candidate.get("expected_blocks") or []
        parsed_strategy = (
            candidate.get("parsed_strategy")
            if isinstance(candidate.get("parsed_strategy"), dict)
            else {}
        )
        extracted_parameters = candidate.get("extracted_parameters")
        samples.append({
            "sample_id": sample_id,
            "hypothesis": str(candidate.get("prompt") or candidate.get("text") or ""),
            "parsed_blocks": [str(block) for block in parsed_blocks],
            "parameter_bucket": str(candidate.get("risk_profile") or candidate.get("complexity") or "unknown"),
            "family": str(candidate.get("category") or "unknown"),
            "validation_purpose": "기존 prompt experiment 결과를 advisor 조언 근거로 재구성",
            "strategy_dsl": {
                **parsed_strategy,
                **(extracted_parameters if isinstance(extracted_parameters, dict) else {}),
            },
        })
        results.append({
            "sample_id": sample_id,
            "metrics": metrics,
        })

    return build_advisor_learning_artifacts(samples, results)


def _delta(candidate: Dict[str, Any], baseline: Dict[str, Any], metric: str) -> Optional[float]:
    candidate_value = _metric(candidate, metric)
    baseline_value = _metric(baseline, metric)
    if candidate_value is None or baseline_value is None:
        return None
    return round(candidate_value - baseline_value, 4)


def _attach_pair_deltas(rows: Sequence[Dict[str, Any]]) -> None:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        pair = row.get("input", {}).get("paired_experiment")
        if isinstance(pair, dict) and pair.get("pair_id"):
            grouped[str(pair["pair_id"])].append(row)

    for pair_rows in grouped.values():
        baseline = next(
            (
                row
                for row in pair_rows
                if row.get("input", {}).get("paired_experiment", {}).get("role") == "baseline"
            ),
            None,
        )
        if not baseline:
            continue
        baseline_evidence = baseline["output"]["evidence"]
        for row in pair_rows:
            pair = row.get("input", {}).get("paired_experiment") or {}
            if pair.get("role") == "baseline":
                continue
            evidence = row["output"]["evidence"]
            cagr_delta = _delta(evidence, baseline_evidence, "cagr")
            sharpe_delta = _delta(evidence, baseline_evidence, "sharpe")
            mdd_delta = _delta(evidence, baseline_evidence, "mdd")
            profit_factor_delta = _delta(evidence, baseline_evidence, "profit_factor")
            trade_delta = _delta(evidence, baseline_evidence, "trade_count")
            row["output"]["paired_delta"] = {
                "pair_id": pair.get("pair_id"),
                "baseline_sample_id": baseline["input"]["sample_id"],
                "change_axis": pair.get("change_axis"),
                "changed_parameter": pair.get("changed_parameter"),
                "cagr_delta": cagr_delta,
                "sharpe_delta": sharpe_delta,
                "mdd_delta": mdd_delta,
                "profit_factor_delta": profit_factor_delta,
                "trade_delta": trade_delta,
                "improves_risk_adjusted": bool(
                    (sharpe_delta is not None and sharpe_delta > 0)
                    and (mdd_delta is None or mdd_delta >= 0)
                ),
            }


def build_advisor_learning_file_payloads(
    samples: Sequence[Dict[str, Any]],
    batch_export: Dict[str, Any],
) -> Dict[str, str]:
    artifacts = build_advisor_learning_artifacts_from_batch_export(samples, batch_export)
    return {
        "strategy_advisor_learning_dataset.jsonl": serialize_learning_dataset_jsonl(
            artifacts["learning_dataset"]
        ),
        "strategy_prompt_experiment_summary.json": json.dumps(
            artifacts["summary"],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
    }


def _summarize_groups(groups: Dict[str, Sequence[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for key, rows in sorted(groups.items()):
        metrics = {
            "median_cagr": _median([row["output"]["evidence"]["median_cagr"] for row in rows]),
            "median_sharpe": _median([row["output"]["evidence"]["median_sharpe"] for row in rows]),
            "median_mdd": _median([row["output"]["evidence"]["median_mdd"] for row in rows]),
            "median_profit_factor": _median([_metric(row["output"]["evidence"], "profit_factor") for row in rows]),
            "median_trades": _median([_metric(row["output"]["evidence"], "trade_count") for row in rows]),
        }
        sample_count = len(rows)
        output[key] = {
            "combination_count": sample_count,
            **metrics,
            "median_quality_score": _quality_score(metrics),
            "confidence": _confidence(sample_count),
            "recommended_guidance": _recommended_guidance(key, metrics),
            "warnings": [] if sample_count >= 10 else ["샘플 수가 적어 단정적으로 해석하면 안 됩니다."],
        }
    return output


def _summarize_paired_deltas(groups: Dict[str, Sequence[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for key, rows in sorted(groups.items()):
        deltas = [
            row["output"]["paired_delta"]
            for row in rows
            if isinstance(row.get("output", {}).get("paired_delta"), dict)
        ]
        output[key] = {
            "sample_count": len(deltas),
            "median_cagr_delta": _median([delta.get("cagr_delta") for delta in deltas]),
            "median_sharpe_delta": _median([delta.get("sharpe_delta") for delta in deltas]),
            "median_mdd_delta": _median([delta.get("mdd_delta") for delta in deltas]),
            "median_profit_factor_delta": _median([delta.get("profit_factor_delta") for delta in deltas]),
            "median_trade_delta": _median([delta.get("trade_delta") for delta in deltas]),
            "risk_adjusted_success_count": sum(1 for delta in deltas if delta.get("improves_risk_adjusted")),
        }
    return output


def serialize_learning_dataset_jsonl(rows: Iterable[Dict[str, Any]]) -> str:
    return "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in rows
    )
