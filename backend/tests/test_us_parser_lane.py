"""US 파서 레인 (Phase 2) — markets enum·정규화·검증·컨버터·미지원 목록 회귀."""

import pytest

from engine import universe_capabilities
from engine.strategy_converter import _estimate_universe_symbol_count
from strategy_conversation.interpreter.models import (
    StrategyCondition,
    StrategyIntent,
    StrategySpec,
    UniverseSpec,
)
from strategy_conversation.registry.capability_registry import SUPPORTED_MARKETS, US_MARKETS
from strategy_conversation.validation.capability_validator import validate_capability


def _cond(factor: str, operator: str = "<=", value: float = 10.0) -> StrategyCondition:
    return StrategyCondition(factor=factor, operator=operator, value=value)


def _intent(markets, **spec_kw) -> StrategyIntent:
    spec = StrategySpec(universe=UniverseSpec(markets=markets), **spec_kw)
    return StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)


# ── enum·정규화 ───────────────────────────────────────────────

def test_registry_includes_us_markets():
    for m in ("SP500", "NASDAQ100", "NASDAQ", "DOW30", "US"):
        assert m in SUPPORTED_MARKETS
    assert "US_ETF" in US_MARKETS


def test_universe_spec_accepts_us_markets():
    spec = UniverseSpec(markets=["SP500"])
    assert spec.markets == ["SP500"]


def test_universe_spec_coerces_us_notation_drift():
    # LLM 출력의 표기 드리프트만 정규화한다(의미 선택은 프롬프트/LLM 몫)
    assert UniverseSpec(markets=["S&P500"]).markets == ["SP500"]
    assert UniverseSpec(markets=["나스닥"]).markets == ["NASDAQ"]
    assert UniverseSpec(markets=["나스닥100"]).markets == ["NASDAQ100"]
    assert UniverseSpec(markets=["다우존스"]).markets == ["DOW30"]
    assert UniverseSpec(markets=["미국"]).markets == ["US"]
    assert UniverseSpec(markets=["미국ETF"]).markets == ["US_ETF"]
    # 한국 시장 정규화는 종전과 동일
    assert UniverseSpec(markets=["코스피"]).markets == ["KOSPI"]


# ── 유니버스 능력(ETF 계약) ───────────────────────────────────

def test_us_etf_is_etf_kind_without_fundamentals():
    assert universe_capabilities.universe_kind(["US_ETF"]) == "ETF"
    assert not universe_capabilities.fundamental_metric_supported(["US_ETF"], "per")
    assert universe_capabilities.fundamental_metric_supported(["US_ETF"], "trading_value")
    assert universe_capabilities.universe_kind(["SP500"]) == "STOCK"
    assert universe_capabilities.fundamental_metric_supported(["SP500"], "per")


# ── capability_validator 미국 제약 ────────────────────────────

def test_us_market_allows_fundamentals():
    intent = _intent(["SP500"], entry_conditions=[_cond("fundamental.per")])
    errors, _w, unsupported, _f = validate_capability(intent)
    assert not errors
    assert not unsupported


def test_kr_us_mix_is_rejected():
    intent = _intent(["KOSPI", "SP500"], entry_conditions=[_cond("fundamental.per")])
    errors, _w, _u, _f = validate_capability(intent)
    assert any("혼합할 수 없습니다" in e for e in errors)


def test_multiple_us_indices_rejected():
    intent = _intent(["SP500", "DOW30"], entry_conditions=[_cond("fundamental.per")])
    errors, _w, _u, _f = validate_capability(intent)
    assert any("하나만" in e for e in errors)


def test_us_sector_filter_unsupported_and_cleared():
    # '반도체'는 2026-08-26부터 앵커 합집합으로 카탈로그 전개된다 — 카탈로그 밖
    # 표현만 미지원 안내로 남는 계약을 정본 밖 업종으로 검증한다.
    spec = StrategySpec(
        universe=UniverseSpec(markets=["SP500"], sectors=["농기계"]),
        entry_conditions=[_cond("fundamental.per")],
    )
    intent = StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)
    errors, _w, unsupported, _f = validate_capability(intent)
    assert any("업종" in e for e in errors)
    assert intent.strategy.universe.sectors == []
    assert any("업종" in u for u in unsupported)


