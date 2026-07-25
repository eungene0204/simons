"""DART 타법인출자현황 → 상장사 간 지분 엣지(kg-equity-edges.json) 결정론 수집.

'넷마블(하이브 주요 주주)' 같은 지분 관계는 뉴스 스니펫 co-mention으로는 이유 없이
확률적으로만 잡힌다 — 정답 소스는 공시다(FR-STR-072b). 사업보고서 '타법인 출자현황'
(otrCprInvstmntSttus)에서 출자사→피출자사 관계를 수집하고, 양쪽 모두 국내 상장사이며
기말 지분율 >= --min-ratio(기본 5%)인 것만 남긴다. 산출물은 Concept Universe의
회사 홉 레이어가 읽는다(KG 그래프 본체엔 합성하지 않음 — related_universe 확장 등
기존 경로의 의미 변화 차단).

용법(백엔드 루트에서):
  python3 scripts/build_equity_edges.py --symbols 251270 035720   # 부분 수집(검증용)
  python3 scripts/build_equity_edges.py                           # 전 상장사 스윕(재개 가능)
  python3 scripts/build_equity_edges.py --bsns-year 2024          # 연도 지정

재개: 진행 파일(data/kg-equity-edges.progress.json, gitignore)이 처리한 corp를 기억
한다 — 중단 후 재실행하면 이어서 수집한다. --symbols 실행은 기존 산출물에 병합된다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_STOCKS_PATH = _BASE_DIR / "data" / "korea-stocks.json"
_CORPCODE_PATH = _BASE_DIR / "data" / "dart_corpcode.json"
_OUT_PATH = _BASE_DIR / "data" / "kg-equity-edges.json"
_PROGRESS_PATH = _BASE_DIR / "data" / "kg-equity-edges.progress.json"
_API = "https://opendart.fss.or.kr/api/otrCprInvstmntSttus.json"
_SLEEP_S = 0.15  # DART 예의상 호출 간격(일일 쿼터 2만 — 전 상장사 스윕 여유)
# 동명 비상장 법인 오탐 가드 — 피출자사가 상장사라면 90%+ 보유는 불가능하다(유통주식
# 요건). 실측(2026-07-25 첫 스윕): 'DS단석→하이브 100%' 등 7건 전부 동명의 비상장
# 자회사가 정확 일치 매칭에 걸린 것(DART 행엔 피출자사 식별자 없이 법인명뿐).
_MAX_LISTED_RATIO = 90.0


def _normalize_name(name: str) -> str:
    """법인명 정규화 — DART inv_prm('(주)하이브')과 정본 종목명('하이브') 매칭용."""
    n = (name or "").strip()
    n = re.sub(r"\(주\)|㈜|주식회사|\(유\)|\s+", "", n)
    n = re.sub(r"\(.*?\)$", "", n)  # 꼬리 괄호 병기('하이브(HYBE)')
    return n.lower()


def _parse_ratio(raw) -> float | None:
    """지분율 문자열('18.2', '18.21 %', '-') → float | None."""
    s = str(raw or "").replace(",", "").replace("%", "").strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_rows(data: dict) -> list[dict]:
    if not isinstance(data, dict) or data.get("status") != "000":
        return []
    rows = data.get("list")
    return rows if isinstance(rows, list) else []


def _row_to_edge(row: dict, source_symbol: str, name_to_symbol: dict[str, str],
                 symbol_to_name: dict[str, str],
                 bsns_year: str, min_ratio: float) -> dict | None:
    """타법인출자현황 행 → invests_in 엣지(양쪽 상장사+지분율 기준 충족 시).

    표시명은 DART inv_prm('㈜하이브 (주1)' — 각주 찌꺼기 동반)이 아니라 정본 종목명."""
    investee = _normalize_name(row.get("inv_prm", ""))
    target_symbol = name_to_symbol.get(investee)
    if not target_symbol or target_symbol == source_symbol:
        return None
    ratio = _parse_ratio(row.get("trmend_blce_qota_rt")) or _parse_ratio(
        row.get("bsis_blce_qota_rt"))
    if ratio is None or ratio < min_ratio or ratio >= _MAX_LISTED_RATIO:
        return None
    target_name = symbol_to_name.get(target_symbol, target_symbol)
    return {
        "source": f"company:{source_symbol}",
        "type": "invests_in",
        "target": f"company:{target_symbol}",
        "ratio": ratio,
        "note": f"{target_name} 지분 {ratio:.1f}% 보유(사업보고서 타법인출자현황 {bsns_year})",
    }


def _fetch(api_key: str, corp_code: str, bsns_year: str) -> dict:
    params = urllib.parse.urlencode({
        "crtfc_key": api_key, "corp_code": corp_code,
        "bsns_year": bsns_year, "reprt_code": "11011",  # 사업보고서
    })
    with urllib.request.urlopen(f"{_API}?{params}", timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def main() -> int:
    ap = argparse.ArgumentParser(description="DART 타법인출자 지분 엣지 수집")
    ap.add_argument("--symbols", nargs="*", help="수집 대상 종목코드(생략=전 상장사)")
    ap.add_argument("--bsns-year", default="2025", help="사업연도(기본 2025)")
    ap.add_argument("--min-ratio", type=float, default=5.0, help="최소 지분율 %% (기본 5)")
    args = ap.parse_args()

    import os
    from dotenv import load_dotenv
    load_dotenv(_BASE_DIR / ".env")
    api_key = os.getenv("DART_API_KEY", "").strip()
    if not api_key:
        print("DART_API_KEY 없음(.env)")
        return 1

    stocks = _load_json(_STOCKS_PATH, [])
    items = stocks if isinstance(stocks, list) else stocks.get("stocks", [])
    name_to_symbol = {_normalize_name(s["name"]): s["symbol"]
                      for s in items if s.get("name") and s.get("symbol")}
    symbol_to_name = {s["symbol"]: s["name"]
                      for s in items if s.get("name") and s.get("symbol")}
    corp_map: dict[str, str] = _load_json(_CORPCODE_PATH, {})

    targets = args.symbols or sorted(s["symbol"] for s in items
                                     if s.get("symbol") in corp_map)
    out = _load_json(_OUT_PATH, {})
    edges: list[dict] = out.get("edges", []) if isinstance(out, dict) else []
    by_pair = {(e["source"], e["target"]): e for e in edges}
    progress: dict = _load_json(_PROGRESS_PATH, {})
    done: set[str] = set(progress.get("done", [])) if not args.symbols else set()

    processed = found = 0
    try:
        for symbol in targets:
            if symbol in done:
                continue
            corp_code = corp_map.get(symbol)
            if not corp_code:
                done.add(symbol)
                continue
            try:
                data = _fetch(api_key, corp_code, args.bsns_year)
            except Exception as exc:  # noqa: BLE001 — 개별 실패는 스킵(재개 시 재시도)
                print(f"  ! {symbol} 조회 실패: {exc}")
                continue
            for row in _extract_rows(data):
                edge = _row_to_edge(row, symbol, name_to_symbol, symbol_to_name,
                                    args.bsns_year, args.min_ratio)
                if edge is not None:
                    by_pair[(edge["source"], edge["target"])] = edge
                    found += 1
            done.add(symbol)
            processed += 1
            if processed % 100 == 0:
                print(f"  … {processed}/{len(targets)} 처리, 엣지 {len(by_pair)}개")
                _save(edges=list(by_pair.values()), done=done, args=args)
            time.sleep(_SLEEP_S)
    finally:
        _save(edges=list(by_pair.values()), done=done, args=args)

    print(f"완료: {processed}개 법인 처리, 신규/갱신 엣지 {found}개, 총 {len(by_pair)}개")
    print(f"산출물: {_OUT_PATH}")
    return 0


def _save(edges: list[dict], done: set, args) -> None:
    edges.sort(key=lambda e: (e["source"], e["target"]))
    _OUT_PATH.write_text(json.dumps({
        "version": 1,
        "source": "DART otrCprInvstmntSttus(타법인출자현황)",
        "bsns_year": args.bsns_year,
        "min_ratio": args.min_ratio,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edges": edges,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    if not args.symbols:  # 전 스윕만 진행 파일 유지(부분 수집은 병합 전용)
        _PROGRESS_PATH.write_text(json.dumps({"done": sorted(done)}), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
