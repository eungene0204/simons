"""전략 ID(canonical DSL 해시)가 신호 모양 칸을 담는지 고정한다.

배경(2026-11-06 발견): `_canonicalize_technical_signal`에 band·cross·side·price_basis·touch_lookback·
timeframe이 빠져, 이 칸만 다른 전략(볼린저 밴드 지정·신저가 돌파·종가 기준 돌파·주봉)이 같은 ID를 받았다.
저장 기록(BacktestHistory·BacktestResult)이 이 ID로 업서트되므로 서로의 기록을 덮어썼다.
"""

from __future__ import annotations

import pytest

from engine.nl_parser import ParsedStrategy, TechnicalSignal
from engine.strategy_converter import compute_strategy_id, to_canonical_strategy_dsl


def _strategy(**signal) -> ParsedStrategy:
    return ParsedStrategy(universe=["KOSPI"], entry_signals=[TechnicalSignal(signal_type="buy", **signal)])


@pytest.mark.parametrize("base, field, value", [
    (dict(indicator="bollinger_bands", period=20), "band", "lower"),
    (dict(indicator="bollinger_bands", period=20, band="lower"), "cross", "below"),
    (dict(indicator="breakout", period=52), "side", "low"),
    (dict(indicator="breakout", period=52), "price_basis", "close"),
    (dict(indicator="bollinger_bands", period=20, band="lower"), "touch_lookback", 5),
    (dict(indicator="rsi", period=14, operator="<=", value=30), "timeframe", "weekly"),
])
def test_signal_shape_field_changes_strategy_id(base, field, value):
    assert compute_strategy_id(_strategy(**base)) != compute_strategy_id(_strategy(**base, **{field: value}))


def test_unset_shape_fields_leave_existing_hash_unchanged():
    """칸을 쓰지 않는 전략은 키 자체가 없어야 한다 — 기존 전략 ID가 바뀌지 않는다."""
    sig = to_canonical_strategy_dsl(_strategy(indicator="rsi", period=14, operator="<=", value=30))["entry_signals"][0]
    assert not {"band", "cross", "side", "price_basis", "touch_lookback", "timeframe"} & sig.keys()
