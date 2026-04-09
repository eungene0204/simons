from typing import Optional


def normalize_market_cap(
    raw_market_cap: int,
    market_cap_key: Optional[str],
    listed_shares: int,
    current_price: int,
) -> int:
    derived_market_cap = current_price * listed_shares if listed_shares > 0 and current_price > 0 else 0

    # 상장주식수와 현재가가 있으면 그 곱이 가장 신뢰할 수 있는 시가총액이다.
    # KIS 상세 응답의 market-cap 계열 필드는 간헐적으로 0이거나 잘못된 단위/값으로 들어올 수 있다.
    if derived_market_cap > 0:
        return derived_market_cap

    market_cap = raw_market_cap

    if market_cap_key in {"hts_avls", "stck_avls"} and market_cap > 0:
        market_cap *= 100_000_000

    return market_cap
