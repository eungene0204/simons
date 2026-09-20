"""엔진 v16.14 — 12-1 모멘텀·묶음 점수·변동성 역비중·시장 국면 필터.

핵심 계약:
- lookback_return_panel(skip_days): t-lookback → t-skip 구간 수익률. skip=0이면 종전과 같다.
- 복합 순위 group: 같은 묶음은 먼저 평균해 한 점수 → 묶음 점수·단독 지표를 동일 가중 평균.
  group이 없으면 종전 식(구성 지표 동일 가중)과 같다.
- 변동성 역비중: 리밸런싱일 목표 비중이 1/σ에 비례(순수 리밸런싱·조건 루프 두 경로).
- 시장 국면: 노출 비율이 바뀐 날 보유 비중을 기준 비중 × 새 노출로 맞추고, 축소 매도에
  국면 사유를 남긴다. 노출 0%는 전량 현금화 후 신규 편입 없음.
- vol_df·exposure가 없으면 두 경로 모두 종전 결과와 비트 단위로 같다.
"""

import pytest

pytest.importorskip("vectorbt")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest_engine import BacktestEngine, _composite_ranking_label  # noqa: E402
from engine import trade_reason as tr  # noqa: E402
from engine.indicators import lookback_return_panel  # noqa: E402
from engine.simulator import Simulator  # noqa: E402


# ─── 12-1 모멘텀 ──────────────────────────────────────────────────────────────

def test_skip_days_return_excludes_recent_window():
    idx = pd.date_range("2024-01-01", periods=6, freq="D")
    px = pd.DataFrame({"A": [100, 110, 121, 50, 50, 50]}, index=idx, dtype=float)
    # lookback=4, skip=2 → t=5: P(3)/P(1)-1 = 50/110-1 (최근 2일의 폭락 이후 구간은 안 봄)
    out = lookback_return_panel(px, 4, skip_days=2)
    assert out["A"].iloc[5] == pytest.approx(px["A"].iloc[3] / px["A"].iloc[1] - 1)
    assert np.isnan(out["A"].iloc[2])   # lookback 미달 구간은 NaN(후보 배제)


def test_skip_days_zero_is_legacy_identity():
    idx = pd.date_range("2024-01-01", periods=30, freq="D")
    rng = np.random.default_rng(0)
    px = pd.DataFrame(rng.uniform(90, 110, size=(30, 3)), index=idx, columns=list("ABC"))
    pd.testing.assert_frame_equal(lookback_return_panel(px, 5), px.ffill().pct_change(5))
    pd.testing.assert_frame_equal(lookback_return_panel(px, 5, skip_days=0), px.ffill().pct_change(5))


