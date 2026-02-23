import sys
import json
import pandas as pd
import numpy as np
import torch
import shap
import warnings
import os
warnings.filterwarnings('ignore')

from backend.ai.ai_engine import AIEngine

def run_xai(symbol, target_date_str):
    # Load AIEngine
    engine = AIEngine(model_dir="model")
    
    # Load data
    try:
        df = pd.read_parquet("model/training_data_processed.parquet")
    except:
        df = pd.read_parquet("backend/data/training_data_processed.parquet")
        
    sym_df = df[df['symbol'] == symbol].copy()
    if sym_df.empty:
        return {"error": f"Symbol '{symbol}' not found in dataset"}
        
    sym_df['date'] = pd.to_datetime(sym_df['date'])
    sym_df = sym_df.sort_values('date')
    
    # Calculate features BEFORE slicing
    for col in ['open', 'high', 'low', 'close']:
        sym_df[f'ret_{col}'] = sym_df[col].pct_change()
    sym_df['ret_volume'] = sym_df['volume'].pct_change()
    actual_rsi = next((c for c in sym_df.columns if c.startswith('rsi')), None)
    
    # Find the row for target_date
    target_date = pd.to_datetime(target_date_str)
    matches = sym_df[sym_df['date'] == target_date]
    if len(matches) == 0:
        return {"error": "Date not found in dataset"}
        
    pos = sym_df.index.get_loc(matches.index[0])
    
    if pos < 59:
        return {"error": "Not enough historical data (need 60 days)"}
        
    # Get EXACTLY 60 days up to the target date
    slice_df = sym_df.iloc[pos-59 : pos+1].copy()
    
    features_to_use = ['ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', actual_rsi]
    slice_df[features_to_use] = slice_df[features_to_use].replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    
    raw_slice_values = slice_df[features_to_use].values
    scaled_data = engine.scaler.transform(raw_slice_values).astype(np.float32)
    # shape: (60, 6)
    
    # 2. Extract Attention Map (using unittest.mock.patch to force need_weights=True)
    import unittest.mock
    attention_weights = []
    layer = engine.transformer.transformer.transformer_encoder.layers[-1].self_attn
    
    orig_forward = torch.nn.MultiheadAttention.forward
    def custom_forward(self, *args, **kwargs):
        kwargs['need_weights'] = True
        attn_out, attn_weights = orig_forward(self, *args, **kwargs)
        if self is layer and attn_weights is not None:
            attention_weights.append(attn_weights.detach().cpu().numpy())
        return attn_out, attn_weights
    
    tensor_input = torch.from_numpy(scaled_data).unsqueeze(0).to(engine.device) # (1, 60, 6)
    with torch.no_grad(), unittest.mock.patch('torch.nn.MultiheadAttention.forward', new=custom_forward):
        _ = engine.transformer(tensor_input)
    
    # attention_weights[0] is shape (1, 60, 60). We want [0, -1, :] to show what the LAST day pays attention to
    attn_map = attention_weights[0][0, -1, :].tolist()
    
    # --- 2. Calculate KernelSHAP ---
    bg_path = "model/shap_background.npy"
    if not os.path.exists(bg_path):
        return {"error": "Missing SHAP background dataset at 'model/shap_background.npy'"}
        
    background = np.load(bg_path) # (100, 60, 6)
    background_2d = background.reshape(background.shape[0], -1) # (100, 360)
    single_2d = scaled_data.reshape(1, -1) # (1, 360)
    
    def model_predict_2d(X_2d):
        X_3d = X_2d.reshape(-1, 60, 6)
        t_input = torch.from_numpy(X_3d.astype(np.float32)).to(engine.device)
        with torch.no_grad():
            embs = engine.transformer(t_input).cpu().numpy()
        try:
            probs = engine.xgb_head.predict_proba(embs)[:, 1]
        except:
            probs = engine.xgb_head.predict(embs).astype(float)
        return probs
        
    # We use a very small sample size for speed (e.g., 500)
    explainer = shap.KernelExplainer(model_predict_2d, background_2d)
    shap_out = explainer.shap_values(single_2d, nsamples=500, silent=True)
    
    # Normalizing SHAP output shape
    if isinstance(shap_out, list):
        shap_values_raw = shap_out[1][0] # class 1
    else:
        shap_values_raw = shap_out[0] if len(shap_out.shape) == 2 else shap_out
        
    shap_matrix = shap_values_raw.reshape(60, 6)
    
    # Calculate feature importance summary (sum over 60 days)
    # Directional (preserves +/- contribution)
    feature_importance_directional = np.sum(shap_matrix, axis=0).tolist()
    
    result = {
        "symbol": symbol,
        "date": target_date_str,
        "status": "success",
        "attention_map": attn_map,  # array of 60 standard floats
        "shap_matrix": shap_matrix.tolist(), # 60x6 matrix
        "feature_importance_directional": feature_importance_directional,
        "features": features_to_use
    }
    
    return result

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Missing arguments. Usage: python xai_engine.py <symbol> <date_str>"}))
        sys.exit(1)
        
    symbol = sys.argv[1]
    date_str = sys.argv[2]
    
    try:
        # Prevent any extra stdout logs from engine initialization
        import io
        import contextlib
        import traceback
        with contextlib.redirect_stdout(io.StringIO()):
            res = run_xai(symbol, date_str)
            
        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))
