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
from typing import Optional

import db

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
# 확정 낱말이 있어도 **절차가 진행되지 않는다는** 제목은 확정이 아니다 — 2026-09-15 실측:
# 신라에스지 "기타시장안내(상장폐지 및 정리매매 절차 미진행)"가 '정리매매' 낱말만으로
# 상장폐지 확정으로 등록돼 정상 거래 중인 종목의 시세 조회가 통째로 막혔다. 반면
# "…가처분 신청 기각에 따른 정리매매절차 재개"(코다코·코스나인)는 진짜 정리매매라
# '기각'은 여기 넣지 않는다 — 절차 자체의 보류·중단을 뜻하는 표현만 본다.
_DELIST_HOLD_KEYWORDS       = ["미진행", "이의신청", "보류", "중단"]
# 조건부 보류 — 효력정지 가처분은 '상장폐지결정'을 **다투는 중**이라는 뜻이라 확정이 아니다
# (2026-09-16 실측: 케이엠제약 "기타경영사항(자율공시)(상장폐지결정 등 효력정지 가처분 신청)"이
# 낱말 포함만으로 확정 처리돼, 가상계좌의 AUTO_LIQUIDATE 정책이 보유 포지션을 강제청산할 수
# 있는 상태였다). 다만 가처분이 기각·각하·취하되면 절차가 재개되므로 그때는 확정이다
# (기존 회귀: "…가처분 신청 기각에 따른 정리매매절차 재개").
_INJUNCTION_KEYWORD         = "가처분"
_INJUNCTION_RESUME_KEYWORDS = ["기각", "각하", "취하"]
_REVIEW_KEYWORDS            = ["상장적격성", "관리종목"]
_SUSPENDED_KEYWORDS         = ["매매거래정지"]
_WARNING_KEYWORDS           = ["상장폐지"]  # 포괄적 (위 키워드에 걸리지 않은 것)


def _is_on_hold(report_nm: str) -> bool:
    """공시 제목이 '절차가 진행되지 않는다/다투는 중'을 뜻하는가 — 확정 판정의 보류 게이트."""
    if any(kw in report_nm for kw in _DELIST_HOLD_KEYWORDS):
        return True
    return (_INJUNCTION_KEYWORD in report_nm
            and not any(kw in report_nm for kw in _INJUNCTION_RESUME_KEYWORDS))


def is_confirmed_delisting(report_nm: str) -> bool:
    """공시 제목이 상장폐지 **확정**(결정·예고·정리매매 진행)인가 — 확정 판정의 단일 정본.

    확정은 `DELISTING_SCHEDULED`(아직 상장 상태 — 정리매매로 매도 가능)까지다. 폐지가
    **완료**됐다는 뜻이 아니므로 시세를 끊는 상장폐지 원장(`data/delisted-stocks.json`)에
    이 판정으로 등록하지 않는다 — 원장은 KRX 명부 이탈(완료)만 담는다(FR-VM-068b).

    거래정지·심사·이의신청·절차 미진행은 확정이 아니다(엔드포인트 계약: "거래정지·심사 중인
    건은 자동 등록하지 않는다"). 확정 낱말과 보류 낱말이 같이 있으면 보류가 이긴다.
    """
    if _is_on_hold(report_nm):
        return False
    return any(kw in report_nm for kw in _CONFIRMED_DELIST_KEYWORDS)


def classify_dart_notice(report_nm: str) -> str:
    """DART 공시 report_nm을 ListingStatus로 분류"""
    if _is_on_hold(report_nm):
        # 절차 미진행·이의신청·가처분 계류 중 — 확정(예정)이 아니라 심사·유보 상태로 본다.
        return ListingStatus.DELISTING_REVIEW
    if is_confirmed_delisting(report_nm):
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

