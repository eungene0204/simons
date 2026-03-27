"""
KRX 시세 데이터 클라이언트
- 1순위: KRX Open API (data-dbg.krx.co.kr) — 서비스 승인 후 사용 가능
- 2순위: pykrx — KRX 공개 데이터 스크래핑, 서비스 승인 불필요
- 갱신: 전일 데이터 익일 08:00 업데이트 (EOD)
"""

import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"

def _get_auth_key() -> str:
    return os.getenv("KRX_API_KEY", "").strip()

def _headers() -> dict:
    return {
        "AUTH_KEY": _get_auth_key(),
        "Content-Type": "application/json",
    }

def _latest_trading_date() -> str:
    """가장 최근 정산된 영업일 반환 (YYYYMMDD)
    KRX EOD 데이터는 전일분이 익일 08:00에 제공되므로 항상 전 영업일을 반환한다.
    """
    candidate = datetime.now() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.strftime("%Y%m%d")

def _request(endpoint: str, params: dict) -> list[dict]:
    url = f"{BASE_URL}/{endpoint}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get("OutBlock_1", [])

def _is_api_available() -> bool:
    """KRX Open API 승인 여부 확인"""
    if not _get_auth_key():
        return False
    try:
        rows = _request("idx/kospi_dd_trd", {"basDd": _latest_trading_date()})
        return len(rows) > 0
    except Exception:
        return False


# ─────────────────────────────────────────────
# pykrx 폴백 (KRX Open API 미승인 시)
# ─────────────────────────────────────────────

def _pykrx_get_multiple_prices(symbols: list[str], date: Optional[str] = None) -> dict[str, dict]:
    """pykrx로 여러 종목 종가 조회"""
    from pykrx import stock as pykrx_stock

    date = date or _latest_trading_date()
    result: dict[str, dict] = {}

    for sym in symbols:
        try:
            df = pykrx_stock.get_market_ohlcv_by_date(date, date, sym)
            if df.empty:
                continue
            row = df.iloc[0]
            name = pykrx_stock.get_market_ticker_name(sym)
            result[sym] = {
                "symbol": sym,
                "name": name,
                "date": date,
                "open": int(row.get("시가", 0)),
                "high": int(row.get("고가", 0)),
                "low":  int(row.get("저가", 0)),
                "close": int(row.get("종가", 0)),
                "volume": int(row.get("거래량", 0)),
            }
        except Exception:
            continue
    return result


def _pykrx_get_stock_price(symbol: str, date: Optional[str] = None) -> Optional[dict]:
    result = _pykrx_get_multiple_prices([symbol], date)
    return result.get(symbol)


# ─────────────────────────────────────────────
# 종목 목록
# ─────────────────────────────────────────────

def get_stock_list(market: str = "STK", base_date: Optional[str] = None) -> pd.DataFrame:
    """
    상장 종목 목록 조회
    market: STK(코스피), KSQ(코스닥)
    반환: isin_cd, short_isin_cd, isu_nm, mkt_nm, ...
    """
    date = base_date or _latest_trading_date()
    endpoint = "sto/stk_isu_base_info" if market == "STK" else "sto/ksq_isu_base_info"
    rows = _request(endpoint, {"basDd": date})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# 일별 OHLCV
# ─────────────────────────────────────────────

def get_daily_ohlcv(market: str = "STK", base_date: Optional[str] = None) -> pd.DataFrame:
    """
    전 종목 일별 시세 조회 (마감 후 익일 08:00 갱신)
    market: STK(코스피), KSQ(코스닥)
    반환 컬럼: ISU_SRT_CD, ISU_ABBRV, TRD_DD, MKT_NM,
               TDD_CLSPRC, TDD_OPNPRC, TDD_HGPRC, TDD_LWPRC,
               ACC_TRDVOL, ACC_TRDVAL, MKTCAP
    """
    date = base_date or _latest_trading_date()
    endpoint = "sto/stk_bydd_trd" if market == "STK" else "sto/ksq_bydd_trd"
    rows = _request(endpoint, {"basDd": date})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # 가격 컬럼 숫자형 변환
    price_cols = ["TDD_CLSPRC", "TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC",
                  "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP"]
    for col in price_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
    return df


