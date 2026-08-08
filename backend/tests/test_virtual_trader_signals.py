from types import SimpleNamespace

import polars as pl
import pytest

import engine.virtual_trader as virtual_trader_module
from engine.live_signal_utils import (
    count_holding_sessions,
    evaluate_live_strategy_signals,
    resolve_live_universe,
)
from engine.virtual_trader import VirtualTrader, _is_strategy_execution_window


class StubLoader:
    def __init__(self, frames):
        self.frames = frames

    def load_symbol_data(self, symbol):
        return self.frames.get(symbol)


def _frame(closes):
    return pl.DataFrame({
        "date": pl.date_range(
            pl.date(2025, 1, 1),
            pl.date(2025, 1, 1) + pl.duration(days=len(closes) - 1),
            eager=True,
        ),
        "open": closes,
        "high": closes,
        "low": closes,
        "close": closes,
        "volume": [1000] * len(closes),
    })


def test_live_signal_preserves_and_group_logic():
    loader = StubLoader({"A": _frame([100, 110, 120])})
    entry = {
        "logic": "AND",
        "conditions": [
            {"id": "price", "params": {"operator": ">", "value": 105}},
            {"id": "price", "params": {"operator": "<", "value": 105}},
        ],
    }

    signals = evaluate_live_strategy_signals(
        loader, ["A"], {}, entry, {}, {"execution_timing": "current_close"}
    )

    assert signals[0]["entry_signal"] is False


def test_return_ranking_uses_previous_close_for_next_open():
    loader = StubLoader({
        "A": _frame([100, 100, 110]),
        "B": _frame([100, 120, 90]),
    })
    risk = {
        "execution_timing": "next_open",
        "ranking_metric": "return",
        "ranking_lookback_days": 1,
        "max_positions": 1,
    }

    signals = evaluate_live_strategy_signals(loader, ["A", "B"], {}, {}, {}, risk)

    assert signals[0]["symbol"] == "B"
    assert signals[0]["entry_signal"] is True
    assert signals[1]["entry_signal"] is False


def test_return_ranking_supports_126_trading_day_lookback():
    flat = [100.0] * 126
    loader = StubLoader({
        "A": _frame(flat + [110.0, 110.0]),
        "B": _frame(flat + [105.0, 105.0]),
    })
    risk = {
        "execution_timing": "next_open",
        "ranking_metric": "return",
        "ranking_lookback_days": 126,
        "max_positions": 1,
    }

    signals = evaluate_live_strategy_signals(loader, ["A", "B"], {}, {}, {}, risk)

    assert signals[0]["symbol"] == "A"
    assert signals[0]["entry_signal"] is True
    assert "126거래일" in signals[0]["entry_reason"]


def test_return_ranking_excludes_symbols_without_full_history():
    loader = StubLoader({
        "A": _frame([100.0] * 128),
        "B": _frame([100.0] * 20),
    })
    risk = {
        "execution_timing": "next_open",
        "ranking_metric": "return",
        "ranking_lookback_days": 126,
        "max_positions": 2,
    }

    signals = evaluate_live_strategy_signals(loader, ["A", "B"], {}, {}, {}, risk)

    by_symbol = {signal["symbol"]: signal for signal in signals}
    assert by_symbol["A"]["entry_signal"] is True
    assert by_symbol["B"]["entry_signal"] is False


def test_zero_return_ranks_above_negative_return():
    loader = StubLoader({
        "FLAT": _frame([100.0, 100.0, 100.0]),
        "DOWN": _frame([100.0, 90.0, 90.0]),
    })
    risk = {
        "execution_timing": "next_open",
        "ranking_metric": "return",
        "ranking_lookback_days": 1,
        "max_positions": 1,
    }

    signals = evaluate_live_strategy_signals(
        loader, ["FLAT", "DOWN"], {}, {}, {}, risk
    )

    assert signals[0]["symbol"] == "FLAT"
    assert signals[0]["entry_signal"] is True


def test_monthly_ranking_only_selects_on_first_session():
    loader = StubLoader({"A": _frame([100.0] * 40)})
    risk = {
        "execution_timing": "next_open",
        "ranking_metric": "return",
        "ranking_lookback_days": 5,
        "max_positions": 1,
        "rebalancing_period": "monthly",
    }

    signals = evaluate_live_strategy_signals(loader, ["A"], {}, {}, {}, risk)

    assert signals[0]["rebalance_due"] is False
    assert signals[0]["entry_signal"] is False