def test_skip_days_must_be_shorter_than_lookback():
    px = pd.DataFrame({"A": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError):
        lookback_return_panel(px, 2, skip_days=2)


def test_composite_label_names_skip_window():
    label = _composite_ranking_label([
        {"metric": "return", "direction": "top", "lookback_days": 252, "skip_days": 21},
        {"metric": "per", "direction": "bottom"},
    ])
    assert "최근 252거래일 수익률(최근 21거래일 제외)" in label


# ─── 묶음 점수 ────────────────────────────────────────────────────────────────

def _fund_values(idx, per_row):
    return {col: {s: pd.Series(v, index=idx) for s, v in by.items()} for col, by in per_row.items()}


def test_composite_group_averages_within_group_first():
    """품질 묶음(ROE·영업이익률·부채비율) + 모멘텀 단독: 품질 지표가 셋이어도 품질은 절반 가중."""
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    syms = ["A", "B"]
    values = _fund_values(idx, {
        # A가 품질 세 지표 모두 우위
        "roe_or_gpa": {"A": 20, "B": 5},
        "operating_margin": {"A": 20, "B": 5},
        "debt_ratio": {"A": 10, "B": 90},
    })
    # 모멘텀은 B가 우위(수익률 +50% vs +0%)
    price = pd.DataFrame({"A": [100.0, 100.0, 100.0], "B": [100.0, 120.0, 150.0]}, index=idx)
    quality = [
        {"metric": "roe_or_gpa", "direction": "top", "group": "quality"},
        {"metric": "operating_margin", "direction": "top", "group": "quality"},
        {"metric": "debt_ratio", "direction": "bottom", "group": "quality"},
    ]
    mom = [{"metric": "return", "direction": "top", "lookback_days": 2}]
    grouped, _, _ = BacktestEngine._composite_rank_panel(
        quality + mom, price, values, idx, syms, "same_close")
    # 묶음: A = (1 + 0.5)/2, B = (0.5 + 1)/2 → 동점
    assert grouped.iloc[-1]["A"] == pytest.approx(grouped.iloc[-1]["B"])
    flat = [{k: v for k, v in c.items() if k != "group"} for c in quality] + mom
    flat_df, _, _ = BacktestEngine._composite_rank_panel(
        flat, price, values, idx, syms, "same_close")
    # 평면 동일 가중이면 품질 3표가 이겨 A 우위(종전 식 그대로)
    assert flat_df.iloc[-1]["A"] > flat_df.iloc[-1]["B"]


# ─── 시뮬레이터: 변동성 역비중·시장 국면 ──────────────────────────────────────

def _frames(n=6, syms=("A", "B")):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    px = pd.DataFrame(100.0, index=idx, columns=list(syms))
    ents = pd.DataFrame(True, index=idx, columns=list(syms))
    exts = pd.DataFrame(False, index=idx, columns=list(syms))
    rank = pd.DataFrame({s: float(len(syms) - k) for k, s in enumerate(syms)}, index=idx)
    return idx, px, ents, exts, rank


def _risk(**extra):
    base = {"max_positions": 2, "init_cash": 10_000_000.0, "allocation_type": "equal",
            "rebalancing_period": "monthly"}
    base.update(extra)
    return base


def _position_values(pf):
    return pf.asset_value(group_by=False)


def test_pure_rebalance_inverse_vol_weights_follow_one_over_sigma():
    idx, px, ents, exts, rank = _frames()
    vol = pd.DataFrame({"A": 10.0, "B": 30.0}, index=idx)   # 1/σ 비 = 3:1
    pf = Simulator().run(px, px, ents, exts, _risk(allocation_type="inverse_volatility"),
                         {"execution_type": "same_close", "fee_rate": 0, "slippage_rate": 0},
                         rank_df=rank, vol_df=vol)
    vals = _position_values(pf).iloc[0]
    assert vals["A"] / vals["B"] == pytest.approx(3.0, rel=0.01)


def test_inverse_vol_in_signal_driven_loop():
    idx, px, ents, exts, rank = _frames()
    vol = pd.DataFrame({"A": 10.0, "B": 30.0}, index=idx)
    pf = Simulator().run(px, px, ents, exts,
                         _risk(allocation_type="inverse_volatility", entry_signal_driven=True),
                         {"execution_type": "same_close", "fee_rate": 0, "slippage_rate": 0},
                         rank_df=rank, vol_df=vol)
    vals = _position_values(pf).iloc[0]
    assert vals["A"] / vals["B"] == pytest.approx(3.0, rel=0.01)
    assert (vals.sum() / 10_000_000.0) == pytest.approx(1.0, abs=0.01)


def test_pure_rebalance_regime_cuts_exposure_and_labels_reason():
    idx, px, ents, exts, rank = _frames()
    exposure = np.array([1.0, 1.0, 1.0, 0.3, 0.3, 1.0])
    risk = _risk(market_regime={"index": "KOSPI", "ma_period": 200, "exposure_pct": 30})
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, risk,
                 {"execution_type": "same_close", "fee_rate": 0, "slippage_rate": 0},
                 rank_df=rank, exposure=exposure)
    invested = _position_values(pf).sum(axis=1) / pf.value()
    assert invested.iloc[2] == pytest.approx(1.0, abs=0.01)
    assert invested.iloc[3] == pytest.approx(0.3, abs=0.01)
    assert invested.iloc[5] == pytest.approx(1.0, abs=0.01)
    reason = sim.exit_reason_overrides["A"]["2024-01-04"]
    assert tr.decode(reason)[0]["t"] == tr.MARKET_REGIME_REDUCE


