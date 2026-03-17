"""
Mock Data Generator for Simons Trading Platform
================================================
GBM(Geometric Brownian Motion) 기반으로 실제 주식시장과 유사한 OHLCV 데이터를 생성합니다.
한국 주식시장 특성(상하한가 ±30%, 호가 단위)을 반영합니다.

Usage:
    from engine.mock_data_generator import MockDataGenerator

    gen = MockDataGenerator(seed=42)
    df = gen.generate_ohlcv("TEST001", base_price=50000, days=252, scenario="realistic")
    gen.save_parquet(df, "TEST001", "/tmp/test_data")
"""

import os
from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np
import pandas as pd
import polars as pl

MarketRegime = Literal["bull", "bear", "sideways", "volatile", "crash", "recovery"]

# Per-regime annual drift and volatility parameters
REGIME_PARAMS: dict[str, tuple[float, float]] = {
    "bull":     (0.30,  0.18),   # 연 30% 상승, 변동성 18%
    "bear":     (-0.25, 0.25),   # 연 25% 하락, 변동성 25%
    "sideways": (0.01,  0.13),   # 보합, 변동성 13%
    "volatile": (0.05,  0.45),   # 고변동성
    "crash":    (-0.70, 0.65),   # 급락 구간
    "recovery": (0.25,  0.30),   # 반등 구간
}


@dataclass
class MarketScenario:
    """시장 시나리오 정의 (regime 구간 조합)"""
    name: str
    regimes: list[tuple[int, MarketRegime]]   # (days, regime) 순서대로
    description: str = ""


# 사전 정의된 시나리오 프리셋
SCENARIOS: dict[str, MarketScenario] = {
    "bull": MarketScenario(
        "bull", [(252, "bull")],
        "지속 상승장"
    ),
    "bear": MarketScenario(
        "bear", [(252, "bear")],
        "지속 하락장"
    ),
    "sideways": MarketScenario(
        "sideways", [(252, "sideways")],
        "보합/횡보"
    ),
    "volatile": MarketScenario(
        "volatile", [(252, "volatile")],
        "고변동성 구간"
    ),
    "crash_recovery": MarketScenario(
        "crash_recovery",
        [(60, "bull"), (15, "crash"), (177, "recovery")],
        "상승 후 급락, 회복"
    ),
    "realistic": MarketScenario(
        "realistic",
        [(50, "bull"), (30, "sideways"), (40, "bear"), (30, "sideways"), (50, "bull"), (52, "sideways")],
        "실제 시장처럼 혼합된 구간"
    ),
    "flat": MarketScenario(
        "flat", [(252, "sideways")],
        "단순 테스트용 (변동 최소화)"
    ),
}


