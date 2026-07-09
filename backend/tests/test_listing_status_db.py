"""listing_status DB 경로(Postgres 어댑터) 회귀 테스트.

SQLite→Supabase Postgres 이관: 식별자 인용/ datetime 바인딩이 정상 동작하는지 검증.
app_db 픽스처가 로컬 simons_test로 DATABASE_URL을 지정하고 테이블을 격리한다.
"""
import importlib


def _mod():
    # DATABASE_URL이 app_db로 세팅된 뒤 import 되도록 지연 로드
    return importlib.import_module("engine.listing_status")


def test_insert_then_read_status(app_db):
    ls = _mod()
    assert ls.get_stock_listing_status("005930") == ls.ListingStatus.NORMAL  # 없으면 NORMAL

    ls.update_stock_listing_status(
        "005930", ls.ListingStatus.TRADING_SUSPENDED,
        suspension_reason="테스트 정지", risk_flags=["TRADING_SUSPENDED"],
    )
    assert ls.get_stock_listing_status("005930") == ls.ListingStatus.TRADING_SUSPENDED


def test_update_existing_row_coalesce(app_db):
    ls = _mod()
    ls.update_stock_listing_status("000660", ls.ListingStatus.WARNING, suspension_reason="1차")
    # 두 번째 업데이트: suspension_reason 미전달 → COALESCE로 기존 값 보존
    ls.update_stock_listing_status("000660", ls.ListingStatus.RISK)

    rows = ls.get_stocks_by_status(ls.ListingStatus.RISK)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "000660"
    assert rows[0]["suspensionReason"] == "1차"  # 보존됨
    assert rows[0]["statusUpdatedAt"] is not None  # DateTime 정상 기록


def test_get_stocks_by_status_multiple(app_db):
    ls = _mod()
    ls.update_stock_listing_status("A", ls.ListingStatus.DELISTED)
    ls.update_stock_listing_status("B", ls.ListingStatus.DELISTED)
    ls.update_stock_listing_status("C", ls.ListingStatus.NORMAL)
    delisted = ls.get_stocks_by_status(ls.ListingStatus.DELISTED)
    assert {r["symbol"] for r in delisted} == {"A", "B"}


def test_write_audit_log(app_db):
    ls = _mod()
    # DelistingAuditLog.accountId → VirtualAccount FK: 계좌 먼저 시딩
    app_db.execute(
        'INSERT INTO "VirtualAccount" (id, name, "initialCash", "currentCash", "updatedAt")'
        " VALUES (?, ?, ?, ?, ?)",
        ("acc1", "테스트계좌", 1000000, 1000000, __import__("db").now()),
    )
    app_db.commit()
    ls.write_audit_log(
        account_id="acc1", symbol="005930", action_type="AUTO_LIQUIDATE",
        previous_status="DELISTING_SCHEDULED", new_status="DELISTED",
        quantity=10, execution_price=100.0, reason="테스트",
    )
    row = app_db.execute(
        'SELECT "accountId", "actionType", quantity, "createdAt" FROM "DelistingAuditLog" WHERE symbol = ?',
        ("005930",),
    ).fetchone()
    assert row["accountId"] == "acc1"
    assert row["actionType"] == "AUTO_LIQUIDATE"
    assert row["quantity"] == 10
    assert row["createdAt"] is not None


def test_sync_from_dart_notices(app_db):
    ls = _mod()
    changed = ls.sync_from_dart_notices([
        {"stock_code": "005930", "report_nm": "매매거래정지", "corp_name": "삼성전자"},
        {"stock_code": "000660", "report_nm": "상장폐지결정", "corp_name": "SK하이닉스"},
    ])
    assert changed["005930"] == ls.ListingStatus.TRADING_SUSPENDED
    assert changed["000660"] == ls.ListingStatus.DELISTING_SCHEDULED
