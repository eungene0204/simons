"""종목 선정 범위(설계 스펙 § 6 `universe.selection_scope`) 계약.

`target_symbols`에는 성격이 다른 두 가지가 같은 모양으로 들어간다 — 사용자가 지목한
종목과 테마 조회가 채운 후보군. 구분하지 않으면 후보군을 지정으로 오인해 사용자가 말한
선정 기준이 조용히 사라진다.

핵심 계약:
  ① 테마 후보군 + 랭킹 → 고를 대상이다(랭킹 유지, 사용자가 말한 보유 수 유지)
  ② 테마 후보군 + 랭킹 없음 → 기존 동작 유지(전부 매수 — 임의 절단 금지)
  ③ 사용자 지목 종목 → 항상 전부 매수(선정 없음)
"""

from __future__ import annotations

import pytest

from engine.nl_parser import ParsedStrategy
from engine.selection_scope import SelectionScope, selection_scope
from engine.strategy_converter import to_backtest_request

_THEME_SYMBOLS = [f"{i:06d}" for i in range(36)]


def _risk(**kwargs) -> dict:
    return to_backtest_request(ParsedStrategy(description="테스트", **kwargs))["risk"]


# ── 범위 판정 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kwargs,expected", [
    ({}, SelectionScope.UNIVERSE),
    ({"universe": ["KOSPI"]}, SelectionScope.UNIVERSE),
    ({"target_symbols": ["005930"]}, SelectionScope.EXPLICIT),
    ({"target_symbols": ["005930", "000660"]}, SelectionScope.EXPLICIT),
    # 테마 유래여도 선정 기준(랭킹)이 없으면 고를 근거가 없다 — 지정으로 둔다.
    ({"target_symbols": _THEME_SYMBOLS, "theme_universe": "이차전지"},
     SelectionScope.EXPLICIT),
    ({"target_symbols": _THEME_SYMBOLS, "theme_universe": "이차전지",
      "ranking_metric": "return"}, SelectionScope.CANDIDATE_POOL),
    # 사용자가 직접 지목한 종목은 랭킹이 있어도 후보군이 아니다(theme_universe 없음).
    ({"target_symbols": ["005930", "000660"], "ranking_metric": "return"},
     SelectionScope.EXPLICIT),
])
def test_scope_judgment(kwargs, expected):
    assert selection_scope(ParsedStrategy(description="t", **kwargs)) is expected


# ── 실측 사고 재현 ───────────────────────────────────────────────────────────

def test_theme_pool_with_ranking_keeps_what_the_user_asked_for():
    """[회귀] '이차전지 관련주 중 최근 60일 수익률 상위 10종목'이 랭킹 없이
    36종목 전부 매수로 나가던 버그 — 사용자가 말한 두 가지가 동시에 증발했다."""
    risk = _risk(
        target_symbols=_THEME_SYMBOLS, theme_universe="이차전지",
        ranking_metric="return", ranking_lookback_days=60, max_positions=10,
    )
    assert risk["ranking_enabled"] is True       # 랭킹이 살아 있다
    assert risk["max_positions"] == 10           # 사용자가 말한 10종목
    assert risk["position_size_pct"] == 10.0     # 36등분이 아니다


def test_theme_pool_without_ranking_is_unchanged():
    """선정 기준이 없으면 기존 동작 그대로 — 테마 유니버스를 임의로 자르지 않는다
    (2026-07-28 '비만치료 관련주' 절단 사고의 결정 유지)."""
    risk = _risk(
        target_symbols=_THEME_SYMBOLS, theme_universe="이차전지", max_positions=10)
    assert risk["ranking_enabled"] is False
    assert risk["max_positions"] == 36
    assert risk["position_size_pct"] == pytest.approx(2.78)


@pytest.mark.parametrize("symbols,size", [(["005930"], 100.0), (["005930", "000660"], 50.0)])
def test_user_named_symbols_are_always_bought_in_full(symbols, size):
    """사용자가 지목한 종목은 고를 대상이 아니다 — 선정도 보유 수 상한도 없다."""
    risk = _risk(target_symbols=symbols, max_positions=10)
    assert risk["ranking_enabled"] is False
    assert risk["max_positions"] == len(symbols)
    assert risk["position_size_pct"] == size


def test_universe_strategy_is_unaffected():
    risk = _risk(universe=["KOSPI"], max_positions=10)
    assert risk["ranking_enabled"] is True
    assert risk["max_positions"] == 10
