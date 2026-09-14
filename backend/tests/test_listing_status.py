"""
상장 상태 관리 모듈 테스트
"""
import pytest
from engine.listing_status import (
    ListingStatus,
    is_buy_allowed, is_sell_allowed, is_zero_valuation,
    get_trade_block_reason, classify_dart_notice, is_confirmed_delisting,
)


# ── 거래 허용 규칙 ─────────────────────────────────────────────────────────────

def test_normal_allows_all_trades():
    assert is_buy_allowed(ListingStatus.NORMAL) is True
    assert is_sell_allowed(ListingStatus.NORMAL) is True


def test_warning_allows_all_trades():
    assert is_buy_allowed(ListingStatus.WARNING) is True
    assert is_sell_allowed(ListingStatus.WARNING) is True


def test_trading_suspended_blocks_all_trades():
    assert is_buy_allowed(ListingStatus.TRADING_SUSPENDED) is False
    assert is_sell_allowed(ListingStatus.TRADING_SUSPENDED) is False


def test_delisting_review_blocks_buy_allows_sell():
    assert is_buy_allowed(ListingStatus.DELISTING_REVIEW) is False
    assert is_sell_allowed(ListingStatus.DELISTING_REVIEW) is True


def test_delisting_scheduled_blocks_buy_allows_sell():
    assert is_buy_allowed(ListingStatus.DELISTING_SCHEDULED) is False
    assert is_sell_allowed(ListingStatus.DELISTING_SCHEDULED) is True  # 정리매매 허용


def test_delisted_blocks_all_trades():
    assert is_buy_allowed(ListingStatus.DELISTED) is False
    assert is_sell_allowed(ListingStatus.DELISTED) is False


# ── 0원 평가 ───────────────────────────────────────────────────────────────────

def test_delisted_is_zero_valuation():
    assert is_zero_valuation(ListingStatus.DELISTED) is True


def test_other_statuses_not_zero_valuation():
    for status in [
        ListingStatus.NORMAL, ListingStatus.WARNING, ListingStatus.RISK,
        ListingStatus.TRADING_SUSPENDED, ListingStatus.DELISTING_REVIEW,
        ListingStatus.DELISTING_SCHEDULED,
    ]:
        assert is_zero_valuation(status) is False, f"{status} should not be zero valuation"


# ── 거래 차단 사유 ─────────────────────────────────────────────────────────────

def test_get_trade_block_reason_buy_normal():
    assert get_trade_block_reason(ListingStatus.NORMAL, "BUY") is None


def test_get_trade_block_reason_buy_suspended():
    reason = get_trade_block_reason(ListingStatus.TRADING_SUSPENDED, "BUY")
    assert reason is not None
    assert "매매거래정지" in reason


def test_get_trade_block_reason_buy_delisted():
    reason = get_trade_block_reason(ListingStatus.DELISTED, "BUY")
    assert reason is not None
    assert "상장폐지" in reason


def test_get_trade_block_reason_sell_suspended():
    reason = get_trade_block_reason(ListingStatus.TRADING_SUSPENDED, "SELL")
    assert reason is not None
    assert "거래" in reason


def test_get_trade_block_reason_sell_delisting_scheduled():
    # 정리매매 기간에는 SELL 허용
    assert get_trade_block_reason(ListingStatus.DELISTING_SCHEDULED, "SELL") is None


# ── DART 공시 분류 ─────────────────────────────────────────────────────────────

def test_classify_dart_delisting_decision():
    assert classify_dart_notice("주권상장폐지결정") == ListingStatus.DELISTING_SCHEDULED


def test_classify_dart_cleanup_trading():
    assert classify_dart_notice("정리매매 기간 안내") == ListingStatus.DELISTING_SCHEDULED


def test_classify_dart_delisting_notice():
    assert classify_dart_notice("상장폐지예고") == ListingStatus.DELISTING_SCHEDULED


def test_classify_dart_review():
    assert classify_dart_notice("상장적격성 심사 결과") == ListingStatus.DELISTING_REVIEW


def test_classify_dart_management_stock():
    assert classify_dart_notice("관리종목 지정") == ListingStatus.DELISTING_REVIEW


def test_classify_dart_trading_suspension():
    assert classify_dart_notice("매매거래정지 공시") == ListingStatus.TRADING_SUSPENDED


def test_classify_dart_general_delisting():
    assert classify_dart_notice("상장폐지 사유 발생") == ListingStatus.WARNING


# ── 상태 전이 우선순위 ─────────────────────────────────────────────────────────

def test_priority_order():
    """DELISTED > DELISTING_SCHEDULED > TRADING_SUSPENDED > DELISTING_REVIEW > WARNING > NORMAL"""
    from engine.listing_status import _priority  # noqa: PLC2701
    assert _priority[ListingStatus.DELISTED] > _priority[ListingStatus.DELISTING_SCHEDULED]
    assert _priority[ListingStatus.DELISTING_SCHEDULED] > _priority[ListingStatus.TRADING_SUSPENDED]
    assert _priority[ListingStatus.TRADING_SUSPENDED] > _priority[ListingStatus.DELISTING_REVIEW]
    assert _priority[ListingStatus.DELISTING_REVIEW] > _priority[ListingStatus.WARNING]
    assert _priority[ListingStatus.WARNING] > _priority[ListingStatus.NORMAL]


# ── 절차 미진행·이의신청은 확정이 아니다(2026-09-15 신라에스지 오등록) ─────────────────

def test_hold_notice_is_not_confirmed_delisting():
    """"상장폐지 및 정리매매 절차 미진행"은 '정리매매' 낱말이 있어도 확정이 아니다 — 종전엔
    낱말 포함만 보고 상장폐지 명부에 자동 등록해 정상 거래 종목(025870)의 시세 조회를 막았다."""
    title = "기타시장안내              (상장폐지 및 정리매매 절차 미진행)"
    assert is_confirmed_delisting(title) is False
    assert classify_dart_notice(title) == ListingStatus.DELISTING_REVIEW


def test_objection_notice_is_review_not_scheduled():
    title = "기타시장안내              (상장폐지 관련 이의신청서 접수)"
    assert is_confirmed_delisting(title) is False
    assert classify_dart_notice(title) == ListingStatus.DELISTING_REVIEW


def test_resumed_cleanup_trading_stays_confirmed():
    """'기각'은 보류 낱말이 아니다 — 가처분 기각으로 정리매매가 **재개**된 건은 진짜 확정."""
    title = "기타시장안내              (상장폐지결정 등 효력정지 가처분 신청 기각에 따른 정리매매절차 재개)"
    assert is_confirmed_delisting(title) is True
    assert classify_dart_notice(title) == ListingStatus.DELISTING_SCHEDULED


def test_suspension_for_delisting_cause_is_not_confirmed():
    """'상장폐지 사유발생'에 따른 거래정지는 확정이 아니라 정지 상태다."""
    title = "주권매매거래정지              (상장폐지 사유발생)"
    assert is_confirmed_delisting(title) is False
    assert classify_dart_notice(title) == ListingStatus.TRADING_SUSPENDED
