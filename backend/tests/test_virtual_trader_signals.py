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
    # 사유는 세그먼트 페이로드로 실린다 — 한국어 문장은 tr.text()로 얻는다(2026-09-13).
    from engine import trade_reason as tr

    assert tr.decode(signals[0]["entry_reason"]) is not None
    assert "126거래일" in tr.text(signals[0]["entry_reason"])
    assert "(1/2위)" in tr.text(signals[0]["entry_reason"])


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


def test_resolve_live_universe_reads_saved_backtest_request_target_symbols(monkeypatch):
    """백테스트 요청을 그대로 저장한 지정 종목 전략(최상위 target_symbols 없음)도 전체 목록을
    매매 대상으로 쓴다 — 종전에는 모니터링 목록(상위 10)으로 폴백해 21종목 중 10종목만 매매."""
    import engine.live_signal_utils as lsu

    monkeypatch.setattr(lsu, "_load_delisted_symbols", lambda: set())
    fallback = ["NBIS", "AMD"]

    # 2) 중첩 canonical_strategy_dsl.target_symbols
    saved = {
        "backtest_mode": "single_asset", "universe_id": None,
        "canonical_strategy_dsl": {"universe": ["US"], "target_symbols": ["NVDA", "AMD", "TSM"]},
        "symbols": ["NVDA", "AMD", "TSM"],
    }
    assert resolve_live_universe(saved, fallback) == ["NVDA", "AMD", "TSM"]

    # 3) 최상위 symbols 만 있는 single_asset (한국 레인도 같은 저장 형태)
    assert resolve_live_universe(
        {"backtest_mode": "single_asset", "universe_id": None, "symbols": ["005930", "000660", "005930"]},
        ["005930"],
    ) == ["005930", "000660"]

    # 1) DSL 정본 target_symbols 가 있으면 그것이 우선
    assert resolve_live_universe(
        {"target_symbols": ["MSFT"], "backtest_mode": "single_asset", "symbols": ["NVDA"]}, fallback
    ) == ["MSFT"]


def test_resolve_live_universe_ignores_universe_mode_symbol_snapshot(monkeypatch):
    """유니버스 모드의 symbols 는 백테스트 시점 스냅샷 — 매매 대상으로 고정하면 생존편향."""
    import engine.live_signal_utils as lsu

    monkeypatch.setattr(lsu, "_load_delisted_symbols", lambda: set())
    monkeypatch.setattr(lsu, "resolve_us_symbols", lambda kind: ["AAPL", "MSFT"])

    snapshot = {"backtest_mode": "universe", "universe_id": "sp500", "symbols": ["OLD1", "OLD2"]}
    assert resolve_live_universe(snapshot, ["NBIS"]) == ["AAPL", "MSFT"]
    # 유니버스를 못 풀면 스냅샷이 아니라 폴백(모니터링 목록)
    assert resolve_live_universe(
        {"backtest_mode": "universe", "universe_id": "unknown_x", "symbols": ["OLD1"]}, ["NBIS"]
    ) == ["NBIS"]


