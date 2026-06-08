"""
Regression tests for AI signal-model bug fixes (Transformer + XGBoost).

Covers the issues found in the model review:
  #1  RoPE applied to Q/K inside attention (proper relative position), not to
      the input embeddings once.
  #2  ret_obv is finite (no NaN from sign-flipping cumulative OBV).
  #3  _score_cache is a bounded LRU cache.
  #4  predict_signals_batch streams windows in bounded chunks (multi-flush)
      while keeping per-symbol length/alignment correct.
  #5  AIEngine falls back to the shipped v3 architecture (128/8/3) and warns
      when model_meta.json is missing shape keys.
  #6  Conv1DStem / RoPEMultiheadAttention reject invalid dimensions.

These tests mock model loading — they never load the real checkpoint, so they
remain valid across retrains.
"""
import io
import json as json_mod
import logging

import numpy as np
import pandas as pd
import pytest
import torch
from unittest.mock import patch, MagicMock


# ──────────────────────────────────────────────────────────────────────────────
# Mock AIEngine helper (no real checkpoint loaded)
# ──────────────────────────────────────────────────────────────────────────────

_real_open = open


def _mock_open_factory(meta):
    def _mock_open(path, *args, **kwargs):
        if isinstance(path, str) and path.endswith('model_meta.json'):
            return io.StringIO(json_mod.dumps(meta))
        return _real_open(path, *args, **kwargs)
    return _mock_open


def _make_mock_engine(meta=None):
    meta = meta or {}
    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', side_effect=_mock_open_factory(meta)), \
         patch('joblib.load') as mock_joblib, \
         patch('torch.load', return_value={}), \
         patch('torch.nn.Module.load_state_dict', return_value=None), \
         patch('xgboost.XGBClassifier.load_model'):
        mock_scaler = MagicMock()
        mock_scaler.transform.side_effect = lambda x: np.asarray(x, dtype=np.float32)
        mock_joblib.return_value = mock_scaler
        from ai.ai_engine import AIEngine
        return AIEngine()


# ══════════════════════════════════════════════════════════════════════════════
# #1 — Proper RoPE inside attention
# ══════════════════════════════════════════════════════════════════════════════

class TestProperRoPE:
    def _model(self):
        from ai.models import HybridAIModel
        torch.manual_seed(0)
        m = HybridAIModel(input_dim=8, d_model=32, nhead=4, num_layers=2,
                          dim_feedforward=64, dropout=0.0, stochastic_depth=0.0)
        m.eval()
        return m

    def test_attention_is_rope_not_vanilla(self):
        """Encoder layers must use RoPEMultiheadAttention, not nn.MultiheadAttention."""
        from ai.models import RoPEMultiheadAttention
        m = self._model()
        attns = [mod for mod in m.modules() if isinstance(mod, RoPEMultiheadAttention)]
        assert len(attns) == 2, "every encoder layer should hold a RoPE attention"
        assert not any(isinstance(mod, torch.nn.MultiheadAttention) for mod in m.modules())

    def test_model_is_position_aware(self):
        """Permuting timesteps must change the [CLS] output (positional signal present)."""
        m = self._model()
        x = torch.randn(2, 12, 8)
        xp = x.clone()
        xp[:, [3, 8]] = xp[:, [8, 3]]
        with torch.no_grad():
            o1, o2 = m(x), m(xp)
        assert not torch.allclose(o1, o2, atol=1e-5)

    def test_rope_relative_shift_invariance(self):
        """RoPE is relative: shifting all keys/queries by the same offset leaves the
        attention logits unchanged. Verify on the attention module directly."""
        from ai.models import RoPEMultiheadAttention
        torch.manual_seed(1)
        attn = RoPEMultiheadAttention(d_model=16, nhead=2, dropout=0.0).eval()
        T = 6
        x = torch.randn(1, T, 16)

        def logits(seq, positions):
            B, t, C = seq.shape
            q = attn.q_proj(seq).view(B, t, attn.nhead, attn.head_dim).transpose(1, 2)
            k = attn.k_proj(seq).view(B, t, attn.nhead, attn.head_dim).transpose(1, 2)
            cos, sin = attn._rope_cos_sin(int(positions.max()) + 1, seq.device, q.dtype)
            from ai.models import _rotate_half
            cs = cos[positions][None, None]
            sn = sin[positions][None, None]
            q = q * cs + _rotate_half(q) * sn
            k = k * cs + _rotate_half(k) * sn
            return (q @ k.transpose(-2, -1)) / (attn.head_dim ** 0.5)

        base = logits(x, torch.arange(T))
        shifted = logits(x, torch.arange(T) + 4)  # shift every position by +4
        assert torch.allclose(base, shifted, atol=1e-4), \
            "attention logits must depend only on relative position"


