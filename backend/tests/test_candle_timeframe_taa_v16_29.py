"""엔진 v16.29 — 캔들 패턴·다중 타임프레임·전술 자산배분(VAA/DAA/PAA) 회귀.

- 캔들 패턴: OHLC 배열의 정의(장악형·도지·망치형·샛별형·적삼병)가 완성 봉에서만 참.
- 타임프레임: 주봉 이동평균 조건이 일봉 프레임에 `__weekly` 열로 붙고, 미완성 주는 보이지 않는다.
- TAA: 13612W 점수와 세 모델의 비중 규칙(VAA 방어 전환·DAA 카나리아 비율·PAA 채권 비중).
- 대화 레인: candle 잎·timeframe 파라미터·taa 스펙이 ParsedStrategy → 엔진 요청 → 디컴파일까지 왕복.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl
import pytest

from engine import taa
from engine.indicators import IndicatorEngine, candle_pattern_mask, resample_ohlcv
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition, to_backtest_request
from engine.nl_parser import TechnicalSignal
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation


# ── 캔들 패턴 ────────────────────────────────────────────────────────────────

def _ohlc(rows):
    o, h, l, c = (np.array([r[i] for r in rows], dtype=float) for i in range(4))
    return o, h, l, c


def test_bullish_engulfing_and_doji():
    rows = [(100, 101, 99, 100)] * 11 + [(100, 101, 96, 97), (96, 103, 95, 102), (102, 102.5, 101.5, 102.02)]
    o, h, l, c = _ohlc(rows)
    eng = candle_pattern_mask(o, h, l, c, "bullish_engulfing")
    assert eng[-2] and not eng[-1] and not eng[-3]
    doji = candle_pattern_mask(o, h, l, c, "doji")
    assert doji[-1] and not doji[-2]


def test_hammer_needs_prior_decline_and_shape():
    down = [(100 - i, 101 - i, 98 - i, 99.5 - i) for i in range(8)]     # 하락 문맥
    rows = down + [(92, 92.5, 86, 92.2)]                                   # 긴 아래꼬리·작은 몸통
    o, h, l, c = _ohlc(rows)
    assert candle_pattern_mask(o, h, l, c, "hammer")[-1]
    assert not candle_pattern_mask(o, h, l, c, "hanging_man")[-1]          # 상승 문맥이 아니다


def test_morning_star_and_three_white_soldiers():
    base = [(100, 101, 99, 100)] * 12
    star = base + [(100, 100.5, 94, 94.5), (94, 94.8, 93.5, 94.2), (94.5, 99, 94.3, 98.5)]
    o, h, l, c = _ohlc(star)
    assert candle_pattern_mask(o, h, l, c, "morning_star")[-1]
    soldiers = base + [(100, 102.2, 99.8, 102), (101, 104.2, 100.8, 104), (103, 106.2, 102.8, 106)]
    o, h, l, c = _ohlc(soldiers)
    assert candle_pattern_mask(o, h, l, c, "three_white_soldiers")[-1]
    assert not candle_pattern_mask(o, h, l, c, "three_black_crows")[-1]


def test_candle_condition_flows_through_indicator_and_signal_engines():
    rows = [(100, 101, 99, 100)] * 11 + [(100, 101, 96, 97), (96, 103, 95, 102)]
    dates = pd.bdate_range("2024-01-01", periods=len(rows))
    df = pl.DataFrame({"date": list(dates), "open": [r[0] for r in rows], "high": [r[1] for r in rows],
                       "low": [r[2] for r in rows], "close": [r[3] for r in rows], "volume": [1000.0] * len(rows)})
    cond = _tech_signal_to_condition(TechnicalSignal(indicator="candle_bullish_engulfing", signal_type="buy"))
    assert cond["id"] == "candle_pattern" and cond["params"]["pattern"] == "bullish_engulfing"
    out = IndicatorEngine.calculate(df, [cond])
    sig, reasons = SignalEngine().generate_signals(out, {"conditions": [cond], "logic": "AND"})
    assert sig[-1] and not sig[-2]
    assert "상승 장악형" in reasons[-1]
    assert SignalEngine().evaluate_condition(cond, len(rows) - 1, out)


# ── 다중 타임프레임 ───────────────────────────────────────────────────────────

def test_weekly_timeframe_columns_align_to_bar_end_without_lookahead():
    dates = pd.bdate_range("2024-01-01", periods=30)     # 6주
    close = np.linspace(100, 129, 30)
    df = pl.DataFrame({"date": list(dates), "open": close, "high": close + 1, "low": close - 1,
                       "close": close, "volume": [1.0] * 30})
    cond = {"type": "indicator", "id": "ma_crossover",
            "params": {"shortMA": 1, "longMA": 2, "timeframe": "weekly", "mode": "above", "signalType": "buy"}}
    out = IndicatorEngine.calculate(df, [cond]).to_pandas()
    assert "close_2_sma__weekly" in out.columns and "close__weekly" in out.columns
    weekly = resample_ohlcv(df.to_pandas(), "weekly")
    # 첫 주 라벨(금요일)에 그 주 종가가 보이고, 그 전 날들은 NaN(미완성 봉 미노출).
    first_label = pd.Timestamp(weekly["date"].iloc[0])
    before = out[pd.to_datetime(out["date"]) < first_label]
    at = out[pd.to_datetime(out["date"]) == first_label]
    assert before["close__weekly"].isna().all()
    assert float(at["close__weekly"].iloc[0]) == pytest.approx(float(weekly["close"].iloc[0]))
    sig, reasons = SignalEngine().generate_signals(IndicatorEngine.calculate(df, [cond]),
                                                   {"conditions": [cond], "logic": "AND"})
    assert sig.any() and "(주봉 기준)" in reasons[np.where(sig)[0][0]]


# ── 전술 자산배분 ──────────────────────────────────────────────────────────────

def _prices(n=320, seed=0):
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.random.default_rng(seed)
    up = 100 * np.cumprod(1 + rng.normal(0.0008, 0.005, n))
    down = 100 * np.cumprod(1 + rng.normal(-0.0015, 0.005, n))
    flat = np.full(n, 100.0) * np.cumprod(1 + rng.normal(0.0001, 0.001, n))
    return pd.DataFrame({"UP": up, "DOWN": down, "BOND": flat, "CANARY_BAD": down * 0.9}, index=idx)


def test_vaa_switches_to_defensive_when_any_offensive_momentum_negative():
    px = _prices()
    w = taa.taa_weight_panel(px, "vaa", ["UP", "DOWN"], ["BOND"], top_n=1)
    last = w.iloc[-1]
    assert last["BOND"] == pytest.approx(1.0) and last["UP"] == 0.0
    w2 = taa.taa_weight_panel(px, "vaa", ["UP"], ["BOND"], top_n=1)
    assert w2.iloc[-1]["UP"] == pytest.approx(1.0)
    assert w.iloc[:taa.LOOKBACK_DAYS - 30].isna().all().all()          # 자료 부족 구간은 NaN


def test_daa_cash_fraction_follows_canary_breadth():
    px = _prices()
    w = taa.taa_weight_panel(px, "daa", ["UP", "DOWN"], ["BOND"], canary=["CANARY_BAD", "UP"], top_n=1)
    last = w.iloc[-1]
    assert last["BOND"] == pytest.approx(0.5) and last["UP"] == pytest.approx(0.5)
    assert last.sum() == pytest.approx(1.0)


def test_paa_bond_fraction_from_breadth():
    px = _prices()
    w = taa.taa_weight_panel(px, "paa", ["UP", "DOWN"], ["BOND"], top_n=2, protection=1)
    last = w.iloc[-1]
    # N=2, 양수 1개, a=1 → 채권 (2−1)/(2−1)=1.0
    assert last["BOND"] == pytest.approx(1.0)
    w0 = taa.taa_weight_panel(px, "paa", ["UP", "DOWN"], ["BOND"], top_n=2, protection=0)
    assert w0.iloc[-1]["BOND"] == pytest.approx(0.5) and w0.iloc[-1]["UP"] == pytest.approx(0.5)


# ── 대화 레인 ────────────────────────────────────────────────────────────────

def _intent(**strategy_overrides):
    strategy = {
        "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": [], "symbols": []},
        "entry_conditions": [], "exit_conditions": [], "ranking": [],
        "portfolio": {"selection_count": 10, "rebalance_frequency": "monthly"},
        "risk_management": {}, "backtest": {},
    }
    strategy.update(strategy_overrides)
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "confidence": 0.9, "strategy": strategy})


def _compile(intent):
    validated, report = run_validation(intent)
    parsed, dropped, pending = compile_partial(validated, report, "")
    return validated, report, parsed, dropped, pending


def test_candle_leaf_and_weekly_timeframe_round_trip():
    _, report, parsed, _, _ = _compile(_intent(
        entry_conditions=[{"factor": "technical.candle_hammer", "operator": None, "value": None,
                           "source_text": "망치형이 나오면"},
                          {"factor": "technical.rsi", "operator": "<", "value": 30,
                           "parameters": {"period": 14, "timeframe": "주봉"}, "source_text": "주봉 RSI 30 이하"}],
        exit_conditions=[{"factor": "technical.candle_bearish_engulfing", "operator": None, "value": None,
                          "source_text": "하락 장악형이면 매도"}],
    ))
    assert not report.unsupported_features and not report.errors, (report.unsupported_features, report.errors)
    inds = {(s.indicator, s.timeframe) for s in parsed.entry_signals}
    assert ("candle_hammer", None) in inds and ("rsi", "weekly") in inds
    assert parsed.exit_signals[0].indicator == "candle_bearish_engulfing"
    req = to_backtest_request(parsed, resolve_symbols=False)
    conds = {c["id"]: c["params"] for c in req["entry"]["conditions"]}
    assert conds["candle_pattern"]["pattern"] == "hammer"
    assert conds["rsi"]["timeframe"] == "weekly"
    spec = decompile_strategy(parsed)
    factors = {c.factor: c.parameters for c in spec.entry_conditions}
    assert "technical.candle_hammer" in factors
    assert factors["technical.rsi"]["timeframe"] == "weekly"


def test_taa_spec_resolves_assets_and_reaches_engine_request():
    _, report, parsed, _, _ = _compile(_intent(
        universe={"markets": ["KOSPI"], "sectors": [], "symbols": []},
        portfolio={},
        taa={"model": "VAA", "offensive": ["삼성전자", "SK하이닉스"], "defensive": ["현대차"], "top_n": 1,
             "source_text": "VAA로"},
    ))
    assert not report.unsupported_features and not report.errors
    assert parsed.ranking_metric == "taa" and parsed.allocation_type == "schedule"
    assert parsed.rebalancing_period == "monthly"
    assert parsed.taa.model == "vaa" and parsed.taa.offensive == ["005930", "000660"]
    assert set(parsed.target_symbols) == {"005930", "000660", "005380"}
    req = to_backtest_request(parsed)
    assert req["risk"]["ranking_metric"] == "taa" and req["risk"]["allocation_type"] == "schedule"
    assert req["risk"]["taa"]["defensive"] == ["005380"] and req["risk"]["max_positions"] == 3
    spec = decompile_strategy(parsed)
    assert spec.taa.model == "vaa" and spec.taa.offensive == ["005930", "000660"]


def test_taa_without_assets_asks_and_is_not_sent():
    _, report, parsed, _, _ = _compile(_intent(portfolio={}, taa={"model": "daa", "source_text": "DAA 전략"}))
    fields = {q.field for q in report.clarification_questions}
    assert "strategy.taa.offensive" in fields
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["taa"] is None
