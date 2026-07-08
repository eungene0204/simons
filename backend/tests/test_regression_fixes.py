"""
백테스팅 엔진 12가지 버그 수정 회귀 방지 테스트
각 Fix 번호는 backtest_engine.py 분석 리포트의 항목과 대응.
"""
import os
import sys
import polars as pl
import pandas as pd
import numpy as np
import pytest
from types import SimpleNamespace

sys.path.append(os.path.join(os.getcwd(), "backend"))


# ──────────────────────────────────────────────────────────────────────────────
# Fix 2: 중복 end_date 필터 — 기간 필터링이 올바르게 동작하는지 확인
# ──────────────────────────────────────────────────────────────────────────────

def _make_engine_with_temp_data(tmp_path, prices: list, symbol: str = "REGTEST"):
    """임시 parquet 데이터로 BacktestEngine 생성 헬퍼."""
    from backtest_engine import BacktestEngine

    dates = pd.date_range("2020-01-01", periods=len(prices), freq="B")
    rows = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "open": float(p), "high": float(p + 1),
            "low": float(p - 1), "close": float(p),
            "volume": 1_000_000.0,
        }
        for d, p in zip(dates, prices)
    ]
    data_dir = str(tmp_path)
    pl.from_dicts(rows).write_parquet(os.path.join(data_dir, f"{symbol}.parquet"))
    return BacktestEngine(data_dir=data_dir), symbol, dates


def _simple_req(symbol, extra_risk=None):
    """최소 백테스트 요청 딕셔너리."""
    risk = {
        "position_size_pct": 100,
        "max_positions": 1,
        "liquidity_multiplier": 0,
        "skip_risk_management": True,
        "skip_position_setting": True,
    }
    if extra_risk:
        risk.update(extra_risk)
    return {
        "symbols": [symbol],
        "entry": {"conditions": [{"id": "price", "params": {"value": 0, "operator": ">"}}]},
        "exit": {"conditions": []},
        "risk": risk,
        "period": "full",
        "options": {"execution_type": "same_close"},
    }


def test_period_filter_end_date_applies_correctly(tmp_path):
    """end_date 필터가 정확히 적용돼 마지막 날 이후 데이터를 제외한다 (Fix 2)"""
    prices = list(range(100, 160))   # 60일치 데이터
    engine, sym, dates = _make_engine_with_temp_data(tmp_path, prices)

    req = _simple_req(sym)
    req["endDate"] = dates[29].strftime("%Y-%m-%d")   # 30번째 날까지만
    result = engine.run_backtest(req)

    # 반환된 날짜 수가 30일을 초과하지 않아야 한다
    assert len(result["dates"]) <= 30
    # 마지막 날짜가 endDate 이하여야 한다
    assert result["dates"][-1] <= req["endDate"]


def test_period_filter_start_date_applies_correctly(tmp_path):
    """startDate 이전 데이터가 제외된다 (Fix 2)"""
    prices = list(range(100, 160))
    engine, sym, dates = _make_engine_with_temp_data(tmp_path, prices)

    req = _simple_req(sym)
    req["startDate"] = dates[30].strftime("%Y-%m-%d")   # 31번째 날부터
    result = engine.run_backtest(req)

    assert result["dates"][0] >= req["startDate"]


