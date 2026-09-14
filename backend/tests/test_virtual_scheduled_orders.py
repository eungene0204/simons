"""가상계좌 예약 주문 큐(engine/virtual_scheduled_orders.py) — 신호 후 N거래일 지연 체결의 자동매매 대응.

고정할 계약:
  - 예약은 같은 계좌·종목·방향에 한 건만(멱등), 닫힌 행은 다시 닫히지 않는다(조건부 UPDATE).
  - 집행 시점 = signalDate 뒤 delayDays-1 거래 세션이 지난 첫 집행 창.
  - 지연>1이면 전략 신호는 즉시 집행 대신 예약되고, 리스크 청산은 종전대로 즉시 집행된다.
  - 예약이 만기되면 같은 창에서 시장가 집행 + EXECUTED로 닫힘. 전략이 바뀐 예약은 CANCELLED.
"""
from datetime import datetime
from types import SimpleNamespace

import polars as pl
import pytest

import engine.virtual_trader as vt
from engine import virtual_scheduled_orders as vso
from engine import trade_reason as tr


# ── DB 계층 ────────────────────────────────────────────────────────────────────

@pytest.fixture
def account(app_db):
    app_db.execute(
        'INSERT INTO "VirtualAccount" (id, name, "initialCash", "currentCash", "updatedAt")'
        " VALUES (?, ?, ?, ?, ?)",
        ("acc-q", "큐 테스트", 1000000, 1000000, datetime(2026, 1, 1)),
    )
    app_db.commit()
    return "acc-q"


def test_enqueue_is_idempotent_per_symbol_side_and_resolve_closes_once(account):
    first = vso.enqueue(account, "s1", "005930", "삼성전자", "BUY", "entry", "2026-09-14", 3, None)
    second = vso.enqueue(account, "s1", "005930", "삼성전자", "BUY", "entry", "2026-09-15", 3, None)
    other_side = vso.enqueue(account, "s1", "005930", "삼성전자", "SELL", "exit", "2026-09-14", 3, None)
    assert first and other_side and second is None

    open_orders = vso.fetch_open(account)
    assert {(o["side"], o["delayDays"], o["signalDate"]) for o in open_orders} == {
        ("BUY", 3, "2026-09-14"), ("SELL", 3, "2026-09-14"),
    }

    assert vso.resolve(first, vso.STATUS_EXECUTED, None, "order-1") is True
    assert vso.resolve(first, vso.STATUS_SKIPPED, vso.RES_NO_POSITION) is False  # 이미 닫힘
    assert [o["id"] for o in vso.fetch_open(account)] == [other_side]


# ── 만기 판정 ──────────────────────────────────────────────────────────────────

class _StubLoader:
    def __init__(self, frames):
        self.frames = frames

    def load_symbol_data(self, symbol):
        return self.frames.get(symbol)


def _frame(n):
    return pl.DataFrame({
        "date": pl.date_range(pl.date(2025, 1, 1), pl.date(2025, 1, 1) + pl.duration(days=n - 1), eager=True),
        "open": [100.0] * n, "high": [100.0] * n, "low": [100.0] * n, "close": [100.0] * n,
        "volume": [1000] * n,
    })


def test_due_after_delay_minus_one_sessions_since_signal_date():
    loader = _StubLoader({"A": _frame(10)})   # 2025-01-01 ~ 01-10 매일 봉
    sessions = vso.sessions_since(loader, "A", "2025-01-02", "2025-01-04")
    assert sessions == 2                        # 01-03, 01-04
    assert vso.is_due({"delayDays": 3}, sessions)        # 3번째 거래일 = 01-04
    assert not vso.is_due({"delayDays": 4}, sessions)    # 4번째 거래일 = 01-05
    assert vso.is_due({"delayDays": 1}, 0)               # 지연 1 = 당일


def test_sessions_since_without_loader_is_zero():
    assert vso.sessions_since(None, "A", "2025-01-02", "2025-01-04") == 0


# ── 트레이더 통합 ─────────────────────────────────────────────────────────────

class _StubMarketData:
    def __init__(self, today):
        self.today = today

    async def get_prices(self, symbols):
        return {s: SimpleNamespace(close=100.0, high=100.0, trading_halted=None, date=self.today)
                for s in symbols}


def _account():
    return {"id": "acct-kr", "tradingMode": "auto", "currency": "KRW",
            "symbols": '["005930"]', "strategyId": "s1"}


