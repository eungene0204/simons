"""
VirtualTrader 자동매매 엔진 테스트

서버/외부 API 없이 임시 SQLite DB로 매매 실행 로직만 검증한다:
  - PENDING 지정가 이중 체결 방지 (원자적 선점)
  - openedAt 파싱 (Prisma epoch ms / ISO 문자열 양쪽)
  - position_size_pct=100 전액 투자 매수
  - notified 로그 하루 1회 dedupe 키
  - KRX 호가단위 (2023 개편)
  - Prisma 호환 epoch ms 타임스탬프 기록
"""
from datetime import datetime, timezone, timedelta

import pytest

from engine.virtual_trader import (
    VirtualTrader,
    _parse_db_datetime,
    _round_tick,
    _filled_price,
    _buy_cost,
    _fee,
    _fresh_price_map,
    TAX_RATE,
)


# ── 픽스처 ────────────────────────────────────────────────────────────────────

@pytest.fixture
def trader(app_db):
    # 스키마는 마이그레이션으로 존재. VirtualAccount 시딩(name/initialCash NOT NULL).
    app_db.execute(
        'INSERT INTO "VirtualAccount" (id, name, "initialCash", "currentCash", "updatedAt")'
        " VALUES (?, ?, ?, ?, ?)",
        ("acc1", "테스트", 1000000, 1000000, datetime(2026, 1, 1)),
    )
    app_db.commit()

    t = VirtualTrader(market_data_provider=None, data_loader=None)
    t._q = app_db  # 테스트 조회용 커넥션 핸들 (트레이더는 db.connect()로 별도 연결)
    return t


def _query(trader, sql, params=()):
    return trader._q.execute(sql, params).fetchall()


# ── _parse_db_datetime ────────────────────────────────────────────────────────

def test_parse_db_datetime_epoch_ms():
    """Prisma가 기록한 epoch ms 정수 — 과거엔 fromisoformat 실패로 최대보유일 청산이 침묵 무시됐다."""
    dt = _parse_db_datetime(1782275498840)
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.year == 2026


def test_parse_db_datetime_iso_string():
    dt = _parse_db_datetime("2026-07-03T00:00:30.454296+00:00")
    assert dt == datetime(2026, 7, 3, 0, 0, 30, 454296, tzinfo=timezone.utc)


def test_parse_db_datetime_iso_z_suffix():
    dt = _parse_db_datetime("2026-07-03T00:00:30Z")
    assert dt == datetime(2026, 7, 3, 0, 0, 30, tzinfo=timezone.utc)


def test_parse_db_datetime_invalid():
    assert _parse_db_datetime(None) is None
    assert _parse_db_datetime("not-a-date") is None


def test_parse_db_datetime_holding_days():
    """epoch ms openedAt 으로도 보유일 계산이 동작해야 한다."""
    opened = datetime.now(timezone.utc) - timedelta(days=10)
    ms = int(opened.timestamp() * 1000)
    dt = _parse_db_datetime(ms)
    assert (datetime.now(timezone.utc) - dt).days == 10


# ── 호가단위 (2023 KRX 개편) ─────────────────────────────────────────────────

def test_round_tick_2023_table():
    assert _round_tick(1_500) == 1_500      # < 2,000: 1원 (구버전은 5원)
    assert _round_tick(3_333) == 3_335      # 2,000~5,000: 5원
    assert _round_tick(7_004) == 7_000      # 5,000~20,000: 10원
    assert _round_tick(15_004) == 15_000    # 5,000~20,000: 10원 (구버전은 50원)
    assert _round_tick(25_120) == 25_100    # 20,000~50,000: 50원
    assert _round_tick(150_060) == 150_100  # 50,000~200,000: 100원 (구버전은 500원)
    assert _round_tick(300_200) == 300_000  # 200,000~500,000: 500원
    assert _round_tick(600_400) == 600_000  # >= 500,000: 1,000원