def test_holding_period_counts_trading_rows_not_calendar_days():
    # 심볼 형태가 시장을 결정한다(is_us_symbol) — 한국 케이스는 6자리 코드로 둔다.
    loader = StubLoader({
        "000001": pl.DataFrame({
            "date": ["2025-01-03", "2025-01-06", "2025-01-07"],
            "open": [100, 100, 100],
            "high": [100, 100, 100],
            "low": [100, 100, 100],
            "close": [100, 100, 100],
            "volume": [1000, 1000, 1000],
        })
    })

    sessions = count_holding_sessions(
        loader, "000001", "2025-01-03T00:30:00+00:00", "2025-01-07"
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
        lambda _dsl, _fallback: ["000111", "000222", "000333"],
    )
    monkeypatch.setattr(
        virtual_trader_module,
        "_is_strategy_execution_window",
        lambda _timing, *_a: True,
    )
    monkeypatch.setattr(trader, "_fetch_strategy", lambda _strategy_id: {
        "universe_id": "kospi",
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {"execution_timing": "next_open", "max_positions": 1},
    })
    monkeypatch.setattr(trader, "_fetch_positions", lambda _account_id: [
        {"symbol": "000900", "avgPrice": 100, "peakPrice": 100, "quantity": 1}
    ])
    monkeypatch.setattr(trader, "_fetch_pending_orders", lambda _account_id: [
        {"symbol": "000800", "side": "BUY", "price": 90}
    ])

    def fake_evaluate(symbols, *_args, **_kwargs):
        evaluated.extend(symbols)
        return [
            {"symbol": symbol, "entry_signal": symbol == "000222", "exit_signal": False}
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

    assert evaluated == ["000111", "000222", "000333"]
    assert market_data.symbols == ["000222", "000900", "000800"]


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
        virtual_trader_module, "_is_strategy_execution_window", lambda _timing, *_a: True
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


def test_holding_period_us_symbol_uses_new_york_session_date():
    """미국 종목의 진입 세션 날짜는 ET 기준 — KST로 바꾸면(ET 오후=KST 새벽 익일) 하루 덜 센다."""
    loader = StubLoader({
        "AAPL": pl.DataFrame({
            "date": ["2025-01-03", "2025-01-06", "2025-01-07"],
            "open": [100, 100, 100], "high": [100, 100, 100], "low": [100, 100, 100],
            "close": [100, 100, 100], "volume": [1000, 1000, 1000],
        })
    })
    # 2025-01-03 15:00 ET 체결 = 2025-01-03T20:00Z = KST 01-04 05:00
    assert count_holding_sessions(loader, "AAPL", "2025-01-03T20:00:00+00:00", "2025-01-07") == 2


def test_live_exit_reasons_are_segment_payloads():
    """사고(2026-09-13): 자동매매가 리스크 청산 사유를 f-string으로 만들어 엔진의 인코딩된
    조건 사유와 문자열로 이어 붙였다 → VirtualMarketLog.reason에 깨진 페이로드가 저장되고
    매매 신호 카드에 `RJ[{"t":...}]`가 그대로 노출. 사유는 전부 세그먼트로 만들고 병합도
    세그먼트로 한다."""
    from engine import trade_reason as tr
    from engine.virtual_trader import _merge_exit_reason

    condition = tr.encode([tr.part(tr.RSI_LEVEL, 40, tr.part(tr.OP_LTE))])
    stop = tr.encode([tr.part(tr.LIVE_STOP_LOSS, "-12.3", 10)])

    merged = _merge_exit_reason(condition, stop)
    assert tr.decode(merged) is not None, "병합 결과가 하나의 페이로드여야 한다"
    assert tr.text(merged) == "RSI 40 이하 + 손절 (-12.3% ≤ -10%)"
    # 기존 사유가 없으면 그대로.
    assert _merge_exit_reason(None, stop) == stop
    assert _merge_exit_reason("", stop) == stop
    # 구버전 평문 사유와도 섞인다.
    assert tr.text(_merge_exit_reason("전략 매도 조건 충족", stop)) == (
        "전략 매도 조건 충족 + 손절 (-12.3% ≤ -10%)"
    )


def test_live_reason_templates_render_korean():
    from engine import trade_reason as tr

    assert tr.text(tr.encode([tr.part(tr.LIVE_TAKE_PROFIT, "15.2", 15)])) == "익절 (15.2% ≥ +15%)"
    assert tr.text(tr.encode([tr.part(tr.LIVE_MAX_HOLDING, 21, 20)])) == "최대보유일 초과 (21거래일 ≥ 20거래일)"
    assert tr.text(tr.encode([tr.part(tr.LIVE_FORCED_LIQUIDATION, "DELISTED")])) == "강제청산 (상장 상태: DELISTED)"
    trailing = tr.encode([tr.part(tr.LIVE_TRAILING_STOP, 71200, "-8.0", money=[0])])
    assert tr.text(trailing) == "트레일링스톱 (최고가 71,200원 대비 -8.0% 하락)"
    assert tr.first_template(tr.encode([tr.part(tr.LIVE_FORCED_LIQUIDATION, "X")])) == tr.LIVE_FORCED_LIQUIDATION