def test_daily_ranking_selects_target_every_session():
    loader = StubLoader({"A": _frame([100.0] * 10)})
    risk = {
        "execution_timing": "next_open",
        "ranking_metric": "return",
        "ranking_lookback_days": 5,
        "max_positions": 1,
        "rebalancing_period": "daily",
    }

    signals = evaluate_live_strategy_signals(loader, ["A"], {}, {}, {}, risk)

    assert signals[0]["rebalance_due"] is True
    assert signals[0]["entry_signal"] is True


def test_next_open_execution_date_uses_latest_completed_bar():
    loader = StubLoader({
        "A": _frame([100.0, 110.0]),
        "B": _frame([100.0, 105.0]),
    })
    risk = {
        "execution_timing": "next_open",
        "ranking_metric": "return",
        "ranking_lookback_days": 1,
        "max_positions": 1,
    }

    signals = evaluate_live_strategy_signals(
        loader, ["A", "B"], {}, {}, {}, risk, execution_date="2025-01-03"
    )

    assert signals[0]["symbol"] == "A"
    assert signals[0]["entry_signal"] is True


def test_resolve_live_universe_returns_current_etfs_only(monkeypatch, tmp_path):
    (tmp_path / "etf-master.json").write_text(
        '{"etfs": ['
        '{"symbol":"A","name":"Alpha ETF","hasOhlcv":true,"delistingDate":null},'
        '{"symbol":"B","name":"Beta ETF","hasOhlcv":true,"delistingDate":"2025-01-01"}'
        ']}'
    )
    monkeypatch.setattr("engine.live_signal_utils._DATA_DIR", tmp_path)

    symbols = resolve_live_universe({"universe_id": "etf"}, ["fallback"])

    assert symbols == ["A"]


def test_resolve_live_universe_applies_market_and_sector(monkeypatch, tmp_path):
    (tmp_path / "korea-stocks.json").write_text(
        '[{"symbol":"A","market":"KOSPI","sector":"반도체"},'
        '{"symbol":"B","market":"KOSDAQ","sector":"반도체"},'
        '{"symbol":"C","market":"KOSPI","sector":"자동차"}]'
    )
    monkeypatch.setattr("engine.live_signal_utils._DATA_DIR", tmp_path)

    symbols = resolve_live_universe(
        {"universe_id": "kospi", "sector": "반도체"}, ["fallback"]
    )

    assert symbols == ["A"]


def test_resolve_live_universe_maps_kor_kospi200_to_kospi200(monkeypatch, tmp_path):
    """KOR_KOSPI200 이 부분일치로 KOSPI 전체(836종목)로 넓어지던 회귀."""
    (tmp_path / "kospi200-cache.json").write_text('{"symbols": ["A", "B"]}')
    (tmp_path / "korea-stocks.json").write_text(
        '[{"symbol":"A","market":"KOSPI"},{"symbol":"B","market":"KOSPI"},'
        '{"symbol":"OUTSIDE","market":"KOSPI"}]'
    )
    monkeypatch.setattr("engine.live_signal_utils._DATA_DIR", tmp_path)

    assert resolve_live_universe({"universe_id": "KOR_KOSPI200"}, ["fallback"]) == ["A", "B"]
    # 리스트로 저장된 복수 시장 표기는 토큰 일치로 그대로 동작해야 한다.
    assert sorted(
        resolve_live_universe({"universe_id": ["kospi", "kosdaq"]}, ["fallback"])
    ) == ["A", "B", "OUTSIDE"]


def test_resolve_live_universe_reads_kosdaq150_roster(monkeypatch, tmp_path):
    """KOR_KOSDAQ150 이 KOSDAQ 전체(1819종목)로 넓어지던 회귀 — 명부를 읽어야 한다."""
    (tmp_path / "kosdaq150-cache.json").write_text('{"symbols": ["K1", "K2"]}')
    (tmp_path / "korea-stocks.json").write_text(
        '[{"symbol":"K1","market":"KOSDAQ","sector":"바이오/제약"},'
        '{"symbol":"K2","market":"KOSDAQ","sector":"소프트웨어"},'
        '{"symbol":"OUTSIDE","market":"KOSDAQ","sector":"바이오/제약"}]'
    )
    monkeypatch.setattr("engine.live_signal_utils._DATA_DIR", tmp_path)

    assert resolve_live_universe({"universe_id": "KOR_KOSDAQ150"}, ["fallback"]) == ["K1", "K2"]
    assert resolve_live_universe({"universe_id": "kosdaq150"}, ["fallback"]) == ["K1", "K2"]
    # 업종 필터는 명부 안에서만 걸린다 — 명부 밖 같은 업종 종목을 끌어오지 않는다.
    assert resolve_live_universe(
        {"universe_id": "kosdaq150", "sector": "바이오/제약"}, ["fallback"]
    ) == ["K1"]