def _wire(monkeypatch, trader, *, positions, scheduled, signals, delay=3):
    """_refresh_account가 DB·외부 API 없이 돌도록 최소 스텁 + 호출 기록."""
    calls = {"enqueue": [], "resolve": [], "buy": [], "sell": [], "logs": []}
    monkeypatch.setattr(vt, "resolve_live_universe", lambda _dsl, _fb: ["005930", "000660"])
    monkeypatch.setattr(vt, "_is_strategy_execution_window", lambda _t, *_a: True)
    monkeypatch.setattr(vt, "get_stock_listing_status", lambda _s: vt.ListingStatus.NORMAL)
    monkeypatch.setattr(trader, "_fetch_strategy", lambda _sid: {
        "entry": {"conditions": []}, "exit": {"conditions": []},
        "risk": {"execution_timing": "next_open", "execution_delay_days": delay,
                 "max_positions": 5, "position_size_pct": 10, "stop_loss_pct": 5},
    })
    monkeypatch.setattr(trader, "_fetch_positions", lambda _a: [dict(p) for p in positions])
    monkeypatch.setattr(trader, "_fetch_pending_orders", lambda _a: [])
    monkeypatch.setattr(trader, "_fetch_stock_names", lambda _s: {})
    monkeypatch.setattr(trader, "_fetch_delisting_policy", lambda _a: "AUTO_LIQUIDATE")
    monkeypatch.setattr(trader, "_fetch_today_logs", lambda *_a: set())
    monkeypatch.setattr(trader, "_count_positions", lambda _a: len(positions))
    monkeypatch.setattr(trader, "_fetch_current_cash", lambda _a: 1_000_000.0)
    monkeypatch.setattr(trader, "_update_positions", lambda *_a: None)
    monkeypatch.setattr(trader, "_update_last_refreshed", lambda *_a: None)
    monkeypatch.setattr(trader, "_evaluate_signals", lambda *_a, **_k: [dict(s) for s in signals])
    monkeypatch.setattr(trader, "_log_signal", lambda *a: calls["logs"].append(a))
    monkeypatch.setattr(trader, "_execute_buy", lambda *a: (calls["buy"].append(a), "buy-1")[1])
    monkeypatch.setattr(trader, "_execute_sell", lambda *a: (calls["sell"].append(a), "sell-1")[1])
    monkeypatch.setattr(trader, "_fetch_scheduled_orders", lambda _a: [dict(o) for o in scheduled])
    monkeypatch.setattr(vt.vso, "enqueue", lambda *a: (calls["enqueue"].append(a), "sched-new")[1])
    monkeypatch.setattr(vt.vso, "resolve", lambda *a: (calls["resolve"].append(a), True)[1])
    return calls


@pytest.mark.asyncio
async def test_delay_queues_strategy_entry_instead_of_executing(monkeypatch):
    today = vt._market_now({"currency": "KRW"}).strftime("%Y-%m-%d")
    trader = vt.VirtualTrader(_StubMarketData(today), data_loader=None)
    entry_reason = tr.encode([tr.part("RSI 과매도")])
    calls = _wire(monkeypatch, trader, positions=[], scheduled=[],
                  signals=[{"symbol": "005930", "close": 100.0, "entry_signal": True,
                            "exit_signal": False, "entry_reason": entry_reason, "exit_reason": None}])

    await trader._refresh_account(_account())

    assert calls["buy"] == []                       # 즉시 매수하지 않는다
    assert len(calls["enqueue"]) == 1
    _acc, sid, sym, _name, side, stype, sdate, delay, reason = calls["enqueue"][0]
    assert (sid, sym, side, stype, sdate, delay, reason) == ("s1", "005930", "BUY", "entry", today, 3, entry_reason)
    assert [(a[4], a[6]) for a in calls["logs"]] == [("entry", "scheduled")]


@pytest.mark.asyncio
async def test_risk_exit_is_not_queued_even_with_delay(monkeypatch):
    """손절은 보호 주문 — 지연 설정과 무관하게 감지 즉시 집행한다(백테스트와 같은 계약)."""
    today = vt._market_now({"currency": "KRW"}).strftime("%Y-%m-%d")
    trader = vt.VirtualTrader(_StubMarketData(today), data_loader=None)
    pos = {"symbol": "005930", "name": "삼성전자", "quantity": 10, "avgPrice": 120.0, "peakPrice": 120.0,
           "openedAt": datetime(2026, 1, 1)}   # 현재가 100 → -16.7% ≤ -5% 손절
    calls = _wire(monkeypatch, trader, positions=[pos], scheduled=[], signals=[])

    await trader._refresh_account(_account())

    assert calls["enqueue"] == []
    assert len(calls["sell"]) == 1 and calls["sell"][0][1] == "005930"


