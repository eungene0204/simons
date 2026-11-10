"""볼린저 밴드폭·스퀴즈, 이동평균 기울기, 52주 고가 비율, 시가 갭(엔진 v16.50) 회귀 테스트.

배경: 50개 전략 감사에서 네 개념이 엔진에 없어 다른 조건으로 치환되거나 사라졌다.
이 파일은 ① 지표 열 계산 ② 벡터/행별 평가 일치 ③ 변환·조립 왕복 ④ 필수값 되묻기 ⑤ 어휘 노출을 고정한다.
"""

import numpy as np
import polars as pl
import pytest

from engine import trade_reason
from engine.indicators import IndicatorEngine
from engine.nl_parser import TechnicalSignal
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition


def _ohlcv(close: list[float], open_: list[float] | None = None, high: list[float] | None = None) -> pl.DataFrame:
    n = len(close)
    dates = pl.date_range(pl.date(2024, 1, 1), pl.date(2024, 1, 1) + pl.duration(days=n - 1),
                          interval="1d", eager=True)
    c = np.array(close, dtype=float)
    return pl.DataFrame({
        "date": dates, "open": np.array(open_, dtype=float) if open_ else c,
        "high": np.array(high, dtype=float) if high else c, "low": c * 0.99,
        "close": c, "volume": np.full(n, 1_000_000.0),
    })


def _cond(cid: str, **params) -> dict:
    return {"type": "indicator", "id": cid, "params": {"signalType": "buy", **params}}


def _assert_evaluators_agree(cond: dict, df: pl.DataFrame) -> list[bool]:
    engine = SignalEngine()
    vec = engine._eval_vec(cond, df).tolist()
    assert [bool(engine.evaluate_condition(cond, i, df)) for i in range(len(df))] == vec
    return vec


def test_bandwidth_is_band_width_over_middle_band():
    close = [100.0 + (i % 5) * 2 for i in range(30)]
    cond = _cond("bollinger_bandwidth", period=20, operator="<=", value=1000)
    df = IndicatorEngine.calculate(_ohlcv(close), [cond, _cond("bollinger_bands", period=20)])
    ub, lb = df["boll_ub"].to_numpy(), df["boll_lb"].to_numpy()
    sma = np.convolve(close, np.ones(20) / 20, mode="valid")[-1]
    assert df["bbw_20_2p0"][-1] == pytest.approx((ub[-1] - lb[-1]) / sma * 100.0)
    assert _assert_evaluators_agree(cond, df)[-1] is True


def test_bandwidth_is_blank_until_window_fills():
    """신규 상장 초기 짧은 창의 좁은 밴드폭이 조건을 통과하거나 스퀴즈 기준이 되면 안 된다."""
    close = [100.0, 100.5, 100.0, 100.5, 100.0, 100.5, 100.0, 100.5]
    cond = _cond("bollinger_bandwidth", period=5, operator="<=", value=1000)
    df = IndicatorEngine.calculate(_ohlcv(close), [cond])
    assert all(v is None or np.isnan(v) for v in df["bbw_5_2p0"].to_list()[:4])
    assert _assert_evaluators_agree(cond, df)[:4] == [False] * 4


def test_squeeze_marks_lowest_width_within_recent_days_only():
    # 앞은 출렁이고 뒤는 잠잠해 밴드폭이 끝에서 최저가 된다.
    wide = [100.0 + (-1) ** i * 10 for i in range(40)]
    calm = [100.0 + (-1) ** i * 0.5 for i in range(25)]
    cond = _cond("bollinger_squeeze", period=5, lookbackPeriod=30, withinDays=2)
    df = IndicatorEngine.calculate(_ohlcv(wide + calm), [cond])
    vec = _assert_evaluators_agree(cond, df)
    assert vec[20] is False  # 넓은 구간
    assert any(vec[-25:])


