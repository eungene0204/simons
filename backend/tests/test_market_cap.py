import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from market_cap import normalize_market_cap


def test_normalize_market_cap_converts_kis_eok_units_to_krw():
    assert normalize_market_cap(12_475_253, "hts_avls", 0, 0) == 1_247_525_300_000_000


def test_normalize_market_cap_falls_back_to_price_times_listed_shares():
    assert normalize_market_cap(0, None, 728_002_365, 68_500) == 49_868_162_002_500


def test_normalize_market_cap_replaces_implausibly_small_value_with_derived_value():
    assert normalize_market_cap(12_475_253_000, "mrkt_cap", 728_002_365, 68_500) == 49_868_162_002_500
