"""테마 ETF 보유종목 → 미국 테마 카탈로그(data/us-theme-catalog.json) 확장.

각 테마의 구성 종목을 그 테마의 대표 ETF 보유 상위 종목(yfinance funds_data)에서
가져온다 — 구성 목록은 운용사가 공시하는 객관적 소속 정보(사실)이며 추천이 아니다.
생성된 테마는 카탈로그에 병합되고, US 지식그래프(engine/us_knowledge_graph.py)가
카탈로그를 합성 로드하므로 별도 배선 없이 테마 해석·콘솔 시각화에 반영된다.

계약(카탈로그·KG 게이트와 동일):
- 정본 필터: us-stocks.json에 있고 data/ohlcv-us 파케이가 있는 티커만 싣는다
  (KG 무결성 테스트가 전 티커 파케이 보유를 단언한다). 글로벌 ETF의 해외 상장분
  (6861.T·ABBN.SW 등)은 여기서 걸러진다.
- 최소 구성 게이트: 필터 후 MIN_MEMBERS 미만이면 그 테마는 싣지 않고 실패 보고
  (2종목짜리 '테마 유니버스'는 잡음 — 조용히 축소 반영하지 않는다).
- 별칭 충돌 사전검사: 시드·기존 카탈로그·신규 테마 상호 간 별칭이 겹치면 쓰지 않고
  실패한다(시드-카탈로그 교차 충돌은 KG 테스트가 금지 — 같은 검사를 쓰기 전에 수행).
- 멱등 병합: 이 스크립트가 만든 테마(source: etf:*)만 갱신하고, 수동 큐레이션
  테마(기존 17종)는 건드리지 않는다.

사용:
  python scripts/build_us_theme_catalog.py            # 병합 실행
  python scripts/build_us_theme_catalog.py --dry-run  # 결과 미리보기(파일 미수정)

실행 후 게이트: cd backend && pytest tests/test_us_knowledge_graph.py tests/test_us_theme_catalog.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "data" / "us-theme-catalog.json"
SEED_PATH = REPO_ROOT / "data" / "us-knowledge-graph.json"
STOCKS_PATH = REPO_ROOT / "data" / "us-stocks.json"
OHLCV_DIR = REPO_ROOT / "data" / "ohlcv-us"

MIN_MEMBERS = 4  # 필터 후 이보다 적으면 테마로 싣지 않는다

# 테마 ← 대표 ETF 매핑(큐레이션 정본 — 테마 선정·별칭은 사람이, 구성은 ETF 공시가).
# 별칭은 기존 시드·카탈로그와 겹치지 않는 것만 쓴다(사전검사 강제):
#  · '로봇/robotics'는 시드 휴머노이드 로봇 소유 → 여기는 '로봇 자동화' 계열만
#  · '인프라/infrastructure'는 카탈로그 리쇼어링·인프라 소유 → PAVE 테마는 제외
ETF_THEMES: list[dict[str, Any]] = [
    {
        "id": "robotics-automation",
        "name": "로봇 자동화",
        "name_en": "Robotics & automation",
        "aliases": ["로봇 자동화", "산업 자동화", "산업용 로봇",
                    "industrial robotics", "factory automation",
                    "robotics automation"],
        "etf": "BOTZ",
    },
    {
        "id": "clean-energy",
        "name": "클린에너지",
        "name_en": "Clean energy",
        "aliases": ["클린에너지", "친환경 에너지", "재생에너지", "신재생에너지",
                    "clean energy", "renewable energy", "green energy"],
        "etf": "ICLN",
    },
    {
        "id": "genomics",
        "name": "유전체·유전자 치료",
        "name_en": "Genomics",
        "aliases": ["유전체", "유전자", "유전자 치료", "genomics", "gene editing",
                    "genomic revolution"],
        "etf": "ARKG",
    },
    {
        "id": "water",
        "name": "수자원",
        "name_en": "Water resources",
        "aliases": ["수자원", "물 관련주", "물 산업", "water", "water stocks",
                    "water resources"],
        "etf": "PHO",
    },
    {
        "id": "regional-banks",
        "name": "지역은행",
        "name_en": "Regional banks",
        "aliases": ["지역은행", "미국 지역은행", "regional banks", "regional banking"],
        "etf": "KRE",
    },
    {
        "id": "reits",
        "name": "리츠",
        "name_en": "REITs",
        "aliases": ["리츠", "부동산 리츠", "REIT", "REITs", "real estate investment trusts"],
        "etf": "VNQ",
    },
    # battery-tech(LIT)는 제외 — 글로벌 ETF라 상위 10 중 미국 정본 생존이 3종목뿐
    # (RIO·ALB·TSLA, 2026-08-26 실측 — MIN_MEMBERS 미달). 미국 중심 배터리 ETF가
    # 생기면 재검토.
    {
        "id": "software",
        "name": "소프트웨어",
        "name_en": "Software",
        "aliases": ["소프트웨어", "소프트웨어 관련주", "software", "software stocks"],
        "etf": "IGV",
    },
    {
        "id": "dividend-aristocrats",
        "name": "배당귀족",
        "name_en": "Dividend aristocrats",
        "aliases": ["배당귀족", "배당 성장", "배당성장주", "dividend aristocrats",
                    "dividend growth"],
        "etf": "NOBL",
    },
]


def _norm_key(text: str) -> str:
    """별칭 정규화 키 — engine/us_knowledge_graph._norm_key와 동일 규약."""
    return (text or "").strip().lower().replace(" ", "")


def load_registry() -> set[str]:
    """정본 티커 — us-stocks.json에 있고 파케이(ohlcv-us)가 있는 심볼."""
    stocks = json.loads(STOCKS_PATH.read_text())
    symbols = {s["symbol"] for s in stocks if s.get("symbol")}
    return {s for s in symbols if (OHLCV_DIR / f"{s}.parquet").exists()}


def fetch_top_holdings(etf: str) -> list[str]:
    """ETF 보유 상위 종목 티커(비중순). yfinance funds_data — 실패 시 빈 목록."""
    import yfinance as yf

    holdings = yf.Ticker(etf).funds_data.top_holdings
    # index=Symbol, 비중 내림차순 정렬 보장
    df = holdings.sort_values("Holding Percent", ascending=False)
    return [str(sym).strip() for sym in df.index if str(sym).strip()]


def build_theme(spec: dict[str, Any], registry: set[str],
                holdings: list[str]) -> tuple[Optional[dict[str, Any]], str]:
    """(테마 dict | None, 사유). 정본·파케이 필터 후 최소 구성 게이트를 적용한다."""
    members = [s for s in holdings if s in registry]
    if len(members) < MIN_MEMBERS:
        return None, (
            f"구성 부족: {spec['etf']} 보유 {len(holdings)}개 중 정본 생존 "
            f"{len(members)}개(<{MIN_MEMBERS}) — {members}"
        )
    theme = {
        "id": spec["id"],
        "name": spec["name"],
        "name_en": spec["name_en"],
        "aliases": list(spec["aliases"]),
        "symbols": members,
        "source": f"etf:{spec['etf']}",
        "as_of": dt.date.today().isoformat(),
    }
    return theme, f"{spec['etf']} 상위 {len(holdings)} → 정본 {len(members)}종목"


def collect_reserved_aliases(catalog: dict, seed: dict,
                             exclude_ids: set[str]) -> dict[str, str]:
    """이미 점유된 별칭 키 → 소유자. exclude_ids(이 스크립트 산출 테마)는 제외."""
    reserved: dict[str, str] = {}
    for node in seed.get("nodes", []):
        if node.get("id", "").startswith(("company:", "etf:")):
            continue
        terms = [node.get("name", ""), node.get("name_en") or ""]
        terms += list(node.get("synonyms", []))
        for t in terms:
            k = _norm_key(t)
            if len(k) >= 2:
                reserved.setdefault(k, f"seed:{node.get('id')}")
    for theme in catalog.get("themes", []):
        if theme.get("id") in exclude_ids:
            continue
        for t in [theme.get("name", ""), theme.get("name_en") or ""] + list(
            theme.get("aliases", [])
        ):
            k = _norm_key(t)
            if len(k) >= 2:
                reserved.setdefault(k, f"catalog:{theme.get('id')}")
    return reserved


def check_alias_collisions(new_themes: list[dict[str, Any]],
                           reserved: dict[str, str]) -> list[str]:
    """신규 테마 별칭이 기존(시드·수동 카탈로그)·신규 상호 간 겹치면 오류 목록."""
    errors: list[str] = []
    claimed: dict[str, str] = dict(reserved)
    for theme in new_themes:
        for t in [theme["name"], theme.get("name_en") or ""] + list(theme["aliases"]):
            k = _norm_key(t)
            if len(k) < 2:
                continue
            owner = claimed.get(k)
            if owner and not owner.endswith(f":{theme['id']}"):
                errors.append(f"별칭 충돌: '{t}' ({theme['id']} ↔ {owner})")
            else:
                claimed[k] = f"new:{theme['id']}"
    return errors


def merge_catalog(catalog: dict, new_themes: list[dict[str, Any]]) -> dict:
    """멱등 병합 — 이 스크립트 산출 테마(id 일치)만 교체하고 나머지는 순서 유지."""
    new_by_id = {t["id"]: t for t in new_themes}
    merged: list[dict[str, Any]] = []
    for theme in catalog.get("themes", []):
        if theme.get("id") in new_by_id:
            merged.append(new_by_id.pop(theme["id"]))
        else:
            merged.append(theme)
    merged.extend(new_by_id.values())
    out = dict(catalog)
    out["themes"] = merged
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="파일을 수정하지 않고 결과만 출력")
    args = parser.parse_args()

    registry = load_registry()
    catalog = json.loads(CATALOG_PATH.read_text())
    seed = json.loads(SEED_PATH.read_text())
    print(f"정본(파케이 보유) {len(registry)}종목, 기존 카탈로그 테마 {len(catalog.get('themes', []))}개")

    new_themes: list[dict[str, Any]] = []
    failures: list[str] = []
    for spec in ETF_THEMES:
        try:
            holdings = fetch_top_holdings(spec["etf"])
        except Exception as exc:  # noqa: BLE001 — 소스 장애는 테마 단위로 보고
            failures.append(f"{spec['id']}: {spec['etf']} 보유종목 조회 실패 — {exc!r}")
            continue
        theme, reason = build_theme(spec, registry, holdings)
        if theme is None:
            failures.append(f"{spec['id']}: {reason}")
            continue
        print(f"  ✓ {spec['id']:22s} {reason}: {theme['symbols']}")
        new_themes.append(theme)

    exclude = {s["id"] for s in ETF_THEMES}
    collisions = check_alias_collisions(
        new_themes, collect_reserved_aliases(catalog, seed, exclude)
    )
    if collisions:
        for c in collisions:
            print(f"  ✗ {c}")
        print("별칭 충돌 — 카탈로그를 수정하지 않았습니다.")
        return 1
    for f in failures:
        print(f"  ✗ {f}")

    merged = merge_catalog(catalog, new_themes)
    print(f"병합 결과: 테마 {len(merged['themes'])}개 (신규/갱신 {len(new_themes)}개, 실패 {len(failures)}개)")
    if args.dry_run:
        print("--dry-run: 파일 미수정")
        return 0
    CATALOG_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"저장: {CATALOG_PATH}")
    print("게이트: cd backend && pytest tests/test_us_knowledge_graph.py tests/test_us_theme_catalog.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
