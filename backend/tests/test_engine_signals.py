import pytest
import polars as pl
import numpy as np
from engine.signals import SignalEngine

@pytest.fixture
def signal_engine():
    return SignalEngine()

def test_evaluate_condition_ma_crossover(signal_engine):
    # Setup dummy data for golden cross and dead cross
    data = {"close_5_sma": [10, 10, 12, 8], "close_20_sma": [11, 11, 11, 11]}
    df = pl.DataFrame(data)
    
    # Golden cross: short crosses above long
    cond_buy = {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}
    
    assert signal_engine.evaluate_condition(cond_buy, 1, df) == False # 10 < 11
    assert signal_engine.evaluate_condition(cond_buy, 2, df) == True  # 10 < 11 -> 12 > 11 (Golden Cross)
    assert signal_engine.evaluate_condition(cond_buy, 3, df) == False # 12 > 11 -> 8 < 11 (Dead Cross, but looking for buy)

    # Dead cross: short crosses below long
    cond_sell = {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "sell"}}
    assert signal_engine.evaluate_condition(cond_sell, 2, df) == False
    assert signal_engine.evaluate_condition(cond_sell, 3, df) == True  # 12 > 11 -> 8 < 11 (Dead Cross)

def test_evaluate_condition_rsi(signal_engine):
    data = {"rsi_14": [20, 30, 40, 80]}
    df = pl.DataFrame(data)
    
    cond_under_30 = {"id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}}
    assert signal_engine.evaluate_condition(cond_under_30, 0, df) == True
    assert signal_engine.evaluate_condition(cond_under_30, 1, df) == False # Not < 30
    
    cond_over_70 = {"id": "rsi", "params": {"period": 14, "value": 70, "operator": ">="}}
    assert signal_engine.evaluate_condition(cond_over_70, 3, df) == True

def test_rsi_rebound_buy_is_cross_up_not_threshold(signal_engine):
    # 'RSI 30 아래로 갔다가 다시 올라오는' 반등 = 30선 상향 돌파(직전 봉 <=30, 당일 >30).
    # 단순 임계값(RSI<=30, 과매도 구간)과 달리 돌파하는 봉에서만 True여야 한다.
    df = pl.DataFrame({"rsi_14": [25.0, 28.0, 32.0, 40.0]})
    cond = {"id": "rsi", "params": {"period": 14, "value": 30, "mode": "rebound", "signalType": "buy"}}

    # 행별 평가자
    assert signal_engine.evaluate_condition(cond, 0, df) == False  # 첫 봉(직전 없음)
    assert signal_engine.evaluate_condition(cond, 1, df) == False  # 28: 아직 30 미돌파
    assert signal_engine.evaluate_condition(cond, 2, df) == True   # 28→32: 상향 돌파
    assert signal_engine.evaluate_condition(cond, 3, df) == False  # 이미 30 위

    # 벡터화 평가자도 동일해야 한다
    assert list(signal_engine._eval_vec(cond, df)) == [False, False, True, False]

    # 같은 데이터를 단순 임계값(RSI<=30)으로 보면 결과가 다르다(반등과 구분됨)
    cond_threshold = {"id": "rsi", "params": {"period": 14, "value": 30, "operator": "<="}}
    assert list(signal_engine._eval_vec(cond_threshold, df)) == [True, True, False, False]

def test_rsi_rebound_sell_is_cross_down(signal_engine):
    # 매도 반등(과매수 후 하향 돌파): 직전 봉 >=70, 당일 <70인 봉에서만 True.
    df = pl.DataFrame({"rsi_14": [75.0, 72.0, 68.0, 60.0]})
    cond = {"id": "rsi", "params": {"period": 14, "value": 70, "mode": "rebound", "signalType": "sell"}}
    assert list(signal_engine._eval_vec(cond, df)) == [False, False, True, False]
    assert signal_engine.evaluate_condition(cond, 2, df) == True

def test_evaluate_condition_price_limit_exit(signal_engine):
    data = {"close": [100.0, 120.0, 80.0]}
    df = pl.DataFrame(data)
    
    # Stop loss krw
    cond_sl = {"id": "price_limit_exit", "params": {"stopLoss": 90, "stopLossMode": "krw"}}
    assert signal_engine.evaluate_condition(cond_sl, 0, df) == False # 100
    assert signal_engine.evaluate_condition(cond_sl, 2, df) == True  # 80 <= 90
    
    # Take profit krw
    cond_tp = {"id": "price_limit_exit", "params": {"takeProfit": 110, "takeProfitMode": "krw"}}
    assert signal_engine.evaluate_condition(cond_tp, 0, df) == False # 100
    assert signal_engine.evaluate_condition(cond_tp, 1, df) == True  # 120 >= 110
    
    # Combined
    cond_both = {"id": "price_limit_exit", "params": {"stopLoss": 90, "stopLossMode": "krw", "takeProfit": 110, "takeProfitMode": "krw"}}
    assert signal_engine.evaluate_condition(cond_both, 0, df) == False
    assert signal_engine.evaluate_condition(cond_both, 1, df) == True # TP
    assert signal_engine.evaluate_condition(cond_both, 2, df) == True # SL

def test_evaluate_condition_ai_model(signal_engine):
    data = {"ai_score": [0.3, 0.7, 0.9]} # Probabilities 30%, 70%, 90%
    df = pl.DataFrame(data)
    
    cond_buy_70 = {"id": "ai_model", "params": {"signalType": "buy", "minProbability": 70}} # threshold 0.7
    assert signal_engine.evaluate_condition(cond_buy_70, 0, df) == False
    assert signal_engine.evaluate_condition(cond_buy_70, 1, df) == True
    assert signal_engine.evaluate_condition(cond_buy_70, 2, df) == True
    
    cond_sell_60 = {"id": "ai_model", "params": {"signalType": "sell", "minProbability": 50}} # threshold 0.5
    assert signal_engine.evaluate_condition(cond_sell_60, 0, df) == True # 0.3 <= 0.5
    assert signal_engine.evaluate_condition(cond_sell_60, 1, df) == False # 0.7 <= 0.5 (False)

def test_evaluate_condition_ai_drop_model(signal_engine):
    data = {"ai_drop_score": [0.2, 0.6, 0.9]} # Drop probs 20%, 60%, 90%
    df = pl.DataFrame(data)
    
    # Buy strategy: Drop prob must be <= threshold (e.g. 50%)
    cond_buy_50 = {"id": "ai_drop_model", "params": {"signalType": "buy", "minProbability": 50}}
    assert signal_engine.evaluate_condition(cond_buy_50, 0, df) == True  # 0.2 <= 0.5
    assert signal_engine.evaluate_condition(cond_buy_50, 1, df) == False # 0.6 <= 0.5 (False)
    
    # Sell strategy: Drop prob must be >= threshold (e.g. 80%)
    cond_sell_80 = {"id": "ai_drop_model", "params": {"signalType": "sell", "minProbability": 80}}
    assert signal_engine.evaluate_condition(cond_sell_80, 1, df) == False # 0.6 >= 0.8 (False)
    assert signal_engine.evaluate_condition(cond_sell_80, 2, df) == True  # 0.9 >= 0.8


def test_ai_signal_default_threshold_is_calibrated_not_dead(signal_engine):
    """Regression: an AI signal block with NO explicit threshold must default to
    the model's val-calibrated threshold (in-distribution), not the legacy 0.70.

    The DOWN head's scores top out near ~0.38, so the old hardcoded 70 (=0.70)
    default — and the dead 0.50 meta fallback — never fired. The default must now
    sit below the head's score range so the signal is usable."""
    from engine.signals import _ai_calibrated_thresholds
    buy_thr, sell_thr = _ai_calibrated_thresholds()
    # Both calibrated defaults must be in-distribution (the dead-signal regression).
    assert sell_thr < 0.5, "sell_threshold default must be < 0.5 (DOWN scores max ~0.38)"
    assert buy_thr < 0.5, "buy_threshold default must be < 0.5"

    just_below = round(sell_thr - 0.02, 4)
    just_above = round(sell_thr + 0.005, 4)
    df = pl.DataFrame({"ai_drop_score": [just_below, just_above]})
    # ai_drop_model defaults: targetType='down', signalType='sell', no threshold given.
    cond = {"id": "ai_drop_model", "params": {}}
    assert list(signal_engine._eval_vec(cond, df)) == [False, True]
    # Row-by-row (test-compat) path must agree with the vectorized path.
    assert signal_engine.evaluate_condition(cond, 0, df) == False
    assert signal_engine.evaluate_condition(cond, 1, df) == True

    # An explicit threshold (frontend 'threshold' or legacy 'minProbability') still wins.
    cond_explicit = {"id": "ai_drop_model", "params": {"threshold": 70}}
    assert list(signal_engine._eval_vec(cond_explicit, df)) == [False, False]


def test_ai_drop_model_rank_mode_suppresses_per_symbol_exit(signal_engine):
    """exitMode='rank' is handled cross-sectionally by backtest_engine; the
    per-symbol signal evaluator must emit no exits (all False), even for scores
    that would clear an absolute threshold."""
    df = pl.DataFrame({"ai_drop_score": [0.1, 0.38, 0.9]})
    cond = {"id": "ai_drop_model", "params": {"exitMode": "rank", "rankPercentile": 0.1}}
    assert list(signal_engine._eval_vec(cond, df)) == [False, False, False]
    for i in range(3):
        assert signal_engine.evaluate_condition(cond, i, df) == False

# ──────────────────────────────────────────────────────────────────────────────
# Fix 3: ema / macd / stochastic / cci / adx 평가자 누락 회귀 방지 테스트
# ──────────────────────────────────────────────────────────────────────────────

def test_evaluate_condition_ema_price_crossover(signal_engine):
    """가격이 EMA를 상향/하향 돌파할 때만 신호 발생 (Fix 3)"""
    data = {
        "close":      [10.0, 10.0, 12.0, 8.0],
        "close_20_ema": [11.0, 11.0, 11.0, 11.0],
    }
    df = pl.DataFrame(data)

    cond_buy  = {"id": "ema", "params": {"period": 20, "signalType": "buy"}}
    cond_sell = {"id": "ema", "params": {"period": 20, "signalType": "sell"}}

    assert signal_engine.evaluate_condition(cond_buy, 0, df) == False  # idx=0 → False (prev 없음)
    assert signal_engine.evaluate_condition(cond_buy, 1, df) == False  # 10 → 10: 여전히 EMA 아래
    assert signal_engine.evaluate_condition(cond_buy, 2, df) == True   # 10 → 12: EMA(11) 상향 돌파
    assert signal_engine.evaluate_condition(cond_buy, 3, df) == False  # 12 → 8: 이미 위에서 아래, buy 아님

    assert signal_engine.evaluate_condition(cond_sell, 2, df) == False # 10 → 12: 위로 돌파, sell 아님
    assert signal_engine.evaluate_condition(cond_sell, 3, df) == True  # 12 → 8: EMA(11) 하향 돌파

def test_evaluate_condition_ema_dual_crossover(signal_engine):
    """단기 EMA가 장기 EMA를 골든/데드 크로스 (Fix 3)"""
    data = {
        "close_5_ema":  [10.0, 10.0, 12.0, 8.0],
        "close_20_ema": [11.0, 11.0, 11.0, 11.0],
    }
    df = pl.DataFrame(data)

    cond_buy  = {"id": "ema", "params": {"shortPeriod": 5, "longPeriod": 20, "signalType": "buy"}}
    cond_sell = {"id": "ema", "params": {"shortPeriod": 5, "longPeriod": 20, "signalType": "sell"}}

    assert signal_engine.evaluate_condition(cond_buy,  2, df) == True   # 골든크로스
    assert signal_engine.evaluate_condition(cond_sell, 3, df) == True   # 데드크로스
    assert signal_engine.evaluate_condition(cond_buy,  3, df) == False  # 데드크로스는 buy 아님

def test_evaluate_condition_macd_crossover(signal_engine):
    """MACD 라인이 시그널 라인을 크로스 (Fix 3)"""
    data = {
        "macd":  [0.5, 0.5, 1.5, 0.5],
        "macds": [1.0, 1.0, 1.0, 1.0],
    }
    df = pl.DataFrame(data)

    cond_buy  = {"id": "macd", "params": {"signalType": "buy",  "mode": "crossover"}}
    cond_sell = {"id": "macd", "params": {"signalType": "sell", "mode": "crossover"}}

    assert signal_engine.evaluate_condition(cond_buy,  0, df) == False  # idx=0 → False
    assert signal_engine.evaluate_condition(cond_buy,  2, df) == True   # 0.5 → 1.5: 시그널선 상향 돌파
    assert signal_engine.evaluate_condition(cond_sell, 3, df) == True   # 1.5 → 0.5: 시그널선 하향 돌파
    assert signal_engine.evaluate_condition(cond_sell, 2, df) == False  # 상향 돌파는 sell 아님

def test_evaluate_condition_macd_zero_line(signal_engine):
    """MACD 제로선 돌파 모드 (Fix 3)"""
    data = {"macd": [-1.0, -0.5, 0.5, 1.0]}
    df = pl.DataFrame(data)

    cond_buy  = {"id": "macd", "params": {"signalType": "buy",  "mode": "zero"}}
    cond_sell = {"id": "macd", "params": {"signalType": "sell", "mode": "zero"}}

    assert signal_engine.evaluate_condition(cond_buy,  0, df) == False  # -1 < 0
    assert signal_engine.evaluate_condition(cond_buy,  2, df) == True   # 0.5 > 0
    assert signal_engine.evaluate_condition(cond_sell, 0, df) == True   # -1 < 0
    assert signal_engine.evaluate_condition(cond_sell, 2, df) == False  # 0.5 NOT < 0

def test_evaluate_condition_stochastic_crossover(signal_engine):
    """Stochastic K/D 크로스오버 (Fix 3)"""
    data = {
        "kdjk": [20.0, 20.0, 40.0, 10.0],
        "kdjd": [30.0, 30.0, 30.0, 30.0],
    }
    df = pl.DataFrame(data)

    cond_buy  = {"id": "stochastic", "params": {"signalType": "buy",  "mode": "crossover"}}
    cond_sell = {"id": "stochastic", "params": {"signalType": "sell", "mode": "crossover"}}

    assert signal_engine.evaluate_condition(cond_buy,  0, df) == False  # idx=0 → False
    assert signal_engine.evaluate_condition(cond_buy,  2, df) == True   # K: 20→40, D=30 골든크로스
    assert signal_engine.evaluate_condition(cond_sell, 3, df) == True   # K: 40→10, D=30 데드크로스

def test_evaluate_condition_stochastic_level(signal_engine):
    """Stochastic 과매수/과매도 레벨 비교 (Fix 3)"""
    data = {"kdjk": [10.0, 25.0, 80.0, 85.0]}
    df = pl.DataFrame(data)

    cond_oversold   = {"id": "stochastic", "params": {"signalType": "buy",  "mode": "level", "value": 20, "operator": "<"}}
    cond_overbought = {"id": "stochastic", "params": {"signalType": "sell", "mode": "level", "value": 80, "operator": ">="}}

    assert signal_engine.evaluate_condition(cond_oversold,   0, df) == True   # 10 < 20
    assert signal_engine.evaluate_condition(cond_oversold,   1, df) == False  # 25 NOT < 20
    assert signal_engine.evaluate_condition(cond_overbought, 2, df) == True   # 80 >= 80
    assert signal_engine.evaluate_condition(cond_overbought, 1, df) == False  # 25 NOT >= 80

def test_evaluate_condition_cci(signal_engine):
    """CCI 임계값 비교 (Fix 3)"""
    data = {"cci_14": [-150.0, -80.0, 80.0, 150.0]}
    df = pl.DataFrame(data)

    cond_buy  = {"id": "cci", "params": {"period": 14, "signalType": "buy",  "value": -100, "operator": "<"}}
    cond_sell = {"id": "cci", "params": {"period": 14, "signalType": "sell", "value":  100, "operator": ">"}}

    assert signal_engine.evaluate_condition(cond_buy,  0, df) == True   # -150 < -100
    assert signal_engine.evaluate_condition(cond_buy,  1, df) == False  # -80 NOT < -100
    assert signal_engine.evaluate_condition(cond_sell, 3, df) == True   # 150 > 100
    assert signal_engine.evaluate_condition(cond_sell, 2, df) == False  # 80 NOT > 100

def test_evaluate_condition_adx(signal_engine):
    """ADX 추세 강도 임계값 비교 (Fix 3)"""
    data = {"adx": [10.0, 20.0, 25.0, 35.0]}
    df = pl.DataFrame(data)

    cond = {"id": "adx", "params": {"value": 25, "operator": ">="}}

    assert signal_engine.evaluate_condition(cond, 0, df) == False  # 10 < 25
    assert signal_engine.evaluate_condition(cond, 1, df) == False  # 20 < 25
    assert signal_engine.evaluate_condition(cond, 2, df) == True   # 25 >= 25
    assert signal_engine.evaluate_condition(cond, 3, df) == True   # 35 >= 25

def test_evaluate_condition_unknown_id_returns_false(signal_engine):
    """정의되지 않은 cid는 False를 반환하고 크래시 없어야 한다 (Fix 3 경계 케이스)"""
    df = pl.DataFrame({"close": [100.0]})
    cond = {"id": "unknown_indicator_xyz", "params": {}}
    assert signal_engine.evaluate_condition(cond, 0, df) == False


def test_evaluate_condition_breakout_uses_intraday_high_and_low(signal_engine):
    """breakout은 종가가 아니라 당일 고가/저가 기준으로 돌파를 판정한다"""
    data = {
        "close": [100.0, 100.0, 100.0, 100.0],
        "high": [100.0, 100.0, 100.0, 106.0],
        "low": [95.0, 95.0, 95.0, 89.0],
        "high_3_max": [100.0, 100.0, 100.0, 100.0],
        "low_3_min": [95.0, 95.0, 95.0, 95.0],
    }
    df = pl.DataFrame(data)

    cond_buy = {"id": "breakout", "params": {"lookbackPeriod": 3, "signalType": "buy"}}
    cond_sell = {"id": "breakout", "params": {"lookbackPeriod": 3, "signalType": "sell"}}

    assert signal_engine.evaluate_condition(cond_buy, 3, df) == True
    assert signal_engine.evaluate_condition(cond_sell, 3, df) == True

# ──────────────────────────────────────────────────────────────────────────────
# Fix 4: _eval_vec(벡터화)과 evaluate_condition(행별) 결과 일관성 검증
# ──────────────────────────────────────────────────────────────────────────────

def test_eval_vec_matches_row_by_row_ma_crossover(signal_engine):
    """ma_crossover: 벡터화 결과 == 행별 결과 (Fix 4)"""
    data = {
        "close_5_sma":  [10.0, 10.0, 12.0, 8.0, 11.0],
        "close_20_sma": [11.0, 11.0, 11.0, 11.0, 11.0],
    }
    df = pl.DataFrame(data)
    cond = {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}

    vec  = list(signal_engine._eval_vec(cond, df))
    rows = [signal_engine.evaluate_condition(cond, i, df) for i in range(len(df))]
    assert vec == rows

def test_eval_vec_matches_row_by_row_rsi(signal_engine):
    """rsi: 벡터화 결과 == 행별 결과 (Fix 4)"""
    data = {"rsi_14": [15.0, 29.9, 30.0, 30.1, 70.0]}
    df = pl.DataFrame(data)
    cond = {"id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}}

    vec  = list(signal_engine._eval_vec(cond, df))
    rows = [signal_engine.evaluate_condition(cond, i, df) for i in range(len(df))]
    assert vec == rows

def test_eval_vec_matches_row_by_row_ema(signal_engine):
    """ema(단일 기간): 벡터화 결과 == 행별 결과 (Fix 4)"""
    data = {
        "close":       [10.0, 10.0, 12.0, 8.0, 13.0],
        "close_20_ema":[11.0, 11.0, 11.0, 11.0, 11.0],
    }
    df = pl.DataFrame(data)
    cond = {"id": "ema", "params": {"period": 20, "signalType": "buy"}}

    vec  = list(signal_engine._eval_vec(cond, df))
    rows = [signal_engine.evaluate_condition(cond, i, df) for i in range(len(df))]
    assert vec == rows

def test_eval_vec_matches_row_by_row_bollinger(signal_engine):
    """bollinger_bands: 벡터화 결과 == 행별 결과 (Fix 4)"""
    data = {
        "close":   [90.0, 95.0, 100.0, 105.0],
        "boll_lb": [92.0, 92.0,  92.0,  92.0],
        "boll_ub": [98.0, 98.0,  98.0,  98.0],
    }
    df = pl.DataFrame(data)
    cond_buy  = {"id": "bollinger_bands", "params": {"signalType": "buy"}}
    cond_sell = {"id": "bollinger_bands", "params": {"signalType": "sell"}}

    for cond in [cond_buy, cond_sell]:
        vec  = list(signal_engine._eval_vec(cond, df))
        rows = [signal_engine.evaluate_condition(cond, i, df) for i in range(len(df))]
        assert vec == rows, f"Mismatch for {cond['params']['signalType']}: {vec} vs {rows}"


def test_eval_vec_matches_row_by_row_breakout(signal_engine):
    """breakout: 벡터화 결과 == 행별 결과, 고가/저가 기준 유지"""
    data = {
        "close": [100.0, 100.0, 100.0, 100.0, 100.0],
        "high": [100.0, 101.0, 102.0, 103.0, 106.0],
        "low": [95.0, 94.0, 93.0, 92.0, 89.0],
        "high_3_max": [None, None, 102.0, 103.0, 103.0],
        "low_3_min": [None, None, 93.0, 92.0, 92.0],
    }
    df = pl.DataFrame(data)
    cond_buy = {"id": "breakout", "params": {"lookbackPeriod": 3, "signalType": "buy"}}
    cond_sell = {"id": "breakout", "params": {"lookbackPeriod": 3, "signalType": "sell"}}

    vec_buy = list(signal_engine._eval_vec(cond_buy, df))
    rows_buy = [signal_engine.evaluate_condition(cond_buy, i, df) for i in range(len(df))]
    assert vec_buy == rows_buy

    vec_sell = list(signal_engine._eval_vec(cond_sell, df))
    rows_sell = [signal_engine.evaluate_condition(cond_sell, i, df) for i in range(len(df))]
    assert vec_sell == rows_sell

def test_generate_signals_vectorized_produces_correct_signals(signal_engine):
    """generate_signals(_eval_vec 기반)가 올바른 신호 배열을 반환한다 (Fix 4)"""
    # RSI < 30 이면 매수
    data = {"rsi_14": [20.0, 35.0, 25.0, 50.0, 15.0]}
    df = pl.DataFrame(data)
    group = {
        "conditions": [
            {"type": "indicator", "id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}}
        ]
    }
    signals, reasons = signal_engine.generate_signals(df, group)

    assert list(signals) == [True, False, True, False, True]
    # 신호가 True인 날은 이유 문자열 존재
    for i, (sig, reason) in enumerate(zip(signals, reasons)):
        if sig:
            assert reason is not None, f"Day {i}: signal=True but reason is None"
        else:
            assert reason is None, f"Day {i}: signal=False but reason is not None"

def test_generate_signals_empty_group_returns_all_false(signal_engine):
    """조건 없는 그룹은 모두 False 반환 (경계 케이스)"""
    df = pl.DataFrame({"close": [100.0, 200.0, 300.0]})

    signals, reasons = signal_engine.generate_signals(df, {})
    assert list(signals) == [False, False, False]
    assert all(r is None for r in reasons)

    signals2, _ = signal_engine.generate_signals(df, None)
    assert list(signals2) == [False, False, False]


# ──────────────────────────────────────────────────────────────────────────────
# 재무 필터 데이터 누락 시 제외(fail-closed) 처리 테스트
# (명시적 재무 필터인데 데이터가 없으면 검증 불가 → 통과시키지 않고 제외)
# ──────────────────────────────────────────────────────────────────────────────

def test_fundamental_filter_missing_column_excludes_vec(signal_engine):
    """재무 컬럼(per/pbr 등)이 없으면 제외(np.zeros) 반환 — 벡터화 (_eval_vec)"""
    df = pl.DataFrame({"close": [1000.0, 1100.0, 950.0]})

    for cid in ["per", "pbr", "roe_or_gpa", "debt_ratio", "market_cap"]:
        cond = {"id": cid, "params": {"operator": "<=", "value": 10.0}}
        result = signal_engine._eval_vec(cond, df)
        assert list(result) == [False, False, False], \
            f"{cid}: 컬럼 없을 때 제외(False) 기대, 실제={list(result)}"

def test_fundamental_filter_missing_column_excludes_row(signal_engine):
    """재무 컬럼이 없으면 제외(False) 반환 — 행별 (evaluate_condition)"""
    df = pl.DataFrame({"close": [1000.0, 1100.0]})

    for cid in ["per", "pbr", "roe_or_gpa", "debt_ratio", "market_cap"]:
        cond = {"id": cid, "params": {"operator": "<=", "value": 10.0}}
        assert signal_engine.evaluate_condition(cond, 0, df) is False, \
            f"{cid}: 컬럼 없을 때 제외(False) 기대"

def test_fundamental_filter_with_column_applies_correctly(signal_engine):
    """재무 컬럼이 존재하면 조건을 정상 평가"""
    df = pl.DataFrame({"close": [1000.0, 1100.0, 950.0], "pbr": [0.8, 1.5, 0.5]})
    cond = {"id": "pbr", "params": {"operator": "<=", "value": 1.0}}

    result = signal_engine._eval_vec(cond, df)
    assert list(result) == [True, False, True]

    assert signal_engine.evaluate_condition(cond, 0, df) is True   # 0.8 <= 1.0
    assert signal_engine.evaluate_condition(cond, 1, df) is False  # 1.5 > 1.0
    assert signal_engine.evaluate_condition(cond, 2, df) is True   # 0.5 <= 1.0

def test_generate_signals_fundamental_filter_only_no_column(signal_engine):
    """재무 필터만 있고 해당 컬럼이 없으면 신호가 모두 False (검증 불가 → 제외)"""
    df = pl.DataFrame({"close": [1000.0, 1100.0, 950.0]})
    group = {
        "conditions": [
            {"type": "filter", "id": "pbr", "params": {"operator": "<=", "value": 1.0}},
            {"type": "filter", "id": "per", "params": {"operator": "<=", "value": 10.0}},
        ]
    }
    signals, reasons = signal_engine.generate_signals(df, group)
    assert list(signals) == [False, False, False], \
        f"재무 필터 컬럼 누락 시 모두 False(제외) 기대, 실제={list(signals)}"

def test_generate_signals_fundamental_filter_with_technical_signal(signal_engine):
    """재무 필터(컬럼 없음) + 기술적 신호 조합 — 재무데이터 검증 불가 시 진입 차단(fail-closed)"""
    df = pl.DataFrame({
        "close":      [10.0, 10.0, 12.0, 8.0],
        "close_5_sma":  [10.0, 10.0, 12.0, 8.0],
        "close_20_sma": [11.0, 11.0, 11.0, 11.0],
    })
    group = {
        "conditions": [
            {"type": "indicator", "id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}},
            {"type": "filter",    "id": "pbr",          "params": {"operator": "<=", "value": 1.0}},  # 컬럼 없음
        ]
    }
    signals, _ = signal_engine.generate_signals(df, group)
    # pbr 데이터가 없어 검증 불가 → 기술 신호가 떠도 진입하지 않는다(전부 False)
    assert list(signals) == [False, False, False, False]


def test_evaluate_group_implicit_logic(signal_engine):
    data = {
        "rsi_14": [20, 40],
        "close_5_sma": [10, 12],
        "close_20_sma": [11, 11]
    }
    df = pl.DataFrame(data)
    
    # Test 1: Only indicators -> implicitly OR
    group_indicators = {
        "conditions": [
            {"type": "indicator", "id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}},
            {"type": "indicator", "id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}
        ]
    }
    
    # Index 0: rsi < 30 is True, ma cross is False -> True because OR
    assert signal_engine.evaluate_group(group_indicators, 0, df)[0] == True
    
    # Test 2: Indicator + Filter -> (Indicator 1 OR Indicator 2) AND Filter
    group_mixed = {
        "conditions": [
            {"type": "indicator", "id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}},
            {"type": "filter", "id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}}
        ]
    }
    
    # Index 0: ma cross is False, but rsi < 30 is True -> False because the signal (ma_cross) was not met.
    assert signal_engine.evaluate_group(group_mixed, 0, df)[0] == False
    
    # Change df so index 1 has ma cross is True AND rsi < 30 is True
    data_true = {
        "rsi_14": [20, 20],
        "close_5_sma": [10, 12],
        "close_20_sma": [11, 11]
    }
    df_true = pl.DataFrame(data_true)
    assert signal_engine.evaluate_group(group_mixed, 1, df_true)[0] == True


def test_generate_signals_respects_group_logic_and(signal_engine):
    df = pl.DataFrame({
        "rsi_14": [20, 20],
        "close_5_sma": [10, 12],
        "close_20_sma": [11, 11]
    })

    group = {
        "logic": "AND",
        "conditions": [
            {"type": "indicator", "id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}},
            {"type": "indicator", "id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}
        ]
    }

    signals, reasons = signal_engine.generate_signals(df, group)

    assert list(signals) == [False, True]
    assert reasons[1] == "RSI 30 이하 + 5일선-20일선 골든크로스"


def test_evaluate_group_respects_explicit_and_logic(signal_engine):
    df = pl.DataFrame({
        "rsi_14": [20, 20],
        "close_5_sma": [10, 12],
        "close_20_sma": [11, 11]
    })

    group = {
        "logic": "AND",
        "conditions": [
            {"type": "indicator", "id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}},
            {"type": "indicator", "id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}
        ]
    }

    assert signal_engine.evaluate_group(group, 0, df) == (False, None)
    assert signal_engine.evaluate_group(group, 1, df) == (True, "RSI 30 이하 + 5일선-20일선 골든크로스")


def test_ema_above_below_state_filter(signal_engine):
    # 추세 필터(지속 상태): mode='above'→가격이 EMA 위인 모든 봉 True(크로스오버 아님).
    df = pl.DataFrame({"close": [90.0, 110.0, 105.0, 95.0], "close_200_ema": [100.0, 100.0, 100.0, 100.0]})
    above = {"id": "ema", "params": {"period": 200, "mode": "above", "signalType": "buy"}}
    below = {"id": "ema", "params": {"period": 200, "mode": "below", "signalType": "buy"}}

    # 벡터화 경로
    va, _ = signal_engine.generate_signals(df, {"conditions": [above]})
    vb, _ = signal_engine.generate_signals(df, {"conditions": [below]})
    assert list(va) == [False, True, True, False]   # close >= ema 인 봉
    assert list(vb) == [True, False, False, True]
    # above/below는 상호 배타 파티션(모든 봉 정확히 한쪽)
    assert all(a ^ b for a, b in zip(va, vb))

    # 행별 평가자도 동일(idx 0 포함, 크로스오버와 달리 첫 봉도 판정)
    assert signal_engine.evaluate_condition(above, 1, df) is True
    assert signal_engine.evaluate_condition(above, 0, df) is False
    assert signal_engine.evaluate_condition(below, 0, df) is True


def test_ema_filter_ands_with_entry_signal(signal_engine):
    # filter 타입(ema above)은 진입 신호와 AND 결합돼 게이트로 작동한다.
    df = pl.DataFrame({
        "close": [90.0, 110.0],
        "close_5_sma": [8.0, 12.0], "close_20_sma": [11.0, 11.0],   # idx1에서 골든크로스
        "close_200_ema": [100.0, 100.0],
    })
    group = {"conditions": [
        {"type": "indicator", "id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}},
        {"type": "filter", "id": "ema", "params": {"period": 200, "mode": "above", "signalType": "buy"}},
    ]}
    res, _ = signal_engine.generate_signals(df, group)
    # idx1: 골든크로스(True) AND close(110)>=ema(100)(True) → True
    assert list(res) == [False, True]