def test_resolve_live_universe_falls_back_when_index_roster_missing(monkeypatch, tmp_path):
    """명부 파일이 없으면 시장 전체로 넓히지 않고 폴백으로 떨어져야 한다."""
    (tmp_path / "korea-stocks.json").write_text(
        '[{"symbol":"K1","market":"KOSDAQ"},{"symbol":"K2","market":"KOSDAQ"}]'
    )
    monkeypatch.setattr("engine.live_signal_utils._DATA_DIR", tmp_path)

    assert resolve_live_universe({"universe_id": "kosdaq150"}, ["fallback"]) == ["fallback"]


def test_resolve_live_universe_excludes_delisted_symbols(monkeypatch, tmp_path):
    """korea-stocks.json 에 남아 있는 상폐 종목이 매매 대상으로 새던 회귀."""
    (tmp_path / "korea-stocks.json").write_text(
        '[{"symbol":"ALIVE","market":"KOSPI"},{"symbol":"DEAD","market":"KOSPI"}]'
    )
    (tmp_path / "delisted-stocks.json").write_text('{"symbols": ["DEAD", "OTHER.KS"]}')
    monkeypatch.setattr("engine.live_signal_utils._DATA_DIR", tmp_path)

    assert resolve_live_universe({"universe_id": "kospi"}, ["fallback"]) == ["ALIVE"]
    # 지정 종목·폴백 경로도 같은 게이트를 거친다.
    assert resolve_live_universe({"target_symbols": ["ALIVE", "DEAD"]}, []) == ["ALIVE"]
    assert resolve_live_universe({}, ["ALIVE", "OTHER"]) == ["ALIVE"]


def test_holding_period_counts_trading_rows_not_calendar_days():
    loader = StubLoader({
        "A": pl.DataFrame({
            "date": ["2025-01-03", "2025-01-06", "2025-01-07"],
            "open": [100, 100, 100],
            "high": [100, 100, 100],
            "low": [100, 100, 100],
            "close": [100, 100, 100],
            "volume": [1000, 1000, 1000],
        })
    })

    sessions = count_holding_sessions(
        loader, "A", "2025-01-03T00:30:00+00:00", "2025-01-07"
    )

    assert sessions == 2


@pytest.mark.asyncio
async def test_next_open_refresh_evaluates_universe_but_quotes_actions_only(monkeypatch):
    class RecordingMarketData:
        def __init__(self):
            self.symbols = []

        async def get_prices(self, symbols):
            self.symbols = list(symbols)
            return {
                symbol: SimpleNamespace(
                    close=100,
                    high=100,
                    date=virtual_trader_module.datetime.now(
                        virtual_trader_module._KST
                    ).strftime("%Y-%m-%d"),
                    trading_halted=None,
                )
                for symbol in symbols
            }

    market_data = RecordingMarketData()
    trader = VirtualTrader(market_data, data_loader=None)
    evaluated = []
    monkeypatch.setattr(
        virtual_trader_module,
        "resolve_live_universe",
        lambda _dsl, _fallback: ["A", "B", "C"],
    )
    monkeypatch.setattr(
        virtual_trader_module,
        "_is_strategy_execution_window",
        lambda _timing: True,
    )
    monkeypatch.setattr(trader, "_fetch_strategy", lambda _strategy_id: {
        "universe_id": "kospi",
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {"execution_timing": "next_open", "max_positions": 1},
    })
    monkeypatch.setattr(trader, "_fetch_positions", lambda _account_id: [
        {"symbol": "HELD", "avgPrice": 100, "peakPrice": 100, "quantity": 1}
    ])
    monkeypatch.setattr(trader, "_fetch_pending_orders", lambda _account_id: [
        {"symbol": "PENDING", "side": "BUY", "price": 90}
    ])

    def fake_evaluate(symbols, *_args, **_kwargs):
        evaluated.extend(symbols)
        return [
            {"symbol": symbol, "entry_signal": symbol == "B", "exit_signal": False}
            for symbol in symbols
        ]

    monkeypatch.setattr(trader, "_evaluate_signals", fake_evaluate)
    monkeypatch.setattr(trader, "_fetch_stock_names", lambda _symbols: {})
    monkeypatch.setattr(trader, "_fetch_delisting_policy", lambda _account_id: "AUTO_LIQUIDATE")
    monkeypatch.setattr(trader, "_fetch_today_logs", lambda *_args: set())
    monkeypatch.setattr(trader, "_count_positions", lambda _account_id: 1)
    monkeypatch.setattr(trader, "_log_signal", lambda *_args: None)
    monkeypatch.setattr(trader, "_fill_pending_order", lambda *_args: None)
    monkeypatch.setattr(trader, "_update_positions", lambda *_args: None)
    monkeypatch.setattr(trader, "_update_last_refreshed", lambda *_args: None)
    monkeypatch.setattr(
        virtual_trader_module,
        "get_stock_listing_status",
        lambda _symbol: virtual_trader_module.ListingStatus.NORMAL,
    )

    await trader._refresh_account({
        "id": "account-1",
        "tradingMode": "manual",
        "symbols": '["DISPLAY_ONLY"]',
        "strategyId": "strategy-1",
    })

    assert evaluated == ["A", "B", "C"]
    assert market_data.symbols == ["B", "HELD", "PENDING"]


