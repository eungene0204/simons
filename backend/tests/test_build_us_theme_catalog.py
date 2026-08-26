"""테마 ETF → 미국 테마 카탈로그 생성 스크립트(scripts/build_us_theme_catalog.py) 회귀.

네트워크(yfinance) 없이 순수 로직만 검증한다: 정본·최소 구성 게이트, 별칭 충돌
사전검사, 멱등 병합(수동 큐레이션 테마 불가침). 실제 카탈로그 파일의 계약(전 티커
파케이 보유·별칭 충돌 0)은 기존 KG 게이트(test_us_knowledge_graph·test_us_theme_catalog)
가 담당한다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "build_us_theme_catalog.py"
spec = importlib.util.spec_from_file_location("build_us_theme_catalog", _SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore[union-attr]


def _spec(**kw):
    base = {
        "id": "test-theme", "name": "테스트", "name_en": "Test",
        "aliases": ["테스트"], "etf": "TEST",
    }
    base.update(kw)
    return base


# ── 정본 필터 + 최소 구성 게이트 ─────────────────────────────────────────────

def test_build_theme_filters_to_registry_and_keeps_weight_order():
    theme, reason = mod.build_theme(
        _spec(), registry={"AAA", "BBB", "CCC", "DDD"},
        holdings=["ZZZ.T", "BBB", "AAA", "YYY.SW", "DDD", "CCC"],
    )
    assert theme is not None
    assert theme["symbols"] == ["BBB", "AAA", "DDD", "CCC"]  # 비중순 유지·해외분 제거
    assert theme["source"] == "etf:TEST"


def test_build_theme_rejects_below_min_members():
    theme, reason = mod.build_theme(
        _spec(), registry={"AAA", "BBB"}, holdings=["AAA", "BBB", "X.T", "Y.T"],
    )
    assert theme is None
    assert "구성 부족" in reason


# ── 별칭 충돌 사전검사 ───────────────────────────────────────────────────────

def test_alias_collision_against_seed_and_manual_catalog():
    reserved = {"로봇": "seed:humanoid", "클라우드소프트웨어": "catalog:cloud-software"}
    errors = mod.check_alias_collisions(
        [{"id": "a", "name": "로봇", "name_en": None, "aliases": ["로봇 관련주"]}],
        reserved,
    )
    assert errors and "로봇" in errors[0]


def test_alias_collision_between_new_themes():
    themes = [
        {"id": "a", "name": "물", "name_en": "Water", "aliases": ["수자원"]},
        {"id": "b", "name": "수자원", "name_en": None, "aliases": []},
    ]
    errors = mod.check_alias_collisions(themes, {})
    assert errors and "수자원" in errors[0]


def test_same_theme_rerun_is_not_a_collision():
    # 재실행 시 자기 자신(id 일치)의 기존 별칭은 충돌이 아니다(멱등 갱신)
    themes = [{"id": "a", "name": "수자원", "name_en": None, "aliases": ["water"]}]
    assert mod.check_alias_collisions(themes, {"수자원": "new:a"}) == []


# ── 멱등 병합(수동 테마 불가침) ─────────────────────────────────────────────

def test_merge_replaces_own_themes_and_preserves_manual_ones():
    catalog = {"note": "n", "themes": [
        {"id": "manual-1", "symbols": ["AAA"]},
        {"id": "etf-old", "symbols": ["BBB"], "source": "etf:X"},
    ]}
    merged = mod.merge_catalog(catalog, [
        {"id": "etf-old", "symbols": ["CCC"], "source": "etf:X"},
        {"id": "etf-new", "symbols": ["DDD"], "source": "etf:Y"},
    ])
    ids = [t["id"] for t in merged["themes"]]
    assert ids == ["manual-1", "etf-old", "etf-new"]  # 순서 유지 + 신규는 뒤에
    assert merged["themes"][0]["symbols"] == ["AAA"]  # 수동 테마 불가침
    assert merged["themes"][1]["symbols"] == ["CCC"]  # 자기 산출물만 교체
    # 멱등: 같은 입력 재병합 시 결과 불변
    assert mod.merge_catalog(merged, [
        {"id": "etf-old", "symbols": ["CCC"], "source": "etf:X"},
        {"id": "etf-new", "symbols": ["DDD"], "source": "etf:Y"},
    ]) == merged


# ── 스펙 자체의 정합 ─────────────────────────────────────────────────────────

def test_shipped_spec_has_unique_ids_and_aliases():
    ids = [s["id"] for s in mod.ETF_THEMES]
    assert len(ids) == len(set(ids))
    errors = mod.check_alias_collisions(
        [dict(s, symbols=[]) for s in mod.ETF_THEMES], {},
    )
    assert errors == []
