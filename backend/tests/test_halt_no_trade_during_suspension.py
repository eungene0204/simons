"""거래정지 추정 가드: 봉은 존재하나 거래량 0(가격 동결)인 날은 실제로 체결이
불가능하므로 백테스트가 그 기간에 매수/매도하지 않아야 한다.

과거 시점의 거래정지 종목은 데이터 피드에 '거래량 0 + 가격 동결' 봉으로 남는다
(예: 신라젠 2020~2022 매매거래정지). 이 봉은 가격이 NaN이 아니므로 기존
available_df(=raw_price_df.notna())로는 걸러지지 않아, 유동성 게이트가 꺼진 경로
(skip_risk_management 등)에서는 동결가로 체결되는 낙관 편향이 있었다.

이 테스트는 정지 구간에 진입 신호가 발생하도록 전략을 구성하고, 실제 체결이
정지 구간을 건너뛰어 재개일 이후로 이월되는지 검증한다.
"""
from pathlib import Path

import pandas as pd
import pytest

from backtest_engine import BacktestEngine

# 15 영업일: 1~5 정상 상승, 6~10 거래정지(거래량 0·가격 동결), 11~15 재개.
_DATES = pd.bdate_range("2024-01-02", periods=15)
_HALT_START = _DATES[5]   # 6번째 봉 = 정지 시작
_HALT_END = _DATES[9]     # 10번째 봉 = 정지 마지막
_RESUME = _DATES[10]      # 11번째 봉 = 재개


def _write_halt_parquet(path: Path):
    frozen = 104.0  # 정지 직전 종가로 동결
    rows = []
    for i, d in enumerate(_DATES):
        halted = 5 <= i <= 9
        if i < 5:
            close = 100.0 + i            # 100..104 상승
            vol = 1_000_000
        elif halted:
            close = frozen               # 동결
            vol = 0                      # 거래정지 → 거래량 0
        else:
            close = frozen + (i - 10)    # 104.. 재개 후
            vol = 1_000_000
        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "open": close, "high": close, "low": close, "close": close,
            "volume": vol,
            "roe_or_gpa": 0.1, "pbr": 1.0, "per": 10.0,
        })
    pd.DataFrame(rows).to_parquet(path)


@pytest.fixture
def data_dir(tmp_path):
    _write_halt_parquet(tmp_path / "HALTED.parquet")
    return tmp_path


def test_no_trade_during_trading_halt(data_dir):
    engine = BacktestEngine(data_dir=str(data_dir))
    req = {
        "symbols": ["HALTED"],
        "universe_id": None,
        "period": "FULL",
        # close > 103.5 → 5번째 봉(종가 104)부터 참. next_open 체결이면 6번째(정지 첫날)
        # 체결을 시도한다 — 정지 가드가 없으면 동결가로 체결된다.
        "entry": {"logic": "OR", "conditions": [
            {"id": "price", "type": "signal", "params": {"operator": ">", "value": 103.5}},
        ]},
        "exit": {"logic": "OR", "conditions": []},
        "risk_params": {"init_cash": 10_000_000.0, "max_positions": 1,
                        "skip_risk_management": True},
        "options": {"execution_type": "next_open"},
    }
    result = engine.run_backtest(req)

    buys = [s for s in result["signals"] if s["type"] == "buy"]
    assert buys, "정지 재개 후 매수가 발생해야 한다(테스트가 유효한지 확인)"

    for s in buys:
        d = pd.Timestamp(s["date"])
        assert not (_HALT_START <= d <= _HALT_END), (
            f"거래정지 구간({_HALT_START.date()}~{_HALT_END.date()})에 매수가 체결됨: {d.date()}"
        )
    earliest = min(pd.Timestamp(s["date"]) for s in buys)
    assert earliest >= _RESUME, (
        f"첫 매수 {earliest.date()} — 재개일 {_RESUME.date()} 이전 (정지 구간 체결 누수)"
    )
