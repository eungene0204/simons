"""미국 테마 카탈로그(data/us-theme-catalog.json) — 무결성·registry 해석·검증기 전개."""

import json
from pathlib import Path

import pytest

from engine.universe_pit import resolve_us_theme
from strategy_conversation.interpreter.models import (
    StrategyCondition,
    StrategyIntent,
    StrategySpec,
    UniverseSpec,
)
from strategy_conversation.validation.capability_validator import validate_capability

_ROOT = Path(__file__).resolve().parents[2]
_CATALOG = _ROOT / "data" / "us-theme-catalog.json"
_OHLCV = _ROOT / "data" / "ohlcv-us"

needs_data = pytest.mark.skipif(not _OHLCV.exists(), reason="미국 파케이 미러 없음")


def _themes():
    return json.loads(_CATALOG.read_text())["themes"]


def test_catalog_integrity():
    themes = _themes()
    ids = [t["id"] for t in themes]
    assert len(set(ids)) == len(ids)
    seen_alias = {}
    for t in themes:
        assert t["name"] and t["symbols"], t["id"]
        assert len(set(t["symbols"])) == len(t["symbols"]), t["id"]
        for alias in [t["name"], t.get("name_en"), *t.get("aliases", [])]:
            if not alias:
                continue
            key = alias.strip().lower().replace(" ", "")
            # 같은 별칭이 두 테마를 가리키면 해석이 비결정적이 된다
            assert seen_alias.get(key, t["id"]) == t["id"], f"별칭 충돌: {alias}"
            seen_alias[key] = t["id"]


@needs_data
def test_catalog_symbols_all_have_parquet():
    # 데이터 없는 티커를 조용히 제외하지 않는다 — 카탈로그 편집 시 여기서 Fail Fast.
    missing = [
        (t["id"], s) for t in _themes() for s in t["symbols"]
        if not (_OHLCV / f"{s}.parquet").exists()
    ]
    assert missing == []


def test_resolve_us_theme_exact_and_us_prefix():
    name, symbols = resolve_us_theme("AI 반도체")
    assert name == "AI 반도체" and "NVDA" in symbols
    # '미국' 접두는 시장 한정어 — 벗겨서 조회한다
    assert resolve_us_theme("미국 사이버보안")[0] == "사이버보안"
    # 정확 일치만 — 부분 문자열 매칭 금지(오폭 방지)
    # '반도체'는 앵커 소속 합집합으로 전개된다(설계 전환 2026-08-26 — 종전 None)
    assert resolve_us_theme("반도체")[0] == "반도체 산업"
    assert resolve_us_theme("없는테마") is None
    assert resolve_us_theme(None) is None


def _intent(sectors):
    spec = StrategySpec(
        universe=UniverseSpec(markets=["US"], sectors=sectors),
        entry_conditions=[StrategyCondition(factor="technical.rsi", operator="<=", value=30.0)],
    )
    return StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)


def test_validator_expands_theme_to_symbols_with_provenance():
    intent = _intent(["AI 반도체"])
    errors, _w, unsupported, _f = validate_capability(intent)
    assert errors == [] and unsupported == []
    assert "NVDA" in intent.strategy.universe.symbols
    assert intent.strategy.universe.theme == "AI 반도체"  # 출처 표기 계약
    assert intent.strategy.universe.sectors == []


def test_validator_reports_unknown_us_theme():
    intent = _intent(["화성테마"])
    errors, _w, unsupported, _f = validate_capability(intent)
    assert any("화성테마" in e for e in errors)
    assert intent.strategy.universe.symbols == []
    assert intent.strategy.universe.sectors == []  # 조용히 남겨 오폭하지 않는다


def test_validator_strips_kr_expansion_from_us_theme():
    """미국 테마 전개에 상류 한국 테마 전개(숫자 코드)가 섞이면 제거+경고한다.

    실측(2026-08-26): "크립토"가 미국 6티커 + 한국 61코드로 혼합 전개돼 한·미 혼합으로
    엔진에서 거절되는 죽은 전략이 됐다. 한국 코드는 시스템이 넣은 잘못된 시장의
    전개이지 사용자 지정이 아니다."""
    spec = StrategySpec(
        universe=UniverseSpec(markets=["US"], sectors=["크립토"], symbols=["112040", "035420"]),
        entry_conditions=[StrategyCondition(factor="technical.rsi", operator="<=", value=30.0)],
    )
    intent = StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)
    _e, warnings, _u, _f = validate_capability(intent)
    assert all(not s[:1].isdigit() for s in intent.strategy.universe.symbols)
    assert "COIN" in intent.strategy.universe.symbols
    assert any("한국 종목 전개" in w for w in warnings)


def test_classify_universe_recognizes_us_theme_with_marker():
    """플래너 유니버스 분류 — '미국' 표지가 있는 미국 테마어는 SECTOR(정본명)로 분류한다.

    실측(2026-08-26): KR KG에 없는 미국 테마어("미국 빅테크")가 CONCEPT 체인(KR 검색
    학습)에서 소실됐다. 표지 없는 표현("빅테크")은 기존 KR 체인을 보존한다."""
    from strategy_conversation.tools.catalog import ClassifyUniverseIn, _classify_universe

    out = _classify_universe(ClassifyUniverseIn(text="미국 빅테크"))
    assert out.universe_type == "SECTOR" and out.canonical == "빅테크"
    out2 = _classify_universe(ClassifyUniverseIn(text="미국 헬스케어 대형주"))
    assert out2.universe_type == "SECTOR" and out2.canonical == "헬스케어 대형주"
    # 표지 없는 표현은 미국 분류로 선점하지 않는다(한국 대화의 테마 학습 체인 보존)
    out3 = _classify_universe(ClassifyUniverseIn(text="빅테크"))
    assert out3.universe_type != "SECTOR" or out3.canonical != "빅테크"
