import sys
import os
import pandas as pd
import numpy as np

# Add parent directory to sys.path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.ai.ai_engine import AIEngine

def verify():
    print("Initializing AI Engine...")
    engine = AIEngine()
    
    # Mock data
    np.random.seed(99) # Separate seed for data generation
    data_len = 200
    df = pd.DataFrame({
        'open': np.random.rand(data_len) * 1000,
        'high': np.random.rand(data_len) * 1000,
        'low': np.random.rand(data_len) * 1000,
        'close': np.random.rand(data_len) * 1000,
        'volume': np.random.rand(data_len) * 100000,
        'rsi_14': np.random.rand(data_len) * 100
    })
    
    print("\nRunning Run 1...")
    probs1 = engine.predict_signals(df.copy())
    
    print("Running Run 2...")
    # Re-initialize engine to test fresh state
    engine2 = AIEngine()
    probs2 = engine2.predict_signals(df.copy())
    
    # Compare
    diff = np.abs(probs1 - probs2)
    max_diff = np.max(diff)
    mean_diff = np.mean(diff)
    
    print(f"\nResults:")
    print(f"Max Difference: {max_diff}")
    print(f"Mean Difference: {mean_diff}")
    
    if max_diff < 1e-7:
        print("\n✅ SUCCESS: Results are identical!")
    else:
        print("\n❌ FAILURE: Results differ!")
        # Print first few differences
        mask = diff > 0
        indices = np.where(mask)[0]
        for idx in indices[:5]:
            print(f"Index {idx}: Run1={probs1[idx]}, Run2={probs2[idx]}")

if __name__ == "__main__":
    verify()