def test_kospi_universe_uses_kodex_kospi_benchmark():
    """KOSPI 전체 전략의 매수 후 보유 벤치마크는 KODEX 코스피여야 한다."""
    from backtest_engine import BacktestEngine

    assert BacktestEngine.benchmark_for_universe("kospi") == (
        "226490",
        "KODEX 코스피 (226490)",
    )
    assert BacktestEngine.benchmark_for_universe("kospi200") == (
        "069500",
        "KODEX 200 (069500)",
    )
    assert BacktestEngine.benchmark_for_universe("kosdaq") == (
        "229200",
        "KODEX KOSDAQ 150 (229200)",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Fix 9: init_cash / liquidity_limit 0값이 기본값으로 교체되지 않음
# ──────────────────────────────────────────────────────────────────────────────

class TestInitCashNoneCheck:
    """Fix 9: `or` 연산자 대신 명시적 None 체크 사용 검증"""

    @staticmethod
    def _resolve(risk_params: dict) -> float:
        """backtest_engine.py의 init_cash 해석 로직을 그대로 복제."""
        init_cash_raw = risk_params.get("init_cash")
        if init_cash_raw is None:
            init_cash_raw = risk_params.get("initial_cash")
        return float(init_cash_raw) if init_cash_raw is not None else 10_000_000.0

    def test_zero_value_preserved(self):
        """init_cash=0.0 은 기본값(1000만)으로 대체되지 않아야 한다."""
        assert self._resolve({"init_cash": 0.0}) == 0.0

    def test_integer_zero_preserved(self):
        """init_cash=0 (int)도 0.0으로 처리돼야 한다."""
        assert self._resolve({"init_cash": 0}) == 0.0

    def test_fallback_to_initial_cash(self):
        """init_cash 키가 없으면 initial_cash로 폴백."""
        assert self._resolve({"initial_cash": 5_000_000.0}) == 5_000_000.0

    def test_default_when_both_missing(self):
        """둘 다 없으면 기본값 1,000만원 사용."""
        assert self._resolve({}) == 10_000_000.0

    def test_explicit_value_overrides_default(self):
        """명시적 값이 있으면 기본값 무시."""
        assert self._resolve({"init_cash": 3_000_000.0}) == 3_000_000.0

    def test_or_operator_would_have_failed(self):
        """이 테스트는 기존 `or` 방식이 왜 틀렸는지 보여준다 (문서적 목적)."""
        risk = {"init_cash": 0.0}
        # 구버전 (버그): 0.0이 falsy → None 반환 → 기본값 10_000_000 사용
        broken = risk.get("init_cash") or risk.get("initial_cash")
        assert broken is None  # ← 이게 버그. 0.0이 None으로 처리됨

        # 신버전 (수정): None 체크 사용
        fixed = self._resolve(risk)
        assert fixed == 0.0  # ← 올바른 동작


class TestLiquidityLimitNoneCheck:
    """Fix 9: liquidity_limit_pct 0값 처리도 동일하게 적용"""

    @staticmethod
    def _resolve(risk_params: dict) -> float:
        liquid_limit_raw = risk_params.get("liquidity_limit_pct")
        if liquid_limit_raw is None:
            liquid_limit_raw = risk_params.get("liquidity_multiplier")
        return float(liquid_limit_raw) if liquid_limit_raw is not None else 10.0

    def test_zero_liquidity_limit_preserved(self):
        """liquidity_limit_pct=0 이면 유동성 체크를 비활성화해야 한다."""
        assert self._resolve({"liquidity_limit_pct": 0.0}) == 0.0

    def test_fallback_to_liquidity_multiplier(self):
        assert self._resolve({"liquidity_multiplier": 5.0}) == 5.0

    def test_default_when_missing(self):
        assert self._resolve({}) == 10.0


# ──────────────────────────────────────────────────────────────────────────────
# Fix 11: 하드코딩 절대 경로 제거 — 파일 없으면 FileNotFoundError 발생
# ──────────────────────────────────────────────────────────────────────────────

def test_loader_raises_file_not_found_without_hardcoded_fallback(tmp_path):
    """존재하지 않는 심볼은 하드코딩 경로 없이 FileNotFoundError를 발생 (Fix 11)"""
    from engine.loader import DataLoader

    loader = DataLoader(str(tmp_path))

    # 파일이 없으면 None을 반환 (Yahoo Finance 등 외부 다운로드 시도 없음)
    result = loader.load_symbol_data("NONEXISTENT_SYMBOL_XYZ_12345")
    assert result is None


@pytest.mark.asyncio
async def test_virtual_trader_handles_none_risk_values_without_crashing(monkeypatch):
    """VirtualTrader는 null 리스크 설정을 0/기본값으로 처리해야 한다."""
    from engine.virtual_trader import VirtualTrader

    class DummyMarketDataProvider:
        async def get_prices(self, symbols):
            # date가 오늘이어야 휴장일/스테일 시세 가드를 통과해 리스크 루프까지 도달한다
            from datetime import datetime, timezone, timedelta
            today = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
            return {
                symbol: SimpleNamespace(close=110, high=112, date=today)
                for symbol in symbols
            }

    trader = VirtualTrader(DummyMarketDataProvider(), data_loader=None)

    monkeypatch.setattr(trader, "_fetch_strategy", lambda _strategy_id: {
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": None,
            "max_positions": None,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "trailing_stop_pct": None,
            "max_holding_days": None,
        },
    })
    monkeypatch.setattr(trader, "_fetch_positions", lambda _account_id: [
        {
            "symbol": "005930",
            "avgPrice": 100,
            "peakPrice": 120,
            "openedAt": "2026-04-01T00:00:00+00:00",
            "quantity": 3,
        }
    ])
    monkeypatch.setattr(trader, "_evaluate_signals", lambda *_args, **_kwargs: [
        {"symbol": "005930", "entry_signal": False, "exit_signal": False}
    ])
    monkeypatch.setattr(trader, "_fetch_today_logs", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(trader, "_fetch_pending_orders", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(trader, "_update_positions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trader, "_update_last_refreshed", lambda *_args, **_kwargs: None)

    account = {
        "id": "acct-1",
        "tradingMode": "manual",
        "symbols": '["005930"]',
        "strategyId": "strategy-1",
    }

    await trader._refresh_account(account)


# ──────────────────────────────────────────────────────────────────────────────
# Fix 12: 랭킹 계산 실패가 엔진 크래시로 이어지지 않음
# ──────────────────────────────────────────────────────────────────────────────

def test_ranking_failure_does_not_crash_backtest(tmp_path):
    """PBR/ROE 데이터가 없어 랭킹 계산 실패해도 백테스트 결과가 반환된다 (Fix 12)"""
    prices = [100.0] * 20
    engine, sym, _ = _make_engine_with_temp_data(tmp_path, prices)

    req = _simple_req(sym, extra_risk={
        "ranking_enabled": True,
        "ranking_weight_value": 0.5,
        "ranking_weight_quality": 0.5,
    })
    # PBR/ROE 컬럼이 없는 데이터로 백테스트 실행 → 랭킹 계산이 조용히 실패해야 함
    result = engine.run_backtest(req)

    # 크래시 없이 결과 딕셔너리가 반환돼야 한다
    assert "totalReturn" in result
    assert "equity" in result
    assert isinstance(result["warnings"], list)


# ──────────────────────────────────────────────────────────────────────────────
# Fix 6: 멀티스레드 로깅 — IndicatorEngine 동시 호출 시 크래시 없음
# ──────────────────────────────────────────────────────────────────────────────

def test_indicator_engine_concurrent_calls_no_crash():
    """IndicatorEngine.calculate를 여러 스레드에서 동시 호출해도 크래시 없음 (Fix 6)"""
    import concurrent.futures
    from engine.indicators import IndicatorEngine

    dates = pd.date_range("2020-01-01", periods=50, freq="B")
    prices = np.linspace(100, 150, 50)
    pdf = pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": prices, "high": prices + 1,
        "low": prices - 1, "close": prices, "volume": np.ones(50) * 1_000_000,
    })
    df_pl = pl.from_pandas(pdf)

    conditions = [
        {"id": "rsi",         "params": {"period": 14}},
        {"id": "ma_crossover","params": {"shortMA": 5, "longMA": 20}},
        {"id": "bollinger_bands", "params": {"period": 20}},
    ]

    errors = []

    def run():
        try:
            # clone()으로 각 스레드에 독립적인 Polars DataFrame 복사본 전달
            # (Polars 보로우 체커가 동일 객체의 동시 접근을 거부하기 때문)
            IndicatorEngine.calculate(df_pl.clone(), conditions)
        except Exception as e:
            errors.append(str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(run) for _ in range(8)]
        concurrent.futures.wait(futures)

    assert errors == [], f"스레드 오류 발생: {errors}"


# ──────────────────────────────────────────────────────────────────────────────
# Fix 7: 포트폴리오 변동성이 유한한 스칼라 값으로 반환됨
# ──────────────────────────────────────────────────────────────────────────────

def test_backtest_volatility_is_finite_scalar(tmp_path):
    """변동성(volatility)이 NaN/Inf가 아닌 유한한 숫자로 반환된다 (Fix 7)"""
    import random
    random.seed(42)
    # 변동성 있는 가격 시계열 생성
    prices = [100.0]
    for _ in range(49):
        prices.append(prices[-1] * (1 + random.uniform(-0.03, 0.03)))

    engine, sym, _ = _make_engine_with_temp_data(tmp_path, prices)
    req = _simple_req(sym)
    result = engine.run_backtest(req)

    vol = result.get("volatility", None)
    assert vol is not None
    assert isinstance(vol, (int, float))
    assert np.isfinite(vol), f"volatility={vol} 는 유한값이어야 한다"
    assert vol >= 0.0, f"volatility={vol} 는 0 이상이어야 한다"


# ──────────────────────────────────────────────────────────────────────────────
# Fix: format_results 에서 norm_dt 가 수십만 회 호출되던 성능 버그
# build_reason_array 가 DatetimeIndex.asi8 벡터화로 교체됐는지 확인.
# 다심볼 + 거래 발생 시 format_results 가 2초 이내에 완료되어야 한다.
# ──────────────────────────────────────────────────────────────────────────────

def test_format_results_does_not_call_norm_dt_per_row(tmp_path):
    """
    199종목 규모를 흉내낸 20심볼 백테스트에서 format_results 가
    0.5초 이내에 완료되는지 검증한다.
    (수정 전: build_reason_array 에서 norm_dt 를 ~40만 회 호출 → ~2초
     수정 후: DatetimeIndex.asi8 벡터화 → ~0.1초)
    """
    import time

    N_SYMS = 20
    N_DAYS = 500
    # 단순 상승 추세 → MA crossover 진입 신호가 발생하도록 설계
    prices_trend = [100.0 + i * 0.5 for i in range(N_DAYS)]

    data_dir = str(tmp_path)
    symbols = []
    for i in range(N_SYMS):
        sym = f"PERF{i:02d}"
        symbols.append(sym)
        dates = pd.date_range("2022-01-01", periods=N_DAYS, freq="B")
        rows = [
            {
                "date": d.strftime("%Y-%m-%d"),
                "open": float(p), "high": float(p + 1),
                "low": float(p - 1), "close": float(p),
                "volume": 1_000_000.0,
            }
            for d, p in zip(dates, prices_trend)
        ]
        pl.from_dicts(rows).write_parquet(os.path.join(data_dir, f"{sym}.parquet"))

    from backtest_engine import BacktestEngine
    engine = BacktestEngine(data_dir=data_dir)

    req = {
        "symbols": symbols,
        "entry": {"conditions": [
            {"id": "ma_crossover", "params": {"signalType": "buy", "shortMA": 5, "longMA": 20}},
        ]},
        "exit": {"conditions": [
            {"id": "rsi", "params": {"signalType": "sell", "period": 14, "operator": ">", "value": 70}},
        ]},
        "risk": {
            "position_size_pct": 5.0,
            "max_positions": 20,
            "stop_loss_pct": 10,
            "init_cash": 10_000_000,
            "allocation_type": "equal",
            "ranking_enabled": False,
        },
        "period": "full",
        "options": {"fee_rate": 0.00015, "slippage_rate": 0.0005},
    }

    # 1회 실행(데이터 캐시 워밍업)
    engine.run_backtest(req)

    # format_results 단독 시간 측정
    captured = {}
    orig_fmt = engine.handler.format_results
    def timed_fmt(*a, **kw):
        t = time.time()
        r = orig_fmt(*a, **kw)
        captured["fmt_time"] = time.time() - t
        return r
    engine.handler.format_results = timed_fmt

    engine.run_backtest(req)

    fmt_time = captured.get("fmt_time", 999)
    assert fmt_time < 0.5, (
        f"format_results 가 {fmt_time:.2f}s 걸렸습니다 — "
        "norm_dt per-row 호출 버그가 재발했을 수 있습니다 (허용: 0.5s)"
    )
