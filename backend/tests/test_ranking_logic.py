import sys
import os
import pandas as pd
import numpy as np
from typing import Dict, Any

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from engine.simulator import Simulator

def test_ranking_priority():
    """
    Test that Simulator prioritizes stocks based on rank_df when max_positions is reached.
    """
    # 1. Setup Data
    dates = pd.date_range("2023-01-01", periods=5)
    symbols = ["StockA", "StockB"]
    
    # Prices (Static)
    price_df = pd.DataFrame(100.0, index=dates, columns=symbols)
    exec_price_df = price_df.copy()
    
    # Both have buy signals on day 1
    entries_df = pd.DataFrame(False, index=dates, columns=symbols)
    entries_df.iloc[1] = True # Buy signal on day 1
    
    exits_df = pd.DataFrame(False, index=dates, columns=symbols)
    
    # 2. Case 1: StockA has higher rank
    # StockA score: 0.9, StockB score: 0.1
    rank_df_1 = pd.DataFrame({
        "StockA": [0.9] * 5,
        "StockB": [0.1] * 5
    }, index=dates)
    
    risk_params = {
        "max_positions": 1,
        "position_size_pct": 100,
        "init_cash": 1000000,
        "allocation_type": "equal"
    }
    options = {}
    simulator = Simulator()
    
    # Simulator should pick StockA because of higher rank
    pf1 = simulator.run(price_df, exec_price_df, entries_df, exits_df, risk_params, options, rank_df=rank_df_1)
    
    print("\n[Test 1] StockA (Score 0.9) vs StockB (Score 0.1), max_pos=1")
    print(f"Trades: {pf1.trades.records}")
    
    # Verify StockA was picked
    trades_assets = [symbols[i] for i in pf1.trades.records['col'].values]
    print(f"Actually picked: {trades_assets}")
    assert "StockA" in trades_assets
    assert "StockB" not in trades_assets
    print("✓ Test 1 Passed: StockA prioritized.")

    # 3. Case 2: StockB has higher rank
    rank_df_2 = pd.DataFrame({
        "StockA": [0.1] * 5,
        "StockB": [0.9] * 5
    }, index=dates)
    
    pf2 = simulator.run(price_df, exec_price_df, entries_df, exits_df, risk_params, options, rank_df=rank_df_2)
    
    print("\n[Test 2] StockA (Score 0.1) vs StockB (Score 0.9), max_pos=1")
    trades_assets_2 = [symbols[i] for i in pf2.trades.records['col'].values]
    print(f"Actually picked: {trades_assets_2}")
    
    # Verify StockB was picked
    assert "StockB" in trades_assets_2
    assert "StockA" not in trades_assets_2
    print("✓ Test 2 Passed: StockB prioritized.")

    # 4. Case 3: Default behavior (No rank_df)
    # Simulator should pick the first alphabetical symbol "StockA" (or by order in DF)
    pf3 = simulator.run(price_df, exec_price_df, entries_df, exits_df, risk_params, options)
    print("\n[Test 3] No rank_df (Default behavior)")
    trades_assets_3 = [symbols[i] for i in pf3.trades.records['col'].values]
    print(f"Actually picked: {trades_assets_3}")
    assert "StockA" in trades_assets_3
    print("✓ Test 3 Passed: Default behavior maintained.")
    print("✓ Test 3 Passed: Default behavior maintained.")

if __name__ == "__main__":
    try:
        test_ranking_priority()
        print("\nAll ranking verification tests passed!")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
