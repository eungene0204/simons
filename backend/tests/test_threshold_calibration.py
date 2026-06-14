"""Regression tests for train_model.calibrate_threshold.

A prior version returned a fixed 0.5 fallback when the val precision target was
unreachable. For a poorly separated head whose scores compress into a narrow band
below 0.5 (the regularized DOWN XGBoost — scores ~[0.24, 0.38]), 0.5 sits above the
max score, producing a permanently dead signal. The calibrator must instead floor
the threshold to the head's own score distribution so it always fires.
"""
import importlib.util
import os

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def calibrate_threshold():
    path = os.path.join(ROOT, "scripts", "train_model.py")
    spec = importlib.util.spec_from_file_location("train_model", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.calibrate_threshold


def test_unreachable_precision_does_not_return_dead_threshold(calibrate_threshold):
    """DOWN-head-like case: scores compressed in [0.24, 0.38], precision never
    reaches 0.55. The threshold must stay in-distribution (≤ max score), not 0.5."""
    rng = np.random.default_rng(0)
    y_prob = rng.uniform(0.24, 0.38, size=5000)
    y_true = (rng.random(5000) < 0.32).astype(int)  # ~base rate, no separation

    thr = calibrate_threshold(y_true, y_prob, target_precision=0.55, min_fire_rate=0.02)

    assert thr <= y_prob.max(), "threshold above max score → dead signal"
    fire_rate = (y_prob >= thr).mean()
    assert fire_rate >= 0.015, f"signal must still fire (got {fire_rate:.3f})"


def test_fire_rate_floor_caps_an_overly_strict_threshold(calibrate_threshold):
    """Even when the precision target IS reachable only at the extreme top, the
    fire-rate floor keeps the threshold from firing on almost nothing."""
    rng = np.random.default_rng(1)
    y_prob = rng.uniform(0.0, 1.0, size=5000)
    # Strong separation so precision 0.55 is reachable, but force a high-only signal.
    y_true = (y_prob > 0.9).astype(int)

    thr = calibrate_threshold(y_true, y_prob, target_precision=0.55, min_fire_rate=0.05)

    fire_rate = (y_prob >= thr).mean()
    assert fire_rate >= 0.045, f"fire-rate floor not enforced (got {fire_rate:.3f})"