def test_signal_loop_regime_zero_goes_to_cash_then_reenters():
    idx, px, ents, exts, rank = _frames()
    exposure = np.array([1.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    risk = _risk(entry_signal_driven=True,
                 market_regime={"index": "KOSPI", "ma_period": 200, "exposure_pct": 0})
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, risk,
                 {"execution_type": "same_close", "fee_rate": 0, "slippage_rate": 0},
                 rank_df=rank, exposure=exposure)
    invested = _position_values(pf).sum(axis=1) / pf.value()
    assert invested.iloc[0] == pytest.approx(1.0, abs=0.01)
    assert invested.iloc[1] == pytest.approx(0.0, abs=1e-9)
    assert invested.iloc[2] == pytest.approx(0.0, abs=1e-9)
    assert invested.iloc[3] == pytest.approx(1.0, abs=0.01)
    assert tr.decode(sim.exit_reason_overrides["A"]["2024-01-02"])[0]["t"] == tr.MARKET_REGIME_REDUCE


@pytest.mark.parametrize("extra", [{}, {"entry_signal_driven": True}, {"stop_loss_pct": 50}])
def test_no_vol_no_exposure_is_bit_identical(extra):
    idx, px, ents, exts, rank = _frames(n=40, syms=("A", "B", "C"))
    rng = np.random.default_rng(3)
    px = px * np.cumprod(1 + rng.normal(0, 0.02, size=px.shape), axis=0)
    opts = {"execution_type": "same_close"}
    base = Simulator().run(px, px, ents, exts, _risk(**extra), opts, rank_df=rank)
    again = Simulator().run(px, px, ents, exts, _risk(**extra), opts, rank_df=rank,
                            vol_df=None, exposure=None)
    pd.testing.assert_series_equal(base.value(), again.value())


# ─── 엔진: 시장 국면 노출 배열 ────────────────────────────────────────────────

def test_market_regime_exposure_uses_index_ma_and_delay(tmp_path):
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    (tmp_path / "index").mkdir()
    dates = pd.date_range("2024-01-01", periods=8, freq="D")
    close = [100, 100, 100, 100, 50, 50, 200, 200]
    pd.DataFrame({"date": dates, "open": close, "high": close, "low": close,
                  "close": close, "volume": 1.0, "source": "t"}).to_parquet(
        tmp_path / "index" / "KOSPI.parquet")
    eng = BacktestEngine(data_dir=str(ohlcv))
    regime = {"index": "KOSPI", "ma_period": 3, "exposure_pct": 30}
    same = eng._market_regime_exposure(regime, dates, 0, 0)
    # 3일 이동평균: d4=(100,100,50)→83.3>50 아래, d5 아래, d6=(50,50,200)=100<200 위
    assert list(same) == [1.0, 1.0, 1.0, 1.0, 0.3, 0.3, 1.0, 1.0]
    delayed = eng._market_regime_exposure(regime, dates, 0, 1)
    assert list(delayed) == [1.0, 1.0, 1.0, 1.0, 1.0, 0.3, 0.3, 1.0]


def _write_vol_spike_index(tmp_path, n_calm=300, n_wild=25):
    """잔잔한 구간(±0.1% 교대) 뒤에 출렁이는 구간(±3% 교대)이 오는 지수 — 이동평균은 계속 위."""
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    (tmp_path / "index").mkdir()
    n = n_calm + n_wild
    dates = pd.bdate_range("2022-01-03", periods=n)
    rets = np.where(np.arange(n) % 2 == 0, 1.0, -1.0) * np.where(np.arange(n) < n_calm, 0.001, 0.03)
    close = 1000.0 * np.cumprod(1.0 + rets + 0.002)      # 완만한 상승 추세(이동평균 위 유지)
    pd.DataFrame({"date": dates, "open": close, "high": close, "low": close,
                  "close": close, "volume": 1.0, "source": "t"}).to_parquet(
        tmp_path / "index" / "KOSPI.parquet")
    return BacktestEngine(data_dir=str(ohlcv)), dates, n_calm


def test_market_regime_volatility_spike_alone(tmp_path):
    """v16.16 — 지수 20일 변동성이 직전 1년 평균의 2배 이상인 날만 노출을 줄인다."""
    eng, dates, n_calm = _write_vol_spike_index(tmp_path)
    regime = {"index": "KOSPI", "triggers": ["volatility_spike"],
              "volatility_multiple": 2.0, "exposure_pct": 50}
    exp = eng._market_regime_exposure(regime, dates, 0, 0)
    assert (exp[:n_calm] == 1.0).all()          # 잔잔한 구간(기준선 미정의 초기 구간 포함)은 전액 투자
    assert (exp[n_calm + 5:] == 0.5).all()      # 출렁이는 구간은 축소
    # 이동평균 판정은 쓰지 않았다 — 같은 지수에 이동평균만 걸면 축소일이 없다.
    ma_only = eng._market_regime_exposure(
        {"index": "KOSPI", "ma_period": 200, "exposure_pct": 50}, dates, 0, 0)
    assert (ma_only == 1.0).all()


def test_market_regime_volatility_spike_or_below_ma(tmp_path):
    """둘을 함께 쓰면 OR — 이동평균 위여도 변동성 급등일은 축소된다."""
    eng, dates, n_calm = _write_vol_spike_index(tmp_path)
    regime = {"index": "KOSPI", "triggers": ["below_ma", "volatility_spike"], "ma_period": 200,
              "volatility_multiple": 2.0, "volatility_period": 20, "exposure_pct": 30}
    exp = eng._market_regime_exposure(regime, dates, 0, 0)
    assert (exp[:n_calm] == 1.0).all() and (exp[n_calm + 5:] == 0.3).all()


def test_market_regime_volatility_spike_requires_multiple(tmp_path):
    eng, dates, _ = _write_vol_spike_index(tmp_path)
    with pytest.raises(ValueError):
        eng._market_regime_exposure(
            {"index": "KOSPI", "triggers": ["volatility_spike"], "exposure_pct": 50}, dates, 0, 0)


def test_regime_reason_template_follows_triggers():
    from engine.simulator import _regime_label
    assert _regime_label({"index": "KOSPI", "ma_period": 200, "exposure_pct": 30}) == (
        tr.MARKET_REGIME_REDUCE, "KOSPI", 200, "30")
    assert _regime_label({"index": "KOSPI", "triggers": ["volatility_spike"],
                          "volatility_multiple": 2.5, "exposure_pct": 0}) == (
        tr.MARKET_REGIME_REDUCE_VOL, "KOSPI", 20, "2.5", "0")
    assert _regime_label({"index": "KOSDAQ", "triggers": ["below_ma", "volatility_spike"],
                          "ma_period": 120, "volatility_period": 60, "volatility_multiple": 2,
                          "exposure_pct": 50}) == (
        tr.MARKET_REGIME_REDUCE_ANY, "KOSDAQ", 120, 60, "2", "50")
