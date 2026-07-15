"""
Fundamental enrichment helpers.

KIS financial-ratio API is the primary source for annual ratio data.
Naver Finance is the fallback, and OpenDART provides operating cash flow for PCR.
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
_DART_BASE_URL = "https://opendart.fss.or.kr/api"
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
_DART_CORP_CODE_PATH = _PROJECT_ROOT / "data" / "dart_corpcode.json"
_DART_YEAR_FLOOR = 2015
_DART_ANNUAL_REPORT_CODE = "11011"
_DART_OPERATING_CASH_FLOW_ACCOUNT_ID = "ifrs-full_CashFlowsFromUsedInOperatingActivities"
_DART_OPERATING_CASH_FLOW_NAMES = {
    "영업활동현금흐름",
    "영업활동으로인한현금흐름",
    "영업활동으로부터의현금흐름",
    "영업활동으로인한순현금흐름",
}
_DART_CORP_CODES: Optional[Dict[str, str]] = None

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
    "roa", "net_margin", "gross_margin", "operating_margin", "current_ratio", "quick_ratio",
    "operating_cash_flow", "pcr",
    # EBITDA(억원)와 EV/EBITDA(배)는 KIS other-major-ratios에서 제공. ev_ebitda는 결산 시점
    # 스냅샷 비율을 다음 결산까지 전진충전(forward-fill)한다 — 스크리닝 필터용 근사.
    "ebitda", "ev_ebitda",
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
# other-major-ratios: EBITDA(억원)·EV/EBITDA(배). ev_ebitda는 0.00을 '데이터 없음' 센티널로
# 쓰므로(2010년 이전) 아래 _sanitize에서 비양수 값을 제거한다.
_KIS_OTHER_RATIO_MAP = {
    "ebitda": "ebitda", "ev_ebitda": "ev_ebitda",
}
_KIS_FINANCE_ENDPOINTS = [
    ("financial-ratio", "FHKST66430300", _KIS_FINANCIAL_RATIO_MAP),
    ("profit-ratio", "FHKST66430400", _KIS_PROFIT_RATIO_MAP),
    ("stability-ratio", "FHKST66430600", _KIS_STABILITY_RATIO_MAP),
    ("other-major-ratios", "FHKST66430500", _KIS_OTHER_RATIO_MAP),
]
# 영업이익률(operating_margin)은 KIS 재무비율 3종에 없어 손익계산서(income-statement)의
# 영업이익(bsop_prti)/매출액(sale_account)으로 직접 계산한다.
_KIS_INCOME_STATEMENT = ("income-statement", "FHKST66430200")


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


def _parse_kis_income_statement(output: list) -> Dict[str, Dict]:
    """KIS 손익계산서 rows → {year_end: {"operating_margin": 영업이익/매출액*100}}."""
    by_year: Dict[str, Dict] = {}
    if not isinstance(output, list):
        return by_year
    for row in output:
        if not isinstance(row, dict):
            continue
        year_end = _parse_kis_stac_yymm(str(row.get("stac_yymm", "")).strip())
        if not year_end:
            continue
        sale = _parse_number(str(row.get("sale_account", "")).strip())
        op = _parse_number(str(row.get("bsop_prti", "")).strip())
        if sale and op is not None:
            by_year[year_end] = {"operating_margin": round(op / sale * 100.0, 2)}
    return by_year


def _parse_dart_receipt_date(receipt_no: object) -> Optional[str]:
    """Return the filing date encoded in a 14-digit OpenDART receipt number."""
    digits = re.sub(r"\D", "", str(receipt_no or ""))
    if len(digits) != 14:
        return None
    try:
        return pd.Timestamp(digits[:8]).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _parse_dart_operating_cash_flow(rows: list) -> Optional[Dict]:
    """Extract net operating cash flow without matching operating-asset subtotals."""
    if not isinstance(rows, list):
        return None

    candidates = []
    for row in rows:
        if not isinstance(row, dict) or row.get("sj_div") != "CF":
            continue
        account_id = str(row.get("account_id", "")).strip()
        normalized_name = re.sub(r"\s+", "", str(row.get("account_nm", "")))
        if (
            account_id != _DART_OPERATING_CASH_FLOW_ACCOUNT_ID
            and normalized_name not in _DART_OPERATING_CASH_FLOW_NAMES
        ):
            continue
        amount = _parse_number(str(row.get("thstrm_amount", "")))
        available_from = _parse_dart_receipt_date(row.get("rcept_no"))
        if amount is None or not available_from:
            continue
        candidates.append((account_id == _DART_OPERATING_CASH_FLOW_ACCOUNT_ID, amount, available_from))

    if not candidates:
        return None
    _, amount, available_from = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
    return {
        "operating_cash_flow": amount,
        "available_from": available_from,
    }


def _get_dart_corp_code(symbol: str) -> Optional[str]:
    global _DART_CORP_CODES
    if _DART_CORP_CODES is None:
        try:
            payload = json.loads(_DART_CORP_CODE_PATH.read_text(encoding="utf-8"))
            _DART_CORP_CODES = payload if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            _DART_CORP_CODES = {}
    return _DART_CORP_CODES.get(symbol)


def _fetch_dart_json(path: str, params: Dict[str, str]) -> Dict:
    try:
        response = requests.get(
            f"{_DART_BASE_URL}/{path}",
            params={"crtfc_key": os.getenv("DART_API_KEY", "").strip(), **params},
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            return {}
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except Exception as error:
        logger.warning("[DART] %s fetch failed: %s", path, error)
        return {}


def _fetch_cash_flow_from_dart(
    symbol: str,
    start_year: int = _DART_YEAR_FLOOR,
    end_year: Optional[int] = None,
) -> Optional[List[Dict]]:
    """Fetch annual operating cash flow for PCR enrichment."""
    if not os.getenv("DART_API_KEY", "").strip():
        return None
    corp_code = _get_dart_corp_code(symbol)
    if not corp_code:
        return None

    last_year = end_year if end_year is not None else pd.Timestamp.now().year - 1
    results = []
    quota_exceeded = False
    for year in range(max(start_year, _DART_YEAR_FLOOR), last_year + 1):
        cash_flow = None
        for fs_div in ("CFS", "OFS"):
            payload = _fetch_dart_json(
                "fnlttSinglAcntAll.json",
                {
                    "corp_code": corp_code,
                    "bsns_year": str(year),
                    "reprt_code": _DART_ANNUAL_REPORT_CODE,
                    "fs_div": fs_div,
                },
            )
            if payload.get("status") == "020":
                quota_exceeded = True
                break
            if payload.get("status") == "000":
                cash_flow = _parse_dart_operating_cash_flow(payload.get("list", []))
                if cash_flow:
                    break
        if quota_exceeded:
            break
        if not cash_flow:
            continue
        results.append({
            "year_end": f"{year}-12-31",
            "available_from": cash_flow["available_from"],
            "operating_cash_flow": cash_flow["operating_cash_flow"],
        })

    return results or None


def _merge_fundamental_records(*record_sets: Optional[List[Dict]]) -> Optional[List[Dict]]:
    merged: Dict[str, Dict] = {}
    for records in record_sets:
        for record in records or []:
            year_end = str(record.get("year_end", "")).strip()
            if not year_end:
                continue
            merged.setdefault(year_end, {"year_end": year_end}).update(record)
    result = [merged[key] for key in sorted(merged, reverse=True)]
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

    # 영업이익률: 재무비율 API에 없어 손익계산서(영업이익/매출액)로 계산해 병합
    is_path, is_tr = _KIS_INCOME_STATEMENT
    is_output = _fetch_kis_finance(symbol, {**headers, "tr_id": is_tr}, is_path)
    for year_end, vals in _parse_kis_income_statement(is_output).items():
        merged.setdefault(year_end, {}).update(vals)

    # ev_ebitda의 0.00은 '데이터 없음' 센티널(2010년 이전 등) — 비양수 값을 제거해
    # 가치 필터('EV/EBITDA 8 이하')가 데이터 없는 연도를 저평가로 오인하지 않게 한다.
    for vals in merged.values():
        if "ev_ebitda" in vals and vals["ev_ebitda"] is not None and vals["ev_ebitda"] <= 0:
            del vals["ev_ebitda"]

    result = [{"year_end": d, **vals} for d, vals in sorted(merged.items(), reverse=True) if vals]
    return result or None


def fetch_fundamentals(symbol: str, retry: int = 2, use_cache: bool = True) -> Optional[List[Dict]]:
    """Fetch annual fundamentals for parquet enrichment.

    1순위: 로컬 JSON 캐시 (90일 이내)
    2순위: 최근 재조회 실패 캐시 (7일 이내) — REITs 등 항상 실패하는 종목의 반복 호출 방지
    3순위: KIS financial-ratio API
    4순위: Naver Finance 스크래핑
    별도 병합: OpenDART 영업활동현금흐름

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

    cash_flow = _fetch_cash_flow_from_dart(symbol)
    result = _merge_fundamental_records(result, cash_flow)

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
        return _add_dividend_metrics(df)

    import numpy as _np

    df = df.copy()

    # 결산일 기준 연간 펀더멘털 시리즈 생성
    fund_df = pd.DataFrame(fundamentals)
    fund_df["year_end"] = pd.to_datetime(fund_df["year_end"])
    fund_df = fund_df.sort_values("year_end")

    date_col = pd.to_datetime(df["date"])

    # 각 거래일에 대해 가장 최근 결산 데이터 매핑 (forward-fill 방식).
    # OpenDART 레코드는 실제 접수일을 사용하고, 그 외 소스는 결산일 + 90일을 적용한다.
    _PUBLISH_DELAY_DAYS = 90

    # 원본 4개(eps/bps/roe/debt_ratio)는 데이터에 없어도 항상 컬럼을 생성하고(하위호환),
    # 추가 지표는 데이터에 존재할 때만 컬럼을 만든다.
    _base = ["eps", "bps", "roe_or_gpa", "debt_ratio"]
    present_keys = list(dict.fromkeys(
        _base + [k for k in ANNUAL_FUNDAMENTAL_KEYS if k in fund_df.columns]
    ))
    series = {k: pd.Series(index=df.index, dtype=float) for k in present_keys}

    for _, row in fund_df.iterrows():
        available_from = pd.to_datetime(row.get("available_from"), errors="coerce")
        if pd.isna(available_from):
            available_from = row["year_end"] + pd.Timedelta(days=_PUBLISH_DELAY_DAYS)
        mask = date_col >= available_from
        for k in present_keys:
            if pd.notna(row.get(k)):
                series[k][mask] = row[k]

    for k in present_keys:
        df[k] = series[k]

    # 가격 기반 밸류에이션 비율: PER=close/EPS, PBR=close/BPS, PSR=close/SPS.
    close = df["close"].astype(float)
    for ratio, denom in (
        ("per", "eps"),
        ("pbr", "bps"),
        ("psr", "sps"),
    ):
        if denom in df.columns:
            valid = df[denom].notna() & (df[denom] != 0)
            df[ratio] = (close / df[denom]).where(valid).replace([_np.inf, -_np.inf], _np.nan)

    # PCR = 시가총액 / 영업활동현금흐름. OHLCV 종가는 기업행사 조정 가격이므로,
    # 과거 비조정 주식 수로 CFPS를 만들면 액면분할 전 기간이 왜곡된다. parquet의
    # 일별 market_cap(억원)을 사용해 동일한 가격 조정 기준을 유지한다.
    if "market_cap" in df.columns and "operating_cash_flow" in df.columns:
        valid = (
            df["market_cap"].notna()
            & df["operating_cash_flow"].notna()
            & (df["operating_cash_flow"] > 0)
        )
        df["pcr"] = (
            df["market_cap"].astype(float) * 1e8 / df["operating_cash_flow"]
        ).where(valid).replace([_np.inf, -_np.inf], _np.nan)

    return _add_dividend_metrics(df)


def _add_dividend_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """ex-date별 주당 현금배당(dividends 컬럼, scripts/backfill_dividends.py로 백필)이 있으면
    배당수익률(TTM DPS/종가)과 배당성향(TTM DPS/EPS) 컬럼을 추가한다. 연간 펀더멘털과
    독립적이라 fundamentals가 비어도 계산된다(dividends 없으면 no-op)."""
    if "dividends" not in df.columns:
        return df
    from .dividends import (
        trailing_dividend_yield, dividend_payout_ratio, dividend_growth_yoy,
    )
    df["dividend_yield"] = trailing_dividend_yield(df["close"].astype(float), df["dividends"])
    df["dividend_growth"] = dividend_growth_yoy(df["dividends"])
    if "eps" in df.columns:
        df["payout_rate"] = dividend_payout_ratio(df["dividends"], df["eps"])
    return df
