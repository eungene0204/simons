import time
import pandas as pd
import numpy as np
import os
import sys
import torch

# Add backend to path
sys.path.append(os.getcwd())

from ai.ai_engine import AIEngine

def benchmark_ai():
    print("=== AI Model Backtest Performance Benchmark ===")
    
    # 1. Initialization Time
    start_init = time.time()
    engine = AIEngine()
    end_init = time.time()
    print(f"[*] AIEngine Initialization: {end_init - start_init:.4f}s")
    print(f"[*] Device: {engine.device}")
    
    # 2. Sample Data Loading
    sample_file = "/Users/eugene/nullalgo/simons/data/ohlcv/000020.parquet"
    if not os.path.exists(sample_file):
        print(f"[!] Sample file not found: {sample_file}")
        return
        
    df = pd.read_parquet(sample_file).sort_values('date')
    df.columns = [c.lower() for c in df.columns]
    num_rows = len(df)
    print(f"[*] Dataset: {sample_file} ({num_rows} rows)")
    
    # 3. Inference Benchmark
    print("\nRunning Inference Benchmark...")
    
    # Warm up (optional for MPS/CUDA)
    _ = engine.predict_signals(df.iloc[:200])
    
    iterations = 5
    inference_times = []
    
    for i in range(iterations):
        start_inf = time.time()
        probs, probs_drop = engine.predict_signals(df)
        end_inf = time.time()
        inference_times.append(end_inf - start_inf)
        print(f"  - Iteration {i+1}: {end_inf - start_inf:.4f}s")
    
    avg_inf = sum(inference_times) / iterations
    print(f"\n[*] Average Inference Time per Symbol: {avg_inf:.4f}s")
    print(f"[*] Estimated Throughput: {1.0/avg_inf:.2f} symbols/sec")
    
    # 4. Breakdown Estimate (from logs or logic)
    # The logs showed most time is spent in Feature Engineering and Transformer Batch Inference.
    
    print("\n=== Scale Calculation ===")
    full_universe_count = 2000 # Standard KRX universe size
    total_time_universe = avg_inf * full_universe_count
    print(f"[*] Estimated time for full universe (2000 stocks): {total_time_universe / 60:.2f} minutes")
    
    print("\nNOTE: This includes Feature Engineering (17 indicators) + Transformer Batch Inference + XGBoost.")

if __name__ == "__main__":
    benchmark_ai()
