"""/us 요청(표시 언어 en)의 시장 격리 — KR 종목 접근 차단 + US 기본값·테마 전개.

2026-08-26 사고: /us에서 EN "AI-Related Stock Investment Strategy"가 시장 미언급
기본값(KOSPI200)과 KR KG 테마 전개를 타고 한국 66종목 유니버스로 조립됐다.
지역(요청 언어) 격리 계약:
- 시장 미언급 → 컴파일 기본값 S&P500 (KR 기본 KOSPI200과 같은 눈높이)
- 한국 시장 명시 → 거절 안내(조용한 제거 금지)
- 지정 종목 해석 → 미국 registry만(한국 이름·6자리 코드는 unresolved 보고)
- 테마어 → US 카탈로그·KG만(KR KG·검색 그라운딩 금지)
"""

from __future__ import annotations

import ui_language
from strategy_conversation.compiler.strategy_compiler import compile_strategy
from strategy_conversation.interpreter.models import (
    StrategyCondition,
    StrategyIntent,
    StrategySpec,
    UniverseSpec,
    ValidationReport,
)
from strategy_conversation.registry.universe_resolver import resolve_symbols
from strategy_conversation.validation.capability_validator import validate_capability


def _ready() -> ValidationReport:
    return ValidationReport(is_valid=True, status="READY")


def _intent(markets, **universe_kw) -> StrategyIntent:
    spec = StrategySpec(
        universe=UniverseSpec(markets=markets, **universe_kw),
        entry_conditions=[
            StrategyCondition(factor="fundamental.per", operator="<=", value=10.0)
        ],
    )
    return StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)


# ── 컴파일 기본값 ────────────────────────────────────────────────────────────

def test_compile_defaults_to_sp500_on_us_request():
    with ui_language.bind("en"):
        parsed = compile_strategy(_intent([]), _ready(), "buy low PER stocks")
    assert parsed.universe == ["SP500"]


def test_compile_keeps_kr_default_on_kr_request():
    parsed = compile_strategy(_intent([]), _ready(), "저PER 종목 매수")
    assert parsed.universe == ["KOSPI200"]


def test_compile_respects_explicit_us_market_choice():
    with ui_language.bind("en"):
        parsed = compile_strategy(_intent(["NASDAQ100"]), _ready(), "nasdaq strategy")
    assert parsed.universe == ["NASDAQ100"]


# ── 검증기: 한국 시장 명시 거절 + 미언급 US 문맥 ─────────────────────────────

def test_validator_rejects_kr_markets_on_us_request():
    intent = _intent(["KOSPI"])
    with ui_language.bind("en"):
        errors, _w, _u, _f = validate_capability(intent)
    assert any("US markets only" in e for e in errors)


def test_validator_allows_kr_markets_on_kr_request():
    intent = _intent(["KOSPI"])
    errors, _w, _u, _f = validate_capability(intent)
    assert not any("US markets only" in e or "미국 시장 전용" in e for e in errors)


def test_validator_expands_us_theme_without_market_mention():
    # 시장 미언급 + 테마어 → US 카탈로그 전개(KR KG 아님). 앵커 'AI'도 하위 테마
    # 합집합으로 선다 — 한국 6자리 코드가 하나도 섞이지 않아야 한다.
    intent = _intent([], sectors=["AI"])
    with ui_language.bind("en"):
        validate_capability(intent)
    symbols = intent.strategy.universe.symbols
    assert symbols and all(not s[:1].isdigit() for s in symbols)
    assert "NVDA" in symbols
    assert intent.strategy.universe.sectors == []


# ── 지정 종목 해석: 미국 registry만 ─────────────────────────────────────────

def test_resolve_symbols_blocks_kr_stocks_on_us_request():
    with ui_language.bind("en"):
        codes, unresolved = resolve_symbols(["삼성전자", "005930", "AAPL", "애플"])
    assert codes == ["AAPL"]
    assert set(unresolved) == {"삼성전자", "005930"}


def test_resolve_symbols_kr_request_unchanged():
    codes, unresolved = resolve_symbols(["삼성전자", "AAPL"])
    assert codes == ["005930", "AAPL"]
    assert unresolved == []


# ── create 레인: 한국 시장 명시 거절(컴파일 전 인터셉트) ────────────────────

def test_primary_refuses_kr_market_before_compile_on_us_request():
    from strategy_conversation.primary import _us_region_kr_market_refusal

    intent = _intent(["KOSPI200"])
    with ui_language.bind("en"):
        msg = _us_region_kr_market_refusal(intent)
    assert msg is not None and "US markets only" in msg
    # ko 요청·미국 시장 지정은 거절하지 않는다
    assert _us_region_kr_market_refusal(intent) is None
    with ui_language.bind("en"):
        assert _us_region_kr_market_refusal(_intent(["SP500"])) is None
        assert _us_region_kr_market_refusal(_intent([])) is None


# ── 표시명: /us는 영문 정식명 ────────────────────────────────────────────────

def test_us_display_name_follows_request_language():
    from engine.universe_pit import us_display_name

    assert us_display_name("NVDA") == "엔비디아"  # KR 기본: 한글명 우선
    with ui_language.bind("en"):
        assert us_display_name("NVDA") == "Nvidia"
        assert us_display_name("SMCI") == "Supermicro"


# ── 초기 자본 통화 — 미국 전략은 달러 체계 ──────────────────────────────────

def test_initial_capital_chips_follow_strategy_market():
    from engine.nl_parser import ParsedStrategy
    from engine.strategy_slots import CAPITAL_CHIP_VALUES, suggestions_for_topic

    kr = suggestions_for_topic("초기 자본", parsed=ParsedStrategy(description="t"))
    us = suggestions_for_topic(
        "초기 자본", parsed=ParsedStrategy(description="t", universe=["SP500"])
    )
    assert kr == ["500만원", "1,000만원", "3,000만원", "5,000만원"]
    assert us == ["$10,000", "$30,000", "$50,000", "$100,000"]
    # 달러 칩은 전부 정본 표로 결속된다(원화 보정 파서가 못 읽는 표기 — 칩=값 계약)
    assert all(chip in CAPITAL_CHIP_VALUES for chip in us)
    assert CAPITAL_CHIP_VALUES["$10,000"] == 10_000.0


def test_initial_capital_bounds_follow_strategy_market():
    from engine.nl_parser import ParsedStrategy, enforce_initial_capital_bounds

    us = ParsedStrategy(description="t", universe=["SP500"], initial_capital=500)
    notice = enforce_initial_capital_bounds(us)
    assert us.initial_capital == 1_000.0 and "$1,000" in notice
    us.initial_capital = 20_000_000
    notice = enforce_initial_capital_bounds(us)
    assert us.initial_capital == 10_000.0 and "$10,000,000" in notice
    # KR 체계는 불변
    kr = ParsedStrategy(description="t", initial_capital=500)
    enforce_initial_capital_bounds(kr)
    assert kr.initial_capital == 1_000_000.0


def test_compile_us_default_capital_is_usd():
    with ui_language.bind("en"):
        parsed = compile_strategy(_intent([]), _ready(), "buy low PER stocks")
    assert parsed.initial_capital == 10_000.0
    parsed_kr = compile_strategy(_intent([]), _ready(), "저PER 종목 매수")
    assert parsed_kr.initial_capital == 10_000_000.0
