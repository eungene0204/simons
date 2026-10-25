"""이동평균 이격도 조건(엔진 v16.43) 회귀 테스트.

배경: '20일선에서 N% 벌어지면 매도' 류 이격 폭 조건이 종목 단위로는 미지원이었다(이동평균 위·아래·교차만 존재).
이 파일은 ① 지표 열 계산(종가÷N일 단순이동평균×100, 창 이전은 비교 불가) ② 벡터/행별 평가 일치
③ 변환기·매매 사유 ④ 인터프리터 어휘 노출(온톨로지 시드)을 고정한다.
"""

import numpy as np
import polars as pl
import pytest

from engine import trade_reason
from engine.indicators import IndicatorEngine
from engine.nl_parser import TechnicalSignal
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition


def _ohlcv(close: list[float]) -> pl.DataFrame:
    n = len(close)
    dates = pl.date_range(pl.date(2024, 1, 1), pl.date(2024, 1, 1) + pl.duration(days=n - 1),
                          interval="1d", eager=True)
    c = np.array(close, dtype=float)
    return pl.DataFrame({"date": dates, "open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": np.full(n, 1_000_000.0)})


_SELL = {"type": "indicator", "id": "disparity",
         "params": {"period": 5, "operator": ">=", "value": 110, "signalType": "sell"}}


def test_indicator_engine_computes_close_over_sma_times_100():
    close = [100.0, 100.0, 100.0, 100.0, 100.0, 130.0]
    out = IndicatorEngine.calculate(_ohlcv(close), [_SELL])
    disp = out["disparity_5"].to_list()
    # 5일 단순이동평균 창이 차기 전(앞 4개)은 값이 없다 — 100으로 위장하면 안 된다.
    assert all(v is None or np.isnan(v) for v in disp[:4])
    assert disp[4] == pytest.approx(100.0)
    # 마지막 창 = (100×4+130)/5 = 106 → 130/106×100
    assert disp[5] == pytest.approx(130.0 / 106.0 * 100.0)


def test_vector_and_row_evaluators_agree_and_use_threshold():
    close = [100.0, 100.0, 100.0, 100.0, 100.0, 130.0, 100.0]
    df = IndicatorEngine.calculate(_ohlcv(close), [_SELL])
    engine = SignalEngine()
    vec = engine._eval_vec(_SELL, df).tolist()
    assert vec == [False, False, False, False, False, True, False]
    assert [engine.evaluate_condition(_SELL, i, df) for i in range(len(df))] == vec


def test_buy_defaults_to_depressed_side_and_missing_column_fails_closed():
    engine = SignalEngine()
    buy = {"id": "disparity", "params": {"period": 20, "signalType": "buy"}}
    df = pl.DataFrame({"disparity_20": [85.0, 100.0, 95.0]})
    assert engine._eval_vec(buy, df).tolist() == [True, False, False]
    assert engine._eval_vec(buy, pl.DataFrame({"close": [1.0, 2.0]})).tolist() == [False, False]


def test_parsed_signal_and_trade_reason_keep_period_and_value():
    signal = TechnicalSignal(indicator="disparity", signal_type="sell", period=20, operator=">=", value=115)
    cond = _tech_signal_to_condition(signal)
    assert cond["id"] == "disparity"
    assert cond["params"]["period"] == 20 and cond["params"]["value"] == 115
    parts = SignalEngine()._base_condition_segments(
        {"id": "disparity", "params": {"period": 20, "operator": ">=", "value": 115, "signalType": "sell"}}
    )
    text = trade_reason.render_kr(parts)
    assert text == "20일선 이격도 115 이상"


def test_disparity_is_exposed_to_the_interpreter_vocabulary():
    """레지스트리에만 있고 온톨로지 시드에 없으면 프롬프트 어휘에 오르지 않는다(consecutive_down 실측과 같은 함정)."""
    from strategy_conversation.interpreter.prompts import build_system_prompt

    assert "technical.disparity" in build_system_prompt()
