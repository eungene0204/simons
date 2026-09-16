"""종목 선정 범위(설계 스펙 § 6 `universe.selection_scope`) 계약.

`target_symbols`에는 성격이 다른 두 가지가 같은 모양으로 들어간다 — 사용자가 지목한
종목과 테마 조회가 채운 후보군. 구분하지 않으면 후보군을 지정으로 오인해 사용자가 말한
선정 기준이 조용히 사라진다.

핵심 계약:
  ① 테마 후보군 + 선정 기준(랭킹·보유 수·비율) → 고를 대상이다(사용자가 말한 값 유지)
  ② 테마 후보군 + 기준 없음 → 기존 동작 유지(전부 매수 — 임의 절단 금지)
  ③ 사용자 지목 종목 → 항상 전부 매수(선정 없음)

'보유 수를 말했는가'는 값으로 알 수 없다(기본값 10 물질화) — 컴파일러가 남긴 출처
표식 `max_positions_explicit`이 유일한 근거다.
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
    # 테마 유래여도 선정 기준이 없으면 고를 근거가 없다 — 지정으로 둔다.
    ({"target_symbols": _THEME_SYMBOLS, "theme_universe": "이차전지"},
     SelectionScope.EXPLICIT),
    # 보유 수가 값으로만 있으면(기본값 물질화와 구분 불가) 여전히 지정이다.
    ({"target_symbols": _THEME_SYMBOLS, "theme_universe": "이차전지",
      "max_positions": 5}, SelectionScope.EXPLICIT),
    ({"target_symbols": _THEME_SYMBOLS, "theme_universe": "이차전지",
      "ranking_metric": "return"}, SelectionScope.CANDIDATE_POOL),
    # 사용자가 보유 수를 **직접 말했으면** 랭킹이 없어도 고를 대상이다(2026-09-16).
    ({"target_symbols": _THEME_SYMBOLS, "theme_universe": "이차전지",
      "max_positions": 5, "max_positions_explicit": True},
     SelectionScope.CANDIDATE_POOL),
    # 비율 선정도 사용자가 말했을 때만 값이 선다 — 같은 기준이다.
    ({"target_symbols": _THEME_SYMBOLS, "theme_universe": "이차전지",
      "max_positions_pct": 10.0}, SelectionScope.CANDIDATE_POOL),
    # 사용자가 직접 지목한 종목은 기준이 있어도 후보군이 아니다(theme_universe 없음).
    ({"target_symbols": ["005930", "000660"], "ranking_metric": "return"},
     SelectionScope.EXPLICIT),
    ({"target_symbols": ["005930", "000660"], "max_positions": 5,
      "max_positions_explicit": True}, SelectionScope.EXPLICIT),
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


def test_theme_pool_keeps_a_position_count_the_user_actually_said():
    """[회귀] '전쟁 관련주 중 … 골든크로스 매수 … **최대 5종목**'(랭킹 미언급)이
    66종목 전부 균등 매수로 나가던 결함(2026-09-16 실측).

    컴파일된 전략에는 `max_positions=5`가 남아 있는데 변환기가
    `max_positions=len(target_symbols)`로 덮어, 사용자가 말한 값이 질문도 안내도 없이
    사라졌다. 보유 수는 기본값이 물질화되는 필드라 **출처 표식**으로만 구분된다."""
    risk = _risk(
        target_symbols=_THEME_SYMBOLS, theme_universe="전쟁",
        max_positions=5, max_positions_explicit=True,
    )
    assert risk["max_positions"] == 5                      # 사용자가 말한 5종목
    assert risk["position_size_pct"] == 20.0               # 36등분이 아니다
    assert risk["ranking_enabled"] is True                 # 유니버스 전략과 같은 선정 경로


def test_theme_pool_with_a_stated_percentage_selects_too():
    """비율 선정(FR-BT-060)도 사용자가 말했을 때만 값이 서므로 같은 기준이다."""
    risk = _risk(
        target_symbols=_THEME_SYMBOLS, theme_universe="전쟁", max_positions_pct=10.0)
    assert risk["max_positions_pct"] == 10.0
    assert risk["max_positions"] != len(_THEME_SYMBOLS)
    assert risk["ranking_enabled"] is True


def test_compiler_records_whether_the_user_said_a_position_count():
    """출처 표식은 컴파일러만 채운다 — selection_count가 non-null일 때만 True.

    값만 보면 '10종목이라고 말했다'와 '아무 말 없었다'가 같아 보인다(기본값 물질화).
    그 구분을 만들어 두는 유일한 자리가 여기다."""
    from strategy_conversation.compiler.strategy_compiler import compile_strategy
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.pipeline import run_validation

    def _compiled(selection_count):
        intent = StrategyIntent.model_validate({
            "intent": "CREATE_STRATEGY",
            "strategy": {
                "universe": {"markets": ["KOSPI"]},
                "entry_conditions": [{"factor": "technical.rsi", "operator": "<=",
                                      "value": 30, "value_source": "USER_PROVIDED"}],
                "exit_conditions": [{"factor": "technical.rsi", "operator": ">=",
                                     "value": 70, "value_source": "USER_PROVIDED"}],
                "portfolio": {"selection_count": selection_count},
            },
        })
        validated, report = run_validation(intent)
        assert report.is_valid, report.errors
        return compile_strategy(validated, report, "RSI 30 이하 매수")

    assert _compiled(5).max_positions_explicit is True
    assert _compiled(5).max_positions == 5
    assert _compiled(None).max_positions_explicit is False
    assert _compiled(None).max_positions == 10             # 물질화 기본값
