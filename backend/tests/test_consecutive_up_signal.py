"""An N-day close-to-close rise is executable from OHLCV parquet data."""

from datetime import date

import polars as pl

from engine.signals import SignalEngine
from engine import trade_reason
from engine.nl_parser import TechnicalSignal
from engine.strategy_converter import _tech_signal_to_condition


def _condition(period: int = 5) -> dict:
    return {"type": "indicator", "id": "consecutive_up",
            "params": {"period": period, "signalType": "buy"}}


def test_five_consecutive_rises_use_only_closes_through_current_day():
    df = pl.DataFrame({"close": [100, 101, 102, 103, 104, 105, 105, 106,
                                 None, 107, 108, 109, 110, 111, 112]})
    engine = SignalEngine()
    condition = _condition()
    signals, reasons = engine.generate_signals(df, {"conditions": [condition]})

    assert signals.tolist() == [False] * 5 + [True] + [False] * 8 + [True]
    assert [engine.evaluate_condition(condition, i, df) for i in range(len(df))] == signals.tolist()
    assert trade_reason.text(reasons[5]) == "종가 5거래일 연속 상승"


def test_five_consecutive_rises_can_be_derived_from_parquet(tmp_path):
    path = tmp_path / "rising_closes.parquet"
    pl.DataFrame({
        "date": pl.date_range(date(2026, 1, 1), date(2026, 1, 12), eager=True),
        "close": [100, 101, 102, 103, 104, 105, 104, 105, 106, 107, 108, 109],
    }).write_parquet(path)
    df = pl.read_parquet(path, columns=["date", "close"])
    closes = df["close"].to_list()
    expected = [i >= 5 and all(closes[j] > closes[j - 1]
                               for j in range(i - 4, i + 1))
                for i in range(len(closes))]

    actual, _ = SignalEngine().generate_signals(df, {"conditions": [_condition()]})
    assert actual.tolist() == expected
    assert any(expected)


def test_parsed_signal_preserves_rise_count_in_backtest_condition():
    signal = TechnicalSignal(indicator="consecutive_up", signal_type="buy", period=5)
    condition = _tech_signal_to_condition(signal)
    assert condition["id"] == "consecutive_up"
    assert condition["params"]["period"] == 5
