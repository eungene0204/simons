"""
Virtual Market Engine
====================
가상 주식시장 엔진 — MockDataGenerator로 OHLCV를 생성하고,
IndicatorEngine/SignalEngine으로 전략 시그널을 평가합니다.

Usage:
    engine = VirtualMarketEngine()
    result = engine.step(
        symbols=["005930"],
        base_prices={"005930": 70000},
        entry_conditions=[{"id": "ma_crossover", "type": "indicator", "params": {"shortMA": 5, "longMA": 20}}],
        exit_conditions=[{"id": "rsi", "type": "indicator", "params": {"period": 14, "operator": ">", "value": 70}}],
        virtual_date="2023-03-15",
    )
"""

from typing import Dict, Any, List, Optional
import polars as pl

from engine.mock_data_generator import MockDataGenerator
from engine.indicators import IndicatorEngine
from engine.signals import SignalEngine


def _symbol_seed(symbol: str) -> int:
    """종목 코드로부터 결정적 시드 생성 (FNV-1a hash)."""
    h = 2166136261
    for ch in symbol:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h % (2**31)


def _mock_ai_score(symbol: str, date_str: str, close: float) -> float:
    """
    (종목+날짜) 해시 기반 결정적 mock AI 스코어.

    - 같은 종목+날짜 → 항상 같은 스코어 (결정적)
    - 날짜마다 자연스럽게 변동
    - 가격 모멘텀을 약간 반영 (close 기반 노이즈)
    - 70% 임계값에서 약 25~30%의 날에 시그널 발생
    """
    import hashlib
    raw = f"{symbol}_{date_str}_{int(close) % 1000}"
    h = hashlib.sha256(raw.encode()).hexdigest()
    # 해시 앞 8자리 → 0~1 균등분포
    base = int(h[:8], 16) / 0xFFFFFFFF
    return base


# 한국 주요 종목 기준가 (mock 시장용)
DEFAULT_BASE_PRICES: Dict[str, float] = {
    "005930": 70000,   # 삼성전자
    "000660": 130000,  # SK하이닉스
    "035720": 55000,   # 카카오
    "035420": 210000,  # NAVER
    "005380": 180000,  # 현대차
    "051910": 400000,  # LG화학
    "006400": 70000,   # 삼성SDI
    "068270": 350000,  # 셀트리온
    "105560": 60000,   # KB금융
    "055550": 45000,   # 신한지주
}


