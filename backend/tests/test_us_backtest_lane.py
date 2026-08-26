"""US 백테스트 레인 (Phase 1) — 유니버스 해석·데이터 라우팅·벤치마크·거래 규약."""

from pathlib import Path

import pytest

from backtest_engine import BacktestEngine
from engine import universe_pit
from engine.loader import DataLoader

_DATA = Path(__file__).resolve().parents[2] / "data"
_HAS_US_DATA = (_DATA / "ohlcv-us" / "AAPL.parquet").exists()
_HAS_MEMBERSHIP = (_DATA / "us-index-membership.json").exists()

needs_us_data = pytest.mark.skipif(not _HAS_US_DATA, reason="미국 파케이 미러 없음")
needs_membership = pytest.mark.skipif(not _HAS_MEMBERSHIP, reason="지수 구성 미수집")

# 엔진 통합 테스트는 pytest 안에서 Polars 전역 스레드 풀과 얽혀 데드락한다(엔진 통합
# 테스트가 기본 스위트에서 제외돼 온 것과 같은 계열). Polars 단일 스레드로 별도 실행:
#   POLARS_MAX_THREADS=1 pytest tests/test_us_backtest_lane.py
import os as _os

engine_integration = pytest.mark.skipif(
    _os.environ.get("POLARS_MAX_THREADS") != "1",
    reason="엔진 통합 — POLARS_MAX_THREADS=1 필요(pytest×Polars 스레드 데드락)",
)


# ── universe_pit ──────────────────────────────────────────────

def test_us_universe_kind_exact_ids_only():
    assert universe_pit.us_universe_kind("sp500") == "sp500"
    assert universe_pit.us_universe_kind("US_ETF") == "us_etf"
    assert universe_pit.us_universe_kind("kospi") is None
    assert universe_pit.us_universe_kind("kospi_sp500") is None  # 한·미 혼합 미지원
    assert universe_pit.us_universe_kind(None) is None


def test_is_us_symbol_shape_rule():
    assert universe_pit.is_us_symbol("AAPL")
    assert universe_pit.is_us_symbol("BRK-B")
    assert not universe_pit.is_us_symbol("005930")   # 한국 보통주
    assert not universe_pit.is_us_symbol("0000D0")   # 한국 ETF(숫자 시작)
    assert not universe_pit.is_us_symbol("")


def test_is_us_symbol_set_majority():
    assert universe_pit.is_us_symbol_set(["AAPL", "MSFT", "005930"])
    assert not universe_pit.is_us_symbol_set(["005930", "000660", "AAPL"])
    assert not universe_pit.is_us_symbol_set([])


@needs_membership
@needs_us_data
def test_resolve_us_symbols_counts():
    assert len(universe_pit.resolve_us_symbols("dow30")) == 30
    assert len(universe_pit.resolve_us_symbols("sp500")) >= 495
    assert len(universe_pit.resolve_us_symbols("us_etf")) >= 25
    assert universe_pit.resolve_us_symbols("kospi") == []


def test_us_benchmark_mapping():
    assert universe_pit.us_benchmark("sp500")[0] == "SPY"
    assert universe_pit.us_benchmark("nasdaq100")[0] == "QQQ"
    assert universe_pit.us_benchmark("dow30")[0] == "DIA"
    assert universe_pit.us_benchmark(None)[0] == "SPY"
    assert universe_pit.us_benchmark("us_etf")[0] == "SPY"


# ── 벤치마크 선택 (엔진) ──────────────────────────────────────

def test_benchmark_for_universe_us_and_kr():
    bench = BacktestEngine.benchmark_for_universe
    assert bench("sp500")[0] == "SPY"
    assert bench("nasdaq100")[0] == "QQQ"
    assert bench("dow30")[0] == "DIA"
    # 지정 종목이 미국 티커면 SPY로 추론
    assert bench("", ["AAPL", "MSFT"])[0] == "SPY"
    # 한국 레인은 기존과 동일
    assert bench("kosdaq")[0] == "229200"
    assert bench("kospi")[0] == "226490"
    assert bench("kospi200")[0] == "069500"


# ── 데이터 라우팅 (loader) ────────────────────────────────────

@needs_us_data
def test_loader_routes_us_symbols_to_us_dir():
    loader = DataLoader(str(_DATA / "ohlcv"))
    df = loader.load_symbol_data("AAPL")
    assert df is not None and len(df) > 1000
    assert loader.us_data_dir.endswith("ohlcv-us")


