import pytest
import pandas as pd
import numpy as np
from engine.simulator import Simulator

@pytest.fixture
def simulator():
    return Simulator()

def create_dummy_data(days=5, symbols=2):
    dates = pd.date_range("2024-01-01", periods=days)
    syms = [f"SYM{i}" for i in range(symbols)]
    
    price_df = pd.DataFrame(np.ones((days, symbols)) * 100, index=dates, columns=syms)
    exec_price_df = pd.DataFrame(np.ones((days, symbols)) * 100, index=dates, columns=syms)
    entries_df = pd.DataFrame(np.zeros((days, symbols), dtype=bool), index=dates, columns=syms)
    exits_df = pd.DataFrame(np.zeros((days, symbols), dtype=bool), index=dates, columns=syms)
    
    return price_df, exec_price_df, entries_df, exits_df

def test_simulator_max_positions(simulator):
    price, exec_price, entries, exits = create_dummy_data(days=5, symbols=3)
    
    # Day 0: all 3 symbols trigger entry
    entries.iloc[0] = [True, True, True]
    
    risk_params = {
        "max_positions": 2, # Only allow 2 positions
        "skip_risk_management": False,
        "allocation_type": "equal"
    }
    options = {}
    
    pf = simulator.run(price, exec_price, entries, exits, risk_params, options)
    
    trades = pf.trades.records_readable
    # We should only have 2 active trades
    assert len(trades) == 2
    
def test_simulator_max_holding_days(simulator):
    price, exec_price, entries, exits = create_dummy_data(days=5, symbols=1)
    
    entries.iloc[0, 0] = True # Entry on Day 0
    # No exits defined in dataframe!
    
    risk_params = {
        "max_holding_days": 2, # Exit after 2 days
        "skip_risk_management": False
    }
    options = {}
    
    pf = simulator.run(price, exec_price, entries, exits, risk_params, options)
    trades = pf.trades.records_readable
    
    assert len(trades) == 1
    
    # Entry on Day 0, holding days = 2 means exit on Day 2
    # The portfolio uses row indices. Exit idx should be 2.
    assert trades.iloc[0]['Exit Timestamp'] == pf.close.index[2]

def test_simulator_stop_loss(simulator):
    price, exec_price, entries, exits = create_dummy_data(days=5, symbols=1)
    
    # Set up price drops
    price.iloc[:, 0] = [100.0, 95.0, 89.0, 85.0, 80.0]
    # Exec price can be same for simplicity
    exec_price.iloc[:, 0] = [100.0, 95.0, 89.0, 85.0, 80.0]
    
    entries.iloc[0, 0] = True # Entry at 100
    
    risk_params = {
        "stop_loss_pct": 10.0, # 10% SL -> Exit when price <= 90
        "skip_risk_management": False
    }
    options = {}
    
    pf = simulator.run(price, exec_price, entries, exits, risk_params, options)
    trades = pf.trades.records_readable
    
    assert len(trades) == 1
    # Entry at 100, drops to 89 on Day 2 (-11%). Should exit on Day 2.
    # Note: Simulator injects True into exits_df at Day 2.
    # VectorBT will then use Day 2's execution price, or depending on execution_type.
    # With freq='D' and default longonly, the exit is triggered at Day 2.
    assert trades.iloc[0]['Exit Timestamp'] == pf.close.index[2]

def test_simulator_take_profit(simulator):
    price, exec_price, entries, exits = create_dummy_data(days=5, symbols=1)
    
    # Set up price rises
    price.iloc[:, 0] = [100.0, 105.0, 110.0, 115.0, 120.0]
    exec_price.iloc[:, 0] = [100.0, 105.0, 110.0, 115.0, 120.0]
    
    entries.iloc[0, 0] = True # Entry at 100
    
    risk_params = {
        "take_profit_pct": 9.0, # 9% TP -> Exit when price >= 109
        "skip_risk_management": False
    }
    options = {}
    
    pf = simulator.run(price, exec_price, entries, exits, risk_params, options)
    trades = pf.trades.records_readable
    
    assert len(trades) == 1
    # Entry at 100, rises to 110 on Day 2 (+10%). Should exit on Day 2.
    assert trades.iloc[0]['Exit Timestamp'] == pf.close.index[2]

# ──────────────────────────────────────────────────────────────────────────────
# Fix 1: 트레일링 스탑 구현 회귀 방지 테스트
# ──────────────────────────────────────────────────────────────────────────────

def test_simulator_trailing_stop_basic(simulator):
    """트레일링 스탑: 고점 대비 ts_pct 이상 하락 시 청산 (Fix 1)"""
    price, exec_price, entries, exits = create_dummy_data(days=7, symbols=1)

    # 가격: 진입 후 상승, 그다음 급락
    # Day 0: 100 (진입)
    # Day 1: 110, Day 2: 120 (고점) → peak = 120
    # Day 3: 108 → 120의 10% 하락선 = 108 → 정확히 -10% 트리거
    price.iloc[:, 0]      = [100.0, 110.0, 120.0, 108.0, 100.0, 90.0, 80.0]
    exec_price.iloc[:, 0] = [100.0, 110.0, 120.0, 108.0, 100.0, 90.0, 80.0]
    entries.iloc[0, 0] = True

    risk_params = {"trailing_stop_pct": 10.0, "skip_risk_management": False}
    pf = simulator.run(price, exec_price, entries, exits, risk_params, {})
    trades = pf.trades.records_readable

    assert len(trades) == 1
    # Day 3에서 고점(120) 대비 -10% 트리거 → Day 3에 청산
    assert trades.iloc[0]['Exit Timestamp'] == pf.close.index[3]

