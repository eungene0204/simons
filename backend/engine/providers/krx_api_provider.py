"""
KRX Open API Provider (기존 krx_client.py 래핑)
- KRX 공식 API (data-dbg.krx.co.kr), 서비스 승인 필요
- 환경변수: KRX_API_KEY
- EOD 데이터 (익일 08:00 갱신)
"""

import asyncio
import os
import time
from typing import Optional
from datetime import datetime, timedelta

from .base import BaseProvider, StockQuote


def _latest_trading_date() -> str:
    candidate = datetime.now() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.strftime("%Y%m%d")


def _fetch_krx_api_prices(symbols: list[str], date: Optional[str] = None) -> dict[str, StockQuote]:
    """KRX Open API로 종목 시세 조회 (동기)"""
    import requests

    api_key = os.getenv("KRX_API_KEY", "").strip()
    if not api_key:
        return {}

    base_url = "https://data-dbg.krx.co.kr/svc/apis"
    headers = {"AUTH_KEY": api_key, "Content-Type": "application/json"}
    date = date or _latest_trading_date()
    date_str = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    sym_set = set(symbols)
    result: dict[str, StockQuote] = {}
    now = time.time()

    for market, endpoint in [("STK", "sto/stk_bydd_trd"), ("KSQ", "sto/ksq_bydd_trd")]:
        try:
            resp = requests.get(
                f"{base_url}/{endpoint}",
                headers=headers,
                params={"basDd": date},
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            rows = resp.json().get("OutBlock_1", [])
            for r in rows:
                sym = r.get("ISU_SRT_CD") or r.get("ISU_CD", "")
                if sym not in sym_set:
                    continue

                def _int(val):
                    try:
                        return int(str(val).replace(",", ""))
                    except (ValueError, TypeError):
                        return 0

                close = _int(r.get("TDD_CLSPRC"))
                if close == 0:
                    continue

                result[sym] = StockQuote(
                    symbol=sym,
                    name=r.get("ISU_ABBRV", sym),
                    date=date_str,
                    open=_int(r.get("TDD_OPNPRC")),
                    high=_int(r.get("TDD_HGPRC")),
                    low=_int(r.get("TDD_LWPRC")),
                    close=close,
                    volume=_int(r.get("ACC_TRDVOL")),
                    source="krx_api",
                    timestamp=now,
                )
        except Exception as e:
            print(f"[KRXApiProvider] {market} 조회 실패: {e}")
            continue

    return result


class KRXApiProvider(BaseProvider):
    name = "krx_api"

    def is_configured(self) -> bool:
        return bool(os.getenv("KRX_API_KEY", "").strip())

    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        result = await asyncio.to_thread(_fetch_krx_api_prices, [symbol])
        return result.get(symbol)

    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        return await asyncio.to_thread(_fetch_krx_api_prices, symbols)

    async def health_check(self) -> bool:
        if not self.is_configured():
            return False
        result = await asyncio.to_thread(_fetch_krx_api_prices, ["005930"])
        return "005930" in result
