"""
Fundamental enrichment helpers.

KIS financial-ratio API is the primary source for annual EPS/BPS/ROE/debt ratio data.
Naver Finance scraping remains as a fallback for EPS/BPS/ROE/debt ratio when KIS is unavailable.
"""

import os
import re
import json
import time
import logging
from pathlib import Path
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
_NAVER_URL = "https://finance.naver.com/item/main.naver?code={symbol}"
_KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
_REQUEST_TIMEOUT = 15
_KIS_TOKEN: Optional[str] = None
_KIS_TOKEN_EXPIRES_AT: float = 0.0
_KIS_TOKEN_FAIL_UNTIL: float = 0.0  # 토큰 발급 실패 시 쿨다운 (120초)
_CACHE_MAX_AGE_DAYS = 90
# KIS/Naver 둘 다 데이터가 없는 종목(REITs, 신규상장 등)은 재시도해도 매번 실패한다.
# 짧은 TTL로 "실패했다"는 사실 자체를 캐싱해 백테스트마다 반복되는 라이브 호출을 줄인다.
_NEGATIVE_CACHE_TTL_DAYS = 7

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CACHE_DIR = _PROJECT_ROOT / "data" / "fundamentals"

load_dotenv(_PROJECT_ROOT / ".env")


def _cache_path(symbol: str) -> Path:
    return _CACHE_DIR / f"{symbol}.json"


def _negative_cache_path(symbol: str) -> Path:
    return _CACHE_DIR / f"{symbol}.nodata.json"


def _is_recently_confirmed_empty(symbol: str) -> bool:
    """최근 _NEGATIVE_CACHE_TTL_DAYS 이내에 이미 조회 실패가 확인됐는지."""
    path = _negative_cache_path(symbol)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        checked_at = data.get("checked_at", "")
        if not checked_at:
            return False
        age = (pd.Timestamp.now() - pd.Timestamp(checked_at)).days
        return age <= _NEGATIVE_CACHE_TTL_DAYS
    except Exception:
        return False


def _write_negative_cache(symbol: str) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _negative_cache_path(symbol).write_text(
        json.dumps({"symbol": symbol, "checked_at": pd.Timestamp.now().isoformat()}),
        encoding="utf-8",
    )


def _read_cache(symbol: str) -> Optional[List[Dict]]:
    """로컬 JSON 캐시에서 펀더멘털 데이터를 읽는다. 만료 시 None 반환."""
    path = _cache_path(symbol)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = data.get("fetched_at", "")
        if fetched_at:
            age = (pd.Timestamp.now() - pd.Timestamp(fetched_at)).days
            if age > _CACHE_MAX_AGE_DAYS:
                return None
        return data.get("fundamentals")
    except Exception:
        return None


