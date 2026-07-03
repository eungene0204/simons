"""
fundamental_fetcher 모듈 유닛 테스트.
Naver Finance 스크래핑 없이 파싱/enrichment 로직을 검증한다.
"""

import pandas as pd
import pytest

from engine.fundamental_fetcher import (
    _parse_kis_financial_ratio_output,
    _parse_fundamentals,
    _parse_number,
    _read_cache,
    _write_cache,
    _is_recently_confirmed_empty,
    _write_negative_cache,
    enrich_ohlcv_with_fundamentals,
    fetch_fundamentals,
)

# ── _parse_number ──

def test_parse_number_normal():
    assert _parse_number("52,002") == 52002.0

def test_parse_number_negative():
    assert _parse_number("-12,517") == -12517.0

def test_parse_number_empty():
    assert _parse_number("") is None

def test_parse_number_dash():
    assert _parse_number("-") is None

def test_parse_number_no_comma():
    assert _parse_number("6564") == 6564.0


# ── _parse_fundamentals ──

_SAMPLE_HTML = """
<html><body>
<table>
<tr><th>주요재무정보</th><th colspan="4">최근 연간 실적</th><th colspan="6">최근 분기 실적</th></tr>
<tr><td>2023.12</td><td>2024.12</td><td>2025.12</td><td>2026.12(E)</td>
    <td>2024.12</td><td>2025.03</td><td>2025.06</td><td>2025.09</td><td>2025.12</td><td>2026.03(E)</td></tr>
<tr><td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td>
    <td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td></tr>
<tr><td>매출액</td><td>100</td><td>200</td><td>300</td><td>400</td>
    <td>50</td><td>55</td><td>60</td><td>65</td><td>70</td><td>75</td></tr>
<tr><td>ROE(지배주주)</td><td>4.15</td><td>9.03</td><td>10.85</td><td>44.98</td>
    <td>9.03</td><td>9.03</td><td>9.03</td><td>9.03</td><td>9.03</td><td></td></tr>
<tr><td>부채비율</td><td>25.10</td><td>30.20</td><td>35.30</td><td>40.40</td>
    <td>30.20</td><td>30.20</td><td>30.20</td><td>30.20</td><td>30.20</td><td></td></tr>
<tr><td>EPS(원)</td><td>2,131</td><td>4,950</td><td>6,564</td><td>36,119</td>
    <td>1,115</td><td>1,186</td><td>733</td><td>1,783</td><td>2,864</td><td>5,298</td></tr>
<tr><td>BPS(원)</td><td>52,002</td><td>57,981</td><td>63,997</td><td>99,649</td>
    <td>57,981</td><td>59,059</td><td>58,135</td><td>60,632</td><td>63,997</td><td></td></tr>
</table>
</body></html>
"""


def test_parse_fundamentals_extracts_annual_data():
    result = _parse_fundamentals(_SAMPLE_HTML)
    assert result is not None
    assert len(result) == 3  # 2023.12, 2024.12, 2025.12 (2026.12(E) 제외)

    # 2023.12
    assert result[0]["year_end"] == "2023-12-31"
    assert result[0]["eps"] == 2131.0
    assert result[0]["bps"] == 52002.0

    # 2024.12
    assert result[1]["year_end"] == "2024-12-31"
    assert result[1]["eps"] == 4950.0
    assert result[1]["bps"] == 57981.0

    # 2025.12
    assert result[2]["year_end"] == "2025-12-31"
    assert result[2]["eps"] == 6564.0
    assert result[2]["bps"] == 63997.0


def test_parse_fundamentals_excludes_estimates():
    result = _parse_fundamentals(_SAMPLE_HTML)
    # 2026.12(E) 포함되지 않아야 함
    year_ends = [r["year_end"] for r in result]
    assert "2026-12-31" not in year_ends


def test_parse_fundamentals_no_table():
    html = "<html><body><p>No data</p></body></html>"
    assert _parse_fundamentals(html) is None


# ── _parse_kis_financial_ratio_output ──

def test_parse_kis_financial_ratio_output_extracts_roe_eps_bps():
    result = _parse_kis_financial_ratio_output([
        {
            "stac_yymm": "202512",
            "roe_val": "10.85",
            "eps": "6564.00",
            "bps": "63997.00",
            "lblt_rate": "35.30",
        },
        {
            "stac_yymm": "202412",
            "roe_val": "9.03",
            "eps": "4950.00",
            "bps": "57981.00",
            "lblt_rate": "30.20",
        },
    ])

    assert result == [
        {"year_end": "2025-12-31", "eps": 6564.0, "bps": 63997.0, "roe_or_gpa": 10.85, "debt_ratio": 35.3},
        {"year_end": "2024-12-31", "eps": 4950.0, "bps": 57981.0, "roe_or_gpa": 9.03, "debt_ratio": 30.2},
    ]


# ── enrich_ohlcv_with_fundamentals ──

