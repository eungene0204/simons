import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine import dart_client


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_fetch_delisting_notices_filters_relevant_disclosures(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-key")
    captured = {}

    def mock_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return _Response({
            "status": "000",
            "total_count": 4,
            "list": [
                {
                    "stock_code": "5930",
                    "corp_name": "삼성전자",
                    "report_nm": "상장폐지결정",
                    "rcept_dt": "20260527",
                    "rcept_no": "1",
                },
                {
                    "stock_code": "000660",
                    "corp_name": "SK하이닉스",
                    "report_nm": "매매거래정지 해제",
                    "rcept_dt": "20260527",
                    "rcept_no": "2",
                },
                {
                    "stock_code": "000001",
                    "corp_name": "테스트",
                    "report_nm": "변경상장",
                    "rcept_dt": "20260527",
                    "rcept_no": "3",
                },
                {
                    "stock_code": "000002",
                    "corp_name": "테스트2",
                    "report_nm": "상장적격성 실질심사 대상",
                    "rcept_dt": "20260527",
                    "rcept_no": "4",
                },
            ],
        })

    monkeypatch.setattr(dart_client.requests, "get", mock_get)

    result = dart_client.fetch_delisting_notices("20260501", "20260527", corp_code="00126380")

    assert captured["url"].endswith("/list.json")
    assert captured["params"]["crtfc_key"] == "test-key"
    assert captured["params"]["pblntf_ty"] == "I"
    assert captured["params"]["corp_code"] == "00126380"
    assert captured["timeout"] == 15
    assert result == [
        {
            "stock_code": "005930",
            "corp_name": "삼성전자",
            "report_nm": "상장폐지결정",
            "rcept_dt": "20260527",
            "rcept_no": "1",
        },
        {
            "stock_code": "000002",
            "corp_name": "테스트2",
            "report_nm": "상장적격성 실질심사 대상",
            "rcept_dt": "20260527",
            "rcept_no": "4",
        },
    ]


def test_fetch_delisting_notices_returns_empty_without_api_key(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)

    result = dart_client.fetch_delisting_notices("20260501", "20260527")

    assert result == []
