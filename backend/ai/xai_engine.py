import sys
import json
import pandas as pd
import numpy as np
import torch
import shap
import warnings
import os
import logging

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

from ai.ai_engine import AIEngine, _engineer_features_v2, _augment_embeddings


def run_xai(symbol, target_date_str):
    engine = AIEngine()

    # Load data
    try:
        processed_path = os.path.join(engine.model_dir, 'training_data_processed.parquet')
        if not os.path.exists(processed_path):
            processed_path = "model/training_data_processed.parquet"
        df = pd.read_parquet(processed_path)
        sym_df = df[df['symbol'] == symbol].copy()
    except (FileNotFoundError, OSError) as e:
        logger.warning(f"Could not load training_data_processed.parquet: {e}")
        sym_df = pd.DataFrame()

    if sym_df.empty:
        raw_path = f"data/ohlcv/{symbol}.parquet"
        if not os.path.exists(raw_path):
            return {"error": f"Symbol '{symbol}' not found in any dataset"}
        sym_df = pd.read_parquet(raw_path)

    sym_df['date'] = pd.to_datetime(sym_df['date'])
    sym_df.columns = [c.lower() for c in sym_df.columns]
    sym_df = sym_df.sort_values('date')

    sym_df = _engineer_features_v2(sym_df)

    lookback = engine.lookback
    features_to_use = engine.ts_features
    n_features = len(features_to_use)

    # Find target date row
    target_date = pd.to_datetime(target_date_str)
    matches = sym_df[sym_df['date'] == target_date]
    if len(matches) == 0:
        return {"error": "Date not found in dataset"}

    pos = sym_df.index.get_loc(matches.index[0])
    if pos < lookback - 1:
        return {"error": f"Not enough historical data (need {lookback} days)"}

    slice_df = sym_df.iloc[pos - lookback + 1:pos + 1].copy()
    slice_df[features_to_use] = slice_df[features_to_use].replace([np.inf, -np.inf], np.nan).ffill().fillna(0)

    raw_slice_values = slice_df[features_to_use].values
    scaled_data = engine.scaler.transform(raw_slice_values).astype(np.float32)

    # --- 1. Extract Attention Map ---
    import unittest.mock
    attention_weights = []

    # V2: Pre-LN layers stored in engine.transformer.transformer.layers
    last_layer = engine.transformer.transformer.layers[-1].self_attn

    orig_forward = torch.nn.MultiheadAttention.forward

    def custom_forward(self, *args, **kwargs):
        kwargs['need_weights'] = True
        attn_out, attn_weights_out = orig_forward(self, *args, **kwargs)
        if self is last_layer and attn_weights_out is not None:
            attention_weights.append(attn_weights_out.detach().cpu().numpy())
        return attn_out, attn_weights_out

    tensor_input = torch.from_numpy(scaled_data).unsqueeze(0).to(engine.device)
    with torch.no_grad(), unittest.mock.patch('torch.nn.MultiheadAttention.forward', new=custom_forward):
        engine.transformer(tensor_input)

    if attention_weights:
        # V2: CLS token prepended, attention shape (1, 1+lookback, 1+lookback)
        # Row 0 = CLS attention; skip self-attention (col 0), take sequence positions
        attn_raw = attention_weights[0][0]
        attn_map = attn_raw[0, 1:].tolist()
    else:
        attn_map = [0.0] * lookback

    # --- 2. Calculate KernelSHAP ---
    bg_path = os.path.join(engine.model_dir, 'shap_background.npy')
    if not os.path.exists(bg_path):
        bg_path = "model/shap_background.npy"
    if not os.path.exists(bg_path):
        return {"error": "Missing SHAP background dataset"}

    background = np.load(bg_path)
    background_2d = background.reshape(background.shape[0], -1)
    single_2d = scaled_data.reshape(1, -1)

    device = engine.device
    transformer = engine.transformer

    def model_predict_2d(X_2d):
        """Predict P(up) for SHAP."""
        X_3d = X_2d.reshape(-1, lookback, n_features).astype(np.float32)
        t_input = torch.from_numpy(X_3d).to(device)

        with torch.inference_mode():
            embs = transformer(t_input).cpu().numpy()

        embs_aug = _augment_embeddings(embs)
        try:
            return engine.xgb_up.predict_proba(embs_aug)[:, 1]
        except Exception:
            return engine.xgb_up.predict(embs_aug).astype(float)

    explainer = shap.KernelExplainer(model_predict_2d, background_2d)
    shap_out = explainer.shap_values(single_2d, nsamples=1000, silent=True)

    if isinstance(shap_out, list):
        shap_values_raw = shap_out[0][0]
    else:
        shap_values_raw = shap_out[0] if len(shap_out.shape) == 2 else shap_out

    shap_matrix = shap_values_raw.reshape(lookback, n_features)
    feature_importance_directional = np.sum(shap_matrix, axis=0).tolist()
    feature_importance_absolute = np.sum(np.abs(shap_matrix), axis=0).tolist()

    return {
        "symbol": symbol,
        "date": target_date_str,
        "status": "success",
        "attention_map": attn_map,
        "shap_matrix": shap_matrix.tolist(),
        "feature_importance_directional": feature_importance_directional,
        "feature_importance_absolute": feature_importance_absolute,
        "features": features_to_use
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Missing arguments. Usage: python xai_engine.py <symbol> <date_str>"}))
        sys.exit(1)

    symbol = sys.argv[1]
    date_str = sys.argv[2]

    try:
        import io
        import contextlib
        import traceback
        with contextlib.redirect_stdout(io.StringIO()):
            res = run_xai(symbol, date_str)
        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))