def test_sell_tax_matches_backtest_default():
    """가상계좌 매도세는 백테스트 엔진 기본값(0.15%)과 같아야 한다."""
    from engine.simulator import DEFAULT_SELL_TAX_RATE
    assert TAX_RATE == DEFAULT_SELL_TAX_RATE


# ── _execute_buy ─────────────────────────────────────────────────────────────

def test_execute_buy_full_cash(trader):
    """position_size_pct=100 이어도 수수료 포함 비용이 현금 내에 들어와 매수돼야 한다."""
    order_id = trader._execute_buy("acc1", "005930", "삼성전자", 10000, 1000000, 100.0)
    assert order_id is not None

    filled = _filled_price(10000, "BUY")
    rows = _query(trader, 'SELECT quantity, "avgPrice" FROM "VirtualPosition" WHERE "accountId"=\'acc1\'')
    assert len(rows) == 1
    qty = rows[0][0]
    assert qty > 0
    assert rows[0][1] == filled

    cash = _query(trader, 'SELECT "currentCash" FROM "VirtualAccount" WHERE id=\'acc1\'')[0][0]
    assert cash == 1000000 - _buy_cost(filled, qty)
    assert cash >= 0


def test_execute_buy_timestamps_are_datetime(trader):
    """이관 후 DateTime 컬럼은 Postgres timestamp — psycopg가 datetime 객체로 왕복한다."""
    trader._execute_buy("acc1", "005930", "삼성전자", 10000, 1000000, 10.0)
    row = _query(trader, 'SELECT "createdAt", "filledAt" FROM "VirtualOrder"')[0]
    assert isinstance(row[0], datetime) and isinstance(row[1], datetime)
    row = _query(trader, 'SELECT "openedAt", "updatedAt" FROM "VirtualPosition"')[0]
    assert isinstance(row[0], datetime) and isinstance(row[1], datetime)


# ── _fill_pending_order 이중 체결 방지 ───────────────────────────────────────

def _insert_pending(trader, order_id, side, qty, price):
    trader._q.execute(
        'INSERT INTO "VirtualOrder" (id, "accountId", symbol, name, side, type, quantity, price, status)'
        " VALUES (?, 'acc1', '005930', '삼성전자', ?, 'LIMIT', ?, ?, 'PENDING')",
        (order_id, side, qty, price),
    )
    trader._q.commit()
    return {"id": order_id, "accountId": "acc1", "symbol": "005930", "name": "삼성전자",
            "side": side, "quantity": qty, "price": price}


def test_fill_pending_buy_only_once(trader):
    """같은 PENDING 주문을 두 번 체결 시도해도 포지션은 한 번만 증가해야 한다."""
    order = _insert_pending(trader, "o1", "BUY", 10, 10000)

    trader._fill_pending_order("acc1", order, 9900)
    trader._fill_pending_order("acc1", order, 9900)  # 두 번째 호출은 no-op

    rows = _query(trader, 'SELECT quantity FROM "VirtualPosition" WHERE "accountId"=\'acc1\' AND symbol=\'005930\'')
    assert rows[0][0] == 10  # 20이면 이중 체결

    status = _query(trader, 'SELECT status FROM "VirtualOrder" WHERE id=\'o1\'')[0][0]
    assert status == "FILLED"


def test_fill_pending_skips_already_filled(trader):
    """다른 경로(브라우저 fill 라우트)가 먼저 체결한 주문은 건드리지 않는다."""
    order = _insert_pending(trader, "o2", "BUY", 10, 10000)
    trader._q.execute('UPDATE "VirtualOrder" SET status=\'FILLED\' WHERE id=\'o2\'')
    trader._q.commit()

    trader._fill_pending_order("acc1", order, 9900)

    rows = _query(trader, 'SELECT COUNT(*) FROM "VirtualPosition" WHERE "accountId"=\'acc1\'')
    assert rows[0][0] == 0


