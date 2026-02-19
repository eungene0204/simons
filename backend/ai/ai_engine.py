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
        
        # Robust Device Selection: CUDA -> MPS -> CPU
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")
        
        print(f"AIEngine initialized on: {self.device}")
        
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
                f.write(f"[{datetime.now()}] [AIEngine-Opt] {msg}\n")
        
        log(f"predict_signals started. input df shape={df.shape}")
        try:
            data_len = len(df)
            probs = np.zeros(data_len)
            
            if data_len <= self.lookback:
                log("Data length too short for lookback")
                return probs

            # 0. Robust Column Name Check
            pdf = df.copy()
            pdf.columns = [c.lower() for c in pdf.columns]
            
            # Find the actual RSI column
            actual_rsi = next((c for c in pdf.columns if c.startswith('rsi')), None)
            
            if not actual_rsi:
                log("RSI column missing. Calculating on the fly.")
                from stockstats import StockDataFrame
                sdf = StockDataFrame.retype(pdf.copy())
                pdf['rsi_14'] = sdf['rsi_14']
                actual_rsi = 'rsi_14'
            
            # 1. Feature Engineering
            for col in ['open', 'high', 'low', 'close']:
                pdf[f'ret_{col}'] = pdf[col].pct_change()
            pdf['ret_volume'] = pdf['volume'].pct_change()
            
            features_to_use = ['ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', actual_rsi]
            
            # 2. Preprocessing & Scaling
            pdf[features_to_use] = pdf[features_to_use].replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0)
            scaled_data = self.scaler.transform(pdf[features_to_use].values).astype(np.float32)
            
            # 3. Optimized Vectorized Window Creation
            # Using stride_tricks for zero-copy windowing
            from numpy.lib.stride_tricks import as_strided
            
            # Calculate strides for a window of size (data_len - lookback, lookback, num_features)
            n_windows = data_len - self.lookback
            itemsize = scaled_data.itemsize
            num_features = len(features_to_use)
            
            # Shape: (num_windows, lookback, num_features)
            # Strides: (row_stride, row_stride, feature_stride)
            # scaled_data strides are (num_features * itemsize, itemsize)
            orig_strides = scaled_data.strides
            new_shape = (n_windows, self.lookback, num_features)
            new_strides = (orig_strides[0], orig_strides[0], orig_strides[1])
            
            windows_arr = as_strided(scaled_data, shape=new_shape, strides=new_strides)
            
            # 4. Batch Transformer Inference
            # Process in one large batch if memory allows, or chunks of 1024
            batch_size = 1024
            all_embeddings = []
            
            with torch.inference_mode():
                for i in range(0, n_windows, batch_size):
                    batch = windows_arr[i:i+batch_size]
                    batch_tensor = torch.from_numpy(batch).to(self.device)
                    emb = self.transformer(batch_tensor).cpu().numpy()
                    all_embeddings.append(emb)
            
            embeddings = np.concatenate(all_embeddings, axis=0)
            
            # 5. XGBoost Inference
            try:
                signal_probs = self.xgb_head.predict_proba(embeddings)[:, 1]
            except:
                signal_probs = self.xgb_head.predict(embeddings).astype(float)
            
            # Fill the probabilities (skipping the first 'lookback' indices)
            probs[self.lookback:] = signal_probs
            
            log(f"predict_signals optimized finished for {data_len} rows")
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
