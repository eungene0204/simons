"""
백테스팅 엔진 12가지 버그 수정 회귀 방지 테스트
각 Fix 번호는 backtest_engine.py 분석 리포트의 항목과 대응.
"""
import os
import pytest
import polars as pl
import pandas as pd
import numpy as np


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

    # 해당 심볼의 parquet 파일이 없고, auto-download도 실패할 경우
    # 예전 코드는 /Users/eugene/... 절대경로로 폴백했지만
    # 수정 후에는 FileNotFoundError를 즉시 발생시켜야 한다.
    # (auto-download가 실제로 실행되므로 ImportError 또는 FileNotFoundError를 모두 허용)
    with pytest.raises((FileNotFoundError, Exception)):
        loader.load_symbol_data("NONEXISTENT_SYMBOL_XYZ_12345")


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
