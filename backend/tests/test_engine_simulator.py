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
