"""
Naver Finance 기반 재무 데이터(EPS/BPS) 스크래핑 모듈.
EPS/BPS를 연도별로 가져와서 일별 PER/PBR 계산에 사용한다.
"""

import re
import time
import logging
import pandas as pd
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
_NAVER_URL = "https://finance.naver.com/item/main.naver?code={symbol}"


def fetch_fundamentals(symbol: str, retry: int = 2) -> Optional[List[Dict]]:
    """Naver Finance에서 연도별 EPS/BPS를 스크래핑한다.

    Returns:
        [{"year_end": "2025-12-31", "eps": 6564.0, "bps": 63997.0}, ...] 또는 None
        추정치(E)가 포함된 연도는 제외한다.
    """
    url = _NAVER_URL.format(symbol=symbol)
    for attempt in range(retry + 1):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            return _parse_fundamentals(r.text)
        except Exception as e:
            logger.warning(f"[{symbol}] fundamental fetch attempt {attempt+1} failed: {e}")
            if attempt < retry:
                time.sleep(0.5)
    return None


def _parse_fundamentals(html: str) -> Optional[List[Dict]]:
    """HTML에서 주요재무정보 테이블을 파싱하여 연도별 EPS/BPS를 추출한다."""
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

        # EPS/BPS 행 찾기
        eps_values: Dict[str, float] = {}
        bps_values: Dict[str, float] = {}

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

        if not eps_values and not bps_values:
            continue

        result = []
        all_dates = sorted(set(list(eps_values.keys()) + list(bps_values.keys())))
        for d in all_dates:
            entry = {"year_end": d}
            if d in eps_values:
                entry["eps"] = eps_values[d]
            if d in bps_values:
                entry["bps"] = bps_values[d]
            result.append(entry)

        return result

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
    """OHLCV DataFrame에 eps, bps, per, pbr 컬럼을 추가한다.

    Args:
        df: OHLCV DataFrame (date 컬럼 포함, datetime 타입)
        fundamentals: fetch_fundamentals() 반환값

    Returns:
        eps, bps, per, pbr 컬럼이 추가된 DataFrame
    """
    if not fundamentals:
        return df

    df = df.copy()

    # 결산일 기준 EPS/BPS 시리즈 생성
    fund_df = pd.DataFrame(fundamentals)
    fund_df["year_end"] = pd.to_datetime(fund_df["year_end"])
    fund_df = fund_df.sort_values("year_end")

    # date 컬럼을 datetime으로 변환
    date_col = pd.to_datetime(df["date"])

    # 각 거래일에 대해 가장 최근 결산 데이터 매핑 (forward-fill 방식)
    # 결산일 이후 ~3개월 후 실적 공시라고 가정하여, 결산일 + 90일 이후부터 적용
    # (실적 발표 전 look-ahead bias 방지)
    _PUBLISH_DELAY_DAYS = 90

    eps_series = pd.Series(index=df.index, dtype=float)
    bps_series = pd.Series(index=df.index, dtype=float)

    for _, row in fund_df.iterrows():
        effective_date = row["year_end"] + pd.Timedelta(days=_PUBLISH_DELAY_DAYS)
        mask = date_col >= effective_date
        if "eps" in row and pd.notna(row.get("eps")):
            eps_series[mask] = row["eps"]
        if "bps" in row and pd.notna(row.get("bps")):
            bps_series[mask] = row["bps"]

    df["eps"] = eps_series
    df["bps"] = bps_series

    # PER = close / EPS, PBR = close / BPS
    close = df["close"].astype(float)
    eps_valid = df["eps"].notna() & (df["eps"] != 0)
    bps_valid = df["bps"].notna() & (df["bps"] != 0)
    per = (close / df["eps"]).where(eps_valid)
    pbr = (close / df["bps"]).where(bps_valid)
    # inf → NaN
    import numpy as _np
    df["per"] = per.replace([_np.inf, -_np.inf], _np.nan)
    df["pbr"] = pbr.replace([_np.inf, -_np.inf], _np.nan)

    return df