# ══════════════════════════════════════════════════════════════════════════════
# #6 — Dimension guards
# ══════════════════════════════════════════════════════════════════════════════

class TestDimensionGuards:
    def test_conv1d_stem_rejects_odd_d_model(self):
        from ai.models import Conv1DStem
        with pytest.raises(ValueError, match="even"):
            Conv1DStem(input_dim=8, d_model=33)

    def test_rope_attention_rejects_indivisible(self):
        from ai.models import RoPEMultiheadAttention
        with pytest.raises(ValueError, match="divisible"):
            RoPEMultiheadAttention(d_model=30, nhead=4)

    def test_rope_attention_rejects_odd_head_dim(self):
        from ai.models import RoPEMultiheadAttention
        # 12 / 4 = head_dim 3 (odd) → invalid for rotary
        with pytest.raises(ValueError, match="even"):
            RoPEMultiheadAttention(d_model=12, nhead=4)


# ══════════════════════════════════════════════════════════════════════════════
# #2 — ret_obv is finite
# ══════════════════════════════════════════════════════════════════════════════

class TestRetObvFinite:
    def test_ret_obv_finite_when_obv_sign_flips(self):
        """A choppy price series makes OBV cross zero repeatedly; ret_obv must stay
        finite (the old log-return-of-signed-OBV produced NaN/garbage there)."""
        from ai.feature_engineering import engineer_features
        rng = np.random.RandomState(7)
        n = 300
        close = np.cumprod(1 + rng.randn(n) * 0.04) * 1000
        df = pd.DataFrame({
            'open': close, 'high': close * 1.02, 'low': close * 0.98,
            'close': close, 'volume': rng.rand(n) * 1e5 + 1e4,
        })
        out = engineer_features(df)
        ro = out['ret_obv'].to_numpy()
        # Only the very first bar (diff of first row) may be NaN.
        assert np.isnan(ro[1:]).sum() == 0
        assert np.isinf(ro).sum() == 0


# ══════════════════════════════════════════════════════════════════════════════
# #3 — Bounded LRU score cache
# ══════════════════════════════════════════════════════════════════════════════

class TestBoundedCache:
    def test_cache_evicts_oldest_when_full(self):
        engine = _make_mock_engine()
        engine._cache_max = 3
        for i in range(6):
            engine._cache_put((f'sym{i}', '', i), (np.zeros(1), np.zeros(1)))
        assert len(engine._score_cache) == 3
        keys = [k[0] for k in engine._score_cache.keys()]
        assert keys == ['sym3', 'sym4', 'sym5']  # oldest three evicted

    def test_cache_hit_refreshes_lru_order(self):
        engine = _make_mock_engine()
        engine._cache_max = 3
        for i in range(3):
            engine._cache_put((f'sym{i}', '', i), (np.zeros(1), np.zeros(1)))
        # touch sym0 → becomes most-recent
        engine._score_cache.move_to_end(('sym0', '', 0))
        engine._cache_put(('sym3', '', 3), (np.zeros(1), np.zeros(1)))  # evicts sym1
        keys = [k[0] for k in engine._score_cache.keys()]
        assert 'sym0' in keys and 'sym1' not in keys


# ══════════════════════════════════════════════════════════════════════════════
# #4 — Streamed batch inference (multi-flush correctness)
# ══════════════════════════════════════════════════════════════════════════════

