"""테마 ETF 보유종목 → 미국 테마 카탈로그(data/us-theme-catalog.json) 확장.

각 테마의 구성 종목을 그 테마의 대표 ETF **전체 보유목록**에서 가져온다 — 구성 목록은
운용사가 공시하는 객관적 소속 정보(사실)이며 추천이 아니다. 생성된 테마는 카탈로그에
병합되고, US 지식그래프(engine/us_knowledge_graph.py)가 카탈로그를 합성 로드하므로
별도 배선 없이 테마 해석·콘솔 시각화에 반영된다.

보유목록 소스(provider) 3종:
- ``globalx`` — assets.globalxetfs.com 전체 보유 CSV(일자 파일명, 최근 영업일 탐색)
- ``ark``     — assets.ark-funds.com 전체 보유 CSV(펀드별 파일명 고정)
- ``yfinance``— funds_data.top_holdings. **상위 10종만** 준다. 2026-08-26 1차 도입분
  중 전체 보유 CSV가 열리지 않는 운용사(iShares·Invesco·SPDR·Vanguard·ProShares)
  테마가 이 경로에 남아 있다. 신규 테마에 쓰지 않는다.

MarketScreener 투자 테마를 소스로 쓰려던 요청(2026-08-29)은 그 사이트가 자동 접근을
전면 차단(모든 URL 403)해 불가능했다 — 대신 접근 가능한 운용사 공시로 같은 taxonomy를
재현한다. 커버리지 실측·판단 근거는 docs/knowledge_graph.md 미국 섹션.

계약(카탈로그·KG 게이트와 동일):
- 정본 필터: us-stocks.json에 있고 data/ohlcv-us 파케이가 있는 티커만 싣는다
  (KG 무결성 테스트가 전 티커 파케이 보유를 단언한다). 글로벌 ETF의 해외 상장분
  (6861 JP·ABBN SW 등)은 여기서 걸러진다.
- 최소 구성 게이트: 필터 후 MIN_MEMBERS 미만이면 그 테마는 싣지 않고 실패 보고
  (2종목짜리 '테마 유니버스'는 잡음 — 조용히 축소 반영하지 않는다).
- 구성 상한: 정본 필터 후 **비중 상위 MAX_MEMBERS종**만 싣는다. 상한 없이 실으면
  PAVE(100종)·MILN(80종) 같은 광범위 ETF가 테마가 아니라 지수 유니버스가 된다.
  상한은 필터 **뒤에** 적용한다 — 앞에 두면 해외 상장분이 자리를 차지한다.
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
import csv
import datetime as dt
import io
import json
import sys
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "data" / "us-theme-catalog.json"
SEED_PATH = REPO_ROOT / "data" / "us-knowledge-graph.json"
STOCKS_PATH = REPO_ROOT / "data" / "us-stocks.json"
OHLCV_DIR = REPO_ROOT / "data" / "ohlcv-us"

MIN_MEMBERS = 4   # 필터 후 이보다 적으면 테마로 싣지 않는다
MAX_MEMBERS = 30  # 필터 후 비중 상위 이만큼만 싣는다(테마가 지수가 되는 것을 막는다)

# 보유목록 CSV 요청 헤더 — 운용사 CDN은 기본 UA를 거른다.
_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
_HTTP_TIMEOUT = 30
_GLOBALX_URL = "https://assets.globalxetfs.com/funds/holdings/{ticker}_full-holdings_{date}.csv"
_ARK_URL = "https://assets.ark-funds.com/fund-documents/funds-etf-csv/{filename}"
_GLOBALX_LOOKBACK_DAYS = 10  # 공시 파일명이 영업일자 — 최근 며칠을 거슬러 탐색한다
_GLOBALX_DATE: Optional[dt.date] = None  # 첫 성공 공시일 — 이후 펀드는 여기부터 시도

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
        "provider": "globalx",
    },
    {
        "id": "clean-energy",
        "name": "클린에너지",
        "name_en": "Clean energy",
        "aliases": ["클린에너지", "친환경 에너지", "재생에너지", "신재생에너지",
                    "clean energy", "renewable energy", "green energy"],
        "etf": "ICLN",
        "provider": "yfinance",  # 전체 보유 CSV 미개방 운용사 — 상위 10종
    },
    {
        "id": "genomics",
        "name": "유전체·유전자 치료",
        "name_en": "Genomics",
        "aliases": ["유전체", "유전자", "유전자 치료", "genomics", "gene editing",
                    "genomic revolution"],
        "etf": "ARKG",
        "provider": "ark",
        "ark_file": "ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS.csv",
    },
    {
        "id": "water",
        "name": "수자원",
        "name_en": "Water resources",
        "aliases": ["수자원", "물 관련주", "물 산업", "water", "water stocks",
                    "water resources"],
        "etf": "PHO",
        "provider": "yfinance",  # 전체 보유 CSV 미개방 운용사 — 상위 10종
    },
    {
        "id": "regional-banks",
        "name": "지역은행",
        "name_en": "Regional banks",
        "aliases": ["지역은행", "미국 지역은행", "regional banks", "regional banking"],
        "etf": "KRE",
        "provider": "yfinance",  # 전체 보유 CSV 미개방 운용사 — 상위 10종
    },
    {
        "id": "reits",
        "name": "리츠",
        "name_en": "REITs",
        "aliases": ["리츠", "부동산 리츠", "REIT", "REITs", "real estate investment trusts"],
        "etf": "VNQ",
        "provider": "yfinance",  # 전체 보유 CSV 미개방 운용사 — 상위 10종
    },
    {
        "id": "software",
        "name": "소프트웨어",
        "name_en": "Software",
        "aliases": ["소프트웨어", "소프트웨어 관련주", "software", "software stocks"],
        "etf": "IGV",
        "provider": "yfinance",  # 전체 보유 CSV 미개방 운용사 — 상위 10종
    },
    {
        "id": "dividend-aristocrats",
        "name": "배당귀족",
        "name_en": "Dividend aristocrats",
        "aliases": ["배당귀족", "배당 성장", "배당성장주", "dividend aristocrats",
                    "dividend growth"],
        "etf": "NOBL",
        "provider": "yfinance",  # 전체 보유 CSV 미개방 운용사 — 상위 10종
    },
    # ── 2026-08-29 확장: Global X 전체 보유 CSV ──────────────────────────────
    # MarketScreener 투자 테마 taxonomy(Millennials·Ageing Population·Hydrogen·
    # Fintechs·IoT·E-Commerce·Strategic Metals 등)를 접근 가능한 운용사 공시로 재현.
    # 기존 테마가 이미 소유한 별칭권역은 넣지 않는다(사전검사가 강제):
    #  · BUG(사이버보안)·DRIV(전기차·자율주행)·PAVE(인프라)·CLOU(클라우드)
    #    ·GNOM(유전체) → 각각 기존 카탈로그 테마 소유
    #  · FINX(핀테크)·EBIZ(이커머스)·SOCL(소셜미디어) → **시드가 같은 id로 소유**.
    #    시드가 이기므로 여기 실으면 조용히 가려진다(전체 보유 기준 30·30·28종을
    #    싣고도 시드 6·5·4종만 조회됐다 — 충돌 검사기 수정으로 드러났다).
    #    시드 구성을 깊게 할지는 별도 결정 사항이라 여기서 정하지 않는다.
    {
        "id": "ai-bigdata",
        "name": "AI 빅데이터",
        "name_en": "AI & big data",
        "aliases": ["AI 빅데이터", "인공지능 빅데이터", "빅데이터", "big data",
                    "AI and big data"],
        "etf": "AIQ",
        "provider": "globalx",
    },
    {
        "id": "iot",
        "name": "사물인터넷",
        "name_en": "Internet of Things",
        "aliases": ["사물인터넷", "IoT", "IoT 관련주", "internet of things"],
        "etf": "SNSR",
        "provider": "globalx",
    },
    {
        "id": "aging-population",
        "name": "고령화",
        "name_en": "Ageing population",
        "aliases": ["고령화", "고령화 사회", "실버산업", "실버 산업",
                    "aging population", "ageing population"],
        "etf": "AGNG",
        "provider": "globalx",
    },
    {
        "id": "millennials",
        "name": "밀레니얼 소비",
        "name_en": "Millennials",
        "aliases": ["밀레니얼", "밀레니얼 세대", "밀레니얼 소비", "millennials"],
        "etf": "MILN",
        "provider": "globalx",
    },
    {
        "id": "blockchain",
        "name": "블록체인",
        "name_en": "Blockchain",
        "aliases": ["블록체인", "블록체인 관련주", "blockchain"],
        "etf": "BKCH",
        "provider": "globalx",
    },
    {
        "id": "cleantech",
        "name": "클린테크",
        "name_en": "Cleantech",
        "aliases": ["클린테크", "친환경 기술", "cleantech", "clean technology"],
        "etf": "CTEC",
        "provider": "globalx",
    },
    {
        "id": "uranium",
        "name": "우라늄",
        "name_en": "Uranium",
        "aliases": ["우라늄", "우라늄 광산", "uranium", "uranium miners"],
        "etf": "URA",
        "provider": "globalx",
    },
    {
        "id": "esports",
        "name": "e스포츠",
        "name_en": "Esports",
        # '게임'·'비디오게임'·'gaming'은 시드 theme:gaming 소유 — 시드가 이긴다.
        # 여기는 겹치지 않는 e스포츠 어휘만 쓴다.
        "aliases": ["e스포츠", "이스포츠", "e 스포츠", "esports", "e-sports"],
        "etf": "HERO",
        "provider": "globalx",
    },
    {
        "id": "silver",
        "name": "은 광산",
        "name_en": "Silver miners",
        # bare "은"은 별칭으로 쓰지 않는다 — 한 글자라 조사·접미와 뒤섞인다.
        "aliases": ["은 광산", "은광", "실버 광산", "silver", "silver miners"],
        "etf": "SIL",
        "provider": "globalx",
    },
    {
        "id": "hydrogen",
        "name": "수소",
        "name_en": "Hydrogen",
        "aliases": ["수소", "수소 경제", "수소 에너지", "hydrogen"],
        "etf": "HYDR",
        "provider": "globalx",
    },
    {
        "id": "battery",
        "name": "배터리",
        "name_en": "Battery technology",
        # 2026-08-26에는 상위 10종 기준 미국 생존 3종목으로 탈락했던 테마 —
        # 전체 보유 기준으로 게이트를 통과한다.
        # '리튬'·'lithium'은 시드 theme:lithium 소유 — 배터리 어휘만 쓴다.
        "aliases": ["배터리", "이차전지", "2차전지", "battery", "battery technology"],
        "etf": "LIT",
        "provider": "globalx",
    },
    {
        "id": "copper",
        "name": "구리 광산",
        "name_en": "Copper miners",
        "aliases": ["구리", "구리 광산", "동광", "copper", "copper miners"],
        "etf": "COPX",
        "provider": "globalx",
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


def _get(url: str) -> Optional[str]:
    """URL 본문 텍스트. 200이 아니면 None(호출부가 다음 후보로 넘어간다)."""
    import requests

    resp = requests.get(url, headers=_HTTP_HEADERS, timeout=_HTTP_TIMEOUT)
    if resp.status_code != 200:
        return None
    return resp.text


def _weighted_tickers(rows: list[dict[str, str]], ticker_col: str,
                      weight_col: str) -> list[str]:
    """(티커, 비중) 행 → 비중 내림차순 티커 목록. 현금·머니마켓 행은 티커가 비어 빠진다."""
    parsed: list[tuple[float, str]] = []
    for row in rows:
        ticker = (row.get(ticker_col) or "").strip()
        if not ticker:
            continue
        raw = (row.get(weight_col) or "").strip().rstrip("%").replace(",", "")
        try:
            weight = float(raw)
        except ValueError:
            continue  # 면책 문구 등 표 밖 행
        parsed.append((weight, ticker))
    parsed.sort(key=lambda pair: pair[0], reverse=True)
    return [ticker for _, ticker in parsed]


def fetch_globalx_holdings(etf: str, as_of: Optional[dt.date] = None) -> list[str]:
    """Global X 전체 보유 CSV → 비중순 티커. 파일명이 영업일자라 최근 날짜를 거슬러 찾는다.

    CSV 앞 2줄은 펀드명·기준일 머리글이고 3번째 줄이 헤더다.
    """
    global _GLOBALX_DATE
    today = as_of or dt.date.today()
    candidates = [today - dt.timedelta(days=back) for back in range(_GLOBALX_LOOKBACK_DAYS)]
    if _GLOBALX_DATE is not None:
        # 같은 실행의 앞선 펀드가 찾아낸 공시일을 먼저 쓴다(펀드마다 되짚지 않는다).
        candidates.insert(0, _GLOBALX_DATE)
    for day in candidates:
        body = _get(_GLOBALX_URL.format(ticker=etf.lower(), date=day.strftime("%Y%m%d")))
        if body is None:
            continue
        _GLOBALX_DATE = day
        rows = list(csv.DictReader(io.StringIO("\n".join(body.splitlines()[2:]))))
        return _weighted_tickers(rows, "Ticker", "% of Net Assets")
    raise RuntimeError(
        f"Global X 보유 CSV를 찾지 못했습니다({etf}, 최근 {_GLOBALX_LOOKBACK_DAYS}일 탐색)"
    )


def fetch_ark_holdings(filename: str) -> list[str]:
    """ARK 전체 보유 CSV → 비중순 티커. 표 끝의 면책 문구 행은 비중 파싱에서 빠진다."""
    body = _get(_ARK_URL.format(filename=filename))
    if body is None:
        raise RuntimeError(f"ARK 보유 CSV 응답 실패({filename})")
    return _weighted_tickers(list(csv.DictReader(io.StringIO(body))), "ticker", "weight (%)")


def fetch_yfinance_holdings(etf: str) -> list[str]:
    """ETF 보유 **상위 10종**(비중순). 전체 보유 CSV가 열리지 않는 운용사 전용 폴백."""
    import yfinance as yf

    holdings = yf.Ticker(etf).funds_data.top_holdings
    # index=Symbol, 비중 내림차순 정렬 보장
    df = holdings.sort_values("Holding Percent", ascending=False)
    return [str(sym).strip() for sym in df.index if str(sym).strip()]


def fetch_holdings(spec: dict[str, Any]) -> list[str]:
    """provider별 보유목록 조회 — 비중 내림차순 티커."""
    provider = spec.get("provider", "yfinance")
    if provider == "globalx":
        return fetch_globalx_holdings(spec["etf"])
    if provider == "ark":
        return fetch_ark_holdings(spec["ark_file"])
    if provider == "yfinance":
        return fetch_yfinance_holdings(spec["etf"])
    raise RuntimeError(f"알 수 없는 provider: {provider!r}")


def build_theme(spec: dict[str, Any], registry: set[str],
                holdings: list[str]) -> tuple[Optional[dict[str, Any]], str]:
    """(테마 dict | None, 사유). 정본·파케이 필터 후 최소 구성 게이트를 적용한다."""
    survivors = [s for s in holdings if s in registry]
    if len(survivors) < MIN_MEMBERS:
        return None, (
            f"구성 부족: {spec['etf']} 보유 {len(holdings)}개 중 정본 생존 "
            f"{len(survivors)}개(<{MIN_MEMBERS}) — {survivors}"
        )
    members = survivors[:MAX_MEMBERS]  # 정본 필터 뒤에 상한 — 순서는 비중 내림차순
    theme = {
        "id": spec["id"],
        "name": spec["name"],
        "name_en": spec["name_en"],
        "aliases": list(spec["aliases"]),
        "symbols": members,
        "source": f"etf:{spec['etf']}",
        "as_of": dt.date.today().isoformat(),
    }
    capped = f" → 상한 {len(members)}" if len(members) < len(survivors) else ""
    return theme, f"{spec['etf']} 보유 {len(holdings)} → 정본 {len(survivors)}{capped}종목"


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
            # 같은 테마가 별칭을 두 번 적은 경우만 통과다. 소유자 접미만 보고
            # 넘기면 **같은 id를 쓰는 시드 노드**('seed:fintech')를 자기 자신으로
            # 오인해 통과시킨다 — 그러면 시드가 이기는 별칭에 카탈로그 테마가
            # 조용히 얹혀 영영 조회되지 않는다(2026-08-29 실측: fintech·ecommerce
            # ·social-media 3건이 30·30·28종목을 싣고도 시드 6·5·4종에 가려졌다).
            if owner and owner != f"new:{theme['id']}":
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
            holdings = fetch_holdings(spec)
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