def get_stock_price(symbol: str, base_date: Optional[str] = None) -> Optional[dict]:
    """
    특정 종목 단일 일봉 조회 (KRX API → pykrx 폴백)
    symbol: 종목코드 6자리 (예: '005930')
    반환: {symbol, name, date, open, high, low, close, volume}
    """
    if _is_api_available():
        for market in ["STK", "KSQ"]:
            df = get_daily_ohlcv(market, base_date)
            if df.empty:
                continue
            row = df[df["ISU_CD"] == symbol]
            if not row.empty:
                r = row.iloc[0]
                return {
                    "symbol": symbol,
                    "name": r.get("ISU_NM", ""),
                    "date": r.get("BAS_DD", ""),
                    "open": int(r.get("TDD_OPNPRC") or 0),
                    "high": int(r.get("TDD_HGPRC") or 0),
                    "low":  int(r.get("TDD_LWPRC") or 0),
                    "close": int(r.get("TDD_CLSPRC") or 0),
                    "volume": int(r.get("ACC_TRDVOL") or 0),
                    "source": "krx_api",
                }
        return None
    return _pykrx_get_stock_price(symbol, base_date)


def get_multiple_prices(symbols: list[str], base_date: Optional[str] = None) -> dict[str, dict]:
    """
    여러 종목 가격 한 번에 조회 (KRX API → pykrx 폴백)
    반환: {symbol: {symbol, name, date, open, high, low, close, volume}}
    """
    if _is_api_available():
        date = base_date or _latest_trading_date()
        result: dict[str, dict] = {}
        sym_set = set(symbols)
        for market in ["STK", "KSQ"]:
            df = get_daily_ohlcv(market, date)
            if df.empty:
                continue
            matched = df[df["ISU_CD"].isin(sym_set)]
            for _, r in matched.iterrows():
                sym = r["ISU_CD"]
                result[sym] = {
                    "symbol": sym,
                    "name": r.get("ISU_NM", ""),
                    "date": r.get("BAS_DD", ""),
                    "open": int(r.get("TDD_OPNPRC") or 0),
                    "high": int(r.get("TDD_HGPRC") or 0),
                    "low":  int(r.get("TDD_LWPRC") or 0),
                    "close": int(r.get("TDD_CLSPRC") or 0),
                    "volume": int(r.get("ACC_TRDVOL") or 0),
                    "source": "krx_api",
                }
        return result
    return _pykrx_get_multiple_prices(symbols, base_date)


# ─────────────────────────────────────────────
# 지수
# ─────────────────────────────────────────────

def get_index(index_code: str = "1", base_date: Optional[str] = None) -> Optional[dict]:
    """
    지수 조회
    index_code: '1'=KOSPI, '2'=KOSDAQ
    반환: {name, close, change_pct, ...}
    """
    date = base_date or _latest_trading_date()
    endpoint = "idx/kospi_dd_trd" if index_code == "1" else "idx/kosdaq_dd_trd"
    rows = _request(endpoint, {"basDd": date})
    if not rows:
        return None
    # "코스피" / "코스닥" 행만 추출 (합산/섹터 행 제외)
    target = "코스피" if index_code == "1" else "코스닥"
    r = next((row for row in rows if row.get("IDX_NM") == target), rows[0])
    return {
        "date": r.get("BAS_DD"),
        "name": r.get("IDX_NM"),
        "close": float(r.get("CLSPRC_IDX") or 0),
        "open": float(r.get("OPNPRC_IDX") or 0),
        "high": float(r.get("HGPRC_IDX") or 0),
        "low": float(r.get("LWPRC_IDX") or 0),
        "change": float(r.get("CMPPREVDD_IDX") or 0),
        "change_pct": float(r.get("FLUC_RT") or 0),
    }


