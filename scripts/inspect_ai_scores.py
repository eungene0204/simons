import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

# Set PYTHONPATH
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backtest_engine import BacktestEngine

def inspect_scores():
    engine = BacktestEngine()
    
    # 1. Prepare a simple request for Samsung Electronics (005930)
    req = {
        'symbols': ['005930'],
        'period': '1Y',
        'entry': {
            'logic': 'AND',
            'conditions': [
                {'id': 'ai_model', 'params': {'threshold': 0.5, 'direction': 'above'}}
            ]
        },
        'exit': {
            'logic': 'OR',
            'conditions': [
                {'id': 'price_level', 'params': {'value': 0, 'operator': '>'}} # Dummy exit
            ]
        },
        'risk_params': {
            'init_cash': 10000000,
            'position_size_pct': 100
        }
    }
    
    print("Running backtest to inspect AI scores...", flush=True)
    try:
        # We need to temporarily modify BacktestEngine or intercept the data
        # Let's just run it and look at what it processes.
        # However, run_backtest returns a formatted result.
        # I'll add a temporary print in BacktestEngine to see the scores or use a separate test check.
        
        from ai.ai_engine import AIEngine
        import polars as pl
        from engine.loader import DataLoader
        
        loader = DataLoader("data/ohlcv")
        df_pl = loader.load_symbol_data('005930')
        
        # Filter 1Y
        ref_date = pd.to_datetime('today').normalize()
        df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(years=1)))
        
        pdf = df_pl.to_pandas()
        ai_engine = AIEngine()
        probs = ai_engine.predict_signals(pdf)
        
        print("\n--- AI Probability Scores (005930, Last 1 Year) ---")
        print(f"Total bars: {len(probs)}")
        print(f"Min Probability: {np.min(probs):.4f}")
        print(f"Max Probability: {np.max(probs):.4f}")
        print(f"Mean Probability: {np.mean(probs):.4f}")
        print(f"Std Deviation: {np.std(probs):.4f}")
        
        # Count high confidence signals
        print(f"\nSignals > 0.5: {(probs > 0.5).sum()} ({((probs > 0.5).sum()/len(probs)*100):.2f}%)")
        print(f"Signals > 0.7: {(probs > 0.7).sum()} ({((probs > 0.7).sum()/len(probs)*100):.2f}%)")
        print(f"Signals > 0.8: {(probs > 0.8).sum()} ({((probs > 0.8).sum()/len(probs)*100):.2f}%)")
        
        print("\nRecent 10 days probabilities:")
        for i in range(-10, 0):
            date_str = pdf.iloc[i]['date']
            print(f"Date: {date_str} | Prob: {probs[i]:.4f}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    inspect_scores()
