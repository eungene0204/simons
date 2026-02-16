import torch
import torch.nn as nn
import xgboost as xgb
import pandas as pd
import numpy as np
import joblib
import os
from backend.ai.models import HybridAIModel

class AIEngine:
    def __init__(self, model_dir="/Users/eugene/nullalgo/simons/model"):
        self.model_dir = model_dir
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 1. Load Scaler
        scaler_path = os.path.join(model_dir, 'feature_scaler.joblib')
        if os.path.exists(scaler_path):
            self.scaler = joblib.load(scaler_path)
        else:
            raise FileNotFoundError(f"Scaler not found at {scaler_path}")
            
        # 2. Load Transformer
        ts_features_count = 6 # (ret_open, ret_high, ret_low, ret_close, ret_volume, rsi_14)
        self.transformer = HybridAIModel(input_dim=ts_features_count).to(self.device)
        model_path = os.path.join(model_dir, 'transformer_engine.pt')
        if os.path.exists(model_path):
            self.transformer.load_state_dict(torch.load(model_path, map_location=self.device))
            self.transformer.eval()
        else:
            raise FileNotFoundError(f"Transformer model not found at {model_path}")
            
        # 3. Load XGBoost
        xgb_path = os.path.join(model_dir, 'xgboost_head.json')
        self.xgb_head = xgb.XGBClassifier()
        if os.path.exists(xgb_path):
            self.xgb_head.load_model(xgb_path)
        else:
            raise FileNotFoundError(f"XGBoost model not found at {xgb_path}")
            
        self.ts_features = ['ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', 'rsi_14']
        self.lookback = 60
        print(f"AIEngine initialized on {self.device}")

    def predict_signals(self, df: pd.DataFrame) -> np.ndarray:
        log_file = "backend_execution.log"
        def log(msg):
            from datetime import datetime
            with open(log_file, "a") as f:
                f.write(f"[{datetime.now()}] [AIEngine] {msg}\n")
        
        log(f"predict_signals started. input df shape={df.shape}")
        try:
            data_len = len(df)
            probs = np.zeros(data_len)
            
            # 0. Robust Column Name Check
            pdf = df.copy()
            pdf.columns = [c.lower() for c in pdf.columns]
            
            # Find the actual RSI column (it might be rsi_14 or rsi)
            actual_rsi = None
            for c in pdf.columns:
                if c.startswith('rsi'):
                    actual_rsi = c
                    break
            
            if not actual_rsi:
                log("RSI column missing. Calculating on the fly.")
                from stockstats import StockDataFrame
                sdf = StockDataFrame.retype(pdf.copy())
                pdf['rsi_14'] = sdf['rsi_14']
                actual_rsi = 'rsi_14'
            
            # 1. Feature Engineering
            log("1. Feature Engineering (Returns)")
            for col in ['open', 'high', 'low', 'close']:
                pdf[f'ret_{col}'] = pdf[col].pct_change()
            pdf['ret_volume'] = pdf['volume'].pct_change()
            
            # Map required features
            features_to_use = ['ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', actual_rsi]
            
            # Handle Inf/NaN before scaling
            log("Handling Inf/NaN")
            pdf[features_to_use] = pdf[features_to_use].replace([np.inf, -np.inf], np.nan)
            pdf[features_to_use] = pdf[features_to_use].ffill().bfill().fillna(0)
            
            # 2. Scaling
            log(f"2. Scaling with columns {features_to_use}")
            # Ensure we pass the data in the same order the scaler expects
            # Scaler was trained on ['ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', 'rsi_14']
            scale_input = pdf[features_to_use].values 
            scaled_data = self.scaler.transform(scale_input)
            
            # 3. Sliding Window Inference
            log("3. Sliding Window Inference")
            ts_data = scaled_data.astype(np.float32)
            
            windows = []
            valid_indices = []
            
            for i in range(self.lookback, data_len):
                window = ts_data[i-self.lookback:i]
                windows.append(window)
                valid_indices.append(i)
            
            if not windows:
                log("No windows found (not enough data)")
                return probs
                
            # 4. Batch Transformer Inference
            log(f"4. Batch Transformer Inference for {len(windows)} windows")
            windows_arr = np.array(windows)
            windows_tensor = torch.from_numpy(windows_arr).to(self.device)
            
            with torch.no_grad():
                log("Running transformer model")
                embeddings = self.transformer(windows_tensor).cpu().numpy()
                log(f"Transformer inference done. embeddings shape={embeddings.shape}")
                
            # 5. XGBoost Inference
            log("5. XGBoost Inference")
            try:
                signal_probs = self.xgb_head.predict_proba(embeddings)[:, 1]
            except Exception as xe:
                log(f"XGBoost Head error: {xe}. Attempting simple predict.")
                signal_probs = self.xgb_head.predict(embeddings).astype(float)
            log("XGBoost inference done.")
            
            for idx, prob in zip(valid_indices, signal_probs):
                probs[idx] = prob
                
            log("predict_signals finished")
            return probs
        except Exception as e:
            log(f"CRITICAL ERROR in predict_signals: {e}")
            import traceback
            with open(log_file, "a") as f:
                traceback.print_exc(file=f)
            raise e

if __name__ == "__main__":
    # Test AIEngine
    engine = AIEngine()
    # Mock data
    dates = pd.date_range('2024-01-01', periods=100)
    df = pd.DataFrame({
        'open': np.random.rand(100) * 1000,
        'high': np.random.rand(100) * 1000,
        'low': np.random.rand(100) * 1000,
        'close': np.random.rand(100) * 1000,
        'volume': np.random.rand(100) * 100000,
        'rsi_14': np.random.rand(100) * 100
    }, index=dates)
    
    probs = engine.predict_signals(df)
    print(f"Predictions generated for {len(probs)} steps. Sample: {probs[-5:]}")
