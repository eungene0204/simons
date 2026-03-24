import torch
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
import logging

logger = logging.getLogger(__name__)

class AIEngine:
    def __init__(self, model_dir=None):
        if model_dir is None:
            model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "model", "expanded_features")
        self.model_lock = threading.Lock()
        self.model_dir = model_dir
        self._score_cache: dict = {}  # {(sym, last_date, n_rows): (probs, probs_drop)}
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

        # Validate scaler input dimension matches feature count
        expected_features = getattr(self.scaler, 'n_features_in_', None)
        actual_features = len(self.ts_features)
        if isinstance(expected_features, int) and expected_features != actual_features:
            raise ValueError(
                f"Scaler expects {expected_features} features but ts_features has {actual_features}. "
                f"Check model_meta.json 'features' list."
            )
        logger.info(f"AIEngine initialized. Device={self.device}, Features={len(self.ts_features)}, Lookback={self.lookback}")

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

    def _preprocess_for_ai(self, df: pd.DataFrame):
        """특징 공학 + 스케일링 + 슬라이딩 윈도우 생성 (잠금 없음, 병렬 안전).

        Returns:
            (scaled_data, data_len, windows_arr, n_windows) 또는
            data가 너무 짧으면 None
        """
        from numpy.lib.stride_tricks import as_strided

        data_len = len(df)
        if data_len <= self.lookback:
            return None

        pdf = df.copy()
        pdf.columns = [c.lower() for c in pdf.columns]

        # RSI 컬럼 확보
        if not any(c.startswith('rsi') for c in pdf.columns):
            from stockstats import StockDataFrame
            sdf = StockDataFrame.retype(pdf.copy())
            pdf['rsi_14'] = sdf['rsi_14']

        # 지표 계산 (AI 모델 고정 피처셋)
        from engine.indicators import IndicatorEngine
        indicator_reqs = [
            {'id': 'ema', 'params': {'period': 20}},
            {'id': 'macd', 'params': {}},
            {'id': 'stochastic', 'params': {}},
            {'id': 'cci', 'params': {'period': 14}},
            {'id': 'adx', 'params': {}},
            {'id': 'bollinger_bands', 'params': {'period': 20}},
            {'id': 'volume_spike', 'params': {'period': 20}},
        ]
        pdf = IndicatorEngine.calculate(pl.from_pandas(pdf), indicator_reqs).to_pandas()

        # 로그 수익률 (pct_change가 -1이면 log1p(-1)=-inf → 이후 replace로 처리)
        with np.errstate(invalid='ignore', divide='ignore'):
            for col in ['open', 'high', 'low', 'close']:
                pdf[f'ret_{col}'] = np.log1p(pdf[col].pct_change())
            pdf['ret_volume'] = np.log1p(pdf['volume'].pct_change())
            pdf['ret_obv'] = np.log1p(pdf['obv'].pct_change())

        # 정상화 피처
        pdf['dist_sma_20'] = pdf['close'] / pdf['close_20_sma'] - 1
        pdf['dist_ema_20'] = pdf['close'] / pdf['close_20_ema'] - 1
        pdf['boll_pos'] = (pdf['close'] - pdf['boll_lb']) / (pdf['boll_ub'] - pdf['boll_lb'] + 1e-8)

        features = self.ts_features
        pdf[features] = pdf[features].replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            scaled_data = np.ascontiguousarray(
                self.scaler.transform(pdf[features]).astype(np.float32)
            )

        n_windows = data_len - self.lookback + 1
        s0, s1 = scaled_data.strides
        windows_arr = as_strided(
            scaled_data,
            shape=(n_windows, self.lookback, len(features)),
            strides=(s0, s0, s1),
        )
        return scaled_data, data_len, windows_arr, n_windows

    @staticmethod
    def _percentile_rank(arr: np.ndarray) -> np.ndarray:
        """Rolling 126-day percentile rank transform"""
        s = pd.Series(arr)
        rolling = s.rolling(window=126, min_periods=20).rank(pct=True)
        expanding = s.expanding(min_periods=1).rank(pct=True)
        return np.nan_to_num(rolling.fillna(expanding).values, nan=0.5)

    def _infer_windows(self, windows_arr: np.ndarray, n_windows: int) -> np.ndarray:
        """Transformer forward pass (호출 전 model_lock을 반드시 보유해야 함)"""
        batch_size = 4096  # larger batch → fewer kernel dispatches → faster
        parts = []
        with torch.inference_mode():
            for i in range(0, n_windows, batch_size):
                batch = torch.from_numpy(np.ascontiguousarray(windows_arr[i:i + batch_size])).to(self.device)
                parts.append(self.transformer(batch).cpu().numpy())
        return np.concatenate(parts, axis=0)

    def _xgb_predict(self, embeddings: np.ndarray):
        """XGBoost 예측 → (signal_probs, drop_probs)"""
        try:
            preds = self.xgb_head.predict_proba(embeddings)
        except Exception:
            preds = self.xgb_head.predict(embeddings).astype(float)

        if preds.ndim == 2 and preds.shape[1] >= 2:
            return preds[:, 0], preds[:, 1]
        return np.zeros(len(embeddings)), np.zeros(len(embeddings))

    # ── 단일 종목 추론 (기존 API 호환) ───────────────────────────────────────────

    def predict_signals(self, df: pd.DataFrame) -> tuple:
        """단일 종목 AI 추론. 내부적으로 predict_signals_batch를 사용."""
        result = self.predict_signals_batch({"_single": df})
        return result["_single"]

    # ── 일괄 추론 (핵심 최적화) ──────────────────────────────────────────────────

    def predict_signals_batch(self, dfs: dict) -> dict:
        """여러 종목을 한 번의 lock 획득으로 일괄 추론.

        Args:
            dfs: {symbol: pd.DataFrame} — 이미 인덱스가 date인 OHLCV+지표 데이터

        Returns:
            {symbol: (ai_probs np.ndarray, ai_drop_probs np.ndarray)}
            데이터 부족 종목은 zeros 반환.
        """
        import concurrent.futures

        # ── 캐시 히트 먼저 처리 ──────────────────────────────────────────────────
        def _cache_key(sym: str, df: pd.DataFrame) -> tuple:
            idx = df.index
            return (sym, str(idx[-1]) if len(idx) else "", len(df))

        results: dict = {}
        uncached_dfs: dict = {}
        for sym, df in dfs.items():
            key = _cache_key(sym, df)
            if key in self._score_cache:
                results[sym] = self._score_cache[key]
            else:
                uncached_dfs[sym] = df

        if uncached_dfs:
            logger.info(f"[AI-Batch] 캐시 히트={len(results)}, 미스={len(uncached_dfs)}")

        # ── Phase 1: 병렬 전처리 (잠금 없음) ────────────────────────────────────
        def _prep(item):
            sym, df = item
            try:
                return sym, self._preprocess_for_ai(df)
            except Exception as e:
                logger.warning(f"[AI-Batch] {sym} 전처리 실패: {e}")
                return sym, None

        with concurrent.futures.ThreadPoolExecutor() as ex:
            prep_results = dict(ex.map(_prep, uncached_dfs.items()))

        valid = {sym: data for sym, data in prep_results.items() if data is not None}
        sym_order = list(valid.keys())

        # ── Phase 2: Transformer + XGBoost (단일 lock 획득) ─────────────────────
        # NOTE: results already contains cache hits — do NOT re-initialize here
        if sym_order:
            with self.model_lock:
                # Transformer: 모든 종목 윈도우를 하나로 합쳐 단일 스트림으로 추론
                # (종목별 루프 대신 단일 스트림 → kernel dispatch 횟수 대폭 감소)
                windows_list = []
                sym_meta = {}
                for sym in sym_order:
                    _, data_len, windows_arr, n_windows = valid[sym]
                    windows_list.append(np.ascontiguousarray(windows_arr))
                    sym_meta[sym] = (n_windows, data_len)

                all_windows = np.concatenate(windows_list, axis=0)
                logger.info(f"[AI-Batch] Transformer 추론: {len(all_windows)}개 윈도우 ({len(sym_order)}종목)")
                all_embeddings = self._infer_windows(all_windows, len(all_windows))

                # XGBoost: 전 종목 임베딩을 한 번에 처리
                all_sig, all_drop = self._xgb_predict(all_embeddings)

                # 결과 분할
                offset = 0
                for sym in sym_order:
                    n_windows, data_len = sym_meta[sym]
                    sig = all_sig[offset:offset + n_windows]
                    drop = all_drop[offset:offset + n_windows]
                    offset += n_windows

                    probs = np.zeros(data_len)
                    probs_drop = np.zeros(data_len)
                    probs[self.lookback - 1:] = self._percentile_rank(sig)
                    probs_drop[self.lookback - 1:] = self._percentile_rank(drop)
                    scored = (probs, probs_drop)
                    results[sym] = scored
                    # 캐시 저장
                    key = _cache_key(sym, uncached_dfs[sym])
                    self._score_cache[key] = scored

        # 전처리 실패 종목 → zeros
        for sym, df in dfs.items():
            if sym not in results:
                n = len(df)
                results[sym] = (np.zeros(n), np.zeros(n))

        return results

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
