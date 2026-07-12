"""
한국투자증권 (KIS) Open API Provider
- REST API 기반 실시간 현재가 조회
- 환경변수: KIS_APP_KEY, KIS_APP_SECRET
- 완전 선택적: 환경변수 없으면 자동 건너뜀
"""

import asyncio
import os
import time
import requests
from typing import Optional

from .base import BaseProvider, StockQuote

_BASE_URL = "https://openapi.koreainvestment.com:9443"
_REQUEST_TIMEOUT = 5


class KISProvider(BaseProvider):
    name = "kis"

    def __init__(self):
        self._app_key = os.getenv("KIS_APP_KEY", "").strip()
        self._app_secret = os.getenv("KIS_APP_SECRET", "").strip()
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    def is_configured(self) -> bool:
        return bool(self._app_key and self._app_secret)

    def _acquire_token_sync(self) -> Optional[str]:
        """access_token 발급 (동기)"""
        try:
            resp = requests.post(
                f"{_BASE_URL}/oauth2/tokenP",
                json={
                    "grant_type": "client_credentials",
                    "appkey": self._app_key,
                    "appsecret": self._app_secret,
                },
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                print(f"[KISProvider] 토큰 발급 실패: {resp.status_code} {resp.text[:200]}")
                return None
            data = resp.json()
            token = data.get("access_token")
            # 토큰 유효기간: 약 24시간, 안전하게 23시간으로 설정
            self._token_expires_at = time.time() + 23 * 3600
            return token
        except Exception as e:
            print(f"[KISProvider] 토큰 발급 예외: {e}")
            return None

    async def _ensure_token(self) -> Optional[str]:
        """토큰 보장 (만료 시 재발급, Lock으로 race condition 방지)"""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        async with self._token_lock:
            # Double-check after acquiring lock
            if self._access_token and time.time() < self._token_expires_at:
                return self._access_token
            self._access_token = await asyncio.to_thread(self._acquire_token_sync)
            return self._access_token

    def _fetch_price_sync(self, symbol: str, token: str) -> Optional[StockQuote]:
        """단일 종목 현재가 REST 조회 (동기)"""
        try:
            headers = {
                "Content-Type": "application/json; charset=UTF-8",
                "authorization": f"Bearer {token}",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
                "tr_id": "FHKST01010100",
                "custtype": "P",
            }
            params = {
                "FID_COND_MRKT_DIV_CODE": "UN",
                "FID_INPUT_ISCD": symbol,
            }
            resp = requests.get(
                f"{_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers=headers,
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            output = data.get("output", {})
            close = int(output.get("stck_prpr", "0") or "0")
            if close == 0:
                return None

            from datetime import datetime
            volume = int(output.get("acml_vol", "0") or "0")
            # volume == 0 이면 장 미개시(공휴일·주말) → 오늘 날짜를 붙이지 않음
            trade_date = datetime.now().strftime("%Y-%m-%d") if volume > 0 else None

            # PER/PBR/EPS/BPS 파싱 (KIS API 응답 필드)
            def _parse_float(val: str) -> Optional[float]:
                try:
                    v = float(val or "0")
                    return v if v != 0 else None
                except (ValueError, TypeError):
                    return None

            return StockQuote(
                symbol=symbol,
                name=output.get("hts_kor_isnm", symbol),
                date=trade_date,
                open=int(output.get("stck_oprc", "0") or "0"),
                high=int(output.get("stck_hgpr", "0") or "0"),
                low=int(output.get("stck_lwpr", "0") or "0"),
                close=close,
                volume=volume,
                source="kis_total",
                timestamp=time.time(),
                prev_close=int(output.get("stck_sdpr", "0") or "0"),
                change_rate=float(output.get("prdy_ctrt", "0") or "0"),
                per=_parse_float(output.get("per", "")),
                pbr=_parse_float(output.get("pbr", "")),
                eps=_parse_float(output.get("eps", "")),
                bps=_parse_float(output.get("bps", "")),
                # 종목상태구분코드: 51=관리종목 52=투자위험 53=투자경고 54=투자주의
                #                  55=신용가능 57=증거금100% 58=거래정지 59=단기과열
                trading_halted=(
                    output["iscd_stat_cls_code"] == "58"
                    if output.get("iscd_stat_cls_code") else None
                ),
            )
        except Exception as e:
            print(f"[KISProvider] {symbol} 조회 실패: {e}")
            return None

    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        if not self.is_configured():
            return None
        token = await self._ensure_token()
        if not token:
            return None
        return await asyncio.to_thread(self._fetch_price_sync, symbol, token)

    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        if not self.is_configured():
            return {}
        token = await self._ensure_token()
        if not token:
            return {}

        # KIS rate limit: 20 req/sec → 5종목 동시 요청은 안전 범위
        quotes = await asyncio.gather(
            *(asyncio.to_thread(self._fetch_price_sync, sym, token) for sym in symbols),
            return_exceptions=True,
        )
        return {
            sym: q
            for sym, q in zip(symbols, quotes)
            if isinstance(q, StockQuote) and q is not None
        }

    def _fetch_investor_trading_sync(
        self, symbol: str, token: str, market_code: str = "J"
    ) -> Optional[list[dict]]:
        """투자자별 매매동향 조회 (동기) — TR_ID: FHKST01010900

        API 응답의 `output` 배열(최대 30일)에서 파싱.
        당일(장중) 행은 투자자 수량이 빈 문자열이므로 제외.
        """
        try:
            headers = {
                "Content-Type": "application/json; charset=UTF-8",
                "authorization": f"Bearer {token}",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
                "tr_id": "FHKST01010900",
                "custtype": "P",
            }
            params = {
                "FID_COND_MRKT_DIV_CODE": market_code,
                "FID_INPUT_ISCD": symbol,
            }
            resp = requests.get(
                f"{_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor",
                headers=headers,
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            if data.get("rt_cd") != "0":
                return None

            output = data.get("output") or []
            if not output:
                return None

            def _parse_int(val: str) -> int:
                try:
                    return int(val or "0")
                except (ValueError, TypeError):
                    return 0

            rows = []
            for row in output:
                # 당일 장중 행은 투자자 수량이 빈 문자열 → 제외
                if not row.get("prsn_ntby_qty", "").strip():
                    continue

                date_raw = row.get("stck_bsop_date", "")
                if len(date_raw) == 8:
                    date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"
                else:
                    date = date_raw

                rows.append({
                    "date": date,
                    "close_price": _parse_int(row.get("stck_clpr")),
                    "individual_net": _parse_int(row.get("prsn_ntby_qty")),
                    "foreign_net": _parse_int(row.get("frgn_ntby_qty")),
                    "institutional_net": _parse_int(row.get("orgn_ntby_qty")),
                    "individual_net_amount": _parse_int(row.get("prsn_ntby_tr_pbmn")),
                    "foreign_net_amount": _parse_int(row.get("frgn_ntby_tr_pbmn")),
                    "institutional_net_amount": _parse_int(row.get("orgn_ntby_tr_pbmn")),
                    "individual_buy_vol": _parse_int(row.get("prsn_shnu_vol")),
                    "foreign_buy_vol": _parse_int(row.get("frgn_shnu_vol")),
                    "institutional_buy_vol": _parse_int(row.get("orgn_shnu_vol")),
                    "individual_sell_vol": _parse_int(row.get("prsn_seln_vol")),
                    "foreign_sell_vol": _parse_int(row.get("frgn_seln_vol")),
                    "institutional_sell_vol": _parse_int(row.get("orgn_seln_vol")),
                })
            return rows if rows else None
        except Exception as e:
            print(f"[KISProvider] {symbol} 투자자 매매동향 조회 실패: {e}")
            return None

    async def get_investor_trading(self, symbol: str) -> Optional[list[dict]]:
        """투자자별 일별 매매동향 — KOSPI 우선, 실패 시 KOSDAQ 재시도"""
        if not self.is_configured():
            return None
        token = await self._ensure_token()
        if not token:
            return None

        for market_code in ("J", "Q"):
            result = await asyncio.to_thread(
                self._fetch_investor_trading_sync, symbol, token, market_code
            )
            if result:
                return result
        return None

    async def get_today_investor(self, symbol: str) -> Optional[dict]:
        """당일 투자자 누적 매매 집계 — output1에서 파싱 (장중/장후에만 유효)"""
        if not self.is_configured():
            return None
        token = await self._ensure_token()
        if not token:
            return None

        def _fetch(symbol: str, token: str, market_code: str) -> Optional[dict]:
            try:
                headers = {
                    "Content-Type": "application/json; charset=UTF-8",
                    "authorization": f"Bearer {token}",
                    "appkey": self._app_key,
                    "appsecret": self._app_secret,
                    "tr_id": "FHKST01010900",
                    "custtype": "P",
                }
                resp = requests.get(
                    f"{_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor",
                    headers=headers,
                    params={"FID_COND_MRKT_DIV_CODE": market_code, "FID_INPUT_ISCD": symbol},
                    timeout=_REQUEST_TIMEOUT,
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                if data.get("rt_cd") != "0":
                    return None
                o1 = data.get("output1") or {}
                if not isinstance(o1, dict):
                    return None

                def _int(val: str) -> int:
                    try:
                        return int(val or "0")
                    except (ValueError, TypeError):
                        return 0

                individual = _int(o1.get("prsn_ntby_qty"))
                foreign = _int(o1.get("frgn_ntby_qty"))
                institutional = _int(o1.get("orgn_ntby_qty"))
                # 모두 0이면 장 미개시 상태 → None 반환
                if individual == 0 and foreign == 0 and institutional == 0:
                    return None

                from datetime import date
                return {
                    "date": date.today().strftime("%Y-%m-%d"),
                    "individual_net": individual,
                    "foreign_net": foreign,
                    "institutional_net": institutional,
                    "individual_net_amount": _int(o1.get("prsn_ntby_tr_pbmn")),
                    "foreign_net_amount": _int(o1.get("frgn_ntby_tr_pbmn")),
                    "institutional_net_amount": _int(o1.get("orgn_ntby_tr_pbmn")),
                }
            except Exception as e:
                print(f"[KISProvider] {symbol} output1 파싱 실패: {e}")
                return None

        for market_code in ("J", "Q"):
            result = await asyncio.to_thread(_fetch, symbol, token, market_code)
            if result:
                return result
        return None

    async def health_check(self) -> bool:
        if not self.is_configured():
            return False
        token = await self._ensure_token()
        if not token:
            return False
        quote = await asyncio.to_thread(self._fetch_price_sync, "005930", token)
        return quote is not None
