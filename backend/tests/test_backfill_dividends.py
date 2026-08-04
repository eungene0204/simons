"""Tests for scripts/backfill_dividends.py (dividend backfill, offline).

The pykrx provider needs network/KRX creds, so these tests inject a stub provider
and exercise the pure series-building logic + the parquet round-trip end to end.
"""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

# Load the script module by path (scripts/ is not a package).
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_dividends.py"
_spec = importlib.util.spec_from_file_location("backfill_dividends", _SCRIPT)
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)


# ── pure build_dividend_series ────────────────────────────────────────────────
def test_dividend_placed_on_last_trading_day_at_or_before_record_date():
    dates = pd.DatetimeIndex(pd.to_datetime([
        "2021-12-29", "2021-12-30", "2022-01-03", "2022-12-28", "2022-12-29",
        "2023-01-02",
    ]))
    # 기준일 12-31은 휴장 → 직전 거래일(12-30 / 12-29)에 찍힌다.
    series = bf.build_dividend_series(dates, {"20211231": 361.0, "20221231": 1444.0})
    assert series.loc["2021-12-30"] == 361.0
    assert series.loc["2022-12-29"] == 1444.0
    assert series.loc["2021-12-29"] == 0.0
    assert series.loc["2022-01-03"] == 0.0
    assert series.loc["2023-01-02"] == 0.0
    assert series.sum() == pytest.approx(1805.0)


def test_interim_dividend_lands_on_its_own_record_date():
    """회귀: 중간배당을 연말로 몰지 않는다 — TTM 창 겹침(2026-08-04 사고)의 근본."""
    dates = pd.DatetimeIndex(pd.date_range("2024-01-01", "2024-12-31", freq="B"))
    series = bf.build_dividend_series(dates, {"20240628": 361.0, "20241231": 1444.0})

    assert series.loc["2024-06-28"] == 361.0   # 중간배당은 6월에 남는다
    assert series.loc["2024-12-31"] == 1444.0
    assert (series > 0).sum() == 2             # 연말 한 점으로 합쳐지지 않음


def test_partial_current_year_does_not_stack_onto_prior_year_end():
    """회귀: 진행 중인 해의 부분 배당이 직전 연말 배당과 TTM 창에서 겹쳐 세지지 않는다.

    구 구현은 연도별 **합계**를 '그 해 마지막 거래일'(진행 중인 해에서는 오늘)에 몰아
    찍었다. 직전 연말 배치와 몇 달 간격이 되어 둘 다 252거래일 창에 들어오고, TTM이
    '1년 배당 + 올해 부분 배당'으로 부풀었다(삼성전자 실측 1,668 → 2,414원).
    기준일 배치는 분기배당을 제 날짜에 흩어 TTM이 정확히 최근 4개 분기가 되게 한다.
    """
    dates = pd.DatetimeIndex(pd.date_range("2024-01-01", "2025-08-01", freq="B"))
    quarterly = {
        "20240329": 361.0, "20240628": 361.0, "20240930": 361.0, "20241231": 361.0,
        "20250331": 373.0, "20250630": 373.0,   # 2025년은 아직 2개 분기만 지급
    }
    series = bf.build_dividend_series(dates, quarterly)

    assert (series > 0).sum() == 6              # 여섯 건이 각자의 기준일에 남는다
    ttm = series.rolling(252, min_periods=1).sum().iloc[-1]
    # 최근 4개 분기 = 2024-09 + 2024-12 + 2025-03 + 2025-06
    assert ttm == pytest.approx(361.0 + 361.0 + 373.0 + 373.0)
    # 구 방식(연도 합계를 연말/오늘에 몰아 찍기)이었다면 2024 전액 1,444 + 2025 부분 746
    # = 2,190원이 같은 창에 들어와 1년치보다 49% 부풀었다.
    assert ttm < 2190.0


def test_scheduled_future_dividend_is_not_pulled_back():
    """회귀: KIS 배당일정은 예정 배당도 준다 — 마지막 봉에 찍으면 미래 정보 누출."""
    dates = pd.DatetimeIndex(pd.date_range("2026-01-01", "2026-08-03", freq="B"))
    series = bf.build_dividend_series(dates, {"20260630": 373.0, "20261231": 1000.0})
    assert series.loc["2026-06-30"] == 373.0     # 이미 지난 기준일은 반영
    assert series.sum() == pytest.approx(373.0)  # 미도래 연말 배당은 제외