def _write_cache(symbol: str, fundamentals: List[Dict]) -> None:
    """펀더멘털 데이터를 로컬 JSON 캐시에 저장한다."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(symbol)
    payload = {
        "symbol": symbol,
        "fetched_at": pd.Timestamp.now().isoformat(),
        "fundamentals": fundamentals,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_kis_token() -> Optional[str]:
    global _KIS_TOKEN, _KIS_TOKEN_EXPIRES_AT, _KIS_TOKEN_FAIL_UNTIL

    if _KIS_TOKEN and time.time() < _KIS_TOKEN_EXPIRES_AT:
        return _KIS_TOKEN

    # 최근 토큰 발급 실패 시 쿨다운 (rate limit 방지)
    if time.time() < _KIS_TOKEN_FAIL_UNTIL:
        return None

    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    if not app_key or not app_secret:
        return None

    try:
        resp = requests.post(
            f"{_KIS_BASE_URL}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": app_key,
                "appsecret": app_secret,
            },
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("[KIS] token request failed: %s %s", resp.status_code, resp.text[:200])
            _KIS_TOKEN_FAIL_UNTIL = time.time() + 120
            return None

        token = resp.json().get("access_token")
        if not token:
            return None

        _KIS_TOKEN = token
        _KIS_TOKEN_EXPIRES_AT = time.time() + 23 * 3600
        _KIS_TOKEN_FAIL_UNTIL = 0.0
        return _KIS_TOKEN
    except Exception as e:
        logger.warning("[KIS] token request failed: %s", e)
        _KIS_TOKEN_FAIL_UNTIL = time.time() + 120
        return None


def _parse_kis_stac_yymm(value: str) -> Optional[str]:
    if not value:
        return None
    try:
        dt = pd.Timestamp(year=int(value[:4]), month=int(value[4:6]), day=1) + pd.offsets.MonthEnd(0)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


# Annual fundamental metrics stored per parquet (forward-filled from year-end reports).
# eps/bps/roe/debt_ratio are the originals; the rest were added to expose growth,
# profitability and stability factors that the same KIS calls already return.
ANNUAL_FUNDAMENTAL_KEYS = [
    "eps", "bps", "roe_or_gpa", "debt_ratio",
    "sps", "revenue_growth", "operating_income_growth", "net_income_growth", "reserve_ratio",
    "roa", "net_margin", "gross_margin", "current_ratio", "quick_ratio",
]

# KIS finance endpoints → {response_field: our_key}. Three endpoints, merged by year-end.
_KIS_FINANCIAL_RATIO_MAP = {
    "eps": "eps", "bps": "bps", "roe_val": "roe_or_gpa", "lblt_rate": "debt_ratio",
    "sps": "sps", "grs": "revenue_growth", "bsop_prfi_inrt": "operating_income_growth",
    "ntin_inrt": "net_income_growth", "rsrv_rate": "reserve_ratio",
}
_KIS_PROFIT_RATIO_MAP = {
    "cptl_ntin_rate": "roa", "sale_ntin_rate": "net_margin", "sale_totl_rate": "gross_margin",
}
_KIS_STABILITY_RATIO_MAP = {
    "crnt_rate": "current_ratio", "quck_rate": "quick_ratio",
}
_KIS_FINANCE_ENDPOINTS = [
    ("financial-ratio", "FHKST66430300", _KIS_FINANCIAL_RATIO_MAP),
    ("profit-ratio", "FHKST66430400", _KIS_PROFIT_RATIO_MAP),
    ("stability-ratio", "FHKST66430600", _KIS_STABILITY_RATIO_MAP),
]


def _parse_kis_ratio_output(output: list, field_map: Dict[str, str]) -> Dict[str, Dict]:
    """KIS finance output rows → {year_end: {our_key: value}} per ``field_map``."""
    by_year: Dict[str, Dict] = {}
    if not isinstance(output, list):
        return by_year
    for row in output:
        if not isinstance(row, dict):
            continue
        year_end = _parse_kis_stac_yymm(str(row.get("stac_yymm", "")).strip())
        if not year_end:
            continue
        bucket = by_year.setdefault(year_end, {})
        for src, key in field_map.items():
            if key in bucket:  # first endpoint to provide a key wins (no overwrite)
                continue
            val = _parse_number(str(row.get(src, "")).strip())
            if val is not None:
                bucket[key] = val
    return by_year


def _parse_kis_financial_ratio_output(output: list[dict]) -> Optional[List[Dict]]:
    """Parse a single financial-ratio output into the fundamentals list (kept for callers)."""
    by_year = _parse_kis_ratio_output(output, _KIS_FINANCIAL_RATIO_MAP)
    result = [{"year_end": d, **vals} for d, vals in sorted(by_year.items(), reverse=True) if vals]
    return result or None


def _fetch_kis_finance(symbol: str, headers: dict, path: str) -> list:
    """GET one KIS finance endpoint; return its ``output`` list ([] on failure)."""
    params = {"FID_DIV_CLS_CODE": "0", "fid_cond_mrkt_div_code": "J", "fid_input_iscd": symbol}
    try:
        resp = requests.get(
            f"{_KIS_BASE_URL}/uapi/domestic-stock/v1/finance/{path}",
            headers=headers, params=params, timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("[%s] KIS %s failed: %s", symbol, path, resp.status_code)
            return []
        return resp.json().get("output", []) or []
    except Exception as e:
        logger.warning("[%s] KIS %s failed: %s", symbol, path, e)
        return []


def _fetch_fundamentals_from_kis(symbol: str) -> Optional[List[Dict]]:
    """Merge financial-ratio + profit-ratio + stability-ratio into one per-year list."""
    token = _get_kis_token()
    if not token:
        return None

    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "authorization": f"Bearer {token}",
        "appkey": os.getenv("KIS_APP_KEY", "").strip(),
        "appsecret": os.getenv("KIS_APP_SECRET", "").strip(),
        "custtype": "P",
    }

    merged: Dict[str, Dict] = {}
    for path, tr_id, field_map in _KIS_FINANCE_ENDPOINTS:
        output = _fetch_kis_finance(symbol, {**headers, "tr_id": tr_id}, path)
        for year_end, vals in _parse_kis_ratio_output(output, field_map).items():
            merged.setdefault(year_end, {}).update(vals)

    result = [{"year_end": d, **vals} for d, vals in sorted(merged.items(), reverse=True) if vals]
    return result or None


def fetch_fundamentals(symbol: str, retry: int = 2, use_cache: bool = True) -> Optional[List[Dict]]:
    """Fetch annual fundamentals for parquet enrichment.

    1순위: 로컬 JSON 캐시 (90일 이내)
    2순위: 최근 재조회 실패 캐시 (7일 이내) — REITs 등 항상 실패하는 종목의 반복 호출 방지
    3순위: KIS financial-ratio API
    4순위: Naver Finance 스크래핑

    Returns:
        [{"year_end": "2025-12-31", "eps": 6564.0, "bps": 63997.0, "roe_or_gpa": 10.85}, ...]
        or None.
    """
    if use_cache:
        cached = _read_cache(symbol)
        if cached:
            return cached
        if _is_recently_confirmed_empty(symbol):
            return None

    result = _fetch_fundamentals_from_kis(symbol)

    if not result:
        url = _NAVER_URL.format(symbol=symbol)
        for attempt in range(retry + 1):
            try:
                r = requests.get(url, headers=_HEADERS, timeout=15)
                if r.status_code != 200:
                    continue
                result = _parse_fundamentals(r.text)
                if result:
                    break
            except Exception as e:
                logger.warning(f"[{symbol}] fundamental fetch attempt {attempt+1} failed: {e}")
                if attempt < retry:
                    time.sleep(0.5)

    if result:
        _write_cache(symbol, result)
    else:
        _write_negative_cache(symbol)

    return result


def _parse_fundamentals(html: str) -> Optional[List[Dict]]:
    """HTML에서 주요재무정보 테이블을 파싱하여 연도별 EPS/BPS/ROE를 추출한다."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    for table in tables:
        text = table.get_text()
        if "EPS" not in text or "BPS" not in text or "주요재무정보" not in text:
            continue

        rows = table.find_all("tr")
        if len(rows) < 3:
            continue

        # Row 0: header — "주요재무정보 | 최근 연간 실적 | 최근 분기 실적"
        # Row 1: period labels — ['2023.12', '2024.12', '2025.12', '2026.12(E)', ...]
        # Naver는 연간 4개 + 분기 6개 구조. "최근 연간 실적" colspan으로 연간 범위 파악.
        header_cells = rows[0].find_all(["th", "td"])
        annual_col_count = 0
        for cell in header_cells:
            cell_text = cell.get_text(strip=True)
            if "연간" in cell_text:
                annual_col_count = int(cell.get("colspan", 1))
                break

        period_cells = rows[1].find_all(["th", "td"])
        periods = [c.get_text(strip=True) for c in period_cells]

        # 연간 데이터만 사용 (colspan으로 범위 결정), 추정치(E) 제외
        annual_periods: List[Tuple[int, str]] = []  # (column_index, year_end_date)
        annual_range = annual_col_count if annual_col_count > 0 else 4
        for i, p in enumerate(periods[:annual_range]):
            if "(E)" in p or "(e)" in p:
                continue
            m = re.match(r"(\d{4})\.(\d{2})", p)
            if m:
                year, month = int(m.group(1)), int(m.group(2))
                # 결산월의 마지막 날
                year_end = pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)
                annual_periods.append((i, year_end.strftime("%Y-%m-%d")))

        if not annual_periods:
            continue

        # EPS/BPS/ROE/debt ratio 행 찾기
        eps_values: Dict[str, float] = {}
        bps_values: Dict[str, float] = {}
        roe_values: Dict[str, float] = {}
        debt_ratio_values: Dict[str, float] = {}

        for row in rows:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue
            label = cells[0].get_text(strip=True)
            values = [c.get_text(strip=True) for c in cells[1:]]

            if label.startswith("EPS"):
                for col_idx, date_str in annual_periods:
                    if col_idx < len(values):
                        eps_values[date_str] = _parse_number(values[col_idx])
            elif label.startswith("BPS"):
                for col_idx, date_str in annual_periods:
                    if col_idx < len(values):
                        bps_values[date_str] = _parse_number(values[col_idx])
            elif label.startswith("ROE"):
                for col_idx, date_str in annual_periods:
                    if col_idx < len(values):
                        roe_values[date_str] = _parse_number(values[col_idx])
            elif label.startswith("부채비율"):
                for col_idx, date_str in annual_periods:
                    if col_idx < len(values):
                        debt_ratio_values[date_str] = _parse_number(values[col_idx])

        if not eps_values and not bps_values and not roe_values and not debt_ratio_values:
            continue

        result = []
        all_dates = sorted(
            set(
                list(eps_values.keys())
                + list(bps_values.keys())
                + list(roe_values.keys())
                + list(debt_ratio_values.keys())
            )
        )
        for d in all_dates:
            entry = {"year_end": d}
            if d in eps_values:
                entry["eps"] = eps_values[d]
            if d in bps_values:
                entry["bps"] = bps_values[d]
            if d in roe_values and roe_values[d] is not None:
                entry["roe_or_gpa"] = roe_values[d]
            if d in debt_ratio_values and debt_ratio_values[d] is not None:
                entry["debt_ratio"] = debt_ratio_values[d]
            result.append(entry)

        return result

    return None


