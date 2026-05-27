"""
상장 상태 관리 모듈 테스트
"""
import pytest
from engine.listing_status import (
    ListingStatus,
    is_buy_allowed, is_sell_allowed, is_zero_valuation,
    get_trade_block_reason, classify_dart_notice,
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