def test_post_delisting_liquidation_is_not_stamped_on_last_bar():
    """회귀: 상폐 후 청산 분배금을 마지막 봉에 찍으면 배당수익률 100%+ 유령 고배당주가 된다.

    실측(2026-08-04): 스팩·상폐 종목 17개가 마지막 봉 +82~+454일 기준일의 청산 분배금을
    받아 배당수익률 100~150%로 튀었다(460280 13,426원 vs 종가 8,915원 등). 엔진은 상폐 시
    강제청산하므로 이 분배금은 실제로 받지 못한다.
    """
    dates = pd.DatetimeIndex(pd.date_range("2024-01-01", "2024-12-30", freq="B"))
    series = bf.build_dividend_series(dates, {
        "20240628": 100.0,     # 상장 중 정상 배당 -> 반영
        "20260329": 13426.0,   # 상폐 +454일 청산 분배금 -> 제외
    })
    assert series.loc["2024-06-28"] == 100.0
    assert series.sum() == pytest.approx(100.0)


def test_same_trading_day_dividends_are_summed():
    """휴장 구간에 기준일이 몰리면 같은 거래일로 떨어진다 — 덮어쓰지 않고 합산."""
    dates = pd.DatetimeIndex(pd.to_datetime(["2024-12-27", "2024-12-30", "2025-01-02"]))
    series = bf.build_dividend_series(dates, {"20241231": 100.0, "20250101": 50.0})
    assert series.loc["2024-12-30"] == pytest.approx(150.0)


def test_skips_zero_unparseable_and_out_of_range():
    dates = pd.DatetimeIndex(pd.to_datetime(["2020-12-30", "2021-12-30", "2022-01-03"]))
    series = bf.build_dividend_series(dates, {
        "20201231": 0.0,      # 0 -> 제외
        "20211231": 100.0,
        "20991231": 500.0,    # 마지막 봉 이후 -> 제외
        "19991231": 300.0,    # 첫 봉 이전 -> 제외
        "not-a-date": 700.0,  # 파싱 불가 -> 제외
    })
    assert series.sum() == pytest.approx(100.0)


def test_empty_inputs():
    assert bf.build_dividend_series(pd.DatetimeIndex([]), {"20211231": 100.0}).empty
    dates = pd.DatetimeIndex(pd.to_datetime(["2021-12-30"]))
    assert bf.build_dividend_series(dates, {}).sum() == 0.0


def test_pykrx_provider_returns_empty_on_failure():
    # No network/creds in test env -> graceful empty dict, never raises.
    assert bf.dps_by_year_end_from_pykrx("000000", "20200101", "20201231") == {}


def test_end_date_default_tracks_today_not_a_hardcoded_year():
    """회귀: 종료일 상수 박기(20251231)로 당해 배당이 통째로 누락됐다(2026-08-04)."""
    assert bf._today() == pd.Timestamp.now().strftime("%Y%m%d")


# ── KIS provider parsing (pure, no network) ───────────────────────────────────
def test_parse_kis_dividends_keys_by_record_date():
    records = [
        {"record_date": "20211230", "per_sto_divi_amt": "361"},   # 2021 기말
        {"record_date": "20210630", "per_sto_divi_amt": "361"},   # 2021 중간 -> 별도 기준일
        {"record_date": "20221230", "per_sto_divi_amt": "1,444"}, # 콤마 포함
        {"record_date": "20231230", "per_sto_divi_amt": "0"},     # 0 -> 제외
        {"record_date": "", "per_sto_divi_amt": "100"},            # 날짜 없음 -> 제외
    ]
    out = bf._parse_kis_dividends(records)
    assert out == {"20211230": 361.0, "20210630": 361.0, "20221230": 1444.0}


def test_parse_kis_dividends_sums_same_record_date():
    records = [
        {"record_date": "20211230", "per_sto_divi_amt": "361"},
        {"record_date": "20211230", "per_sto_divi_amt": "100"},
    ]
    assert bf._parse_kis_dividends(records) == {"20211230": 461.0}


def test_parse_kis_dividends_handles_empty():
    assert bf._parse_kis_dividends([]) == {}
    assert bf._parse_kis_dividends(None) == {}


def test_parse_kis_dividends_split_adjusts_via_face_val():
    # Samsung 50:1 split (face 5000 -> 100): pre-split DPS must be /50 to match
    # the split-adjusted parquet prices. 17700 * (100/5000) = 354.
    records = [
        {"record_date": "20171231", "per_sto_divi_amt": "21500", "face_val": "5000"},
        {"record_date": "20241231", "per_sto_divi_amt": "363", "face_val": "100"},
    ]
    out = bf._parse_kis_dividends(records)
    assert out["20171231"] == pytest.approx(430.0)  # 21500 * (100/5000), back-adjusted
    assert out["20241231"] == pytest.approx(363.0)  # current basis unchanged


