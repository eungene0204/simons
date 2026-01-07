import sys
import os
import json

# Add current directory to path so we can import backtest_engine
sys.path.append(os.getcwd())

from backtest_engine import BacktestEngine

def test_samsung_rsi():
    engine = BacktestEngine(data_dir="../data/ohlcv")
    
    # Strategy: Buy when RSI < 30, Sell when RSI > 70
    req = {
        "symbol": "005930",
        "universe": "kospi",
        "entry": {
            "logic": "AND",
            "conditions": [
                {
                    "id": "rsi",
                    "params": {"period": 14, "value": 30, "operator": "<"}
                }
            ]
        },
        "exit": {
            "logic": "AND",
            "conditions": [
                {
                    "id": "rsi",
                    "params": {"period": 14, "value": 70, "operator": ">"}
                }
            ]
        },
        "risk": {
            "init_cash": 10000000,
            "position_size_pct": 100,
            "liquidity_multiplier": 0 # Disable for simplicity
        },
        "options": {
            "execution_type": "next_open",
            "fee_rate": 0.0015,
            "slippage_rate": 0.001
        }
    }
    
    try:
        print(f"Testing RSI strategy on Samsung (005930)...")
        result = engine.run_backtest(req)
        
        print("\n--- Backtest Results ---")
        print(f"Total Return: {result['totalReturn']:.2f}%")
        print(f"CAGR: {result['cagr']:.2f}%")
        print(f"Max Drawdown: {result['maxDrawdown']:.2f}%")
        print(f"Win Rate: {result['winRate']:.2f}%")
        print(f"Sharpe Ratio: {result['sharpe']:.2f}")
        print(f"Total Signals: {len(result['signals'])}")
        
        if len(result['signals']) > 0:
            print("\nFirst 5 signals:")
            for s in result['signals'][:5]:
                print(f"  {s['date']} | {s['type']} | Price: {s['price']}")
        else:
            print("\nNo signals generated. Consider relaxing conditions.")
            
    except Exception as e:
        print(f"Error during backtest: {e}")
        import traceback
        traceback.print_exc()

def test_skhynix_ma_cross():
    engine = BacktestEngine(data_dir="../data/ohlcv")
    
    # Strategy: Golden Cross (MA 5 > 20)
    req = {
        "symbol": "000660",
        "universe": "kospi",
        "entry": {
            "logic": "AND",
            "conditions": [
                {
                    "id": "ma_crossover",
                    "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}
                }
            ]
        },
        "exit": {
            "logic": "AND",
            "conditions": [
                {
                    "id": "ma_crossover",
                    "params": {"shortMA": 5, "longMA": 20, "signalType": "sell"}
                }
            ]
        },
        "risk": {
            "init_cash": 10000000,
            "position_size_pct": 100,
            "liquidity_multiplier": 0
        },
        "options": {
            "execution_type": "same_close",
            "fee_rate": 0.0015,
            "slippage_rate": 0.001
        }
    }
    
    try:
        print(f"\nTesting MA Cross strategy on SK Hynix (000660)...")
        result = engine.run_backtest(req)
        
        print("\n--- Backtest Results ---")
        print(f"Total Return: {result['totalReturn']:.2f}%")
        print(f"CAGR: {result['cagr']:.2f}%")
        print(f"Max Drawdown: {result['maxDrawdown']:.2f}%")
        print(f"Win Rate: {result['winRate']:.2f}%")
        print(f"Total Signals: {len(result['signals'])}")
        
    except Exception as e:
        print(f"Error during backtest: {e}")

if __name__ == "__main__":
    test_samsung_rsi()
    test_skhynix_ma_cross()
