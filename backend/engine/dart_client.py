"""
OpenDART 상장폐지 공시 조회 클라이언트

거래소공시(pblntf_ty=I) 중 상장폐지·매매거래정지 관련 공시를 필터링해 반환한다.
DART 응답의 stock_code 필드는 KRX 6자리 종목코드와 동일하다.
"""

import os
import requests
from datetime import datetime, timedelta
from typing import Optional

_DART_BASE = "https://opendart.fss.or.kr/api"

# 포함 키워드 — 이 중 하나라도 있으면 후보
_INCLUDE_KEYWORDS = ["상장폐지", "매매거래정지", "상장적격성"]
# 제외 키워드 — 이게 있으면 무조건 스킵 (해제/변경상장 등은 폐지 아님)
_EXCLUDE_KEYWORDS = ["해제", "변경상장"]


def _api_key() -> str:
    return os.getenv("DART_API_KEY", "").strip()


def fetch_delisting_notices(
    start_date: str,
    end_date: str,
    corp_code: Optional[str] = None,
) -> list[dict]:
    """
    거래소공시 조회 후 상장폐지 관련 공시만 반환한다.

    Args:
        start_date: 조회 시작일 (YYYYMMDD)
        end_date:   조회 종료일 (YYYYMMDD)
        corp_code: OpenDART 8자리 corp_code로 범위를 좁힐 때 (선택)

    Returns:
        [{"stock_code", "corp_name", "report_nm", "rcept_dt", "rcept_no"}, ...]
    """
    key = _api_key()
    if not key:
        return []

    results = []
    page = 1

    while True:
        params: dict = {
            "crtfc_key": key,
            "pblntf_ty": "I",  # 거래소공시
            "bgn_de": start_date,
            "end_de": end_date,
            "page_no": page,
            "page_count": 100,
        }
        if corp_code:
            params["corp_code"] = corp_code

        try:
            resp = requests.get(f"{_DART_BASE}/list.json", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"OpenDART API 요청 실패: {e}") from e

        # 000=정상, 013=데이터없음
        status = data.get("status")
        if status == "013":
            break
        if status != "000":
            raise RuntimeError(f"OpenDART API 오류: status={status}, message={data.get('message')}")

        for item in data.get("list", []):
            report_nm = item.get("report_nm", "")
            if not any(kw in report_nm for kw in _INCLUDE_KEYWORDS):
                continue
            if any(kw in report_nm for kw in _EXCLUDE_KEYWORDS):
                continue
            code = item.get("stock_code", "").strip().zfill(6)
            if not code or code == "000000":
                continue
            results.append({
                "stock_code": code,
                "corp_name": item.get("corp_name", ""),
                "report_nm": report_nm,
                "rcept_dt": item.get("rcept_dt", ""),
                "rcept_no": item.get("rcept_no", ""),
            })

        total_count = int(data.get("total_count", 0))
        if page * 100 >= total_count:
            break
        page += 1

    return results


def fetch_recent_delisting_notices(days: int = 7) -> list[dict]:
    """최근 N일간의 상장폐지 관련 공시를 반환한다."""
    today = datetime.now()
    start = today - timedelta(days=days)
    return fetch_delisting_notices(
        start_date=start.strftime("%Y%m%d"),
        end_date=today.strftime("%Y%m%d"),
    )
