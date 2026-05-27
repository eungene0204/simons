"""
상장 상태 관리 모듈

상태 머신:
  NORMAL            → 정상 거래 가능
  WARNING           → 경고 (거래 허용, 배지 표시)
  RISK              → 위험 (신규 매수 제한 가능)
  TRADING_SUSPENDED → 매매거래정지 (매수/매도 모두 차단)
  DELISTING_REVIEW  → 상장적격성 심사 (신규 매수 차단)
  DELISTING_SCHEDULED → 상장폐지 확정 (신규 매수 차단, 자동청산 카운트다운)
  DELISTED          → 상장폐지 완료 (모든 거래 차단, 0원 평가)
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── 상태 상수 ─────────────────────────────────────────────────────────────────

class ListingStatus:
    NORMAL               = "NORMAL"
    WARNING              = "WARNING"
    RISK                 = "RISK"
    TRADING_SUSPENDED    = "TRADING_SUSPENDED"
    DELISTING_REVIEW     = "DELISTING_REVIEW"
    DELISTING_SCHEDULED  = "DELISTING_SCHEDULED"
    DELISTED             = "DELISTED"


# 거래 허용 여부 규칙
_BUY_ALLOWED = {
    ListingStatus.NORMAL:               True,
    ListingStatus.WARNING:              True,
    ListingStatus.RISK:                 True,   # 허용하되 UI에서 경고
    ListingStatus.TRADING_SUSPENDED:    False,
    ListingStatus.DELISTING_REVIEW:     False,
    ListingStatus.DELISTING_SCHEDULED:  False,
    ListingStatus.DELISTED:             False,
}

_SELL_ALLOWED = {
    ListingStatus.NORMAL:               True,
    ListingStatus.WARNING:              True,
    ListingStatus.RISK:                 True,
    ListingStatus.TRADING_SUSPENDED:    False,  # 거래정지: 매도 불가
    ListingStatus.DELISTING_REVIEW:     True,   # 심사 중에도 청산 허용
    ListingStatus.DELISTING_SCHEDULED:  True,   # 정리매매 허용
    ListingStatus.DELISTED:             False,
}

# 0원 평가 여부
_ZERO_VALUATION = {
    ListingStatus.DELISTED: True,
}


def is_buy_allowed(status: str) -> bool:
    return _BUY_ALLOWED.get(status, False)


def is_sell_allowed(status: str) -> bool:
    return _SELL_ALLOWED.get(status, False)


def is_zero_valuation(status: str) -> bool:
    return _ZERO_VALUATION.get(status, False)


def get_trade_block_reason(status: str, side: str) -> Optional[str]:
    """거래 차단 사유 반환. 허용 시 None."""
    if side.upper() == "BUY" and not is_buy_allowed(status):
        msgs = {
            ListingStatus.TRADING_SUSPENDED: "매매거래정지 종목은 매수할 수 없습니다.",
            ListingStatus.DELISTING_REVIEW:  "상장적격성 심사 중인 종목은 신규 매수가 불가합니다.",
            ListingStatus.DELISTING_SCHEDULED: "상장폐지가 확정된 종목은 신규 매수가 불가합니다.",
            ListingStatus.DELISTED:          "상장폐지 종목은 거래할 수 없습니다.",
        }
        return msgs.get(status, f"현재 상태({status})에서 매수할 수 없습니다.")
    if side.upper() == "SELL" and not is_sell_allowed(status):
        msgs = {
            ListingStatus.TRADING_SUSPENDED: "매매거래정지 종목은 거래가 정지된 상태입니다.",
            ListingStatus.DELISTED:          "상장폐지 종목은 거래할 수 없습니다.",
        }
        return msgs.get(status, f"현재 상태({status})에서 매도할 수 없습니다.")
    return None


# ── DART 공시 → ListingStatus 매핑 ───────────────────────────────────────────

_CONFIRMED_DELIST_KEYWORDS = ["상장폐지결정", "상장폐지 결정", "정리매매", "상장폐지예고"]
_REVIEW_KEYWORDS            = ["상장적격성", "관리종목"]
_SUSPENDED_KEYWORDS         = ["매매거래정지"]
_WARNING_KEYWORDS           = ["상장폐지"]  # 포괄적 (위 키워드에 걸리지 않은 것)


def classify_dart_notice(report_nm: str) -> str:
    """DART 공시 report_nm을 ListingStatus로 분류"""
    for kw in _CONFIRMED_DELIST_KEYWORDS:
        if kw in report_nm:
            return ListingStatus.DELISTING_SCHEDULED
    for kw in _REVIEW_KEYWORDS:
        if kw in report_nm:
            return ListingStatus.DELISTING_REVIEW
    for kw in _SUSPENDED_KEYWORDS:
        if kw in report_nm:
            return ListingStatus.TRADING_SUSPENDED
    for kw in _WARNING_KEYWORDS:
        if kw in report_nm:
            return ListingStatus.WARNING
    return ListingStatus.WARNING  # 기타 DART 공시는 WARNING


# ── DB 동기화 ─────────────────────────────────────────────────────────────────

def _db_path() -> str:
    project_root = Path(__file__).resolve().parent.parent.parent
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("file:"):
        rel = db_url[len("file:"):]
        prisma_dir = project_root / "prisma"
        return str((prisma_dir / rel).resolve())
    return str(project_root / "prisma" / "dev.db")


def update_stock_listing_status(
    symbol: str,
    status: str,
    suspension_reason: Optional[str] = None,
    delisting_date: Optional[str] = None,
    last_tradable_date: Optional[str] = None,
    risk_flags: Optional[list] = None,
) -> None:
    """Stock 테이블의 listingStatus 필드를 업데이트"""
    db = _db_path()
    now = datetime.now(timezone.utc).isoformat()
    risk_flags_json = json.dumps(risk_flags, ensure_ascii=False) if risk_flags else None

    con = sqlite3.connect(db)
    try:
        # Stock row가 없으면 삽입
        existing = con.execute("SELECT id FROM Stock WHERE symbol = ?", (symbol,)).fetchone()
        if existing:
            con.execute("""
                UPDATE Stock SET
                    listingStatus = ?,
                    suspensionReason = COALESCE(?, suspensionReason),
                    delistingDate = COALESCE(?, delistingDate),
                    lastTradableDate = COALESCE(?, lastTradableDate),
                    riskFlags = COALESCE(?, riskFlags),
                    statusUpdatedAt = ?,
                    updatedAt = ?
                WHERE symbol = ?
            """, (status, suspension_reason, delisting_date, last_tradable_date, risk_flags_json, now, now, symbol))
        else:
            con.execute("""
                INSERT INTO Stock (symbol, listingStatus, suspensionReason, delistingDate,
                    lastTradableDate, riskFlags, statusUpdatedAt, updatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, status, suspension_reason, delisting_date, last_tradable_date, risk_flags_json, now, now))
        con.commit()
    finally:
        con.close()


