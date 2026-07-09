"""force_liquidate_position (강제청산) DB 경로 회귀 — SQLite→Postgres 이관 검증.

계좌·포지션을 시딩하고 시세 provider를 목킹한 뒤 강제청산 라우트를 호출해,
VirtualOrder 생성·VirtualPosition 삭제·현금 증가·DelistingAuditLog 기록을 확인한다.
"""
import asyncio
from datetime import datetime

import pytest


def _seed_account_position(conn):
    conn.execute(
        'INSERT INTO "VirtualAccount" (id, name, "initialCash", "currentCash", "updatedAt")'
        " VALUES (?, ?, ?, ?, ?)",
        ("acc_fl", "청산테스트", 10_000_000, 5_000_000, datetime(2026, 1, 1)),
    )
    conn.execute(
        'INSERT INTO "VirtualPosition" (id, "accountId", symbol, name, quantity, "avgPrice", "updatedAt")'
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("pos_fl", "acc_fl", "005930", "삼성전자", 10, 70000, datetime(2026, 1, 1)),
    )
    conn.commit()


def test_force_liquidate_settles_position(app_db, monkeypatch):
    _seed_account_position(app_db)

    import main

    class _Quote:
        close = 80000

    async def _fake_get_price(symbol):
        return _Quote()

    monkeypatch.setattr(main.market_data_provider, "get_price", _fake_get_price)

    result = asyncio.run(main.force_liquidate_position("acc_fl", "005930"))

    assert result["success"] is True
    assert result["quantity"] == 10

    # 포지션 삭제됨
    assert app_db.execute(
        'SELECT COUNT(*) FROM "VirtualPosition" WHERE "accountId" = ?', ("acc_fl",)
    ).fetchone()[0] == 0

    # 매도 주문(FILLED) 기록됨
    order = app_db.execute(
        'SELECT side, status, quantity FROM "VirtualOrder" WHERE "accountId" = ?', ("acc_fl",)
    ).fetchone()
    assert order["side"] == "SELL"
    assert order["status"] == "FILLED"
    assert order["quantity"] == 10

    # 현금 증가 (매도 대금 유입)
    cash = app_db.execute('SELECT "currentCash" FROM "VirtualAccount" WHERE id = ?', ("acc_fl",)).fetchone()[0]
    assert float(cash) > 5_000_000

    # 감사 로그 기록됨
    audit = app_db.execute(
        'SELECT "actionType" FROM "DelistingAuditLog" WHERE "accountId" = ? AND symbol = ?',
        ("acc_fl", "005930"),
    ).fetchone()
    assert audit["actionType"] == "AUTO_LIQUIDATE"