class MockDataGenerator:
    """
    GBM 기반 한국 주식시장 OHLCV Mock 데이터 생성기.

    - 시나리오별 drift/volatility 자동 설정
    - 한국 상하한가 ±30% 반영
    - 호가 단위(tick size) 반영
    - 거래량-가격변동 상관관계 반영
    - 완전 재현 가능 (seed 고정)
    """

    # 한국 주식 상하한가
    DAILY_LIMIT = 0.30

    # 한국 호가 단위: (가격 상한, 틱 단위)
    TICK_RULES = [
        (1_000,   1),
        (5_000,   5),
        (10_000,  10),
        (50_000,  50),
        (100_000, 100),
        (500_000, 500),
        (float("inf"), 1_000),
    ]

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_ohlcv(
        self,
        symbol: str,
        base_price: float = 50_000,
        days: int = 252,
        start_date: str = "2023-01-01",
        scenario: str = "realistic",
    ) -> pd.DataFrame:
        """
        GBM 시뮬레이션으로 일봉 OHLCV 데이터를 생성합니다.

        Args:
            symbol: 종목 코드 (예: "005930")
            base_price: 시작 기준가격
            days: 거래일 수 (252 = 1년)
            start_date: 시작일 (YYYY-MM-DD)
            scenario: 시나리오 이름 (SCENARIOS 키 참고)

        Returns:
            pd.DataFrame: date, open, high, low, close, volume 컬럼
        """
        scenario_obj = SCENARIOS.get(scenario, SCENARIOS["realistic"])
        drifts, vols = self._build_regime_arrays(scenario_obj, days)

        dates = pd.bdate_range(start_date, periods=days)
        dt = 1.0 / 252  # 일 단위 시간

        # --- GBM 가격 경로 생성 ---
        log_returns = (drifts - 0.5 * vols ** 2) * dt + vols * np.sqrt(dt) * self.rng.standard_normal(days)
        prices = base_price * np.exp(np.cumsum(log_returns))

        # 상하한가 클리핑 (전일 종가 기준)
        prev = np.concatenate([[base_price], prices[:-1]])
        limit_up   = prev * (1 + self.DAILY_LIMIT)
        limit_down = prev * (1 - self.DAILY_LIMIT)
        closes = np.clip(prices, limit_down, limit_up)

        # 시가 = 전일 종가에 갭 노이즈 추가 (±1%)
        gap_noise = self.rng.uniform(-0.01, 0.01, days)
        opens = prev * (1 + gap_noise)
        opens = np.clip(opens, limit_down, limit_up)

        # 인트라데이 노이즈로 고가/저가 생성
        intraday_sigma = vols * np.sqrt(dt) * 0.7
        upper_noise = np.abs(self.rng.normal(0, intraday_sigma * closes, days))
        lower_noise = np.abs(self.rng.normal(0, intraday_sigma * closes, days))
        highs = np.maximum(opens, closes) + upper_noise
        lows  = np.minimum(opens, closes) - lower_noise

        # 거래량: 변동성이 클수록 증가, 로그 정규 분포
        abs_returns = np.abs(closes - prev) / prev
        base_vol = base_price * 500  # 기준 거래량 (가격 스케일)
        volumes = base_vol * (1 + 5 * abs_returns) * np.exp(self.rng.normal(0, 0.4, days))
        volumes = volumes.astype(np.int64)

        # 호가 단위 반올림
        vround = np.vectorize(self._round_to_tick)
        df = pd.DataFrame({
            "date":   dates.strftime("%Y-%m-%d"),
            "open":   vround(opens).astype(float),
            "high":   vround(highs).astype(float),
            "low":    vround(lows).astype(float),
            "close":  vround(closes).astype(float),
            "volume": volumes.astype(float),
        })

        # OHLC 정합성 보정 (high >= max(o,c), low <= min(o,c))
        df["high"] = df[["open", "high", "close"]].max(axis=1)
        df["low"]  = df[["open", "low",  "close"]].min(axis=1)

        return df

    def generate_portfolio(
        self,
        symbols: list[str],
        base_prices: Optional[dict[str, float]] = None,
        days: int = 252,
        start_date: str = "2023-01-01",
        scenario: str = "realistic",
        output_dir: Optional[str] = None,
    ) -> dict[str, pd.DataFrame]:
        """
        여러 종목의 OHLCV 데이터를 생성합니다.
        종목별로 독립적인 GBM 경로를 생성합니다.

        Args:
            symbols: 종목 코드 리스트
            base_prices: {symbol: 시작가격} (없으면 50,000원 기본값)
            output_dir: 지정 시 parquet 파일로 저장

        Returns:
            {symbol: DataFrame} 딕셔너리
        """
        result: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            bp = (base_prices or {}).get(sym, 50_000)
            df = self.generate_ohlcv(sym, bp, days, start_date, scenario)
            result[sym] = df
            if output_dir:
                self.save_parquet(df, sym, output_dir)
        return result

    def save_parquet(self, df: pd.DataFrame, symbol: str, output_dir: str) -> str:
        """
        DataLoader가 읽을 수 있는 형식으로 parquet 저장합니다.

        Returns:
            저장된 파일 경로
        """
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"{symbol}.parquet")
        pl.from_pandas(df).write_parquet(path)
        return path

    def generate_with_signals(
        self,
        symbol: str,
        base_price: float = 50_000,
        days: int = 252,
        start_date: str = "2023-01-01",
        scenario: str = "realistic",
        entry_every_n: int = 20,
        hold_days: int = 10,
    ) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
        """
        OHLCV + 미리 계산된 진입/청산 시그널을 함께 반환합니다.
        (테스트 시 예상 P&L 검증에 사용)

        Returns:
            (ohlcv_df, entry_series, exit_series)
        """
        df = self.generate_ohlcv(symbol, base_price, days, start_date, scenario)
        idx = pd.to_datetime(df["date"])

        entries = pd.Series(False, index=range(days))
        exits   = pd.Series(False, index=range(days))

        i = 0
        while i < days:
            entries.iloc[i] = True
            exit_i = min(i + hold_days, days - 1)
            exits.iloc[exit_i] = True
            i += entry_every_n

        return df, entries, exits

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_regime_arrays(
        self, scenario: MarketScenario, total_days: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """시나리오에서 일별 drift/volatility 배열 생성"""
        drifts = np.zeros(total_days)
        vols   = np.zeros(total_days)

        idx = 0
        for regime_days, regime in scenario.regimes:
            end = min(idx + regime_days, total_days)
            mu, sigma = REGIME_PARAMS[regime]
            drifts[idx:end] = mu
            vols[idx:end]   = sigma
            idx = end
            if idx >= total_days:
                break

        if idx < total_days:
            # 마지막 regime으로 나머지 채우기
            mu, sigma = REGIME_PARAMS[scenario.regimes[-1][1]]
            drifts[idx:] = mu
            vols[idx:]   = sigma

        return drifts, vols

    def _tick_size(self, price: float) -> int:
        """한국 주식 호가 단위 반환"""
        for threshold, tick in self.TICK_RULES:
            if price < threshold:
                return tick
        return 1_000

    def _round_to_tick(self, price: float) -> int:
        """호가 단위로 반올림"""
        tick = self._tick_size(abs(price))
        return max(tick, int(round(price / tick) * tick))


# ------------------------------------------------------------------
# Convenience functions
# ------------------------------------------------------------------

def make_test_data(
    symbol: str = "TEST",
    base_price: float = 50_000,
    days: int = 252,
    start_date: str = "2023-01-01",
    scenario: str = "realistic",
    seed: int = 42,
) -> pd.DataFrame:
    """단일 종목 테스트 데이터 빠른 생성"""
    return MockDataGenerator(seed=seed).generate_ohlcv(symbol, base_price, days, start_date, scenario)


def make_test_parquet(
    output_dir: str,
    symbols: list[str],
    base_prices: Optional[dict[str, float]] = None,
    days: int = 252,
    start_date: str = "2023-01-01",
    scenario: str = "realistic",
    seed: int = 42,
) -> dict[str, str]:
    """여러 종목 parquet 파일 생성 → {symbol: file_path}"""
    gen = MockDataGenerator(seed=seed)
    paths: dict[str, str] = {}
    for sym in symbols:
        bp = (base_prices or {}).get(sym, 50_000)
        df = gen.generate_ohlcv(sym, bp, days, start_date, scenario)
        paths[sym] = gen.save_parquet(df, sym, output_dir)
    return paths


# ------------------------------------------------------------------
# CLI (python -m engine.mock_data_generator)
# ------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Mock OHLCV 데이터 생성기")
    parser.add_argument("--output", "-o", default="./mock_data", help="출력 디렉토리")
    parser.add_argument("--symbols", "-s", nargs="+", default=["MOCK001", "MOCK002", "MOCK003"])
    parser.add_argument("--days", "-d", type=int, default=252, help="거래일 수")
    parser.add_argument("--start", default="2023-01-01", help="시작일 (YYYY-MM-DD)")
    parser.add_argument("--scenario", "-c", default="realistic",
                        choices=list(SCENARIOS.keys()), help="시나리오 선택")
    parser.add_argument("--base-price", "-p", type=float, default=50_000, help="기준 주가")
    parser.add_argument("--seed", type=int, default=42, help="랜덤 시드")
    args = parser.parse_args()

    gen = MockDataGenerator(seed=args.seed)
    print(f"[Mock Data Generator] 시나리오: {args.scenario} ({SCENARIOS[args.scenario].description})")
    print(f"  종목: {args.symbols}, 기간: {args.days}일, 시작: {args.start}")

    for sym in args.symbols:
        df = gen.generate_ohlcv(sym, args.base_price, args.days, args.start, args.scenario)
        path = gen.save_parquet(df, sym, args.output)
        start_p = df["close"].iloc[0]
        end_p   = df["close"].iloc[-1]
        ret     = (end_p / start_p - 1) * 100
        print(f"  [{sym}] {len(df)}일 → {path}  (수익률: {ret:+.1f}%, {start_p:,.0f} → {end_p:,.0f})")

    print(f"\n총 {len(args.symbols)}개 종목 생성 완료 → {args.output}")
