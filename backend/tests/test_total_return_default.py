"""total_return 디폴트(=True) + 벤치마크 일관성 회귀 테스트.

배당이 있는 합성 종목으로, total_return 옵션을 생략하면 True와 동일하고
False(가격리턴)와는 달라짐을 확인한다. 디폴트가 가격리턴으로 되돌아가면 실패.
"""
from pathlib import Path

import pandas as pd
import pytest

from backtest_engine import BacktestEngine

_DATES = pd.bdate_range("2020-01-02", "2024-12-31")  # 5y, spans year-ends


def _write(path: Path, with_div: bool):
    n = len(_DATES)
    div = [0.0] * n
    if with_div:
        # place a dividend on the last trading day of each year
        years = pd.DatetimeIndex(_DATES).year
        for y in sorted(set(years)):
            last = max(i for i in range(n) if years[i] == y)
            div[last] = 5.0
    pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in _DATES],
        "open": [100.0] * n, "high": [100.0] * n, "low": [100.0] * n,
        "close": [100.0] * n, "volume": [1_000_000] * n,
        "roe_or_gpa": [0.1] * n, "pbr": [1.0] * n, "per": [10.0] * n,
        "dividends": div,
    }).to_parquet(path)


@pytest.fixture
def data_dir(tmp_path):
    _write(tmp_path / "DIVDIV.parquet", with_div=True)
    return tmp_path


def _run(data_dir, options):
    return BacktestEngine(data_dir=str(data_dir)).run_backtest({
        "symbols": ["DIVDIV"], "universe_id": None, "period": "FULL",
        "entry": {"logic": "OR", "conditions": [
            {"id": "price", "type": "signal", "params": {"operator": ">", "value": 0}}]},
        "exit": {"logic": "OR", "conditions": []},
        "risk_params": {"init_cash": 10_000_000.0, "skip_position_setting": True,
                        "skip_risk_management": True},
        "options": {"execution_type": "next_open", **options},
    })


def test_default_is_total_return(data_dir):
    default = _run(data_dir, {})                       # omit total_return
    on = _run(data_dir, {"total_return": True})
    off = _run(data_dir, {"total_return": False})
    # Flat price + yearly dividends: price-return ~0, total-return strongly positive.
    assert default["totalReturn"] == pytest.approx(on["totalReturn"])
    assert default["totalReturn"] > off["totalReturn"] + 1.0
    assert off["totalReturn"] == pytest.approx(0.0, abs=1.0)