def update_stock_listing_status(
    symbol: str,
    status: str,
    suspension_reason: Optional[str] = None,
    delisting_date: Optional[str] = None,
    last_tradable_date: Optional[str] = None,
    risk_flags: Optional[list] = None,
) -> None:
    """Stock 테이블의 listingStatus 필드를 업데이트"""
    now = db.now()
    risk_flags_json = json.dumps(risk_flags, ensure_ascii=False) if risk_flags else None

    con = db.connect()
    try:
        # Stock row가 없으면 삽입
        existing = con.execute('SELECT id FROM "Stock" WHERE symbol = ?', (symbol,)).fetchone()
        if existing:
            con.execute("""
                UPDATE "Stock" SET
                    "listingStatus" = ?,
                    "suspensionReason" = COALESCE(?, "suspensionReason"),
                    "delistingDate" = COALESCE(?, "delistingDate"),
                    "lastTradableDate" = COALESCE(?, "lastTradableDate"),
                    "riskFlags" = COALESCE(?, "riskFlags"),
                    "statusUpdatedAt" = ?,
                    "updatedAt" = ?
                WHERE symbol = ?
            """, (status, suspension_reason, delisting_date, last_tradable_date, risk_flags_json, now, now, symbol))
        else:
            con.execute("""
                INSERT INTO "Stock" (symbol, "listingStatus", "suspensionReason", "delistingDate",
                    "lastTradableDate", "riskFlags", "statusUpdatedAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, status, suspension_reason, delisting_date, last_tradable_date, risk_flags_json, now, now))
        con.commit()
    finally:
        con.close()


def get_stock_listing_status(symbol: str) -> str:
    """Stock 테이블에서 listingStatus 조회. 없으면 NORMAL 반환."""
    con = db.connect()
    try:
        row = con.execute('SELECT "listingStatus" FROM "Stock" WHERE symbol = ?', (symbol,)).fetchone()
        return row[0] if row else ListingStatus.NORMAL
    finally:
        con.close()


def get_stocks_by_status(status: str) -> list[dict]:
    """특정 listingStatus를 가진 종목 목록 조회"""
    con = db.connect()
    try:
        rows = con.execute("""
            SELECT symbol, name, "listingStatus", "suspensionReason",
                   "delistingDate", "lastTradableDate", "riskFlags", "statusUpdatedAt"
            FROM "Stock" WHERE "listingStatus" = ?
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


def clear_delisted_status(symbol: str) -> bool:
    """오등록 정정 — DELISTED로 굳은 상태를 NORMAL로 되돌린다. 되돌렸으면 True.

    `sync_from_dart_notices`는 DELISTED를 강등하지 않는다(폐지 완료는 번복하지 않는다는
    정상 계약). 그래서 원장 오등록으로 DELISTED가 된 종목은 공시·시세가 정상으로 돌아와도
    스스로 회복하지 못하고 0원 평가에 갇힌다 — 원장 해제(`DELETE /market/delist/{symbol}`)만
    이 강등을 수행한다. NORMAL로 되돌린 뒤 실제 상태는 거래정지 플래그(sync_trading_halt)와
    공시 분류가 다시 채운다.
    """
    if get_stock_listing_status(symbol) != ListingStatus.DELISTED:
        return False
    now = db.now()
    con = db.connect()
    try:
        con.execute("""
            UPDATE "Stock" SET
                "listingStatus" = ?,
                "suspensionReason" = NULL,
                "delistingDate" = NULL,
                "lastTradableDate" = NULL,
                "riskFlags" = NULL,
                "statusUpdatedAt" = ?,
                "updatedAt" = ?
            WHERE symbol = ?
        """, (ListingStatus.NORMAL, now, now, symbol))
        con.commit()
    finally:
        con.close()
    return True


def sync_trading_halt(halt_flags: dict[str, bool]) -> dict[str, str]:
    """시세 제공자의 거래정지 플래그(KIS 종목상태코드 58) → Stock.listingStatus 동기화.

    DART 공시 폴링이 놓친 거래정지 종목을 시세 수신 경로에서 자동 보정한다.
    - True:  NORMAL/WARNING/RISK → TRADING_SUSPENDED (Stock 행이 없으면 생성)
    - False: TRADING_SUSPENDED → NORMAL (거래 재개)
    - DELISTING_REVIEW/DELISTING_SCHEDULED/DELISTED는 건드리지 않는다 (DART 분류 우선)

    Returns: {symbol: new_status} 변경된 종목 매핑
    """
    if not halt_flags:
        return {}

    symbols = list(halt_flags.keys())
    placeholders = ",".join("?" for _ in symbols)
    con = db.connect()
    try:
        rows = con.execute(
            f'SELECT symbol, "listingStatus" FROM "Stock" WHERE symbol IN ({placeholders})',
            tuple(symbols),
        ).fetchall()
    finally:
        con.close()
    current_map = {row[0]: row[1] for row in rows}

    changed: dict[str, str] = {}
    for sym, halted in halt_flags.items():
        current = current_map.get(sym, ListingStatus.NORMAL)
        if halted and current in (ListingStatus.NORMAL, ListingStatus.WARNING, ListingStatus.RISK):
            update_stock_listing_status(
                sym,
                ListingStatus.TRADING_SUSPENDED,
                suspension_reason="매매거래정지 (KIS 종목상태코드 58)",
                risk_flags=[ListingStatus.TRADING_SUSPENDED, "KIS_STAT_58"],
            )
            changed[sym] = ListingStatus.TRADING_SUSPENDED
        elif halted is False and current == ListingStatus.TRADING_SUSPENDED:
            update_stock_listing_status(sym, ListingStatus.NORMAL)
            changed[sym] = ListingStatus.NORMAL
    return changed


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
    con = db.connect()
    try:
        con.execute("""
            INSERT INTO "DelistingAuditLog"
                (id, "accountId", symbol, "actionType", "previousStatus", "newStatus",
                 quantity, "executionPrice", reason, "createdAt")
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()), account_id, symbol, action_type,
            previous_status, new_status, quantity, execution_price,
            reason, db.now(),
        ))
        con.commit()
    finally:
        con.close()