def _make_ohlcv_df(dates, close_prices):
    """테스트용 간단한 OHLCV DataFrame 생성."""
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "open": close_prices,
        "high": close_prices,
        "low": close_prices,
        "close": close_prices,
        "volume": [1000] * len(dates),
    })


def test_enrich_adds_per_pbr_columns():
    # 2024-04-01 이후 = 2023.12 결산 데이터 적용 (결산일 + 90일)
    dates = ["2024-04-01", "2024-06-01", "2024-12-01"]
    close = [50000.0, 60000.0, 70000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "eps": 2000.0, "bps": 50000.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    assert "per" in result.columns
    assert "pbr" in result.columns
    assert "eps" in result.columns
    assert "bps" in result.columns
    assert "roe_or_gpa" in result.columns
    assert "debt_ratio" in result.columns

    # PER = close / EPS = 50000 / 2000 = 25.0
    assert result.iloc[0]["per"] == pytest.approx(25.0)
    # PBR = close / BPS = 50000 / 50000 = 1.0
    assert result.iloc[0]["pbr"] == pytest.approx(1.0)
    assert pd.isna(result.iloc[0]["roe_or_gpa"])
    assert pd.isna(result.iloc[0]["debt_ratio"])


def test_enrich_respects_publish_delay():
    """결산일 + 90일 이전에는 해당 연도 데이터가 적용되지 않아야 함."""
    # 2023-12-31 결산 + 90일 = 2024-03-30 (effective date)
    # 2024-03-29: 미공시, 2024-03-30: 공시일 (>= effective_date)
    dates = ["2024-02-01", "2024-03-29", "2024-03-30"]
    close = [50000.0, 50000.0, 50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "eps": 2000.0, "bps": 50000.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    # 2024-02-01, 2024-03-29: 아직 미공시 → NaN
    assert pd.isna(result.iloc[0]["per"])
    assert pd.isna(result.iloc[1]["per"])
    # 2024-03-30: 공시 후 → 값 있음
    assert result.iloc[2]["per"] == pytest.approx(25.0)


def test_enrich_forward_fill_updates_with_new_fiscal_year():
    """새로운 결산 데이터가 공시되면 PER/PBR이 업데이트되어야 함."""
    dates = ["2024-04-01", "2025-04-01"]
    close = [50000.0, 50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "eps": 2000.0, "bps": 50000.0},
        {"year_end": "2024-12-31", "eps": 5000.0, "bps": 60000.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    # 2024-04-01: 2023.12 데이터 → PER = 50000/2000 = 25
    assert result.iloc[0]["per"] == pytest.approx(25.0)
    # 2025-04-01: 2024.12 데이터 → PER = 50000/5000 = 10
    assert result.iloc[1]["per"] == pytest.approx(10.0)


def test_enrich_forward_fills_roe_or_gpa():
    dates = ["2024-04-01", "2025-04-01"]
    close = [50000.0, 50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "roe_or_gpa": 4.15},
        {"year_end": "2024-12-31", "roe_or_gpa": 9.03},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    assert result.iloc[0]["roe_or_gpa"] == pytest.approx(4.15)
    assert result.iloc[1]["roe_or_gpa"] == pytest.approx(9.03)


def test_enrich_forward_fills_debt_ratio():
    dates = ["2024-04-01", "2025-04-01"]
    close = [50000.0, 50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "debt_ratio": 45.5},
        {"year_end": "2024-12-31", "debt_ratio": 38.2},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    assert result.iloc[0]["debt_ratio"] == pytest.approx(45.5)
    assert result.iloc[1]["debt_ratio"] == pytest.approx(38.2)


def test_enrich_negative_eps_produces_negative_per():
    """적자 기업의 경우 음수 PER이 계산되어야 함."""
    dates = ["2024-04-01"]
    close = [50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "eps": -1000.0, "bps": 50000.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)
    assert result.iloc[0]["per"] == pytest.approx(-50.0)


def test_enrich_zero_eps_produces_nan_per():
    """EPS가 0이면 PER은 NaN이어야 함 (0 나누기 방지)."""
    dates = ["2024-04-01"]
    close = [50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "eps": 0.0, "bps": 50000.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)
    assert pd.isna(result.iloc[0]["per"])
    assert result.iloc[0]["pbr"] == pytest.approx(1.0)


def test_enrich_empty_fundamentals_no_change():
    """fundamentals가 비어있으면 원본 DataFrame이 반환되어야 함."""
    dates = ["2024-04-01"]
    close = [50000.0]
    df = _make_ohlcv_df(dates, close)

    result = enrich_ohlcv_with_fundamentals(df, [])
    assert "per" not in result.columns

    result2 = enrich_ohlcv_with_fundamentals(df, None)
    assert "per" not in result2.columns


# ── Naver ROE 파싱 ──

def test_parse_fundamentals_extracts_roe():
    """Naver Finance HTML에서 ROE 값이 파싱되어야 함."""
    result = _parse_fundamentals(_SAMPLE_HTML)
    assert result is not None
    # 2023.12
    assert result[0].get("roe_or_gpa") == 4.15
    # 2024.12
    assert result[1].get("roe_or_gpa") == 9.03
    # 2025.12
    assert result[2].get("roe_or_gpa") == 10.85


def test_parse_fundamentals_extracts_debt_ratio():
    result = _parse_fundamentals(_SAMPLE_HTML)
    assert result is not None
    assert result[0].get("debt_ratio") == 25.10
    assert result[1].get("debt_ratio") == 30.20
    assert result[2].get("debt_ratio") == 35.30


def test_parse_fundamentals_roe_excluded_for_estimates():
    """추정치(E) 연도의 ROE는 포함되지 않아야 함."""
    result = _parse_fundamentals(_SAMPLE_HTML)
    # 2026.12(E) → 제외됨
    year_ends = [r["year_end"] for r in result]
    assert "2026-12-31" not in year_ends


_SAMPLE_HTML_NO_ROE = """
<html><body>
<table>
<tr><th>주요재무정보</th><th colspan="2">최근 연간 실적</th></tr>
<tr><td>2023.12</td><td>2024.12</td></tr>
<tr><td>EPS(원)</td><td>1,000</td><td>2,000</td></tr>
<tr><td>BPS(원)</td><td>10,000</td><td>20,000</td></tr>
</table>
</body></html>
"""


def test_parse_fundamentals_no_roe_row():
    """ROE 행이 없는 HTML에서는 roe_or_gpa가 결과에 포함되지 않아야 함."""
    result = _parse_fundamentals(_SAMPLE_HTML_NO_ROE)
    assert result is not None
    for entry in result:
        assert "roe_or_gpa" not in entry


# ── 캐시 read/write ──

def test_cache_write_and_read(tmp_path, monkeypatch):
    """캐시 write 후 read가 동일한 데이터를 반환해야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)

    fundamentals = [
        {"year_end": "2024-12-31", "eps": 5000.0, "bps": 60000.0, "roe_or_gpa": 9.03},
    ]
    _write_cache("005930", fundamentals)
    result = _read_cache("005930")
    assert result == fundamentals


def test_cache_expired(tmp_path, monkeypatch):
    """만료된 캐시는 None을 반환해야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(ff, "_CACHE_MAX_AGE_DAYS", 0)

    fundamentals = [{"year_end": "2024-12-31", "roe_or_gpa": 9.03}]
    _write_cache("005930", fundamentals)

    # fetched_at을 과거로 수정
    import json
    cache_file = tmp_path / "005930.json"
    data = json.loads(cache_file.read_text())
    data["fetched_at"] = "2020-01-01T00:00:00"
    cache_file.write_text(json.dumps(data))

    result = _read_cache("005930")
    assert result is None


def test_cache_missing_symbol(tmp_path, monkeypatch):
    """캐시에 없는 종목은 None을 반환해야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)

    result = _read_cache("999999")
    assert result is None


# ── negative 캐시 (조회 실패 반복 방지) ──

def test_negative_cache_write_and_read(tmp_path, monkeypatch):
    """실패를 기록하면 TTL 이내에는 '최근 확인된 실패'로 인식돼야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)

    assert _is_recently_confirmed_empty("088980") is False
    _write_negative_cache("088980")
    assert _is_recently_confirmed_empty("088980") is True


def test_negative_cache_expired(tmp_path, monkeypatch):
    """TTL이 지난 negative 캐시는 더 이상 유효하지 않아야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(ff, "_NEGATIVE_CACHE_TTL_DAYS", 0)

    _write_negative_cache("088980")

    import json
    cache_file = tmp_path / "088980.nodata.json"
    data = json.loads(cache_file.read_text())
    data["checked_at"] = "2020-01-01T00:00:00"
    cache_file.write_text(json.dumps(data))

    assert _is_recently_confirmed_empty("088980") is False


def test_fetch_fundamentals_skips_network_when_recently_confirmed_empty(tmp_path, monkeypatch):
    """REITs처럼 KIS/Naver 둘 다 실패하는 종목은 negative 캐시 TTL 내에서 재조회하지 않아야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)

    kis_calls = {"n": 0}
    naver_calls = {"n": 0}

    def _fail_kis(symbol):
        kis_calls["n"] += 1
        return None

    class _FakeResp:
        status_code = 404
        text = ""

    def _fail_naver(*a, **k):
        naver_calls["n"] += 1
        return _FakeResp()

    monkeypatch.setattr(ff, "_fetch_fundamentals_from_kis", _fail_kis)
    monkeypatch.setattr(ff.requests, "get", _fail_naver)

    # 첫 호출: KIS+Naver 실패 → negative 캐시 기록
    result1 = fetch_fundamentals("088980", retry=0)
    assert result1 is None
    assert kis_calls["n"] == 1
    assert naver_calls["n"] == 1

    # 두 번째 호출: negative 캐시가 있으니 KIS/Naver를 다시 호출하지 않아야 함
    result2 = fetch_fundamentals("088980", retry=0)
    assert result2 is None
    assert kis_calls["n"] == 1
    assert naver_calls["n"] == 1
