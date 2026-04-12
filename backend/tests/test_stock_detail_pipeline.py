import os
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import _extract_latest_debt_ratio, _fetch_kis_stock_detail, _financial_ratio_cache


class _MockResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_extract_latest_debt_ratio_uses_most_recent_period():
    result = _extract_latest_debt_ratio([
        {"stac_yymm": "202412", "lblt_rate": "45.50"},
        {"stac_yymm": "202512", "lblt_rate": "38.25"},
        {"stac_yymm": "202312", "lblt_rate": "55.10"},
    ])

    assert result == 38.25


def test_extract_latest_debt_ratio_skips_invalid_values():
    result = _extract_latest_debt_ratio([
        {"stac_yymm": "202412", "lblt_rate": "-"},
        {"stac_yymm": "202512", "lblt_rate": "0"},
        {"stac_yymm": "202612", "lblt_rate": ""},
    ])

    assert result is None


def test_fetch_kis_stock_detail_includes_debt_ratio(monkeypatch):
    _financial_ratio_cache.clear()

    def mock_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/quotations/inquire-price"):
            return _MockResponse(200, {
                "output": {
                    "hts_kor_isnm": "삼성전자",
                    "stck_prpr": "72500",
                    "stck_oprc": "72000",
                    "stck_hgpr": "72800",
                    "stck_lwpr": "71800",
                    "acml_vol": "12500000",
                    "stck_sdpr": "70770",
                    "prdy_ctrt": "2.44",
                    "hts_avls": "432000000000000",
                    "perx": "12.50",
                    "pbrx": "1.20",
                }
            })

        if url.endswith("/finance/financial-ratio"):
            return _MockResponse(200, {
                "output": [
                    {"stac_yymm": "202412", "lblt_rate": "28.10"},
                    {"stac_yymm": "202512", "lblt_rate": "25.75"},
                ]
            })

        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("main.requests.get", mock_get)

    result = _fetch_kis_stock_detail("005930", "app-key", "app-secret", "token")

    assert result is not None
    assert result["symbol"] == "005930"
    assert result["debtRatio"] == 25.75
    assert result["per"] == 12.5
    assert result["pbr"] == 1.2