def test_parse_kis_dividends_ignores_corrupt_face_value():
    """회귀: 정본 밖 액면가가 조정 기준이 되면 배당이 뻥튀기된다.

    실측(2026-08-04): 002005의 폐지 후 레코드 액면가가 500,000원(정상 배당기 5,000원)이라
    과거 배당이 100배가 되어 배당수익률 1,069%가 나왔다. KRX 액면가는 6종뿐이다.
    """
    records = [
        {"record_date": "20171231", "per_sto_divi_amt": "1050", "face_val": "5000"},
        {"record_date": "20181231", "per_sto_divi_amt": "825", "face_val": "5000"},
        {"record_date": "20211231", "per_sto_divi_amt": "0", "face_val": "500000"},
        {"record_date": "20241231", "per_sto_divi_amt": "0", "face_val": "500000"},
    ]
    out = bf._parse_kis_dividends(records)
    assert out == {"20171231": 1050.0, "20181231": 825.0}   # 무조정(기준=5000/5000)


def test_parse_kis_dividends_uses_split_after_last_dividend():
    """회귀: 마지막 배당 **이후** 액면분할한 종목도 역조정돼야 한다.

    조정 기준을 '배당이 있는 레코드 중 최신'으로 좁히면 분할 전 액면가가 기준이 되어
    역조정이 사라진다 — 실측 001080(1,000→100)·002420·006345(5,000→500)가 10배로 남았다.
    무배당 레코드도 '현재 액면가'는 정확히 알려준다.
    """
    records = [
        {"record_date": "20091231", "per_sto_divi_amt": "1000", "face_val": "5000"},
        {"record_date": "20251231", "per_sto_divi_amt": "0", "face_val": "500"},  # 분할 후
    ]
    out = bf._parse_kis_dividends(records)
    assert out == {"20091231": pytest.approx(100.0)}   # 1000 * (500/5000)


def test_parse_kis_dividends_no_face_val_is_unadjusted():
    records = [{"record_date": "20211230", "per_sto_divi_amt": "1444"}]
    assert bf._parse_kis_dividends(records) == {"20211230": 1444.0}


def test_kis_provider_composes_parser_over_fetch(monkeypatch):
    # Offline: stub the network layer; verify the provider parses it.
    monkeypatch.setattr(bf, "_kis_dividend_records", lambda sym, s, e: [
        {"record_date": "20211230", "per_sto_divi_amt": "1444"},
    ])
    assert bf.dps_by_record_date_from_kis(
        "005930", "20200101", "20231231") == {"20211230": 1444.0}


def test_kis_provider_graceful_when_fetch_empty(monkeypatch):
    monkeypatch.setattr(bf, "_kis_dividend_records", lambda sym, s, e: [])
    assert bf.dps_by_record_date_from_kis("005930", "20200101", "20231231") == {}


def test_kis_is_default_provider():
    assert bf.PROVIDERS["kis"] is bf.dps_by_record_date_from_kis


# ── end-to-end parquet round-trip with a stub provider ────────────────────────
def _make_parquet(tmp_path: Path) -> Path:
    # 2022 기말(12-31) 기준일 배당이 마지막 봉 이후로 밀리지 않도록 2023년까지 둔다.
    df = pd.DataFrame({
        "date": pd.date_range("2021-01-01", "2023-01-31", freq="B").astype(str),
        "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000,
    })
    p = tmp_path / "005930.parquet"
    df.to_parquet(p)
    return p


def test_dry_run_does_not_write(tmp_path):
    p = _make_parquet(tmp_path)
    stub = lambda sym, s, e: {"20211231": 361.0, "20221231": 1444.0}  # noqa: E731
    stats = bf.backfill_file(p, stub, dry_run=True)
    assert stats["status"] == "dry-run"
    assert stats["events"] == 2
    # File on disk must be untouched (no dividends column persisted).
    assert "dividends" not in pd.read_parquet(p).columns


def test_write_adds_dividends_column(tmp_path):
    p = _make_parquet(tmp_path)
    stub = lambda sym, s, e: {"20211231": 361.0, "20221231": 1444.0}  # noqa: E731
    stats = bf.backfill_file(p, stub, dry_run=False)
    assert stats["status"] == "written"
    out = pd.read_parquet(p)
    assert "dividends" in out.columns
    assert out["dividends"].sum() == pytest.approx(1805.0)
    assert (out["dividends"] > 0).sum() == 2


def test_backfilled_parquet_feeds_total_return_engine(tmp_path):
    """The backfilled column must be consumable by loader total-return path."""
    import polars as pl
    from engine.loader import DataLoader

    p = _make_parquet(tmp_path)
    bf.backfill_file(p, lambda sym, s, e: {"20211231": 5.0}, dry_run=False)

    loader = DataLoader(data_dir=str(tmp_path))
    out = loader.preprocess_data(pl.read_parquet(p), apply_dividends=True)
    # Flat 100 price + a 5/share dividend in 2021 -> total-return close steps up.
    assert float(out["close"].iloc[-1]) > 100.0
