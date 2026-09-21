"""KR 요청(표시 언어 ko)의 시장 격리 — 미국 시장 대상 요청 거절.

2026-09-21 지시·실측: "매월 첫 거래일마다 S&P500 ETF를 100만 원씩 매수합니다…"가 KR
레인에서 markets=["ETF"](한국 ETF) + symbols=["S&P500 ETF"](미해석)로 조립돼, 미국 요청이
조용히 **국내 ETF 전략**으로 바뀌어 나갔다. /us의 거울 계약(test_us_region_isolation)을
KR 방향에도 세운다.

판정 근거 셋 — ①② 결정론, ③만 LLM(원문은 읽지 않는다):
  ① 시장 enum ∩ US_MARKETS  ② registry가 미국 티커로 푼 지정 종목
  ③ registry가 못 푼 표현의 시장 판정(market_region_check) — 실패·모름은 거절하지 않음
"""

from __future__ import annotations

import pytest

import ui_language
from strategy_conversation.interpreter import market_region_check
from strategy_conversation.interpreter.models import (
    StrategyCondition,
    StrategySpec,
    StrategyIntent,
    UniverseSpec,
)
from strategy_conversation.primary import KR_ONLY_MARKET_REFUSAL, _kr_region_us_market_refusal


def _intent(**universe_kw) -> StrategyIntent:
    spec = StrategySpec(
        universe=UniverseSpec(**universe_kw),
        entry_conditions=[
            StrategyCondition(factor="fundamental.per", operator="<=", value=10.0)
        ],
    )
    return StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)


def _chat(payload: str):
    def chat(_system, _user, **_kw):
        return payload
    return chat


# ── ① 시장 enum ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("market", ["SP500", "NASDAQ100", "NASDAQ", "DOW30", "US", "US_ETF"])
def test_rejects_us_markets_on_kr_request(market):
    assert _kr_region_us_market_refusal(_intent(markets=[market])) == KR_ONLY_MARKET_REFUSAL


@pytest.mark.parametrize("market", ["KOSPI", "KOSDAQ", "KOSPI200", "KOSDAQ150", "ETF"])
def test_allows_kr_markets(market):
    assert _kr_region_us_market_refusal(_intent(markets=[market])) is None


def test_us_request_is_not_touched():
    """/us(en) 레인은 이 가드의 대상이 아니다 — 반대 방향 가드가 담당한다."""
    with ui_language.bind("en"):
        assert _kr_region_us_market_refusal(_intent(markets=["SP500"])) is None


# ── ② registry가 푼 지정 종목 ────────────────────────────────────────────────

def test_rejects_us_ticker_symbol():
    from strategy_conversation.registry.universe_resolver import resolve_symbols

    codes, _unresolved = resolve_symbols(["애플"])
    if not codes:
        pytest.skip("미국 registry/파케이 미러 없음")
    assert _kr_region_us_market_refusal(_intent(symbols=["애플"])) == KR_ONLY_MARKET_REFUSAL


def test_allows_kr_symbol():
    assert _kr_region_us_market_refusal(_intent(symbols=["삼성전자"])) is None


# ── ③ 미해석 표현의 시장 판정(LLM) ──────────────────────────────────────────

def test_rejects_unresolved_term_judged_us():
    """'S&P500 ETF'는 시장 enum에도 registry에도 없다 — 시장 판정이 미국이면 거절."""
    refusal = _kr_region_us_market_refusal(
        _intent(markets=["ETF"], symbols=["S&P500 ETF"]),
        _chat('{"items": [{"market": "US"}]}'),
    )
    assert refusal == KR_ONLY_MARKET_REFUSAL


def test_keeps_turn_when_term_judged_kr():
    """한국 상장 해외지수 ETF('TIGER 미국S&P500' 같은 표현)는 거절 대상이 아니다."""
    assert _kr_region_us_market_refusal(
        _intent(markets=["ETF"], symbols=["듣도보도못한ETF"]),
        _chat('{"items": [{"market": "KR"}]}'),
    ) is None


def test_no_verdict_does_not_reject():
    """판정 실패(fail-open)는 거절하지 않는다 — 보조 그물이 턴을 깨지 않는다."""
    assert _kr_region_us_market_refusal(
        _intent(symbols=["S&P500 ETF"]), _chat("not json"),
    ) is None


def test_no_chat_handle_does_not_reject():
    """주입 스텁(테스트·QA 하니스)은 chat 핸들이 없다 — 판정 없이 진행."""
    assert _kr_region_us_market_refusal(_intent(symbols=["S&P500 ETF"])) is None


def test_only_terms_limits_llm_check():
    """수정 레인: 이번 턴에 새로 들어온 표현만 묻는다(이월분은 자기 턴에서 판정됐다)."""
    calls = []

    def chat(_system, user, **_kw):
        calls.append(user)
        return '{"items": [{"market": "US"}]}'

    assert _kr_region_us_market_refusal(
        _intent(symbols=["S&P500 ETF"]), chat, only_terms=[],
    ) is None
    assert not calls


# ── market_region_check 자체 계약 ────────────────────────────────────────────

def test_check_markets_drops_unknown_and_out_of_enum():
    verdicts = market_region_check.check_markets(
        ["가", "나", "다"],
        _chat('{"items": [{"market": "US"}, {"market": "UNKNOWN"}, {"market": "일본"}]}'),
    )
    assert verdicts == {"가": "US"}


def test_check_markets_count_mismatch_is_no_verdict():
    assert market_region_check.check_markets(
        ["가", "나"], _chat('{"items": [{"market": "US"}]}'),
    ) is None


def test_check_markets_no_terms_is_no_call():
    def chat(*_a, **_kw):
        raise AssertionError("호출되면 안 된다")

    assert market_region_check.check_markets([], chat) == {}
