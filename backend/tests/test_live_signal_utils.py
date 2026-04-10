import numpy as np
import polars as pl

from engine.live_signal_utils import apply_realtime_quote, prepare_signal_dataframe


class DummyAIEngine:
    def predict_signals(self, df):
        n = len(df)
        up = np.zeros(n)
        down = np.zeros(n)
        up[-1] = 0.91
        down[-1] = 0.12
        return up, down


def test_apply_realtime_quote_appends_intraday_bar_for_new_date():
    df = pl.DataFrame({
        "date": ["2026-04-06"],
        "open": [100.0],
        "high": [110.0],
        "low": [95.0],
        "close": [105.0],
        "volume": [1000.0],
    })

    updated = apply_realtime_quote(df, {
        "date": "2026-04-07",
        "open": 106.0,
        "high": 112.0,
        "low": 101.0,
        "close": 111.0,
        "volume": 1500.0,
    })

    assert len(updated) == 2
    last = updated.tail(1).to_dicts()[0]
    assert str(last["date"])[:10] == "2026-04-07"
    assert last["close"] == 111.0
    assert last["volume"] == 1500.0


def test_apply_realtime_quote_injects_fundamentals():
    """실시간 quote의 PER/PBR/EPS/BPS가 DataFrame에 반영되는지 확인"""
    df = pl.DataFrame({
        "date": ["2026-04-06"],
        "open": [100.0],
        "high": [110.0],
        "low": [95.0],
        "close": [105.0],
        "volume": [1000.0],
    })

    updated = apply_realtime_quote(df, {
        "date": "2026-04-07",
        "open": 106.0,
        "high": 112.0,
        "low": 101.0,
        "close": 111.0,
        "volume": 1500.0,
        "per": 12.5,
        "pbr": 1.3,
        "eps": 4440.0,
        "bps": 42692.0,
    })

    assert len(updated) == 2
    last = updated.tail(1).to_dicts()[0]
    assert last["per"] == 12.5
    assert last["pbr"] == 1.3
    assert last["eps"] == 4440.0
    assert last["bps"] == 42692.0


def test_apply_realtime_quote_no_fundamentals_no_columns():
    """quote에 PER/PBR이 없으면 컬럼이 추가되지 않음"""
    df = pl.DataFrame({
        "date": ["2026-04-06"],
        "open": [100.0],
        "high": [110.0],
        "low": [95.0],
        "close": [105.0],
        "volume": [1000.0],
    })

    updated = apply_realtime_quote(df, {
        "date": "2026-04-07",
        "open": 106.0,
        "high": 112.0,
        "low": 101.0,
        "close": 111.0,
        "volume": 1500.0,
    })

    assert "per" not in updated.columns
    assert "pbr" not in updated.columns


def test_prepare_signal_dataframe_injects_live_ai_scores():
    df = pl.DataFrame({
        "date": [f"2026-02-{i:02d}" for i in range(1, 63)],
        "open": [100.0 + i for i in range(62)],
        "high": [101.0 + i for i in range(62)],
        "low": [99.0 + i for i in range(62)],
        "close": [100.0 + i for i in range(62)],
        "volume": [1000.0 + i for i in range(62)],
    })

    prepared = prepare_signal_dataframe(
        df,
        {
            "date": "2026-04-07",
            "open": 200.0,
            "high": 205.0,
            "low": 198.0,
            "close": 204.0,
            "volume": 5000.0,
        },
        [{"id": "ai_model", "params": {"threshold": 70}}],
        [{"id": "ai_drop_model", "params": {"threshold": 70, "targetType": "down"}}],
        DummyAIEngine(),
    )

    last = prepared.tail(1).to_dicts()[0]
    assert str(last["date"])[:10] == "2026-04-07"
    assert last["close"] == 204.0
    assert last["ai_score"] == 0.91
    assert last["ai_drop_score"] == 0.12