@pytest.mark.asyncio
async def test_due_scheduled_buy_executes_and_resolves(monkeypatch):
    today = vt._market_now({"currency": "KRW"}).strftime("%Y-%m-%d")
    trader = vt.VirtualTrader(_StubMarketData(today), data_loader=None)
    entry_reason = tr.encode([tr.part("RSI 과매도")])
    scheduled = [{"id": "sched-1", "accountId": "acct-kr", "strategyId": "s1", "symbol": "000660",
                  "name": None, "side": "BUY", "signalType": "entry", "signalDate": "2026-09-10",
                  "delayDays": 3, "reason": entry_reason, "status": "SCHEDULED"}]
    calls = _wire(monkeypatch, trader, positions=[], scheduled=scheduled, signals=[])
    monkeypatch.setattr(vt.vso, "sessions_since", lambda *_a: 2)   # 만기(3-1 세션 경과)

    await trader._refresh_account(_account())

    assert len(calls["buy"]) == 1 and calls["buy"][0][1] == "000660"
    assert calls["resolve"] == [("sched-1", vso.STATUS_EXECUTED, None, "buy-1")]
    log = next(a for a in calls["logs"] if a[6] == "auto_executed")
    assert log[2] == "000660" and log[4] == "entry" and log[7] == "buy-1"
    # 사유 = 원 사유 + 지연 체결 세그먼트(세그먼트 페이로드로 병합)
    templates = [seg.get("t") for seg in tr.segments_of(log[5]) if isinstance(seg, dict)]
    assert "RSI 과매도" in templates and tr.LIVE_DELAYED_FILL in templates


@pytest.mark.asyncio
async def test_scheduled_order_waits_until_due(monkeypatch):
    today = vt._market_now({"currency": "KRW"}).strftime("%Y-%m-%d")
    trader = vt.VirtualTrader(_StubMarketData(today), data_loader=None)
    scheduled = [{"id": "sched-1", "accountId": "acct-kr", "strategyId": "s1", "symbol": "000660",
                  "name": None, "side": "BUY", "signalType": "entry", "signalDate": "2026-09-12",
                  "delayDays": 3, "reason": None, "status": "SCHEDULED"}]
    calls = _wire(monkeypatch, trader, positions=[], scheduled=scheduled, signals=[])
    monkeypatch.setattr(vt.vso, "sessions_since", lambda *_a: 1)   # 아직 1세션

    await trader._refresh_account(_account())

    assert calls["buy"] == [] and calls["resolve"] == []


@pytest.mark.asyncio
async def test_scheduled_sell_without_position_is_skipped_and_strategy_change_cancels(monkeypatch):
    today = vt._market_now({"currency": "KRW"}).strftime("%Y-%m-%d")
    trader = vt.VirtualTrader(_StubMarketData(today), data_loader=None)
    scheduled = [
        {"id": "sched-sell", "accountId": "acct-kr", "strategyId": "s1", "symbol": "000660", "name": None,
         "side": "SELL", "signalType": "exit", "signalDate": "2026-09-10", "delayDays": 2,
         "reason": None, "status": "SCHEDULED"},
        {"id": "sched-old", "accountId": "acct-kr", "strategyId": "s-old", "symbol": "005930", "name": None,
         "side": "BUY", "signalType": "entry", "signalDate": "2026-09-10", "delayDays": 2,
         "reason": None, "status": "SCHEDULED"},
    ]
    calls = _wire(monkeypatch, trader, positions=[], scheduled=scheduled, signals=[])
    monkeypatch.setattr(vt.vso, "sessions_since", lambda *_a: 5)

    await trader._refresh_account(_account())

    assert calls["buy"] == [] and calls["sell"] == []
    assert sorted(calls["resolve"]) == sorted([
        ("sched-sell", vso.STATUS_SKIPPED, vso.RES_NO_POSITION),
        ("sched-old", vso.STATUS_CANCELLED, vso.RES_STRATEGY_CHANGED),
    ])
    assert [(a[2], a[6]) for a in calls["logs"]] == [("000660", "skipped")]


@pytest.mark.asyncio
async def test_delay_one_keeps_immediate_execution(monkeypatch):
    today = vt._market_now({"currency": "KRW"}).strftime("%Y-%m-%d")
    trader = vt.VirtualTrader(_StubMarketData(today), data_loader=None)
    calls = _wire(monkeypatch, trader, positions=[], scheduled=[], delay=1,
                  signals=[{"symbol": "005930", "close": 100.0, "entry_signal": True,
                            "exit_signal": False, "entry_reason": None, "exit_reason": None}])

    await trader._refresh_account(_account())

    assert calls["enqueue"] == [] and len(calls["buy"]) == 1
