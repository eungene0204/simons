import torch
import torch.nn as nn
import xgboost as xgb
import pandas as pd
import numpy as np
import polars as pl
import joblib
import os
from ai.models import HybridAIModel

# 0. Set Seeds for Determinism
seed = 42
torch.manual_seed(seed)
np.random.seed(seed)
import random
random.seed(seed)

import threading

class AIEngine:
    def __init__(self, model_dir="/Users/eugene/nullalgo/simons/model/expanded_features"):
        self.model_lock = threading.Lock()
        self.model_dir = model_dir
        # ... Re-apply seeds inside init as well for absolute safety ...
        torch.manual_seed(seed)
        np.random.seed(seed)
        random.seed(seed)
        
        if torch.cuda.is_available():
            torch.cuda.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
            self.device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            # Note: MPS determinism is partially supported in newer torch versions
            # os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")
        
        print(f"AIEngine initialized on: {self.device} (Seed: {seed})")
        
        # 1. Load Scaler
        scaler_path = os.path.join(model_dir, 'feature_scaler.joblib')
        if os.path.exists(scaler_path):
            self.scaler = joblib.load(scaler_path)
        else:
            raise FileNotFoundError(f"Scaler not found at {scaler_path}")
            
        # 2.5 Load Metadata
        import json
        meta_path = os.path.join(model_dir, 'model_meta.json')
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                self.meta = json.load(f)
        else:
            self.meta = {"buy_threshold": 0.07, "sell_threshold": 0.07, "lookback": 60}
            
        # 2. Load Transformer
        ts_features_count = len(self.meta.get('features', [])) or 17
        
        # Load hyperparams from meta, with safe defaults
        d_model = self.meta.get('d_model', 64)
        nhead = self.meta.get('nhead', 4)
        num_layers = self.meta.get('num_layers', 2)
        dim_feedforward = self.meta.get('dim_feedforward', 128)
        dropout = self.meta.get('dropout', 0.1)
        
        self.transformer = HybridAIModel(
            input_dim=ts_features_count,
            d_model=d_model,
            nhead=nhead,
            num_layers=num_layers,
            dim_feedforward=dim_feedforward,
            dropout=dropout
        ).to(self.device)
        
        model_path = os.path.join(model_dir, 'transformer_engine.pt')
        if os.path.exists(model_path):
            self.transformer.load_state_dict(torch.load(model_path, map_location=self.device))
            self.transformer.eval()
        else:
            raise FileNotFoundError(f"Transformer model not found at {model_path}")
            
        # 3. Load XGBoost Head (Multi-Output Expected)
        xgb_path = os.path.join(model_dir, 'xgboost_head.json')
        self.xgb_head = xgb.XGBClassifier()
        if os.path.exists(xgb_path):
            self.xgb_head.load_model(xgb_path)
        else:
            raise FileNotFoundError(f"XGBoost model not found at {xgb_path}")
            
        self.ts_features = self.meta.get('features', [
            'ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', 'ret_obv', 
            'rsi_14', 'macd', 'macds', 'macdh', 'kdjk', 'kdjd', 'cci_14', 'adx', 
            'dist_sma_20', 'dist_ema_20', 'boll_pos'
        ])
        self.lookback = self.meta.get('lookback', 60)
        print(f"AIEngine initialized on {self.device}")

    def predict_signals(self, df: pd.DataFrame) -> np.ndarray:
        log_file = "backend_execution.log"
        def log(msg):
            from datetime import datetime
            with open(log_file, "a") as f:
                f.write(f"[{datetime.now()}] [AIEngine-Thread-{threading.get_ident()}] {msg}\n")
        
        log(f"predict_signals started. input df shape={df.shape}")
        
        # Use lock to prevent concurrent GPU access on MPS/CUDA
        with self.model_lock:
            log("Acquired model lock")
            result = self._predict_signals_internal(df, log)
            log("Released model lock")
            return result

    def _predict_signals_internal(self, df: pd.DataFrame, log_func) -> np.ndarray:
        try:
            log = log_func
            data_len = len(df)
            probs = np.zeros(data_len)
            probs_drop = np.zeros(data_len)
            
            if data_len <= self.lookback:
                log("Data length too short for lookback")
                return probs, probs_drop

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
            
            # 1. Feature Engineering (Log Returns & Technical Indicators)
            from engine.indicators import IndicatorEngine
            indicator_reqs = [
                {'id': 'ema', 'params': {'period': 20}},
                {'id': 'macd', 'params': {}},
                {'id': 'stochastic', 'params': {}},
                {'id': 'cci', 'params': {'period': 14}},
                {'id': 'adx', 'params': {}},
                {'id': 'bollinger_bands', 'params': {'period': 20}},
                {'id': 'volume_spike', 'params': {'period': 20}}
            ]
            pdf_pl = IndicatorEngine.calculate(pl.from_pandas(pdf), indicator_reqs)
            pdf = pdf_pl.to_pandas()

            # Price/Volume Log Returns
            for col in ['open', 'high', 'low', 'close']:
                pdf[f'ret_{col}'] = np.log1p(pdf[col].pct_change())
            pdf['ret_volume'] = np.log1p(pdf['volume'].pct_change())
            pdf['ret_obv'] = np.log1p(pdf['obv'].pct_change())

            # Stationary Technical Features
            pdf['dist_sma_20'] = pdf['close'] / pdf['close_20_sma'] - 1
            pdf['dist_ema_20'] = pdf['close'] / pdf['close_20_ema'] - 1
            pdf['boll_pos'] = (pdf['close'] - pdf['boll_lb']) / (pdf['boll_ub'] - pdf['boll_lb'] + 1e-8)
            
            features_to_use = self.ts_features
            
            # 2. Preprocessing & Scaling
            pdf[features_to_use] = pdf[features_to_use].replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
            scaled_data = self.scaler.transform(pdf[features_to_use].values).astype(np.float32)
            
            # 3. Optimized Vectorized Window Creation
            # Using stride_tricks for zero-copy windowing
            from numpy.lib.stride_tricks import as_strided
            
            # Calculate strides for a window of size (lookback, num_features)
            n_windows = data_len - self.lookback + 1
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
            
            # 5. XGBoost Inference (Multi-Target)
            try:
                preds_proba = self.xgb_head.predict_proba(embeddings)
                if len(preds_proba.shape) == 2 and preds_proba.shape[1] == 2:
                    signal_probs = preds_proba[:, 0]
                    drop_probs = preds_proba[:, 1]
                else:
                    signal_probs = np.zeros(len(embeddings))
                    drop_probs = np.zeros(len(embeddings))
            except Exception as e:
                log(f"Falling back to direct predict for XGBoost: {e}")
                preds = self.xgb_head.predict(embeddings).astype(float)
                if len(preds.shape) == 2 and preds.shape[1] == 2:
                    signal_probs = preds[:, 0]
                    drop_probs = preds[:, 1]
                else:
                    signal_probs = np.zeros(len(embeddings))
                    drop_probs = np.zeros(len(embeddings))
            
            # --- Percentile Rank Transform (Dynamic Score 0.0 ~ 1.0) ---
            if len(signal_probs) > 0:
                s = pd.Series(signal_probs)
                # 6 months rolling rank (126 days), fallback to expanding for initial days
                rolling_rank = s.rolling(window=126, min_periods=20).rank(pct=True)
                expanding_rank = s.expanding(min_periods=1).rank(pct=True)
                final_scores = rolling_rank.fillna(expanding_rank).values
                # Handle edge case NaNs
                final_scores = np.nan_to_num(final_scores, nan=0.5)
                
                # Do the same for drop probabilities
                s_drop = pd.Series(drop_probs)
                rolling_rank_drop = s_drop.rolling(window=126, min_periods=20).rank(pct=True)
                expanding_rank_drop = s_drop.expanding(min_periods=1).rank(pct=True)
                final_drop_scores = rolling_rank_drop.fillna(expanding_rank_drop).values
                final_drop_scores = np.nan_to_num(final_drop_scores, nan=0.5)
            else:
                final_scores = np.array([])
                final_drop_scores = np.array([])
            
            # Fill the probabilities (skipping the first 'lookback - 1' indices)
            probs[self.lookback - 1:] = final_scores
            probs_drop[self.lookback - 1:] = final_drop_scores
            
            log(f"predict_signals optimized finished for {data_len} rows")
            return probs, probs_drop
        except Exception as e:
            log(f"CRITICAL ERROR in _predict_signals_internal: {e}")
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
    
    probs, probs_drop = engine.predict_signals(df)
    print(f"Predictions generated for {len(probs)} steps. Sample Up: {probs[-5:]}, Sample Drop: {probs_drop[-5:]}")
