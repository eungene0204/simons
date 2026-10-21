"""KR 요청(표시 언어 ko)의 시장 격리 — 미국 시장 요청 거절 + 국내 ETF 상품 표현 복구.

2026-09-21 지시: KR 버전에서 미국 시장 전략을 요청하면 "한국 주식시장만 지원"으로 답한다
(/us의 거울 계약 — test_us_region_isolation).

같은 날 사용자 정정: "S&P500 ETF"는 미국 요청이 아니라 **국내 상장 상품**을 말한다(명부에
'S&P500' 52개·'나스닥' 33개). 첫 구현은 그 표현을 미국 상품으로 거절했다. 정작 원래 결함은
따로 있었다 — 120B 인터프리터가 그 표현을 etf_theme에 옮기지 않아(symbols로 보내거나·
흘리거나·US_ETF로 보냄) 국내 ETF 1,384개 전체가 대상이 됐다. planner-first가 뽑은 표현으로
빈 칸을 채운다(_recover_kr_etf_product).

거절 근거 셋 — ①② 결정론, ③만 LLM(원문은 읽지 않는다):
  ① 시장 enum ∩ US_MARKETS  ② registry가 미국 티커로 푼 지정 종목
  ③ registry가 못 푼 **종목** 표현의 시장 판정(market_region_check) — ETF 상품 표현 제외,
     실패·모름은 거절하지 않음
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
from strategy_conversation.primary import (
    KR_ONLY_MARKET_REFUSAL,
    _kr_region_us_market_refusal,
    _recover_kr_etf_product,
    _recover_kr_theme_group,
)


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
    """registry가 못 푼 종목 표현 — 시장 판정이 미국이면 거절."""
    refusal = _kr_region_us_market_refusal(
        _intent(symbols=["가나다라홀딩스인크"]), _chat('{"items": [{"market": "US"}]}'),
    )
    assert refusal == KR_ONLY_MARKET_REFUSAL


def test_keeps_turn_when_term_judged_kr():
    assert _kr_region_us_market_refusal(
        _intent(symbols=["가나다라홀딩스"]), _chat('{"items": [{"market": "KR"}]}'),
    ) is None


def test_etf_expression_is_never_sent_to_region_check():
    """사용자 정정: "S&P500 ETF"는 국내 상장 상품이다 — 미국 상품으로 묻지도 거절하지도 않는다."""
    def chat(*_a, **_kw):
        raise AssertionError("ETF 상품 표현은 시장 판정 대상이 아니다")

    assert _kr_region_us_market_refusal(
        _intent(markets=["ETF"], symbols=["S&P500 ETF"]), chat) is None


def test_no_verdict_does_not_reject():
    """판정 실패(fail-open)는 거절하지 않는다 — 보조 그물이 턴을 깨지 않는다."""
    assert _kr_region_us_market_refusal(
        _intent(symbols=["가나다라홀딩스인크"]), _chat("not json"),
    ) is None


def test_no_chat_handle_does_not_reject():
    """주입 스텁(테스트·QA 하니스)은 chat 핸들이 없다 — 판정 없이 진행."""
    assert _kr_region_us_market_refusal(_intent(symbols=["가나다라홀딩스인크"])) is None


def test_only_terms_limits_llm_check():
    """수정 레인: 이번 턴에 새로 들어온 표현만 묻는다(이월분은 자기 턴에서 판정됐다)."""
    calls = []

    def chat(_system, user, **_kw):
        calls.append(user)
        return '{"items": [{"market": "US"}]}'

    assert _kr_region_us_market_refusal(
        _intent(symbols=["가나다라홀딩스인크"]), chat, only_terms=[],
    ) is None
    assert not calls


# ── planner 관찰값 — 인터프리터가 표현을 흘린 턴 ─────────────────────────────

class _Node:
    type = "tool"

    def __init__(self, text):
        self.args = {"text": text}


class _Entry:
    def __init__(self, text, observation):
        self.node = _Node(text)
        self.observation = observation


class _Planner:
    def __init__(self, *pairs):
        self.executed = {i: _Entry(t, o) for i, (t, o) in enumerate(pairs)}
        self.auto_steps = []


_SP500 = ("S&P500 ETF", {"universe_type": "ETF", "canonical": None})


@pytest.mark.parametrize("universe_kw", [
    {"markets": ["ETF"], "symbols": ["S&P500 ETF"]},   # 지정 종목 칸에 잘못 적음
    {"markets": ["ETF"]},                               # 표현을 통째로 흘림(사용자 스크린샷 턴)
    {"markets": ["US_ETF"]},                            # 미국 ETF로 보냄
    {},                                                 # 시장도 비움
])
def test_recovers_kr_etf_product_from_planner_term(universe_kw):
    """120B가 같은 문장에 낸 형태들 — 어느 쪽이든 국내 ETF 상품 키워드로 착지한다."""
    intent = _intent(**universe_kw)
    assert _recover_kr_etf_product(intent, _Planner(_SP500)) == "S&P500"
    universe = intent.strategy.universe
    assert (universe.markets, universe.etf_theme, universe.symbols) == (["ETF"], "S&P500", [])
    assert _kr_region_us_market_refusal(intent, planner_result=_Planner(_SP500)) is None


def test_recovers_nasdaq_etf():
    intent = _intent(markets=["ETF"])
    planner = _Planner(("나스닥 ETF", {"universe_type": "ETF", "canonical": None}))
    assert _recover_kr_etf_product(intent, planner) == "나스닥"


def test_recovery_keeps_interpreter_etf_theme():
    intent = _intent(markets=["ETF"], etf_theme="미국S&P500")
    assert _recover_kr_etf_product(intent, _Planner(_SP500)) is None
    assert intent.strategy.universe.etf_theme == "미국S&P500"


def test_recovery_fixes_market_token_when_interpreter_wrote_the_theme():
    """네 번째 실측 형태: markets=["US_ETF"] + etf_theme="S&P500" — 키워드는 맞는데 시장
    토큰만 미국이라 지역 가드가 거절했다(planner 없이도 성립)."""
    intent = _intent(markets=["US_ETF"], etf_theme="S&P500")
    assert _recover_kr_etf_product(intent, None) == "S&P500"
    assert intent.strategy.universe.markets == ["ETF"]
    assert _kr_region_us_market_refusal(intent) is None


def test_recovery_strips_marker_from_interpreter_theme():
    intent = _intent(markets=["ETF"], etf_theme="S&P500 ETF")
    assert _recover_kr_etf_product(intent, None) == "S&P500"
    assert intent.strategy.universe.etf_theme == "S&P500"


def test_recovery_needs_a_master_match():
    """국내 명부에 걸리지 않는 표현은 키워드를 지어내지 않는다."""
    intent = _intent(markets=["US_ETF"])
    planner = _Planner(("ZZQX ETF", {"universe_type": "ETF", "canonical": None}))
    assert _recover_kr_etf_product(intent, planner) is None
    assert intent.strategy.universe.markets == ["US_ETF"]


def test_recovery_does_not_pick_between_two_products():
    intent = _intent(markets=["ETF"])
    planner = _Planner(_SP500, ("나스닥 ETF", {"universe_type": "ETF", "canonical": None}))
    assert _recover_kr_etf_product(intent, planner) is None


def test_recovery_leaves_kr_stock_market_turn_alone():
    intent = _intent(markets=["KOSPI"])
    assert _recover_kr_etf_product(intent, _Planner(_SP500)) is None


def test_recovery_is_kr_lane_only():
    intent = _intent(markets=["US_ETF"])
    with ui_language.bind("en"):
        assert _recover_kr_etf_product(intent, _Planner(_SP500)) is None


def test_planner_us_market_observation_rejects_without_llm():
    planner = _Planner(("나스닥", {"universe_type": "MARKET", "canonical": "NASDAQ"}))
    assert _kr_region_us_market_refusal(
        _intent(), planner_result=planner) == KR_ONLY_MARKET_REFUSAL


def test_planner_us_ticker_observation_rejects_without_llm():
    planner = _Planner(("애플", {"universe_type": "SINGLE_STOCK", "canonical": "AAPL"}))
    assert _kr_region_us_market_refusal(
        _intent(), planner_result=planner) == KR_ONLY_MARKET_REFUSAL


def test_planner_kr_observations_are_kept():
    def chat(*_a, **_kw):
        raise AssertionError("정본이 풀린 표현은 LLM에 묻지 않는다")

    planner = _Planner(
        ("코스피200", {"universe_type": "MARKET", "canonical": "KOSPI200"}),
        ("삼성전자", {"universe_type": "SINGLE_STOCK", "canonical": "005930"}),
        ("반도체", {"universe_type": "SECTOR", "canonical": "반도체"}),
    )
    assert _kr_region_us_market_refusal(_intent(), chat, planner_result=planner) is None


# ── '미국' 명시 없는 관련주 → 국내 테마(2026-10-21) ─────────────────────────

_SPACEX_THEME = ("스페이스x 관련주", {"found": True, "term": "스페이스X",
                                    "companies": [{"symbol": "295310"}]})
_USER = "스페이스x 관련주 전략을 만들어줘"
_NOT_SPECIFIED = _chat('{"verdict": "NOT_SPECIFIED"}')


def test_recovers_kr_theme_group_from_planner_term():
    """실측: 인터프리터 markets=["US"]+sectors=["스페이스x"] → "한국 주식시장만 지원" 거절.
    planner는 '스페이스x 관련주'로 국내 테마 상장사를 찾았다 — 미국 토큰을 걷는다."""
    intent = _intent(markets=["US"], sectors=["스페이스x"])
    planner = _Planner(_SPACEX_THEME)
    assert _recover_kr_theme_group(intent, planner, _USER, _NOT_SPECIFIED) == "스페이스x 관련주"
    assert intent.strategy.universe.markets == []
    assert intent.strategy.universe.sectors == ["스페이스x"]
    assert _kr_region_us_market_refusal(intent, planner_result=planner) is None


@pytest.mark.parametrize("chat", [
    _chat('{"verdict": "US_EXPLICIT"}'),   # 사용자가 미국을 말함
    _chat("not json"),                     # 판정 실패 — 조용히 바꾸지 않는다
    None,                                  # 판정 핸들 없음
])
def test_theme_group_recovery_needs_unspecified_market_verdict(chat):
    intent = _intent(markets=["US"])
    assert _recover_kr_theme_group(intent, _Planner(_SPACEX_THEME), _USER, chat) is None
    assert intent.strategy.universe.markets == ["US"]


def test_theme_group_recovery_needs_group_suffix():
    """접미 없는 회사명('스페이스X')은 미국 종목 요청이다(2026-10-02 결정) — 거절 유지."""
    intent = _intent(markets=["US"])
    planner = _Planner(("스페이스X", {"found": True, "companies": [{"symbol": "295310"}]}))
    assert _recover_kr_theme_group(intent, planner, _USER, _NOT_SPECIFIED) is None
    assert intent.strategy.universe.markets == ["US"]


def test_theme_group_recovery_needs_domestic_companies():
    intent = _intent(markets=["US"])
    planner = _Planner(("가나다 관련주", {"found": False, "companies": []}))
    assert _recover_kr_theme_group(intent, planner, _USER, _NOT_SPECIFIED) is None
    assert _kr_region_us_market_refusal(intent, planner_result=planner) == KR_ONLY_MARKET_REFUSAL


@pytest.mark.parametrize("term", ["미국 AI 관련주", "US AI 관련주"])
def test_theme_group_recovery_keeps_explicit_us_prefix(term):
    """회귀(2026-10-21 검토): '미국 AI 관련주'는 미국을 명시한 요청이다 — 판정을 부르지 않고
    거절을 유지한다(판정이 틀려 NOT_SPECIFIED를 내도 바꾸지 않는다)."""
    def chat(*_a, **_kw):
        raise AssertionError("시장 접두가 있는 표현은 판정을 부르지 않는다")

    intent = _intent(markets=["US"])
    planner = _Planner((term, {"found": True, "companies": [{"symbol": "295310"}]}))
    assert _recover_kr_theme_group(intent, planner, f"{term} 전략", chat) is None
    assert intent.strategy.universe.markets == ["US"]
    assert _kr_region_us_market_refusal(intent, planner_result=planner) == KR_ONLY_MARKET_REFUSAL


def test_theme_group_recovery_leaves_kr_market_and_en_lane_alone():
    intent = _intent(markets=["KOSPI"])
    assert _recover_kr_theme_group(intent, _Planner(_SPACEX_THEME), _USER, _NOT_SPECIFIED) is None
    intent = _intent(markets=["US"])
    with ui_language.bind("en"):
        assert _recover_kr_theme_group(
            intent, _Planner(_SPACEX_THEME), _USER, _NOT_SPECIFIED) is None
    assert intent.strategy.universe.markets == ["US"]


# ── us_market_explicit_check 자체 계약 ───────────────────────────────────────

def test_us_market_explicit_check_enum_and_failure():
    from strategy_conversation.interpreter.us_market_explicit_check import (
        check_us_market_explicit,
    )

    assert check_us_market_explicit(_USER, "스페이스x 관련주", _NOT_SPECIFIED) == "NOT_SPECIFIED"
    assert check_us_market_explicit(_USER, "x", _chat('{"verdict": "US_EXPLICIT"}')) == "US_EXPLICIT"
    assert check_us_market_explicit(_USER, "x", _chat('{"verdict": "KR"}')) is None
    assert check_us_market_explicit(_USER, "x", _chat("oops")) is None


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