def fetch_shares_outstanding(symbol: str) -> Optional[int]:
    """Naver Finance에서 상장주식수를 조회한다. 실패 시 None.

    시가총액 = close × 상장주식수. 현재 주식수를 전 기간에 적용하는 근사로, 엔진의
    런타임 market_cap 계산(data_resolver._resolve_market_cap)과 동일한 방식이다.
    """
    try:
        r = requests.get(_NAVER_URL.format(symbol=symbol), headers=_HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        for th in soup.find_all(["th", "td"]):
            if "상장주식수" in th.get_text(strip=True):
                sib = th.find_next_sibling(["td", "em"]) or th.find_next(["td", "em"])
                if sib:
                    num = sib.get_text(strip=True).replace(",", "").replace("주", "")
                    if num.isdigit():
                        return int(num)
    except Exception as e:
        logger.debug("[%s] shares fetch failed: %s", symbol, e)
    return None


def _parse_number(s: str) -> Optional[float]:
    """'52,002' → 52002.0, '-12,517' → -12517.0, '' → None"""
    s = s.strip().replace(",", "")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def enrich_ohlcv_with_fundamentals(
    df: pd.DataFrame, fundamentals: List[Dict]
) -> pd.DataFrame:
    """OHLCV DataFrame에 eps, bps, per, pbr, roe_or_gpa, debt_ratio 컬럼을 추가한다.

    Args:
        df: OHLCV DataFrame (date 컬럼 포함, datetime 타입)
        fundamentals: fetch_fundamentals() 반환값

    Returns:
        eps, bps, per, pbr, roe_or_gpa, debt_ratio 컬럼이 추가된 DataFrame
    """
    if not fundamentals:
        return df

    import numpy as _np

    df = df.copy()

    # 결산일 기준 연간 펀더멘털 시리즈 생성
    fund_df = pd.DataFrame(fundamentals)
    fund_df["year_end"] = pd.to_datetime(fund_df["year_end"])
    fund_df = fund_df.sort_values("year_end")

    date_col = pd.to_datetime(df["date"])

    # 각 거래일에 대해 가장 최근 결산 데이터 매핑 (forward-fill 방식)
    # 결산일 이후 ~3개월 후 실적 공시라고 가정하여, 결산일 + 90일 이후부터 적용
    # (실적 발표 전 look-ahead bias 방지)
    _PUBLISH_DELAY_DAYS = 90

    # 원본 4개(eps/bps/roe/debt_ratio)는 데이터에 없어도 항상 컬럼을 생성하고(하위호환),
    # 추가 지표는 데이터에 존재할 때만 컬럼을 만든다.
    _base = ["eps", "bps", "roe_or_gpa", "debt_ratio"]
    present_keys = list(dict.fromkeys(
        _base + [k for k in ANNUAL_FUNDAMENTAL_KEYS if k in fund_df.columns]
    ))
    series = {k: pd.Series(index=df.index, dtype=float) for k in present_keys}

    for _, row in fund_df.iterrows():
        mask = date_col >= row["year_end"] + pd.Timedelta(days=_PUBLISH_DELAY_DAYS)
        for k in present_keys:
            if pd.notna(row.get(k)):
                series[k][mask] = row[k]

    for k in present_keys:
        df[k] = series[k]

    # 가격 기반 밸류에이션 비율: PER=close/EPS, PBR=close/BPS, PSR=close/SPS
    close = df["close"].astype(float)
    for ratio, denom in (("per", "eps"), ("pbr", "bps"), ("psr", "sps")):
        if denom in df.columns:
            valid = df[denom].notna() & (df[denom] != 0)
            df[ratio] = (close / df[denom]).where(valid).replace([_np.inf, -_np.inf], _np.nan)

    return df
