"""
ParsedStrategy → BacktestRequest 변환기

LLM이 파싱한 ParsedStrategy를 기존 Back테스트 엔진이 이해하는
BacktestRequest 형식으로 변환한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from engine.nl_parser import ParsedStrategy, TechnicalSignal


# ─── 유니버스 심볼 로딩 ───────────────────────────────────────────────────────

_STOCKS_PATH = Path(__file__).parent.parent.parent / "data" / "korea-stocks.json"

def _load_universe(markets: List[str]) -> List[str]:
    """universe 설정에 맞는 종목 코드 목록 반환"""
    with open(_STOCKS_PATH, encoding="utf-8") as f:
        all_stocks = json.load(f)

    # KOSPI200 → KOSPI 포함으로 처리 (market 필드가 'KOSPI'임)
    target_markets = set()
    for m in markets:
        if m == "KOSPI200":
            target_markets.add("KOSPI")
        else:
            target_markets.add(m)

    symbols = [s["symbol"] for s in all_stocks if s.get("market") in target_markets]
    return symbols


# ─── 기술 신호 → Condition dict 변환 ─────────────────────────────────────────

def _tech_signal_to_condition(sig: TechnicalSignal) -> dict:
    """TechnicalSignal → SignalEngine이 이해하는 Condition dict"""
    params: dict = {"signalType": sig.signal_type}

    if sig.indicator == "ma_crossover":
        params["shortMA"] = sig.short_period or 5
        params["longMA"] = sig.long_period or 20

    elif sig.indicator == "rsi":
        params["period"] = sig.period or 14
        params["operator"] = sig.operator or ("<" if sig.signal_type == "buy" else ">")
        params["value"] = sig.value if sig.value is not None else (30 if sig.signal_type == "buy" else 70)

    elif sig.indicator == "ema":
        if sig.short_period and sig.long_period:
            params["shortPeriod"] = sig.short_period
            params["longPeriod"] = sig.long_period
        else:
            params["period"] = sig.period or 20

    elif sig.indicator == "macd":
        params["mode"] = sig.mode or "crossover"

    elif sig.indicator == "bollinger_bands":
        pass  # signalType 만으로 충분

    elif sig.indicator == "breakout":
        params["lookbackPeriod"] = sig.lookback_period or 20

    elif sig.indicator == "volume_spike":
        params["period"] = sig.period or 20

    elif sig.indicator == "stochastic":
        params["mode"] = sig.mode or "crossover"
        if sig.operator:
            params["operator"] = sig.operator
        if sig.value is not None:
            params["value"] = sig.value

    elif sig.indicator in ("cci", "adx"):
        if sig.period:
            params["period"] = sig.period
        if sig.operator:
            params["operator"] = sig.operator
        if sig.value is not None:
            params["value"] = sig.value

    return {
        "type": "indicator",
        "id": sig.indicator,
        "params": params,
        "weight": 1.0,
    }


# ─── 변환 함수 ────────────────────────────────────────────────────────────────

def to_backtest_request(strategy: ParsedStrategy) -> dict:
    """
    ParsedStrategy → BacktestRequest dict 변환.
    반환값은 BacktestRequest(**result) 또는 engine.run_backtest(result)에 바로 사용 가능.
    """

    # 1. 심볼 목록
    symbols = _load_universe(strategy.universe)

    # 2. 진입 조건 구성
    entry_conditions = []

    # 재무 필터 → type="filter" 조건
    for f in strategy.fundamental_filters:
        entry_conditions.append({
            "type": "filter",
            "id": f.metric,
            "params": {"operator": f.operator, "value": f.value},
            "weight": 1.0,
        })

    # 기술적 진입 신호 → type="indicator" 조건
    for sig in strategy.entry_signals:
        entry_conditions.append(_tech_signal_to_condition(sig))

    # 3. 청산 조건 구성
    exit_conditions = [_tech_signal_to_condition(sig) for sig in strategy.exit_signals]

    # 4. 리스크 관리 설정
    position_size_pct = round(100.0 / strategy.max_positions, 2)

    risk = {
        "position_size_pct": position_size_pct,
        "max_positions": strategy.max_positions,
        "stop_loss_pct": strategy.stop_loss_pct,
        "take_profit_pct": strategy.take_profit_pct,
        "max_holding_days": strategy.hold_period_days,
        "rebalancing_period": strategy.rebalancing_period,
        "init_cash": strategy.initial_capital,
        "ranking_enabled": True,
        "ranking_weight_value": 0.5,
        "ranking_weight_quality": 0.5,
        "execution_timing": "next_open",
        "allocation_type": "equal",
    }

    return {
        "symbols": symbols,
        "entry": {"conditions": entry_conditions},
        "exit": {"conditions": exit_conditions},
        "risk": risk,
        "period": strategy.backtest_period,
        "options": {},
    }