def test_mixed_kr_us_symbols_rejected():
    # 한·미 혼합 지정 — 세금·벤치마크·통화가 시장 단위 계약이라 명시 거절(조용한 실행 금지).
    # Phase1 진입 전에 발화하므로 기본 스위트에서 안전하다.
    eng = BacktestEngine()
    with pytest.raises(ValueError, match="함께 지정할 수 없습니다"):
        eng.run_backtest({
            "symbols": ["005930", "AAPL"],
            "entry": {"logic": "AND", "conditions": [
                {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20}}]},
            "exit": {"conditions": []},
            "risk": {"position_size_pct": 50, "liquidity_multiplier": 0},
            "period": "1Y",
        })


# ── 엔진 통합 (골든 케이스) ───────────────────────────────────

@engine_integration
@needs_membership
@needs_us_data
def test_dow30_golden_cross_backtest_runs(monkeypatch):
    # Phase1 프로세스 풀은 pytest 컨텍스트에서 데드락한다(엔진 통합 테스트가 기본
    # 스위트에서 제외돼 온 이유와 동일) — 엔진 안 스레드 경로로 강제한다.
    monkeypatch.setenv("BACKTEST_PHASE1_WORKERS", "0")
    eng = BacktestEngine()
    req = {
        "universe_id": "dow30",
        "symbols": [],
        "entry": {"logic": "AND", "conditions": [
            {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20}}]},
        "exit": {"conditions": [
            {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "sell"}}]},
        "risk": {"position_size_pct": 20, "max_positions": 5, "liquidity_multiplier": 0},
        "startDate": "2024-01-01",
        "endDate": "2024-06-30",
    }
    result = eng.run_backtest(req)

    buys = [s for s in result.get("signals", []) if s.get("type") == "buy"]
    assert len(buys) > 0
    assert result.get("benchmark_label", "").startswith("SPDR Dow Jones")
    assert len(result.get("benchmark_equity") or []) > 0
    # 미국 시장: 증권거래세 미부과(경고 없음) + 생존편향·현행 명부 고지
    assert not any("거래세" in w for w in eng.warnings)
    assert any("생존 편향" in w for w in eng.warnings)
    assert any("현재 구성종목 명부" in w for w in eng.warnings)


@engine_integration
@needs_membership
@needs_us_data
def test_us_universe_rejects_ai_and_kr_sector():
    eng = BacktestEngine()
    base = {
        "universe_id": "sp500",
        "symbols": [],
        "exit": {"conditions": []},
        "risk": {"position_size_pct": 20, "liquidity_multiplier": 0},
        "period": "1Y",
    }
    with pytest.raises(Exception, match="미국 유니버스에서는 사용할 수 없습니다"):
        eng.run_backtest({**base, "entry": {"logic": "AND", "conditions": [
            {"id": "ai_drop_model", "params": {}}]}})

    # 한국 섹터 정본은 미국 유니버스에 적용할 수 없다(분류 체계가 다르다) — 미국 업종은
    # us_industry 필드가 담당한다(FR-STR-074 ⑩).
    eng2 = BacktestEngine()
    with pytest.raises(ValueError, match="한국 업종 분류"):
        eng2.run_backtest({**base, "sector": "반도체",
                           "entry": {"logic": "AND", "conditions": [
                               {"id": "ma_crossover", "params": {}}]}})


@engine_integration
@needs_membership
@needs_us_data
def test_us_industry_filter_narrows_universe():
    """미국 업종 필터(FR-STR-074 ⑩) — GICS 분류 정본으로 유니버스를 교집합한다.

    분류는 현행 기준이라(과거 재분류 미반영) 그 사실을 경고로 남긴다 — 테마가 소속
    최초 관측일을 갖는 것과 갈리는 지점이다."""
    base = {
        "universe_id": "sp500",
        "symbols": [],
        "exit": {"conditions": []},
        "risk": {"position_size_pct": 20, "liquidity_multiplier": 0},
        "period": "1Y",
        "entry": {"logic": "AND", "conditions": [{"id": "ma_crossover", "params": {}}]},
    }
    eng = BacktestEngine()
    result = eng.run_backtest({**base, "us_industry": "Airlines"})
    assert result is not None
    assert any("업종(Airlines) 필터는 현재 분류 기준" in w for w in eng.warnings)

    # 분류에 해당하는 종목이 유니버스에 없으면 조용히 0거래로 끝내지 않고 명시 실패
    eng2 = BacktestEngine()
    with pytest.raises(ValueError, match="업종에 해당하는 종목을 찾지 못했"):
        eng2.run_backtest({**base, "universe_id": "dow30", "us_industry": "Airlines"})
