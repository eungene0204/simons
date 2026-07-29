"""신규 상장(IPO) 유니버스 — 엔진 필터 회귀 (FR-STR-073).

"2026년 신규 상장 종목"은 상장일이 그 구간에 속하는 종목 집합이다. 이 테스트는 실제
엔진을 돌려 ① 구간 밖 상장 종목이 유니버스에 남지 않고 ② 상장일을 알 수 없는 종목이
조용히 섞이지 않으며 ③ 공집합이 0거래로 위장되지 않는다는 것을 잠근다.

실측 사고(2026-07-29): 이 필터가 없어 "2026년 신규 상장 종목 투자 전략"이 코스피·코스닥
전 종목(삼양홀딩스·CJ대한통운 등)을 매매했다.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from backtest_engine import BacktestEngine
from engine import universe_pit

_DATES = pd.bdate_range("2024-01-01", "2024-12-31")


def _write_parquet(path: Path, dates: pd.DatetimeIndex):
    n = len(dates)
    df = pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.0] * n,
        "volume": [1_000_000] * n,
        "roe_or_gpa": [0.1] * n,   # present -> no network fundamental enrichment
        "pbr": [1.0] * n,
        "per": [10.0] * n,
    })
    df.to_parquet(path)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """OLDCO0=2005년 상장, NEWCO0=2024년 상장, NOLIST=상장일 미상."""
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    for sym in ("OLDCO0", "NEWCO0", "NOLIST"):
        _write_parquet(data_dir / f"{sym}.parquet", _DATES)

    master = tmp_path / "stock-master.json"
    master.write_text(json.dumps({"stocks": [
        {"symbol": "OLDCO0", "market": "KOSDAQ", "delistingDate": None,
         "listingDate": "2005-03-04", "dataStart": "2005-03-04",
         "dataEnd": "2024-12-31", "hasOhlcv": True},
        {"symbol": "NEWCO0", "market": "KOSDAQ", "delistingDate": None,
         "listingDate": "2024-01-02", "dataStart": "2024-01-02",
         "dataEnd": "2024-12-31", "hasOhlcv": True},
        # 상장일도 데이터 시작일도 없는 종목 — 신규 상장 판정 근거가 없다.
        {"symbol": "NOLIST", "market": "KOSDAQ", "delistingDate": None,
         "listingDate": None, "dataStart": None, "dataEnd": None, "hasOhlcv": False},
    ]}), encoding="utf-8")
    monkeypatch.setattr(universe_pit, "_MASTER_PATH", master)
    universe_pit.reload_master()
    yield data_dir
    universe_pit.reload_master()


def _req(symbols, listing_from, listing_to):
    return {
        "symbols": list(symbols),
        "universe_id": None,            # custom set -> PIT 재해석 없이 이 목록을 쓴다
        "listing_from": listing_from,
        "listing_to": listing_to,
        "period": "FULL",
        "entry": {"logic": "OR", "conditions": [
            {"id": "price", "type": "signal", "params": {"operator": ">", "value": 0}},
        ]},
        "exit": {"logic": "OR", "conditions": []},
        "risk_params": {"init_cash": 10_000_000.0, "max_positions": 3,
                        "allocation_type": "equal", "skip_risk_management": True},
        "options": {"execution_type": "next_open"},
    }


def _traded(result, symbol):
    return [s for s in result["signals"] if s["symbol"] == symbol and s["type"] == "buy"]


def test_only_the_listing_cohort_is_traded(env):
    engine = BacktestEngine(data_dir=str(env))
    result = engine.run_backtest(_req(["OLDCO0", "NEWCO0"], "2024-01-01", "2024-12-31"))
    # 2005년 상장 종목은 2024년 신규 상장 코호트가 아니다 — 유니버스에서 빠진다.
    assert not _traded(result, "OLDCO0")
    assert _traded(result, "NEWCO0")
    assert result["symbols"] == ["NEWCO0"]


def test_cohort_membership_does_not_expire(env):
    # 코호트는 '그 해 상장한 종목'이지 '상장 후 N일'이 아니다 — 시간이 지나도 대상으로
    # 남는다(정적 심볼 필터라 백테스트 창과 무관하다).
    kept, _ = universe_pit.filter_by_listing_window(
        ["OLDCO0", "NEWCO0"], "2024-01-01", "2024-12-31"
    )
    assert kept == ["NEWCO0"]
    engine = BacktestEngine(data_dir=str(env))
    result = engine.run_backtest(_req(["NEWCO0"], "2024-01-01", "2024-12-31"))
    # 진입 후 청산 규칙이 없으면 연말까지 보유가 이어진다(유니버스에서 밀려나지 않는다).
    assert result["symbols"] == ["NEWCO0"]
    assert not [s for s in result["signals"] if s["type"] == "sell"
                and pd.Timestamp(s["date"]) < pd.Timestamp("2024-12-01")]


def test_unknown_listing_date_excluded_and_reported(env):
    engine = BacktestEngine(data_dir=str(env))
    result = engine.run_backtest(_req(["NEWCO0", "NOLIST"], "2024-01-01", "2024-12-31"))
    assert not _traded(result, "NOLIST")
    assert any("상장일을 확인할 수 없는 종목" in w for w in result["warnings"])


def test_no_matching_symbols_fails_fast(env):
    engine = BacktestEngine(data_dir=str(env))
    # 조용히 0거래로 끝나지 않고 명시적으로 실패한다(섹터 필터 공집합과 같은 계약).
    with pytest.raises(ValueError, match="상장한 종목을 찾지 못했습니다"):
        engine.run_backtest(_req(["OLDCO0"], "2026-01-01", "2026-12-31"))
