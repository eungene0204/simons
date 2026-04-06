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
# 재무 필터 데이터 누락 시 필터 통과 처리 테스트
# ──────────────────────────────────────────────────────────────────────────────

def test_fundamental_filter_missing_column_passes_vec(signal_engine):
    """재무 컬럼(per/pbr 등)이 없으면 필터 통과(np.ones) 반환 — 벡터화 (_eval_vec)"""
    df = pl.DataFrame({"close": [1000.0, 1100.0, 950.0]})

    for cid in ["per", "pbr", "roe_or_gpa", "debt_ratio", "market_cap"]:
        cond = {"id": cid, "params": {"operator": "<=", "value": 10.0}}
        result = signal_engine._eval_vec(cond, df)
        assert list(result) == [True, True, True], \
            f"{cid}: 컬럼 없을 때 np.ones 기대, 실제={list(result)}"

def test_fundamental_filter_missing_column_passes_row(signal_engine):
    """재무 컬럼이 없으면 필터 통과(True) 반환 — 행별 (evaluate_condition)"""
    df = pl.DataFrame({"close": [1000.0, 1100.0]})

    for cid in ["per", "pbr", "roe_or_gpa", "debt_ratio", "market_cap"]:
        cond = {"id": cid, "params": {"operator": "<=", "value": 10.0}}
        assert signal_engine.evaluate_condition(cond, 0, df) is True, \
            f"{cid}: 컬럼 없을 때 True 기대"

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
    """재무 필터만 있고 해당 컬럼이 없으면 신호가 모두 True (데이터 없어도 거래 가능)"""
    df = pl.DataFrame({"close": [1000.0, 1100.0, 950.0]})
    group = {
        "conditions": [
            {"type": "filter", "id": "pbr", "params": {"operator": "<=", "value": 1.0}},
            {"type": "filter", "id": "per", "params": {"operator": "<=", "value": 10.0}},
        ]
    }
    signals, reasons = signal_engine.generate_signals(df, group)
    assert list(signals) == [True, True, True], \
        f"재무 필터 컬럼 누락 시 모두 True 기대, 실제={list(signals)}"

def test_generate_signals_fundamental_filter_with_technical_signal(signal_engine):
    """재무 필터(컬럼 없음) + 기술적 신호 조합 — 기술적 신호만으로 진입 결정"""
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
    # pbr 필터는 통과, MA 크로스오버만 결정 (idx=2에서 골든크로스)
    assert list(signals) == [False, False, True, False]


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
