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

from ai.ai_engine import AIEngine


def _compute_features(sym_df: pd.DataFrame) -> pd.DataFrame:
    """
    Shared feature engineering: indicators + log returns + stationary features.
    Matches the exact pipeline used in ai_engine.predict_signals.
    """
    from engine.indicators import IndicatorEngine
    import polars as pl

    indicator_reqs = [
        {'id': 'ema', 'params': {'period': 20}},
        {'id': 'macd', 'params': {}},
        {'id': 'stochastic', 'params': {}},
        {'id': 'cci', 'params': {'period': 14}},
        {'id': 'adx', 'params': {}},
        {'id': 'bollinger_bands', 'params': {'period': 20}},
        {'id': 'volume_spike', 'params': {'period': 20}}
    ]
    sym_df_pl = IndicatorEngine.calculate(pl.from_pandas(sym_df), indicator_reqs)
    sym_df = sym_df_pl.to_pandas()

    # Price/Volume Log Returns (consistent with ai_engine pipeline)
    for col in ['open', 'high', 'low', 'close']:
        sym_df[f'ret_{col}'] = np.log1p(sym_df[col].pct_change())
    sym_df['ret_volume'] = np.log1p(sym_df['volume'].pct_change())
    sym_df['ret_obv'] = np.log1p(sym_df['obv'].pct_change())

    # Stationary Technical Features
    sym_df['dist_sma_20'] = sym_df['close'] / sym_df['close_20_sma'] - 1
    sym_df['dist_ema_20'] = sym_df['close'] / sym_df['close_20_ema'] - 1
    sym_df['boll_pos'] = (sym_df['close'] - sym_df['boll_lb']) / (sym_df['boll_ub'] - sym_df['boll_lb'] + 1e-8)

    return sym_df


def run_xai(symbol, target_date_str):
    # Load AIEngine with dynamic path (same default as AIEngine.__init__)
    engine = AIEngine()

    # Enable GPU for XGBoost if possible
    if engine.device.type == 'cuda':
        try:
            engine.xgb_head.set_params(tree_method='gpu_hist', predictor='gpu_predictor')
        except Exception:
            pass

    # Load data
    try:
        df = pd.read_parquet("model/training_data_processed.parquet")
        sym_df = df[df['symbol'] == symbol].copy()
    except (FileNotFoundError, OSError) as e:
        logger.warning(f"Could not load training_data_processed.parquet: {e}")
        sym_df = pd.DataFrame()

    if sym_df.empty:
        # Fallback to raw OHLCV data
        raw_path = f"data/ohlcv/{symbol}.parquet"
        if not os.path.exists(raw_path):
            return {"error": f"Symbol '{symbol}' not found in any dataset"}
        sym_df = pd.read_parquet(raw_path)

    sym_df['date'] = pd.to_datetime(sym_df['date'])
    sym_df = sym_df.sort_values('date')
    sym_df = _compute_features(sym_df)

    # Resolve dynamic dimensions from the engine
    lookback = engine.lookback
    features_to_use = engine.ts_features
    n_features = len(features_to_use)

    # Find the row for target_date
    target_date = pd.to_datetime(target_date_str)
    matches = sym_df[sym_df['date'] == target_date]
    if len(matches) == 0:
        return {"error": "Date not found in dataset"}

    pos = sym_df.index.get_loc(matches.index[0])

    if pos < lookback - 1:
        return {"error": f"Not enough historical data (need {lookback} days)"}

    # Get exactly `lookback` days up to the target date
    slice_df = sym_df.iloc[pos - lookback + 1 : pos + 1].copy()

    slice_df[features_to_use] = slice_df[features_to_use].replace([np.inf, -np.inf], np.nan).ffill().fillna(0)

    raw_slice_values = slice_df[features_to_use].values
    scaled_data = engine.scaler.transform(raw_slice_values).astype(np.float32)

    # --- 1. Extract Attention Map ---
    import unittest.mock
    attention_weights = []
    layer = engine.transformer.transformer.transformer_encoder.layers[-1].self_attn

    orig_forward = torch.nn.MultiheadAttention.forward
    def custom_forward(self, *args, **kwargs):
        kwargs['need_weights'] = True
        attn_out, attn_weights_out = orig_forward(self, *args, **kwargs)
        if self is layer and attn_weights_out is not None:
            attention_weights.append(attn_weights_out.detach().cpu().numpy())
        return attn_out, attn_weights_out

    tensor_input = torch.from_numpy(scaled_data).unsqueeze(0).to(engine.device)
    with torch.no_grad(), unittest.mock.patch('torch.nn.MultiheadAttention.forward', new=custom_forward):
        _ = engine.transformer(tensor_input)

    # attention_weights[0] shape: (1, lookback, lookback). Last row = what the LAST day pays attention to.
    attn_map = attention_weights[0][0, -1, :].tolist()

    # --- 2. Calculate KernelSHAP ---
    bg_path = "model/shap_background.npy"
    if not os.path.exists(bg_path):
        return {"error": "Missing SHAP background dataset at 'model/shap_background.npy'"}

    background = np.load(bg_path)
    background_2d = background.reshape(background.shape[0], -1)
    single_2d = scaled_data.reshape(1, -1)

    # Pre-cache for faster access in predict function
    device = engine.device
    transformer = engine.transformer
    xgb_head = engine.xgb_head

    def model_predict_2d(X_2d):
        """Predict P(up) for SHAP — consistent with ai_engine col 0 = P(up)."""
        X_3d = X_2d.reshape(-1, lookback, n_features).astype(np.float32)
        t_input = torch.from_numpy(X_3d).to(device)

        with torch.inference_mode():
            embs = transformer(t_input).cpu().numpy()

        try:
            # col 0 = P(up), matching ai_engine's signal_probs convention
            return xgb_head.predict_proba(embs)[:, 0]
        except Exception:
            return xgb_head.predict(embs).astype(float)

    explainer = shap.KernelExplainer(model_predict_2d, background_2d)
    shap_out = explainer.shap_values(single_2d, nsamples=1000, silent=True)

    # Normalizing SHAP output shape
    if isinstance(shap_out, list):
        # For multi-class output, use class 0 (up) to match model_predict_2d
        shap_values_raw = shap_out[0][0]
    else:
        shap_values_raw = shap_out[0] if len(shap_out.shape) == 2 else shap_out

    shap_matrix = shap_values_raw.reshape(lookback, n_features)

    # Calculate feature importance summary (sum over lookback window)
    feature_importance_directional = np.sum(shap_matrix, axis=0).tolist()
    feature_importance_absolute = np.sum(np.abs(shap_matrix), axis=0).tolist()

    result = {
        "symbol": symbol,
        "date": target_date_str,
        "status": "success",
        "attention_map": attn_map,
        "shap_matrix": shap_matrix.tolist(),
        "feature_importance_directional": feature_importance_directional,
        "feature_importance_absolute": feature_importance_absolute,
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
        import io
        import contextlib
        import traceback
        with contextlib.redirect_stdout(io.StringIO()):
            res = run_xai(symbol, date_str)

        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))