def test_simulator_trailing_stop_no_exit_when_not_triggered(simulator):
    """트레일링 스탑: 낙폭이 임계값 미만이면 청산 안 됨 (Fix 1)"""
    price, exec_price, entries, exits = create_dummy_data(days=5, symbols=1)

    # 고점 100, 최대 낙폭 5% → 트레일링 스탑 10% 미달
    price.iloc[:, 0]      = [100.0, 100.0, 100.0, 95.0, 95.0]
    exec_price.iloc[:, 0] = [100.0, 100.0, 100.0, 95.0, 95.0]
    entries.iloc[0, 0] = True

    risk_params = {"trailing_stop_pct": 10.0, "skip_risk_management": False}
    pf = simulator.run(price, exec_price, entries, exits, risk_params, {})
    trades = pf.trades.records_readable

    assert len(trades) == 1
    # 청산 조건 미달 → 마지막 날(Day 4)에 백테스트 종료로 청산
    assert trades.iloc[0]['Exit Timestamp'] == pf.close.index[4]

def test_simulator_trailing_stop_updates_peak_on_new_highs(simulator):
    """트레일링 스탑: 가격이 신고점 경신 시 기준선도 올라간다 (Fix 1)"""
    price, exec_price, entries, exits = create_dummy_data(days=8, symbols=1)

    # Day 0: 100 진입, Day 1: 105, Day 2: 110, Day 3: 115 (신고점, peak=115)
    # Day 4: 104 → 115의 10% = 103.5, 104 > 103.5 → 미트리거
    # Day 5: 103 → 115의 10% = 103.5, 103 < 103.5 → 트리거
    price.iloc[:, 0]      = [100.0, 105.0, 110.0, 115.0, 104.0, 103.0, 90.0, 80.0]
    exec_price.iloc[:, 0] = [100.0, 105.0, 110.0, 115.0, 104.0, 103.0, 90.0, 80.0]
    entries.iloc[0, 0] = True

    risk_params = {"trailing_stop_pct": 10.0, "skip_risk_management": False}
    pf = simulator.run(price, exec_price, entries, exits, risk_params, {})
    trades = pf.trades.records_readable

    assert len(trades) == 1
    # Day 5에서 peak(115) 대비 -10% (=103.5) 이하 → Day 5 청산
    assert trades.iloc[0]['Exit Timestamp'] == pf.close.index[5]

def test_simulator_trailing_stop_does_not_conflict_with_sl(simulator):
    """SL과 트레일링 스탑이 동시에 있을 때 먼저 트리거된 것이 실행된다 (Fix 1)"""
    price, exec_price, entries, exits = create_dummy_data(days=6, symbols=1)

    # SL=15%, TS=10%. Day 2에 TS가 먼저 트리거 (고점 120의 10% = 108, Day 3 price=108)
    # SL은 100의 15% = 85 → Day 3에는 아직 미달
    price.iloc[:, 0]      = [100.0, 110.0, 120.0, 108.0, 85.0, 80.0]
    exec_price.iloc[:, 0] = [100.0, 110.0, 120.0, 108.0, 85.0, 80.0]
    entries.iloc[0, 0] = True

    risk_params = {
        "stop_loss_pct": 15.0,
        "trailing_stop_pct": 10.0,
        "skip_risk_management": False
    }
    pf = simulator.run(price, exec_price, entries, exits, risk_params, {})
    trades = pf.trades.records_readable

    assert len(trades) == 1
    # TS가 Day 3에 먼저 트리거 → Day 3에 청산
    assert trades.iloc[0]['Exit Timestamp'] == pf.close.index[3]


def test_simulator_ranking(simulator):
    price, exec_price, entries, exits = create_dummy_data(days=5, symbols=3)
    
    # Day 0: all 3 symbols trigger entry
    entries.iloc[0] = [True, True, True]
    
    # Setup simple linear data
    # Ranking highest to lowest -> SYM2, SYM1, SYM0
    rank_df = pd.DataFrame([[0.1, 0.5, 0.9], [0,0,0], [0,0,0], [0,0,0], [0,0,0]], 
                           index=price.index, columns=price.columns)
                           
    risk_params = {
        "max_positions": 1, # Only allow 1 position
        "skip_risk_management": False
    }
    options = {}
    
    pf = simulator.run(price, exec_price, entries, exits, risk_params, options, rank_df=rank_df)
    
    trades = pf.trades.records_readable
    assert len(trades) == 1
    assert trades.iloc[0]['Column'] == 'SYM2' # Highest rank won