def test_ma_rising_requires_consecutive_days_and_falling_mirrors():
    close = [10.0] * 5 + [10.0 + i for i in range(1, 8)] + [5.0] * 8
    rising = _cond("ma_rising", period=3, days=2)
    falling = _cond("ma_falling", period=3, days=2)
    df = IndicatorEngine.calculate(_ohlcv(close), [rising, falling])
    up, down = _assert_evaluators_agree(rising, df), _assert_evaluators_agree(falling, df)
    assert up[:5] == [False] * 5
    assert up[8] is True
    assert not any(a and b for a, b in zip(up, down))
    assert any(down[12:])


def test_high_ratio_uses_intraday_high_of_window_including_today():
    close, high = [100.0, 100.0, 90.0], [100.0, 120.0, 90.0]
    cond = _cond("high_52w_ratio", period=3, operator=">=", value=75)
    df = IndicatorEngine.calculate(_ohlcv(close, high=high), [cond])
    assert df["high_ratio_3"][-1] == pytest.approx(75.0)
    assert _assert_evaluators_agree(cond, df) == [False, False, True]


def test_gap_compares_open_with_previous_close():
    close, open_ = [100.0, 100.0, 100.0], [100.0, 105.0, 98.0]
    up, down = _cond("gap", operator=">=", value=3), _cond("gap", operator="<=", value=-2)
    df = IndicatorEngine.calculate(_ohlcv(close, open_=open_), [up, down])
    assert df["gap_pct"][1] == pytest.approx(5.0)
    assert _assert_evaluators_agree(up, df) == [False, True, False]
    assert _assert_evaluators_agree(down, df) == [False, False, True]


@pytest.mark.parametrize("cid", ["bollinger_squeeze", "ma_rising", "ma_falling"])
def test_event_indicator_fails_closed_without_column(cid):
    cond = _cond(cid, period=20, days=5, lookbackPeriod=120, withinDays=5)
    assert SignalEngine()._eval_vec(cond, pl.DataFrame({"close": [1.0, 2.0]})).tolist() == [False, False]


@pytest.mark.parametrize("kwargs, expected", [
    ({"indicator": "bollinger_bandwidth", "period": 20, "operator": "<=", "value": 10},
     {"period": 20, "operator": "<=", "value": 10}),
    ({"indicator": "bollinger_squeeze", "period": 20, "lookback_period": 120, "within_days": 5},
     {"period": 20, "lookbackPeriod": 120, "withinDays": 5}),
    ({"indicator": "ma_rising", "period": 20, "days": 5}, {"period": 20, "days": 5}),
    ({"indicator": "high_52w_ratio", "period": 252, "operator": ">=", "value": 95},
     {"period": 252, "operator": ">=", "value": 95}),
    ({"indicator": "gap", "operator": ">=", "value": 3}, {"operator": ">=", "value": 3}),
])
def test_converter_keeps_every_parameter(kwargs, expected):
    cond = _tech_signal_to_condition(TechnicalSignal(signal_type="buy", **kwargs))
    assert cond["id"] == kwargs["indicator"]
    assert expected.items() <= cond["params"].items()


@pytest.mark.parametrize("cond, text", [
    (_cond("bollinger_bandwidth", period=20, operator="<=", value=10), "볼린저 밴드폭(20일) 10% 이하"),
    (_cond("bollinger_squeeze", lookbackPeriod=120, withinDays=5), "볼린저 밴드폭 최근 120일 최저(최근 5거래일 내)"),
    (_cond("ma_rising", period=20, days=5), "20일 이동평균 5거래일 연속 상승"),
    (_cond("ma_falling", period=20, days=5), "20일 이동평균 5거래일 연속 하락"),
    (_cond("high_52w_ratio", period=252, operator=">=", value=95), "최근 252거래일 최고가 대비 95% 이상"),
    (_cond("gap", operator=">=", value=3), "시가 갭 3% 이상"),
])
def test_trade_reason_text(cond, text):
    assert trade_reason.render_kr(SignalEngine()._base_condition_segments(cond)) == text