def get_stock_listing_status(symbol: str) -> str:
    """Stock 테이블에서 listingStatus 조회. 없으면 NORMAL 반환."""
    db = _db_path()
    con = sqlite3.connect(db)
    try:
        row = con.execute("SELECT listingStatus FROM Stock WHERE symbol = ?", (symbol,)).fetchone()
        return row[0] if row else ListingStatus.NORMAL
    finally:
        con.close()


def get_stocks_by_status(status: str) -> list[dict]:
    """특정 listingStatus를 가진 종목 목록 조회"""
    db = _db_path()
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("""
            SELECT symbol, name, listingStatus, suspensionReason,
                   delistingDate, lastTradableDate, riskFlags, statusUpdatedAt
            FROM Stock WHERE listingStatus = ?
        """, (status,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def sync_from_delisted_store(delisted_symbols: set[str]) -> int:
    """DelistedSymbolStore의 심볼들을 Stock 테이블에 DELISTED로 동기화. 변경된 수 반환."""
    count = 0
    for sym in delisted_symbols:
        current = get_stock_listing_status(sym)
        if current != ListingStatus.DELISTED:
            update_stock_listing_status(
                sym,
                ListingStatus.DELISTED,
                suspension_reason="상장폐지 완료",
                risk_flags=["DELISTED"],
            )
            count += 1
    return count


# 상태 우선순위 (높을수록 심각)
_priority: dict[str, int] = {
    ListingStatus.DELISTED:              7,
    ListingStatus.DELISTING_SCHEDULED:   6,
    ListingStatus.TRADING_SUSPENDED:     5,
    ListingStatus.DELISTING_REVIEW:      4,
    ListingStatus.WARNING:               3,
    ListingStatus.RISK:                  2,
    ListingStatus.NORMAL:                1,
}


def sync_from_dart_notices(notices: list[dict]) -> dict[str, str]:
    """DART 공시 목록으로 Stock 테이블 listingStatus 업데이트.

    Returns: {symbol: new_status} 변경된 종목 매핑
    """
    changed: dict[str, str] = {}
    for notice in notices:
        symbol = notice.get("stock_code")
        report_nm = notice.get("report_nm", "")
        if not symbol:
            continue

        # 이미 DELISTED인 종목은 강등 불가
        current = get_stock_listing_status(symbol)
        if current == ListingStatus.DELISTED:
            continue

        new_status = classify_dart_notice(report_nm)

        if _priority.get(new_status, 0) > _priority.get(current, 0):
            corp_name = notice.get("corp_name", "")
            update_stock_listing_status(
                symbol,
                new_status,
                suspension_reason=f"{corp_name}: {report_nm}" if corp_name else report_nm,
                risk_flags=[new_status, report_nm[:50]],
            )
            changed[symbol] = new_status

    return changed


def write_audit_log(
    account_id: str,
    symbol: str,
    action_type: str,
    previous_status: Optional[str] = None,
    new_status: Optional[str] = None,
    quantity: Optional[int] = None,
    execution_price: Optional[float] = None,
    reason: Optional[str] = None,
) -> None:
    """DelistingAuditLog에 이벤트 기록"""
    import uuid
    db = _db_path()
    con = sqlite3.connect(db)
    try:
        con.execute("""
            INSERT INTO DelistingAuditLog
                (id, accountId, symbol, actionType, previousStatus, newStatus,
                 quantity, executionPrice, reason, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()), account_id, symbol, action_type,
            previous_status, new_status, quantity, execution_price,
            reason, datetime.now(timezone.utc).isoformat(),
        ))
        con.commit()
    finally:
        con.close()
