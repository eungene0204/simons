"""유니버스별 지원 팩터 레지스트리 테스트 — ETF는 기업 재무지표 불가, 기술/가격 파생 허용."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.universe_capabilities import (
    fundamental_metric_supported,
    is_etf_strategy,
    universe_kind,
    unsupported_fundamental_metrics,
)


def test_universe_kind():
    assert universe_kind(["KOSPI"]) == "STOCK"
    assert universe_kind(["ETF"]) == "ETF"
    assert universe_kind(None) == "STOCK"
    assert is_etf_strategy(["ETF"])
    assert not is_etf_strategy(["KOSPI200"])


def test_stock_universe_supports_all_fundamentals():
    assert fundamental_metric_supported(["KOSPI"], "per")
    assert fundamental_metric_supported(["KOSPI200"], "market_cap")


def test_etf_universe_rejects_fundamentals_but_allows_price_derived():
    assert not fundamental_metric_supported(["ETF"], "per")
    assert not fundamental_metric_supported(["ETF"], "roe_or_gpa")
    # 시가총액은 ETF에선 AUM이라 의미가 달라 미지원.
    assert not fundamental_metric_supported(["ETF"], "market_cap")
    # 거래대금은 가격·거래량 파생이라 허용.
    assert fundamental_metric_supported(["ETF"], "trading_value")


def test_unsupported_fundamental_metrics_order_and_dedup():
    out = unsupported_fundamental_metrics(
        ["ETF"], ["per", "trading_value", "pbr", "per"]
    )
    assert out == ["per", "pbr"]
    assert unsupported_fundamental_metrics(["KOSPI"], ["per", "pbr"]) == []