# ─────────────────────────────────────────────
# 실시간 지수 (pykrx — 장중 현재가 반영)
# ─────────────────────────────────────────────

def get_index_realtime(index_code: str = "1") -> Optional[dict]:
    """
    pykrx로 실시간 지수 조회 (장중에도 현재 가격 반영)
    index_code: '1'=KOSPI, '2'=KOSDAQ
    반환: {name, close, open, high, low, change, change_pct, date, source}
    """
    from pykrx import stock as pykrx_stock

    ticker = "1001" if index_code == "1" else "2001"
    name = "코스피" if index_code == "1" else "코스닥"
    today = datetime.now().strftime("%Y%m%d")
    prev_day = _latest_trading_date()

    try:
        df_today = pykrx_stock.get_index_ohlcv_by_date(today, today, ticker)
        df_prev = pykrx_stock.get_index_ohlcv_by_date(prev_day, prev_day, ticker)

        # 오늘 데이터 없으면(장 전/주말) 전일 데이터 반환
        if df_today is None or df_today.empty:
            if df_prev is None or df_prev.empty:
                return None
            row = df_prev.iloc[0]
            close = float(row.get("종가", 0))
            prev_prev = pykrx_stock.get_index_ohlcv_by_date(
                (datetime.strptime(prev_day, "%Y%m%d") - timedelta(days=5)).strftime("%Y%m%d"),
                prev_day, ticker
            )
            prev_close = float(prev_prev.iloc[-2]["종가"]) if prev_prev is not None and len(prev_prev) >= 2 else 0.0
            change = round(close - prev_close, 2) if prev_close else 0.0
            change_pct = round((change / prev_close) * 100, 2) if prev_close else float(row.get("등락률", 0))
            return {
                "date": prev_day,
                "name": name,
                "close": close,
                "open": float(row.get("시가", 0)),
                "high": float(row.get("고가", 0)),
                "low": float(row.get("저가", 0)),
                "change": change,
                "change_pct": change_pct,
                "source": "pykrx",
            }

        row = df_today.iloc[0]
        close = float(row.get("종가", 0))
        prev_close = float(df_prev.iloc[0].get("종가", 0)) if df_prev is not None and not df_prev.empty else 0.0
        change = round(close - prev_close, 2) if prev_close else 0.0
        change_pct = round((change / prev_close) * 100, 2) if prev_close else float(row.get("등락률", 0))

        return {
            "date": today,
            "name": name,
            "close": close,
            "open": float(row.get("시가", 0)),
            "high": float(row.get("고가", 0)),
            "low": float(row.get("저가", 0)),
            "change": change,
            "change_pct": change_pct,
            "source": "pykrx",
        }
    except Exception as e:
        print(f"[pykrx] get_index_realtime {index_code} 실패: {e}")
        return None


# ─────────────────────────────────────────────
# 연결 테스트
# ─────────────────────────────────────────────

def health_check() -> dict:
    """데이터 소스 연결 상태 확인"""
    date = _latest_trading_date()
    # KRX Open API 시도
    try:
        rows = _request("idx/kospi_dd_trd", {"basDd": date})
        if rows:
            return {"status": "ok", "source": "krx_api", "date": date}
    except Exception as e:
        krx_error = str(e)

    # pykrx 폴백
    try:
        from pykrx import stock as pykrx_stock
        df = pykrx_stock.get_market_ohlcv_by_date(date, date, "005930")
        if not df.empty:
            return {"status": "ok", "source": "pykrx", "date": date,
                    "note": f"KRX API 미승인 — pykrx 사용 중 ({krx_error})"}
    except Exception as e:
        return {"status": "error", "source": "none",
                "krx_error": krx_error, "pykrx_error": str(e)}

    return {"status": "empty", "source": "pykrx", "date": date}
