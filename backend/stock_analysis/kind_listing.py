"""KRX KIND 상장법인목록 — 현재 상장 종목의 **공식 회사명** 정본.

`data/korea-stocks.json`의 이름은 이 목록의 '회사명' 컬럼이다(거래소 약칭 '현대차'가 아니라
공식 회사명 '현대자동차'). 전체 명부 동기화(`POST /sync-stocks`)와 매일 이름만 갱신하는
`scripts/refresh_stock_names.py`가 같은 조회를 쓴다(DRY).
"""

from __future__ import annotations

import io
from typing import Optional

import requests

_KIND_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do"
_MARKETS = (("stockMkt", "KOSPI"), ("kosdaqMkt", "KOSDAQ"))


def fetch_kind_listing(session: Optional[requests.Session] = None) -> list[dict]:
    """KOSPI+KOSDAQ 상장법인 행 목록 — {symbol, name, market, industry}.

    한 시장이라도 조회에 실패하면 예외를 그대로 올린다(반쪽 목록으로 명부를 쓰지 않는다).
    """
    import pandas as pd

    http = session or requests
    rows: list[dict] = []
    for market_type, market_label in _MARKETS:
        r = http.get(
            _KIND_URL,
            params={"method": "download", "searchType": "13", "marketType": market_type},
            timeout=15,
        )
        r.raise_for_status()
        r.encoding = "euc-kr"
        df = pd.read_html(io.StringIO(r.text))[0]
        for _, row in df.iterrows():
            symbol = str(row.get("종목코드", "")).strip().zfill(6)
            name = str(row.get("회사명", "")).strip()
            if not symbol or not name:
                continue
            rows.append({
                "symbol": symbol,
                "name": name,
                "market": market_label,
                "industry": str(row.get("업종", "") or "").strip(),
            })
    return rows