class VirtualMarketEngine:
    """
    가상 시장 1일 스텝 실행 엔진.

    각 step() 호출마다:
    1. MockDataGenerator로 history_days 만큼 OHLCV 생성
    2. IndicatorEngine으로 기술적 지표 계산
    3. SignalEngine으로 entry/exit 시그널 평가
    4. 마지막 행(= virtual_date)의 시그널 + 가격 반환
    """

    def __init__(self):
        self.signal_engine = SignalEngine()

    def step(
        self,
        symbols: List[str],
        base_prices: Optional[Dict[str, float]],
        entry_conditions: List[Dict[str, Any]],
        exit_conditions: List[Dict[str, Any]],
        virtual_date: str,
        scenario: str = "realistic",
        history_days: int = 60,
    ) -> Dict[str, Any]:
        """
        가상 시장 1일 진행.

        Args:
            symbols: 평가할 종목 코드 리스트
            base_prices: {symbol: 기준가격} (없으면 DEFAULT_BASE_PRICES 사용)
            entry_conditions: 진입 조건 리스트
            exit_conditions: 청산 조건 리스트
            virtual_date: 현재 가상 날짜 (YYYY-MM-DD)
            scenario: 시장 시나리오 ("bull", "bear", "realistic", etc.)
            history_days: 지표 계산용 과거 데이터 일수 (기본 60)

        Returns:
            {
                "date": "2023-03-15",
                "signals": [
                    {
                        "symbol": "005930",
                        "close": 72500,
                        "open": 71800,
                        "high": 73000,
                        "low": 71500,
                        "volume": 35000000,
                        "entry_signal": True,
                        "exit_signal": False,
                        "entry_reason": "MA(5) > MA(20) 골든크로스",
                        "exit_reason": null
                    },
                    ...
                ]
            }
        """
        bp = base_prices or {}
        all_conditions = entry_conditions + exit_conditions
        signals = []

        for symbol in symbols:
            try:
                price = bp.get(symbol, DEFAULT_BASE_PRICES.get(symbol, 50000))
                sig = self._evaluate_symbol(
                    symbol=symbol,
                    base_price=price,
                    entry_conditions=entry_conditions,
                    exit_conditions=exit_conditions,
                    all_conditions=all_conditions,
                    virtual_date=virtual_date,
                    scenario=scenario,
                    history_days=history_days,
                )
                signals.append(sig)
            except Exception as e:
                # 개별 종목 실패 시 스킵
                signals.append({
                    "symbol": symbol,
                    "close": 0,
                    "open": 0,
                    "high": 0,
                    "low": 0,
                    "volume": 0,
                    "entry_signal": False,
                    "exit_signal": False,
                    "entry_reason": None,
                    "exit_reason": None,
                    "error": str(e),
                })

        return {
            "date": virtual_date,
            "signals": signals,
        }

    def _evaluate_symbol(
        self,
        symbol: str,
        base_price: float,
        entry_conditions: List[Dict[str, Any]],
        exit_conditions: List[Dict[str, Any]],
        all_conditions: List[Dict[str, Any]],
        virtual_date: str,
        scenario: str,
        history_days: int,
    ) -> Dict[str, Any]:
        """단일 종목에 대한 시그널 평가."""

        # 1. OHLCV 생성 (결정적 시드)
        seed = _symbol_seed(symbol)
        gen = MockDataGenerator(seed=seed)

        # start_date 계산: virtual_date에서 history_days 영업일 전
        import pandas as pd
        end_date = pd.Timestamp(virtual_date)
        # bdate_range로 정확한 영업일 수 확보
        # history_days + 여유분으로 충분한 데이터 생성
        start_date = end_date - pd.tseries.offsets.BDay(history_days + 10)

        df_pd = gen.generate_ohlcv(
            symbol=symbol,
            base_price=base_price,
            days=history_days + 5,
            start_date=start_date.strftime("%Y-%m-%d"),
            scenario=scenario,
        )

        # virtual_date 이후 데이터 제거
        df_pd = df_pd[df_pd["date"] <= virtual_date]

        if len(df_pd) == 0:
            raise ValueError(f"No data generated for {symbol} up to {virtual_date}")

        # AI 시그널 조건이 있으면 mock ai_score / ai_drop_score 주입
        # (GBM 가격에 기반한 모멘텀 근사치 — 실제 모델 없이도 시그널 작동)
        needs_ai = any(
            c.get("id") in ("ai_model", "ai_drop_model")
            for c in all_conditions
        )
        if needs_ai:
            df_pd = df_pd.copy()
            df_pd["ai_score"] = df_pd.apply(
                lambda row: _mock_ai_score(symbol, row["date"], row["close"]), axis=1
            )
            df_pd["ai_drop_score"] = 1.0 - df_pd["ai_score"]

        # 2. Polars 변환 + 지표 계산
        df_pl = pl.from_pandas(df_pd)
        df_pl = IndicatorEngine.calculate(df_pl, all_conditions)

        # 3. 시그널 평가
        entry_group = {"conditions": entry_conditions} if entry_conditions else None
        exit_group = {"conditions": exit_conditions} if exit_conditions else None

        entry_signals, entry_reasons = self.signal_engine.generate_signals(df_pl, entry_group)
        exit_signals, exit_reasons = self.signal_engine.generate_signals(df_pl, exit_group)

        # 4. 마지막 행 결과 반환
        last_idx = len(df_pl) - 1
        last_row = df_pl.row(last_idx, named=True)

        return {
            "symbol": symbol,
            "close": float(last_row.get("close", 0)),
            "open": float(last_row.get("open", 0)),
            "high": float(last_row.get("high", 0)),
            "low": float(last_row.get("low", 0)),
            "volume": int(last_row.get("volume", 0)),
            "entry_signal": bool(entry_signals[last_idx]),
            "exit_signal": bool(exit_signals[last_idx]),
            "entry_reason": entry_reasons[last_idx],
            "exit_reason": exit_reasons[last_idx],
        }
