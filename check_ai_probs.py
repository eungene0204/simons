import pandas as pd
import numpy as np
from backend.ai.ai_engine import AIEngine

def main():
    print("Loading data...")
    try:
        df = pd.read_parquet("model/training_data_processed.parquet")
    except:
        df = pd.read_parquet("backend/data/training_data_processed.parquet")
        
    # Use a subset of 2023 for validation checking
    df['date'] = pd.to_datetime(df['date'])
    df = df[df['date'].dt.year == 2023]
    df = df.sort_values(by=['symbol', 'date'])

    print(f"Data shape: {df.shape}")
    
    # Let's get top 10 symbols to evaluate
    top_symbols = df['symbol'].value_counts().head(10).index
    
    engine = AIEngine()
    all_probs = []
    
    for sym in top_symbols:
        sym_df = df[df['symbol'] == sym].copy()
        if len(sym_df) > 60:
            probs = engine.predict_signals(sym_df)
            # Exclude the 0s which are purely lookback buffers
            valid_probs = probs[probs > 0.0]
            if len(valid_probs) > 0:
                all_probs.extend(valid_probs)
                
    all_probs = np.array(all_probs)
    
    if len(all_probs) == 0:
        print("No valid probabilities generated.")
        return
        
    print("\n--- Summary Statistics of Predicted Probabilities ---")
    print(f"Number of valid predictions: {len(all_probs)}")
    print("Percentiles:")
    for p in [50, 75, 90, 95, 99]:
        val = np.percentile(all_probs, p)
        print(f"  {p}th: {val:.4f}")
    print(f"Max: {all_probs.max():.4f}")
    print(f"Fraction > 0.5: {np.mean(all_probs > 0.5):.4%}")
    print(f"Fraction > 0.7: {np.mean(all_probs > 0.7):.4%}")

if __name__ == "__main__":
    main()