def test_us_semiconductor_sector_expands_via_anchor_union():
    # 광의어 '반도체'는 미지원 안내가 아니라 앵커 소속 합집합의 지정 종목으로 선다
    spec = StrategySpec(
        universe=UniverseSpec(markets=["SP500"], sectors=["반도체"]),
        entry_conditions=[_cond("fundamental.per")],
    )
    intent = StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)
    errors, _w, _u, _f = validate_capability(intent)
    assert not any("업종" in e for e in errors)
    assert "NVDA" in intent.strategy.universe.symbols
    assert intent.strategy.universe.theme == "반도체 산업"


def test_us_ai_signal_unsupported_and_removed():
    intent = _intent(
        ["SP500"],
        entry_conditions=[_cond("technical.ai_model", ">=", 70.0)],
        exit_conditions=[_cond("technical.ai_drop_model", ">=", 70.0)],
    )
    errors, _w, unsupported, _f = validate_capability(intent)
    assert any("AI" in e for e in errors)
    assert intent.strategy.entry_conditions == []
    assert intent.strategy.exit_conditions == []


def test_us_etf_fundamental_condition_rejected():
    intent = _intent(["US_ETF"], entry_conditions=[_cond("fundamental.per")])
    errors, _w, unsupported, _f = validate_capability(intent)
    assert any("ETF" in e for e in errors)


# ── 컨버터 ────────────────────────────────────────────────────

def test_symbol_count_estimates_for_us_indices():
    assert _estimate_universe_symbol_count(["SP500"]) == 500
    assert _estimate_universe_symbol_count(["NASDAQ100"]) == 100
    assert _estimate_universe_symbol_count(["DOW30"]) == 30
    assert _estimate_universe_symbol_count(["US"]) is None


def test_parsed_strategy_universe_to_universe_id():
    from engine.nl_parser import ParsedStrategy
    from engine.strategy_converter import to_backtest_request

    strategy = ParsedStrategy(description="US 테스트", universe=["SP500"])
    req = to_backtest_request(strategy, resolve_symbols=False)
    assert req["universe_id"] == "sp500"
    assert req["symbol_count"] == 500

    req2 = to_backtest_request(
        ParsedStrategy(description="US ETF 테스트", universe=["US_ETF"]),
        resolve_symbols=False,
    )
    assert req2["universe_id"] == "us_etf"


# ── nl_parser 미지원 목록 회귀 ────────────────────────────────

def test_us_market_terms_no_longer_flagged_unsupported():
    from engine.nl_parser import _mentioned_unsupported_concepts

    for text in ("나스닥에서 골든크로스가 나오면 매수해 주세요",
                 "S&P500에서 PER 15 이하 종목을 담아 주세요",
                 "미국 시장 전체에서 모멘텀 상위 10종목"):
        assert "overseas" not in _mentioned_unsupported_concepts(text), text


def test_us_stock_and_etf_refs_resolve_to_tickers():
    # 미국 개별 종목·ETF 티커 지정 — universe_resolver의 미국 registry 해석 (2026-08-25)
    from strategy_conversation.registry.universe_resolver import resolve_symbols

    codes, unresolved = resolve_symbols(["애플", "SPY", "엔비디아", "005930"])
    assert set(codes) == {"AAPL", "SPY", "NVDA", "005930"}
    assert unresolved == []

    codes2, unresolved2 = resolve_symbols(["ZZZZZZZ"])  # 데이터 없는 티커 — 조용한 통과 금지
    assert codes2 == [] and unresolved2 == ["ZZZZZZZ"]


def test_us_market_keyword_no_longer_flagged():
    from engine.nl_parser import _mentioned_unsupported_concepts

    assert "overseas" not in _mentioned_unsupported_concepts("애플 주식으로 백테스트 해줘")
    assert "overseas" not in _mentioned_unsupported_concepts("QQQ만 투자하는 전략")
