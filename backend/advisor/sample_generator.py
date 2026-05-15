"""
Deterministic smoke sample generator for advisor learning backtests.

The generator creates executable strategy DSL payloads only. It does not run
backtests or persist generated rows.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from .experiment_learning import extract_strategy_blocks


UNIVERSES = ("KOSPI200",)
BACKTEST_PERIODS = ("1y", "3y", "5y")
INITIAL_CAPITALS = (5_000_000, 10_000_000, 30_000_000)
MAX_POSITIONS = (3, 5, 10, 20)
STOP_LOSSES = (None, 5, 8, 12)
TAKE_PROFITS = (None, 10, 15, 25)
HOLD_DAYS = (None, 10, 20, 60)
REBALANCING = ("none", "monthly", "quarterly", "yearly")


@dataclass(frozen=True)
class StrategyFamilyPlan:
    family: str
    hypothesis: str
    validation_purpose: str
    buckets: tuple[str, ...]


FAMILY_PLANS: tuple[StrategyFamilyPlan, ...] = (
    StrategyFamilyPlan(
        family="momentum",
        hypothesis="추세 추종 신호가 상승 구간에서는 수익을 만들지만 횡보장에서는 손실이 커질 수 있다.",
        validation_purpose="추세 신호와 청산 조건의 손실 제어 효과 비교",
        buckets=("ma_cross_adx", "macd_trend", "breakout_volume", "ema_trend"),
    ),
    StrategyFamilyPlan(
        family="mean_reversion",
        hypothesis="과매도 진입은 반등장에서 유효하지만 강한 하락 추세에서는 손실이 누적될 수 있다.",
        validation_purpose="평균회귀 진입과 추세 필터/보유기간 제한의 민감도 비교",
        buckets=("rsi_reversal", "bollinger_reversal", "stochastic_reversal", "cci_reversal"),
    ),
    StrategyFamilyPlan(
        family="value",
        hypothesis="저평가 필터는 장기 성과에 기여할 수 있지만 단기 모멘텀이 없으면 회전율과 기회비용이 커질 수 있다.",
        validation_purpose="밸류 필터와 기술적 진입 조건 결합 효과 비교",
        buckets=("pbr_per", "pbr_roe", "per_dividend", "value_momentum"),
    ),
    StrategyFamilyPlan(
        family="quality",
        hypothesis="수익성/성장성 필터는 부실 종목을 줄이지만 밸류에이션 부담을 함께 확인해야 한다.",
        validation_purpose="품질 필터와 가격/거래대금 필터의 안정성 비교",
        buckets=("roe_margin", "growth_quality", "debt_quality", "quality_value"),
    ),
    StrategyFamilyPlan(
        family="liquidity",
        hypothesis="거래대금과 시가총액 필터는 체결 가능성을 높이지만 초과수익을 희석할 수 있다.",
        validation_purpose="유동성 필터 강도와 종목 수 분산 효과 비교",
        buckets=("trading_value", "market_cap", "volume_liquidity", "liquidity_momentum"),
    ),
    StrategyFamilyPlan(
        family="volatility_breakout",
        hypothesis="변동성 돌파는 강한 추세에서 유리하지만 손절과 보유기간 제한 없이는 MDD가 커질 수 있다.",
        validation_purpose="돌파 진입과 리스크 제한 조건의 MDD 완화 효과 비교",
        buckets=("breakout_stop", "breakout_trailing", "breakout_hold", "breakout_volume"),
    ),
)


def _choice(values: tuple[Any, ...], index: int) -> Any:
    return values[index % len(values)]


def _filter(metric: str, operator: str, value: Any) -> Dict[str, Any]:
    return {"metric": metric, "operator": operator, "value": value}


def _signal(indicator: str, **params: Any) -> Dict[str, Any]:
    return {"indicator": indicator, **{key: value for key, value in params.items() if value is not None}}


def _family_conditions(family: str, bucket: str, index: int) -> tuple[list[dict], list[dict], list[dict]]:
    filters: list[dict] = []
    entries: list[dict] = []
    exits: list[dict] = []

    if family == "momentum":
        if bucket == "ma_cross_adx":
            entries = [_signal("ma_crossover", short_period=_choice((5, 10, 20), index), long_period=_choice((20, 60, 120), index)), _signal("adx", operator=">=", value=_choice((20, 25, 30), index))]
        elif bucket == "macd_trend":
            entries = [_signal("macd"), _signal("volume_spike", threshold=_choice((120, 150, 200), index))]
            exits = [_signal("macd")]
        elif bucket == "breakout_volume":
            entries = [_signal("breakout", lookback_period=252), _signal("volume_spike", threshold=_choice((150, 200, 300), index))]
        else:
            entries = [_signal("ema", short_period=_choice((10, 20), index), long_period=_choice((60, 120), index))]

    elif family == "mean_reversion":
        if bucket == "rsi_reversal":
            entries = [_signal("rsi", operator="<=", value=_choice((25, 30, 35), index), period=14)]
            exits = [_signal("rsi", operator=">=", value=_choice((60, 70), index), period=14)]
        elif bucket == "bollinger_reversal":
            entries = [_signal("bollinger_bands", period=_choice((20, 40), index))]
            exits = [_signal("bollinger_bands", period=_choice((20, 40), index))]
        elif bucket == "stochastic_reversal":
            entries = [_signal("stochastic", operator="<=", value=_choice((15, 20), index))]
        else:
            entries = [_signal("cci", operator="<=", value=_choice((-150, -100), index))]

    elif family == "value":
        if bucket == "pbr_per":
            filters = [_filter("pbr", "<=", _choice((0.7, 1.0, 1.3), index)), _filter("per", "<=", _choice((8, 12, 16), index))]
        elif bucket == "pbr_roe":
            filters = [_filter("pbr", "<=", _choice((1.0, 1.5), index)), _filter("roe_or_gpa", ">=", _choice((8, 12, 16), index))]
        elif bucket == "per_dividend":
            filters = [_filter("per", "<=", _choice((10, 15), index)), _filter("trading_value", ">=", _choice((5_000_000_000, 10_000_000_000), index))]
        else:
            filters = [_filter("pbr", "<=", 1.2)]
            entries = [_signal("ma_crossover", short_period=20, long_period=60)]

    elif family == "quality":
        if bucket == "roe_margin":
            filters = [_filter("roe_or_gpa", ">=", _choice((10, 15, 20), index)), _filter("trading_value", ">=", _choice((5_000_000_000, 10_000_000_000), index))]
        elif bucket == "growth_quality":
            filters = [_filter("roe_or_gpa", ">=", _choice((8, 12, 16), index)), _filter("market_cap", ">=", _choice((300_000_000_000, 1_000_000_000_000), index))]
        elif bucket == "debt_quality":
            filters = [_filter("debt_ratio", "<=", _choice((50, 100, 150), index)), _filter("roe_or_gpa", ">=", 10)]
        else:
            filters = [_filter("roe_or_gpa", ">=", 12), _filter("pbr", "<=", _choice((1.5, 2.0), index))]

    elif family == "liquidity":
        if bucket == "trading_value":
            filters = [_filter("trading_value", ">=", _choice((5_000_000_000, 10_000_000_000, 30_000_000_000), index))]
        elif bucket == "market_cap":
            filters = [_filter("market_cap", ">=", _choice((300_000_000_000, 1_000_000_000_000), index))]
        elif bucket == "volume_liquidity":
            entries = [_signal("volume_spike", threshold=_choice((120, 150, 200), index))]
        else:
            filters = [_filter("trading_value", ">=", 10_000_000_000)]
            entries = [_signal("ma_crossover", short_period=10, long_period=60)]

    else:
        if bucket == "breakout_stop":
            entries = [_signal("breakout", lookback_period=_choice((20, 60), index))]
        elif bucket == "breakout_trailing":
            entries = [_signal("breakout", lookback_period=252)]
        elif bucket == "breakout_hold":
            entries = [_signal("breakout", lookback_period=_choice((20, 120), index))]
        else:
            entries = [_signal("breakout", lookback_period=252), _signal("volume_spike", threshold=_choice((150, 250), index))]

    return filters, entries, exits


def _build_strategy_dsl(plan: StrategyFamilyPlan, index: int) -> Dict[str, Any]:
    bucket = _choice(plan.buckets, index)
    filters, entries, exits = _family_conditions(plan.family, bucket, index)

    return {
        "description": f"{plan.family} smoke sample {index + 1}",
        "universe": [_choice(UNIVERSES, index)],
        "fundamental_filters": filters,
        "entry_signals": entries,
        "exit_signals": exits,
        "max_positions": _choice(MAX_POSITIONS, index),
        "stop_loss_pct": _choice(STOP_LOSSES, index),
        "take_profit_pct": _choice(TAKE_PROFITS, index + 1),
        "trailing_stop_pct": 10 if plan.family == "volatility_breakout" and index % 4 == 1 else None,
        "hold_period_days": _choice(HOLD_DAYS, index + 2),
        "rebalancing_period": _choice(REBALANCING, index),
        "backtest_period": _choice(BACKTEST_PERIODS, index),
        "initial_capital": _choice(INITIAL_CAPITALS, index),
        "fee_rate": 0.00015,
        "slippage_rate": 0.0002,
    }


def generate_advisor_smoke_samples(count: int = 300) -> List[Dict[str, Any]]:
    if count < len(FAMILY_PLANS):
        raise ValueError(f"count must be at least {len(FAMILY_PLANS)}")

    samples: list[dict] = []
    for sample_index in range(count):
        plan = FAMILY_PLANS[sample_index % len(FAMILY_PLANS)]
        family_index = sample_index // len(FAMILY_PLANS)
        strategy_dsl = _build_strategy_dsl(plan, family_index)
        bucket = _choice(plan.buckets, family_index)
        parsed_blocks = extract_strategy_blocks(strategy_dsl)
        samples.append({
            "sample_id": f"advisor_smoke_{sample_index + 1:04d}",
            "family": plan.family,
            "hypothesis": plan.hypothesis,
            "parameter_bucket": bucket,
            "validation_purpose": plan.validation_purpose,
            "parsed_blocks": parsed_blocks,
            "strategy_dsl": strategy_dsl,
            "backtest_settings": {
                "period": strategy_dsl["backtest_period"],
                "universe": strategy_dsl["universe"],
                "initial_capital": strategy_dsl["initial_capital"],
                "fee_rate": strategy_dsl["fee_rate"],
                "slippage_rate": strategy_dsl["slippage_rate"],
            },
        })

    return samples


def _paired_sample(
    *,
    sample_id: str,
    plan: StrategyFamilyPlan,
    bucket: str,
    strategy_dsl: Dict[str, Any],
    pair_id: str,
    role: str,
    change_axis: str,
    changed_parameter: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    parsed_blocks = extract_strategy_blocks(strategy_dsl)
    return {
        "sample_id": sample_id,
        "family": plan.family,
        "hypothesis": plan.hypothesis,
        "parameter_bucket": bucket,
        "validation_purpose": f"{plan.validation_purpose}: {change_axis} 단일 변경 비교",
        "parsed_blocks": parsed_blocks,
        "strategy_dsl": strategy_dsl,
        "paired_experiment": {
            "pair_id": pair_id,
            "role": role,
            "change_axis": change_axis,
            "changed_parameter": changed_parameter or {},
        },
        "backtest_settings": {
            "period": strategy_dsl["backtest_period"],
            "universe": strategy_dsl["universe"],
            "initial_capital": strategy_dsl["initial_capital"],
            "fee_rate": strategy_dsl["fee_rate"],
            "slippage_rate": strategy_dsl["slippage_rate"],
        },
    }


def generate_advisor_paired_smoke_samples(pair_count: int = 30) -> List[Dict[str, Any]]:
    if pair_count < len(FAMILY_PLANS):
        raise ValueError(f"pair_count must be at least {len(FAMILY_PLANS)}")

    samples: list[dict] = []
    variants = (
        ("stop_loss_pct", 8, "stop_loss"),
        ("take_profit_pct", 15, "take_profit"),
        ("hold_period_days", 20, "max_holding_days"),
    )
    for pair_index in range(pair_count):
        plan = FAMILY_PLANS[pair_index % len(FAMILY_PLANS)]
        family_index = pair_index // len(FAMILY_PLANS)
        bucket = _choice(plan.buckets, family_index)
        baseline = _build_strategy_dsl(plan, family_index)
        baseline["stop_loss_pct"] = None
        baseline["take_profit_pct"] = None
        baseline["trailing_stop_pct"] = None
        baseline["hold_period_days"] = None
        pair_id = f"advisor_pair_{pair_index + 1:04d}"

        samples.append(_paired_sample(
            sample_id=f"{pair_id}_baseline",
            plan=plan,
            bucket=bucket,
            strategy_dsl=baseline,
            pair_id=pair_id,
            role="baseline",
            change_axis="baseline",
        ))
        for field, value, change_axis in variants:
            candidate = deepcopy(baseline)
            candidate[field] = value
            samples.append(_paired_sample(
                sample_id=f"{pair_id}_{field}",
                plan=plan,
                bucket=bucket,
                strategy_dsl=candidate,
                pair_id=pair_id,
                role="candidate",
                change_axis=change_axis,
                changed_parameter={field: value},
            ))

    return samples


def _sample_to_parsed_strategy(sample: Dict[str, Any]):
    from engine.nl_parser import FundamentalFilter, ParsedStrategy, TechnicalSignal

    strategy = sample.get("strategy_dsl") or {}
    return ParsedStrategy(
        description=str(strategy.get("description") or sample.get("hypothesis") or sample.get("sample_id")),
        universe=list(strategy.get("universe") or ["KOSPI200"]),
        fundamental_filters=[
            FundamentalFilter(
                metric=item["metric"],
                operator=item["operator"],
                value=item["value"],
            )
            for item in strategy.get("fundamental_filters") or []
        ],
        entry_signals=[
            TechnicalSignal(signal_type="buy", **item)
            for item in strategy.get("entry_signals") or []
        ],
        exit_signals=[
            TechnicalSignal(signal_type="sell", **item)
            for item in strategy.get("exit_signals") or []
        ],
        max_positions=strategy.get("max_positions") or 10,
        hold_period_days=strategy.get("hold_period_days"),
        rebalancing_period=strategy.get("rebalancing_period") or "none",
        stop_loss_pct=strategy.get("stop_loss_pct"),
        take_profit_pct=strategy.get("take_profit_pct"),
        trailing_stop_pct=strategy.get("trailing_stop_pct"),
        backtest_period=strategy.get("backtest_period") or "5y",
        initial_capital=strategy.get("initial_capital") or 10_000_000,
        fee_rate=strategy.get("fee_rate") if strategy.get("fee_rate") is not None else 0.015,
        slippage_rate=strategy.get("slippage_rate") if strategy.get("slippage_rate") is not None else 0.05,
    )


def build_advisor_batch_run_candidates(
    samples: Iterable[Dict[str, Any]],
    *,
    resolve_symbols: bool = True,
    candidate_id_prefix: str = "",
) -> List[Dict[str, Any]]:
    from engine.strategy_converter import to_backtest_request

    candidates: List[Dict[str, Any]] = []
    for sample in samples:
        parsed = _sample_to_parsed_strategy(sample)
        candidate_id = sample["sample_id"]
        if candidate_id_prefix:
            candidate_id = f"{candidate_id_prefix}__{candidate_id}"
        candidates.append({
            "id": candidate_id,
            "prompt": sample["hypothesis"],
            "strategyName": f"{sample['family']} / {sample['parameter_bucket']}",
            "backtestRequest": to_backtest_request(parsed, resolve_symbols=resolve_symbols),
        })
    return candidates


def build_advisor_batch_run_payload(
    samples: Iterable[Dict[str, Any]],
    *,
    run_id: str = "advisor_smoke_300",
    concurrency: int = 2,
    resolve_symbols: bool = True,
) -> Dict[str, Any]:
    return {
        "action": "run_backtest_requests",
        "runId": run_id,
        "concurrency": concurrency,
        "candidates": build_advisor_batch_run_candidates(
            samples,
            resolve_symbols=resolve_symbols,
            candidate_id_prefix=run_id,
        ),
    }


def serialize_advisor_smoke_samples_jsonl(samples: Iterable[Dict[str, Any]]) -> str:
    return "\n".join(
        json.dumps(sample, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for sample in samples
    )