def test_fill_pending_sell_only_once(trader):
    """SELL 이중 체결 시 현금이 두 번 입금되면 안 된다."""
    trader._q.execute(
        'INSERT INTO "VirtualPosition" (id, "accountId", symbol, name, quantity, "avgPrice", "updatedAt")'
        " VALUES ('p1', 'acc1', '005930', '삼성전자', 10, 9000, ?)",
        (datetime(2026, 1, 1),),
    )
    trader._q.commit()
    order = _insert_pending(trader, "o3", "SELL", 10, 10000)

    trader._fill_pending_order("acc1", order, 10100)
    trader._fill_pending_order("acc1", order, 10100)

    fee = _fee(10000, 10)
    tax = int(10000 * 10 * TAX_RATE)
    expected_cash = 1000000 + (10000 * 10 - fee - tax)
    cash = _query(trader, 'SELECT "currentCash" FROM "VirtualAccount" WHERE id=\'acc1\'')[0][0]
    assert cash == expected_cash

    rows = _query(trader, 'SELECT COUNT(*) FROM "VirtualPosition" WHERE "accountId"=\'acc1\'')
    assert rows[0][0] == 0


def test_fill_pending_sell_insufficient_position_cancels(trader):
    """보유 수량 부족 시 주문을 CANCELLED 처리한다 (fill 라우트와 동일)."""
    order = _insert_pending(trader, "o4", "SELL", 10, 10000)

    trader._fill_pending_order("acc1", order, 10100)

    status = _query(trader, 'SELECT status FROM "VirtualOrder" WHERE id=\'o4\'')[0][0]
    assert status == "CANCELLED"
    cash = _query(trader, 'SELECT "currentCash" FROM "VirtualAccount" WHERE id=\'acc1\'')[0][0]
    assert cash == 1000000


# ── 휴장일/스테일 시세 가드 ──────────────────────────────────────────────────

def _quote(symbol, close, date):
    from engine.providers.base import StockQuote
    return StockQuote(
        symbol=symbol, name=symbol, date=date,
        open=close, high=close, low=close, close=close,
        volume=100, source="test", timestamp=0.0,
    )


def test_fresh_price_map_filters_stale_quotes():
    """휴장일(마지막 거래일 날짜)·소스 장애(과거/None 날짜) 시세는 매매에 쓰지 않는다."""
    today = "2026-07-08"
    quotes = {
        "A": _quote("A", 10000, "2026-07-08"),   # 오늘 → 사용
        "B": _quote("B", 20000, "2026-07-07"),   # 어제(휴장일 패턴) → 제외
        "C": _quote("C", 30000, None),           # KIS 휴장 응답(date=None) → 제외
        "D": _quote("D", 0, "2026-07-08"),       # 가격 0 → 제외
    }
    assert _fresh_price_map(quotes, today) == {"A": 10000}


def test_fresh_price_map_holiday_blocks_all():
    """평일 공휴일: 전 종목이 스테일 → 빈 맵 → 매매 전체 보류."""
    quotes = {
        "A": _quote("A", 10000, "2026-07-07"),
        "B": _quote("B", 20000, "2026-07-07"),
    }
    assert _fresh_price_map(quotes, "2026-07-08") == {}


# ── notified dedupe ──────────────────────────────────────────────────────────

def test_fetch_today_logs_includes_notified(trader):
    """notified 로그도 하루 1회 dedupe 대상 — 30초 틱마다 중복 기록되면 안 된다."""
    trader._log_signal("acc1", "2026-07-08", "005930", 10000, "entry", "이유", "notified", None)
    trader._log_signal("acc1", "2026-07-08", "000660", 20000, "exit", "이유", "auto_executed", "oid")

    keys = trader._fetch_today_logs("acc1", "2026-07-08")
    assert "005930_entry_notified" in keys
    assert "000660_exit_auto_executed" in keys
    # 서로 다른 action 은 서로를 차단하지 않는다
    assert "005930_entry_auto_executed" not in keys


def test_log_signal_records_stock_name(trader):
    trader._log_signal("acc1", "2026-07-08", "005930", 10000, "entry", "이유", "auto_executed", "oid", "삼성전자")
    rows = _query(trader, 'SELECT "stockName" FROM "VirtualMarketLog" WHERE symbol=\'005930\'')
    assert rows[0][0] == "삼성전자"
