"""결과 로그에 동봉하는 '적용 거래 비용'(engine/simulator.py applied_trading_costs).

2026-09-14: 결과 화면·기록에서 이 결과가 어떤 수수료·슬리피지·거래세로 계산됐는지 볼 곳이
없었다(설정 화면 값만 있고 결과 DTO에는 없음). 시뮬레이터와 같은 해석을 결과에 싣는다.
"""
import pandas as pd

from engine.simulator import (
    DEFAULT_FEE_RATE, DEFAULT_SLIPPAGE_RATE, Simulator, applied_trading_costs,
)
from schemas import BacktestResponse


def _index(start: str, end: str) -> pd.Index:
    return pd.bdate_range(start, end)


def test_defaults_when_options_empty_use_statutory_tax_schedule():
    costs = applied_trading_costs({}, _index("2022-06-01", "2025-06-01"))
    assert costs["buyFeeRate"] == DEFAULT_FEE_RATE
    assert costs["sellFeeRate"] == DEFAULT_FEE_RATE
    assert costs["slippageRate"] == DEFAULT_SLIPPAGE_RATE
    assert costs["sellTaxRate"] is None
    # 2022(0.23%)→2025(0.15%) 스케줄 구간
    assert costs["sellTaxRateRange"] == [0.0015, 0.0023]


def test_explicit_rates_and_fixed_tax_are_echoed():
    opts = {"fee_rate": 0.00015, "slippage_rate": 0.0005, "sell_tax_rate": 0.0}
    costs = applied_trading_costs(opts, _index("2020-01-01", "2020-03-01"))
    assert costs == {
        "buyFeeRate": 0.00015, "sellFeeRate": 0.00015, "slippageRate": 0.0005,
        "sellTaxRate": 0.0, "sellTaxRateRange": None,
    }


def test_side_specific_fee_overrides_legacy_fee_rate():
    opts = {"fee_rate": 0.001, "buy_fee_rate": 0.0002, "sell_fee_rate": 0.0003}
    costs = applied_trading_costs(opts, _index("2024-01-01", "2024-02-01"))
    assert (costs["buyFeeRate"], costs["sellFeeRate"]) == (0.0002, 0.0003)


def test_matches_simulator_fee_resolution():
    # 결과에 싣는 값과 시뮬레이터가 실제로 쓰는 값이 갈리면 안 된다.
    idx = _index("2018-01-01", "2025-06-01")
    opts = {"buy_fee_rate": 0.0002, "sell_fee_rate": 0.0003}
    buy_fee, sell_vec = Simulator._resolve_fee_rates(opts, idx)
    costs = applied_trading_costs(opts, idx)
    assert buy_fee == costs["buyFeeRate"]
    lo, hi = costs["sellTaxRateRange"]
    assert float(sell_vec.min()) == costs["sellFeeRate"] + lo
    assert float(sell_vec.max()) == costs["sellFeeRate"] + hi


def test_backtest_response_keeps_trading_costs():
    # /backtest는 response_model 필터라 스키마에 없는 필드는 조용히 사라진다.
    result = {
        "symbols": ["005930"],
        "totalReturn": 1.0, "cagr": 1.0, "buyAndHoldReturn": 0.5, "maxDrawdown": -2.0,
        "winRate": 50.0, "sharpe": 0.1, "sortino": 0.1, "volatility": 10.0, "trades": 1,
        "equity": [1.0, 1.01], "dates": ["2024-01-02", "2024-01-03"], "signals": [],
        "tradingCosts": applied_trading_costs({}, _index("2024-01-02", "2024-01-03")),
    }
    dumped = BacktestResponse(**result).model_dump()
    assert dumped["tradingCosts"]["sellTaxRateRange"] == [0.0018, 0.0018]
