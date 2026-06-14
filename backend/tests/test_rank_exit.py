"""Tests for cross-sectional AI drop-rank exit (engine/rank_exit.py)."""
import numpy as np
import pandas as pd
import pytest

from engine.rank_exit import compute_topk_drop_exits


def _df(rows, cols=None):
    cols = cols or [f"S{i}" for i in range(len(rows[0]))]
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="D")
    return pd.DataFrame(rows, index=idx, columns=cols)


def test_selects_top_percentile_highest_drop():
    # 10 symbols, top 20% → 2 highest drop scores per day exit.
    drop = _df([[0.30, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36, 0.37, 0.38, 0.39]])
    out = compute_topk_drop_exits(drop, 0.2)
    # S8 (0.38) and S9 (0.39) are the two highest.
    assert list(out.iloc[0]) == [False] * 8 + [True, True]


def test_min_one_selected_when_universe_small():
    # 8 symbols, 10% → floor(0.8)=0 → clamped to 1 (the single highest).
    drop = _df([[0.35, 0.36, 0.37, 0.38, 0.34, 0.33, 0.32, 0.31]])
    out = compute_topk_drop_exits(drop, 0.1)
    assert out.iloc[0].sum() == 1
    assert out.iloc[0]["S3"]  # 0.38 is highest


def test_available_mask_excludes_unavailable():
    # The true-highest score belongs to an unavailable (untraded) symbol → excluded.
    drop = _df([[0.39, 0.20, 0.21, 0.22]])
    avail = _df([[False, True, True, True]])
    out = compute_topk_drop_exits(drop, 0.25, avail)
    # S0 excluded despite top score; among the rest the highest (S3=0.22) is chosen.
    assert not out.iloc[0]["S0"]
    assert out.iloc[0]["S3"]
    assert out.iloc[0].sum() == 1


def test_ties_at_ceiling_select_exact_count_deterministically():
    # Compressed scores all tied at the ceiling (realistic for the DOWN head).
    # Must still pick exactly k by deterministic column-order tie-break, not all.
    drop = _df([[0.383] * 10])
    out = compute_topk_drop_exits(drop, 0.2)
    assert out.iloc[0].sum() == 2          # exactly top 20%, not all 10
    assert list(out.iloc[0][:2]) == [True, True]  # 'first' tie-break = earliest columns


def test_nan_scores_never_selected():
    drop = _df([[np.nan, np.nan, 0.30, 0.31]])
    out = compute_topk_drop_exits(drop, 0.5)
    assert not out.iloc[0]["S0"] and not out.iloc[0]["S1"]
    assert out.iloc[0]["S3"]  # highest valid


def test_all_nan_day_selects_nothing():
    drop = _df([[np.nan, np.nan, np.nan]])
    out = compute_topk_drop_exits(drop, 0.5)
    assert out.iloc[0].sum() == 0


@pytest.mark.parametrize("pct", [0.0, -0.1, 1.5])
def test_invalid_percentile_returns_all_false(pct):
    drop = _df([[0.30, 0.31, 0.32]])
    out = compute_topk_drop_exits(drop, pct)
    assert out.to_numpy().sum() == 0


def test_none_input_returns_none():
    assert compute_topk_drop_exits(None, 0.1) is None