@pytest.mark.asyncio
async def test_pending_limit_order_blocked_when_trading_suspended(monkeypatch):
    """지정가 대기 주문이 상장 상태를 보지 않고 가격만으로 체결되던 회귀."""
    class StubMarketData:
        async def get_prices(self, symbols):
            return {
                symbol: SimpleNamespace(
                    close=100,
                    high=100,
                    date=virtual_trader_module.datetime.now(
                        virtual_trader_module._KST
                    ).strftime("%Y-%m-%d"),
                    trading_halted=None,
                )
                for symbol in symbols
            }

    trader = VirtualTrader(StubMarketData(), data_loader=None)
    filled = []

    monkeypatch.setattr(
        virtual_trader_module, "resolve_live_universe", lambda _dsl, _fallback: []
    )
    monkeypatch.setattr(
        virtual_trader_module, "_is_strategy_execution_window", lambda _timing: True
    )
    monkeypatch.setattr(trader, "_fetch_strategy", lambda _strategy_id: {
        "universe_id": "kospi",
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {"execution_timing": "next_open"},
    })
    monkeypatch.setattr(trader, "_fetch_positions", lambda _account_id: [])
    monkeypatch.setattr(trader, "_fetch_pending_orders", lambda _account_id: [
        {"symbol": "HALTED", "side": "BUY", "price": 200},
        {"symbol": "OK", "side": "BUY", "price": 200},
    ])
    monkeypatch.setattr(trader, "_evaluate_signals", lambda *_a, **_k: [])
    monkeypatch.setattr(trader, "_fetch_stock_names", lambda _symbols: {})
    monkeypatch.setattr(trader, "_fetch_delisting_policy", lambda _account_id: "AUTO_LIQUIDATE")
    monkeypatch.setattr(trader, "_fetch_today_logs", lambda *_args: set())
    monkeypatch.setattr(trader, "_update_positions", lambda *_args: None)
    monkeypatch.setattr(trader, "_update_last_refreshed", lambda *_args: None)
    monkeypatch.setattr(
        trader, "_fill_pending_order",
        lambda _account_id, order, _price: filled.append(order["symbol"]),
    )
    monkeypatch.setattr(
        virtual_trader_module, "get_stock_listing_status",
        lambda symbol: (
            virtual_trader_module.ListingStatus.TRADING_SUSPENDED
            if symbol == "HALTED"
            else virtual_trader_module.ListingStatus.NORMAL
        ),
    )

    await trader._refresh_account({
        "id": "account-1",
        "tradingMode": "auto",
        "symbols": "[]",
        "strategyId": "strategy-1",
    })

    assert filled == ["OK"]


def test_strategy_execution_windows(monkeypatch):
    class FakeDateTime:
        current = (9, 3)

        @classmethod
        def now(cls, _timezone):
            return SimpleNamespace(hour=cls.current[0], minute=cls.current[1])

    monkeypatch.setattr(virtual_trader_module, "datetime", FakeDateTime)
    assert _is_strategy_execution_window("next_open") is True
    assert _is_strategy_execution_window("current_close") is False

    FakeDateTime.current = (15, 30)
    assert _is_strategy_execution_window("next_open") is False
    assert _is_strategy_execution_window("current_close") is True
