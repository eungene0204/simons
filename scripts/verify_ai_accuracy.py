import os
import sys
import pandas as pd
import numpy as np
import polars as pl
from datetime import datetime

# Set PYTHONPATH
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from ai.ai_engine import AIEngine
from engine.loader import DataLoader

def verify_accuracy(symbol='005930'):
    print(f"Verifying AI accuracy for {symbol}...", flush=True)
    
    loader = DataLoader("data/ohlcv")
    df_pl = loader.load_symbol_data(symbol)
    
    if df_pl is None or len(df_pl) == 0:
        print(f"Error: Could not load data for {symbol}")
        return

    # Use a longer period for better statistics (e.g., 2 years)
    ref_date = pd.to_datetime('today').normalize()
    df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(years=2)))
    
    pdf = df_pl.to_pandas()
    ai_engine = AIEngine()
    probs = ai_engine.predict_signals(pdf)
    
    # Calculate actual 10-day forward return
    # (Price at t+10 / Price at t) - 1
    pdf['actual_fwd_return_10d'] = pdf['close'].shift(-10) / pdf['close'] - 1
    pdf['hit_7pct'] = (pdf['close'].rolling(window=10).max().shift(-10) / pdf['close'] - 1 >= 0.07).astype(int)
    pdf['ai_prob'] = probs
    
    # Drop rows where we don't have future data (the last 10 rows)
    valid_pdf = pdf.dropna(subset=['actual_fwd_return_10d'])
    
    # Define buckets
    buckets = [0, 0.3, 0.5, 0.7, 0.8, 0.9, 1.0]
    bucket_labels = ["0-30%", "30-50%", "50-70%", "70-80%", "80-90%", "90-100%"]
    
    valid_pdf['bucket'] = pd.cut(valid_pdf['ai_prob'], bins=buckets, labels=bucket_labels)
    
    # Analysis
    stats = valid_pdf.groupby('bucket').agg({
        'ai_prob': 'count',
        'actual_fwd_return_10d': 'mean',
        'hit_7pct': 'mean'
    }).rename(columns={
        'ai_prob': 'Count',
        'actual_fwd_return_10d': 'Avg 10D Return',
        'hit_7pct': 'Hit Rate (>=7%)'
    })
    
    print("\n--- AI Score vs. Actual Performance (Last 2 Years) ---")
    print(stats)
    
    # Overall Correlation
    correlation = valid_pdf['ai_prob'].corr(valid_pdf['actual_fwd_return_10d'])
    print(f"\nOverall Correlation (Score vs. 10D Return): {correlation:.4f}")

if __name__ == "__main__":
    verify_accuracy('005930') # Samsung
    print("\n" + "="*50 + "\n")
    verify_accuracy('000660') # SK Hynix
