"""An N-day close-to-close fall is executable from OHLCV parquet data (engine v16.42)."""

import polars as pl

from engine import trade_reason
from engine.nl_parser import TechnicalSignal
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition


def _condition(period: int = 3, cid: str = "consecutive_down") -> dict:
    return {"type": "indicator", "id": cid, "params": {"period": period, "signalType": "buy"}}


def test_three_consecutive_falls_use_only_closes_through_current_day():
    df = pl.DataFrame({"close": [110, 109, 108, 107, 107, 106, 105, 104, None, 103, 102, 101, 100]})
    engine = SignalEngine()
    condition = _condition()
    signals, reasons = engine.generate_signals(df, {"conditions": [condition]})

    # 3연속 하락이 완성되는 날: idx 3(109→108→107), idx 7(106→105→104), idx 12(103→102→101→100은 결측 직후라 idx 11부터)
    assert signals.tolist() == [False, False, False, True, False, False, False, True,
                                False, False, False, False, True]
    assert [engine.evaluate_condition(condition, i, df) for i in range(len(df))] == signals.tolist()
    assert trade_reason.text(reasons[3]) == "종가 3거래일 연속 하락"


def test_rising_closes_never_trigger_consecutive_down_and_vice_versa():
    rising = pl.DataFrame({"close": [100, 101, 102, 103, 104, 105]})
    falling = pl.DataFrame({"close": [105, 104, 103, 102, 101, 100]})
    engine = SignalEngine()
    assert not engine.generate_signals(rising, {"conditions": [_condition()]})[0].any()
    assert not engine.generate_signals(falling, {"conditions": [_condition(cid="consecutive_up")]})[0].any()


def test_parsed_signal_preserves_fall_count_in_backtest_condition():
    signal = TechnicalSignal(indicator="consecutive_down", signal_type="buy", period=3)
    condition = _tech_signal_to_condition(signal)
    assert condition["id"] == "consecutive_down"
    assert condition["params"]["period"] == 3


def test_consecutive_down_is_exposed_to_the_interpreter_vocabulary():
    """레지스트리에만 있고 온톨로지 시드(분류·방향성)에 없으면 프롬프트 어휘에 오르지 않아
    LLM이 '연속 하락'을 연속 상승으로 뒤집는다(2026-10-23 실측)."""
    from strategy_conversation.interpreter.prompts import build_system_prompt

    assert "technical.consecutive_down" in build_system_prompt()
