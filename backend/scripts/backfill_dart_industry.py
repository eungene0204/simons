"""DART 기업개황에서 표준산업분류코드(induty_code)를 전 종목 백필한다(재개 가능·멱등).

왜 필요한가: 섹터 분류가 KRX 업종 '문자열' + **사명**을 키워드 부분 문자열 매칭해 왔다.
그 결과 메"가스"터디교육이 '가스'에 걸려 에너지/원자력이 되고, 사명에 '바이오'만 있으면
동물사료 회사가 바이오/제약이 됐다. 문자열 대신 **코드**를 쓰면 이 사고 유형이 원천 차단된다.

한계: induty_code는 DART에 '등록된 주업종'이라 실제 주력 사업과 다를 수 있다
(삼성전자=264 통신·방송장비). 코드는 오분류를 없애는 게 아니라 **문자열 사고를 없애고
불일치를 드러나게** 한다 — 교차 검증(scripts/audit_sector_sources.py)이 그 역할이다.

    python backend/scripts/backfill_dart_industry.py [--limit N]

결과는 data/dart-industry.json에 누적 저장되며, 이미 받은 종목은 건너뛴다.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import time
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parents[2]
KOREA_STOCKS = REPO / "data" / "korea-stocks.json"
OUT_PATH = REPO / "data" / "dart-industry.json"
CORP_CODE_CACHE = REPO / "data" / "dart-corp-code.json"

_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
_COMPANY_URL = "https://opendart.fss.or.kr/api/company.json"
_SLEEP = 0.08  # DART 분당 제한 여유 (일 20,000건)


def _api_key() -> str:
    key = os.getenv("DART_API_KEY", "").strip()
    if not key:
        env = REPO / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("DART_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        raise SystemExit("DART_API_KEY가 없습니다 (.env 또는 환경변수)")
    return key


def load_corp_codes(key: str) -> dict[str, str]:
    """stock_code → corp_code. 한 번 받아 캐시한다(전체 기업 고유번호 파일)."""
    if CORP_CODE_CACHE.exists():
        return json.loads(CORP_CODE_CACHE.read_text(encoding="utf-8"))
    print("DART 기업 고유번호 목록 내려받는 중…")
    with urllib.request.urlopen(f"{_CORP_CODE_URL}?crtfc_key={key}", timeout=120) as resp:
        blob = resp.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        xml = zf.read(zf.namelist()[0])
    mapping: dict[str, str] = {}
    for item in ElementTree.fromstring(xml).iter("list"):
        stock = (item.findtext("stock_code") or "").strip()
        corp = (item.findtext("corp_code") or "").strip()
        if stock and corp:
            mapping[stock] = corp
    CORP_CODE_CACHE.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=0) + "\n", encoding="utf-8"
    )
    print(f"  상장 종목 {len(mapping)}건 캐시")
    return mapping


def fetch_industry(key: str, corp_code: str) -> dict | None:
    url = f"{_COMPANY_URL}?crtfc_key={key}&corp_code={corp_code}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001 — 개별 실패는 건너뛰고 재개 가능하게
        return {"error": str(exc)}
    if data.get("status") != "000":
        return {"error": f"{data.get('status')} {data.get('message')}"}
    return {
        "induty_code": (data.get("induty_code") or "").strip(),
        "corp_name": data.get("corp_name"),
        "corp_cls": data.get("corp_cls"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="이번 실행에서 받을 최대 종목 수")
    args = parser.parse_args()

    key = _api_key()
    corp_codes = load_corp_codes(key)

    payload = json.loads(KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload["stocks"]

    out: dict = json.loads(OUT_PATH.read_text(encoding="utf-8")) if OUT_PATH.exists() else {}
    todo = [s for s in rows if s["symbol"] not in out]
    if args.limit:
        todo = todo[: args.limit]
    print(f"대상 {len(todo)}종목 (이미 받음 {len(out)} / 전체 {len(rows)})")

    no_corp, failed, ok = 0, 0, 0
    for i, stock in enumerate(todo, 1):
        symbol = stock["symbol"]
        corp = corp_codes.get(symbol)
        if not corp:
            out[symbol] = {"name": stock.get("name"), "induty_code": None, "error": "corp_code 없음"}
            no_corp += 1
            continue
        result = fetch_industry(key, corp)
        result["name"] = stock.get("name")
        out[symbol] = result
        if result.get("error"):
            failed += 1
        else:
            ok += 1
        if i % 100 == 0:
            OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"  {i}/{len(todo)}  성공 {ok} 실패 {failed} corp_code없음 {no_corp}")
        time.sleep(_SLEEP)

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n✅ 성공 {ok} / 실패 {failed} / corp_code 없음 {no_corp} → {OUT_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