@pytest.mark.parametrize("factor", [
    "bollinger_bandwidth", "bollinger_squeeze", "ma_rising", "ma_falling", "high_52w_ratio", "gap",
])
def test_exposed_to_interpreter_vocabulary(factor):
    from strategy_conversation.interpreter.prompts import build_system_prompt

    assert f"technical.{factor}" in build_system_prompt()


def test_warmup_covers_chained_windows():
    from backtest_engine import _max_indicator_period

    entry = {"logic": "and", "conditions": [_cond("bollinger_squeeze", period=20, lookbackPeriod=120, withinDays=5)]}
    assert _max_indicator_period(entry, None) >= 145


def _validated(*conditions):
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.pipeline import run_validation

    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["KOSPI200"]}, "portfolio": {"selection_count": 5}, "backtest": {"period": "5y"},
        "declined": [{"field": "stop_loss", "source_text": "안 함"}, {"field": "take_profit", "source_text": "안 함"}],
        "entry_conditions": list(conditions),
        "exit_conditions": [{"factor": "technical.rsi", "operator": ">", "value": 70.0, "parameters": {"period": 14},
                             "source_text": "RSI 70 초과", "value_source": "USER_PROVIDED"}],
    }})
    normalized, report = run_validation(intent)
    intent.strategy = normalized.strategy
    return intent, report


def _leaf(factor, operator=None, value=None, **parameters):
    return {"factor": factor, "operator": operator, "value": value, "parameters": parameters,
            "source_text": "조건", "value_source": "USER_PROVIDED" if value is not None else "MISSING"}


@pytest.mark.parametrize("leaf, indicator, fields", [
    (_leaf("technical.bollinger_bandwidth", "<=", 10.0), "bollinger_bandwidth", {"value": 10.0}),
    (_leaf("technical.bollinger_squeeze", period=20, lookback_period=120, within_days=5),
     "bollinger_squeeze", {"lookback_period": 120, "within_days": 5}),
    (_leaf("technical.ma_rising", period=20, days=5), "ma_rising", {"period": 20, "days": 5}),
    (_leaf("technical.ma_falling", period=60, days=3), "ma_falling", {"period": 60, "days": 3}),
    (_leaf("technical.high_52w_ratio", ">=", 95.0), "high_52w_ratio", {"period": 252, "value": 95.0}),
    (_leaf("technical.gap", ">=", 3.0), "gap", {"value": 3.0}),
])
def test_validated_condition_compiles_and_decompiles(leaf, indicator, fields):
    from strategy_conversation.compiler.strategy_compiler import compile_strategy
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy

    intent, report = _validated(leaf)
    assert report.errors == []
    parsed = compile_strategy(intent, report, "")
    signal = parsed.entry_signals[0]
    assert signal.indicator == indicator
    assert fields.items() <= signal.model_dump().items()
    restored = decompile_strategy(parsed).entry_conditions[0]
    assert restored.factor == f"technical.{indicator}"
    for key in set(fields) - {"value"}:
        assert restored.parameters[key] == fields[key]


@pytest.mark.parametrize("leaf, missing", [
    (_leaf("technical.ma_rising", period=20), "days"),
    (_leaf("technical.ma_falling", days=5), "period"),
    (_leaf("technical.bollinger_squeeze", period=20, lookback_period=120), "within_days"),
    (_leaf("technical.bollinger_squeeze", period=20, within_days=5), "lookback_period"),
])
def test_required_parameter_is_asked_not_defaulted(leaf, missing):
    _, report = _validated(leaf)
    assert any(missing in field for field in report.missing_fields), report.missing_fields


def test_gap_notice_on_next_open_only():
    from engine import result_warnings as rw

    assert "그다음 거래일" in rw.GAP_FILLED_NEXT_OPEN
