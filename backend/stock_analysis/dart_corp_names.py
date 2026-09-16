"""DART 기업 고유번호 목록(corpCode.xml) — 종목코드별 **공식 회사명**.

`data/korea-stocks.json`의 이름 기준은 KRX KIND 상장법인목록의 '회사명'인데, 프로덕션 박스
IP는 kind.krx.co.kr에서 403(Access Denied)으로 차단된다(2026-09-16 실측). DART의 corp_name은
KIND 회사명과 현재 상장 2,649종목 전부 일치해(차이 0) 같은 공식 회사명을 박스에서 받을 수
있는 출처다. 일일 종목명 갱신(`scripts/refresh_stock_names.py`)이 쓴다.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import requests

_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def dart_api_key() -> str:
    key = os.getenv("DART_API_KEY", "").strip()
    if not key and _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("DART_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    return key


def fetch_dart_corp_names(api_key: str) -> dict[str, str]:
    """종목코드 → 공식 회사명(상장 이력이 있는 법인 전부).

    오류 응답(키 오류·한도 초과)은 ZIP이 아니라 상태 메시지로 오므로 예외를 올린다.
    """
    r = requests.get(_CORP_CODE_URL, params={"crtfc_key": api_key}, timeout=120)
    r.raise_for_status()
    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            xml = zf.read(zf.namelist()[0])
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"DART corpCode 오류 응답: {r.text[:200]}") from exc
    names: dict[str, str] = {}
    for item in ElementTree.fromstring(xml).iter("list"):
        stock = (item.findtext("stock_code") or "").strip()
        name = (item.findtext("corp_name") or "").strip()
        if stock and name:
            names[stock] = name
    return names
