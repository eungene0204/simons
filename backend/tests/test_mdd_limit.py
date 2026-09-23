"""포트폴리오 최대 낙폭 한도(max_mdd_limit_pct, 엔진 v16.24) 회귀.

배경(2026-09-23): 한도는 스키마·프롬프트·컴파일러·변경 로그·요약 카드까지 전부 있었지만
시뮬레이터가 읽지 않았다 — 사용자가 "누적 손실 8%면 노출 축소"라고 쓰면 반영된 것처럼 보이고
실행엔 효과가 없었다(죽은 코드).

계약: 자산이 고점 대비 한도 이상 내려간 첫날 t → t+지연(익일 시가=1, 당일 종가=0)에 전량
현금화(사유 '포트폴리오 최대 낙폭 한도 도달') → 다음 리밸런싱일(정기 리밸런싱이 없으면 다음
거래일)부터 전략 규칙대로 재편입, 고점은 재편입 시점 자산에서 다시 잡는다. 한도가 없거나
닿지 않으면 결과 비트 동일.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import trade_reason as tr
from engine.simulator import Simulator

_OPTS = {"execution_type": "same_close", "fee_rate": 0, "slippage_rate": 0, "sell_tax_rate": 0}
_CASH = 10_000_000.0


def _frames(closes, syms=("A", "B")):
    """closes: 종목 공통 종가 경로(길이 n). 매일 진입 후보, 매도 신호 없음, 랭킹 A>B."""
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    px = pd.DataFrame({s: list(map(float, closes)) for s in syms}, index=idx)
    ents = pd.DataFrame(True, index=idx, columns=list(syms))
    exts = pd.DataFrame(False, index=idx, columns=list(syms))
    rank = pd.DataFrame({s: float(len(syms) - k) for k, s in enumerate(syms)}, index=idx)
    return idx, px, ents, exts, rank


def _risk(**extra):
    base = {"max_positions": 2, "init_cash": _CASH, "allocation_type": "equal"}
    base.update(extra)
    return base


def _first_rows_of_month(idx):
    return np.where(pd.Series(idx).dt.to_period("M").ne(pd.Series(idx).dt.to_period("M").shift(1)))[0]


# 1월(23영업일) 동안 100→70으로 내려가고 2월부터 반등하는 경로.
_PATH = [100] * 3 + [90, 80, 70] + [70] * 17 + [72, 74, 76, 78, 80] + [80] * 15


@pytest.mark.parametrize("rp", [{"rebalancing_period": "monthly"},
                                {"rebalancing_period": "monthly", "entry_signal_driven": True},
                                {"rebalancing_period": "monthly", "stop_loss_pct": 90}])
def test_limit_liquidates_and_reenters_at_next_rebalance(rp):
    """한도 20%: 낙폭 -20%(80)에 닿은 날 종가에 전량 현금화 → 2월 첫 거래일 재편입.

    순수 리밸런싱 경로·조건 루프(매수 조건 전략·손절 동반) 모두 같은 계약."""
    idx, px, ents, exts, rank = _frames(_PATH)
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, _risk(max_mdd_limit_pct=20, **rp), _OPTS, rank_df=rank)
    nav = pf.value()
    liq = 4                                   # 종가 80 = 고점 100 대비 -20% (같은 날 종가 체결)
    reentry = int(_first_rows_of_month(idx)[1])
    assert pf.cash().iloc[liq] == pytest.approx(nav.iloc[liq])            # 전량 현금
    assert (pf.cash().iloc[liq:reentry] > 0).all()
    assert pf.cash().iloc[reentry] < nav.iloc[reentry] * 0.05              # 재편입
    assert nav.iloc[liq + 1] == pytest.approx(nav.iloc[liq])               # 현금 구간 자산 불변(70으로 더 빠져도)
    assert sim.mdd_events == [(idx[liq].strftime("%Y-%m-%d"), idx[reentry].strftime("%Y-%m-%d"))]
    reasons = {r for by_date in sim.exit_reason_overrides.values() for r in by_date.values()}
    assert tr.encode([tr.part(tr.MDD_LIMIT_LIQUIDATION, "20")]) in reasons


def test_next_open_liquidates_the_day_after_the_breach():
    idx, px, ents, exts, rank = _frames(_PATH)
    opts = dict(_OPTS, execution_type="next_open")
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, _risk(max_mdd_limit_pct=20, rebalancing_period="monthly"),
                 opts, rank_df=rank)
    assert sim.mdd_events[0][0] == idx[5].strftime("%Y-%m-%d")
    assert pf.cash().iloc[5] == pytest.approx(pf.value().iloc[5])


def test_no_rebalancing_reenters_next_trading_day_and_resets_peak():
    """정기 리밸런싱 없음: 현금화 다음 거래일부터 진입 규칙(매일 후보)으로 재편입, 고점은 재편입
    자산에서 다시 잡아 옛 고점 기준으로 영구 현금이 되지 않는다."""
    path = [100, 100, 80, 80, 80, 80, 64, 64, 64]      # 두 번째 -20%는 재편입 뒤 새 고점(80) 기준
    idx, px, ents, exts, rank = _frames(path)
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, _risk(max_mdd_limit_pct=20, entry_signal_driven=True),
                 _OPTS, rank_df=rank)
    assert [e[0] for e in sim.mdd_events] == [idx[2].strftime("%Y-%m-%d"), idx[6].strftime("%Y-%m-%d")]
    assert sim.mdd_events[0][1] == idx[3].strftime("%Y-%m-%d")
    assert pf.cash().iloc[3] < pf.value().iloc[3] * 0.05                   # 다음 거래일 재편입


@pytest.mark.parametrize("limit", [None, 50])
def test_absent_or_untouched_limit_is_bit_identical(limit):
    idx, px, ents, exts, rank = _frames(_PATH)
    base = Simulator().run(px, px, ents, exts, _risk(rebalancing_period="monthly"), _OPTS, rank_df=rank)
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, _risk(rebalancing_period="monthly", max_mdd_limit_pct=limit),
                 _OPTS, rank_df=rank)
    assert np.array_equal(pf.value().values, base.value().values)
    assert sim.mdd_events == ([] if limit else None)


def test_limit_stacks_on_market_regime_exposure():
    """시장 국면 노출(50%)과 함께: 낙폭 한도가 닿은 구간만 0, 재편입 뒤엔 국면 노출로 복귀."""
    idx, px, ents, exts, rank = _frames(_PATH)
    exposure = np.full(len(idx), 0.5)
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, _risk(max_mdd_limit_pct=10, rebalancing_period="monthly"),
                 _OPTS, rank_df=rank, exposure=exposure)
    reentry = int(_first_rows_of_month(idx)[1])
    assert sim.mdd_events and sim.mdd_events[0][1] == idx[reentry].strftime("%Y-%m-%d")
    invested = 1 - pf.cash().iloc[reentry] / pf.value().iloc[reentry]
    assert invested == pytest.approx(0.5, abs=0.02)