class TestStreamedBatchInference:
    def _wire_fake_model(self, engine):
        engine.lookback = 5
        # transformer pass → deterministic embedding per window
        engine._infer_windows = lambda w: w.reshape(len(w), -1)[:, :8].astype(np.float32)
        engine.xgb_up = MagicMock()
        engine.xgb_up.predict_proba = lambda e: np.column_stack(
            [np.zeros(len(e)), np.full(len(e), 0.7)])
        engine.xgb_down = MagicMock()
        engine.xgb_down.predict_proba = lambda e: np.column_stack(
            [np.zeros(len(e)), np.full(len(e), 0.3)])

    def _make_dfs(self, specs):
        dfs = {}
        for sym, nlen in specs:
            dfs[sym] = pd.DataFrame({
                'open': np.arange(nlen) + 1.0, 'high': np.arange(nlen) + 2.0,
                'low': np.arange(nlen) + 0.5, 'close': np.arange(nlen) + 1.0,
                'volume': np.ones(nlen) * 100.0,
            }, index=pd.RangeIndex(nlen))
        return dfs

    def test_multi_symbol_lengths_and_warmup_zero(self):
        engine = _make_mock_engine()
        self._wire_fake_model(engine)
        specs = [('A', 20), ('B', 8), ('C', 30)]
        res = engine.predict_signals_batch(self._make_dfs(specs))
        for sym, nlen in specs:
            up, down = res[sym]
            assert len(up) == nlen and len(down) == nlen
            # first lookback-1 bars have no complete window → zero
            assert np.all(up[:engine.lookback - 1] == 0)
            assert np.all(down[:engine.lookback - 1] == 0)
            # scored region carries the model probability
            assert np.allclose(up[engine.lookback - 1:], 0.7)
            assert np.allclose(down[engine.lookback - 1:], 0.3)

    def test_distinct_frames_same_len_and_last_index_do_not_collide(self):
        """Two different frames sharing length + last index must not collide in
        the score cache (regression: single-symbol path uses a constant sym)."""
        engine = _make_mock_engine()
        engine.lookback = 5
        # content-sensitive mock: prob depends on the window's mean feature value
        engine._infer_windows = lambda w: w.reshape(len(w), -1).astype(np.float32)
        def _sig(e):
            p = 1.0 / (1.0 + np.exp(-e.mean(axis=1)))
            return np.column_stack([1 - p, p])
        engine.xgb_up = MagicMock(); engine.xgb_up.predict_proba = _sig
        engine.xgb_down = MagicMock(); engine.xgb_down.predict_proba = _sig

        n = 30
        idx = pd.RangeIndex(n)  # identical index → same last_index for both
        rise = np.linspace(100, 200, n)
        fall = np.linspace(200, 100, n)
        df_a = pd.DataFrame({'open': rise, 'high': rise + 1, 'low': rise - 1,
                             'close': rise, 'volume': np.ones(n) * 100}, index=idx)
        df_b = pd.DataFrame({'open': fall, 'high': fall + 1, 'low': fall - 1,
                             'close': fall, 'volume': np.ones(n) * 100}, index=idx)

        engine._score_cache.clear()
        up_a, _ = engine.predict_signals_batch({'_single': df_a})['_single']
        up_b, _ = engine.predict_signals_batch({'_single': df_b})['_single']
        # both distinct frames must be cached independently and score differently
        assert len(engine._score_cache) == 2
        assert not np.allclose(up_a[engine.lookback - 1:], up_b[engine.lookback - 1:])

    def test_small_window_budget_forces_multiple_flushes(self):
        engine = _make_mock_engine()
        self._wire_fake_model(engine)
        engine._window_budget = 7  # tiny → several flushes across symbols
        flushes = {'n': 0}
        orig = engine._infer_windows
        def counting(w):
            flushes['n'] += 1
            return orig(w)
        engine._infer_windows = counting
        specs = [('A', 12), ('B', 12), ('C', 12)]  # 8+8+8 = 24 windows / budget 7
        res = engine.predict_signals_batch(self._make_dfs(specs))
        assert flushes['n'] >= 2, "tiny budget must trigger multiple flushes"
        for sym, nlen in specs:
            up, _ = res[sym]
            assert len(up) == nlen
            assert np.allclose(up[engine.lookback - 1:], 0.7)


# ══════════════════════════════════════════════════════════════════════════════
# #5 — Architecture defaults + warning
# ══════════════════════════════════════════════════════════════════════════════

class TestArchitectureDefaults:
    def test_missing_arch_keys_warn_and_use_shipped_shape(self, caplog):
        with caplog.at_level(logging.WARNING):
            engine = _make_mock_engine(meta={})  # no d_model/nhead/...
        backbone = engine.transformer.transformer
        # shipped v3 shape: d_model=128, num_layers=3
        assert backbone.d_model == 128
        assert len(backbone.layers) == 3
        assert any('architecture keys' in r.message for r in caplog.records)

    def test_meta_overrides_defaults(self):
        engine = _make_mock_engine(meta={
            'd_model': 64, 'nhead': 4, 'num_layers': 2, 'dim_feedforward': 128,
        })
        backbone = engine.transformer.transformer
        assert backbone.d_model == 64
        assert len(backbone.layers) == 2
