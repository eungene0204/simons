"""분기 EPS·실적 발표일 수집(DART) — SUE·발표일 초과수익률(PEAD)의 원재료.

연간 재무(`fundamental_fetcher`)와 두 가지가 다르다.

① **발표일이 값과 동급의 1급 정보다.** PEAD(실적 발표 후 표류)는 발표 *시점* 전후의
   사건이므로, 결산일이 아니라 공시 접수일(`rcept_no` 앞 8자리)에 정렬한다.
② **분기 3개월 값만 쓴다.** DART 분기보고서의 손익계산서는 `thstrm_amount`=당기 3개월,
   `thstrm_add_amount`=당기 누적이다(실측 2026-09-20, 삼성전자·SK하이닉스·NAVER·셀트리온·
   에코프로비엠 5종목 일관). 4분기는 분기보고서가 없으므로 **연간 − 3분기 누적**으로 구한다.

③ **발표일은 원공시 접수일이다.** `fnlttSinglAcntAll`의 `rcept_no`는 정정공시가 있으면
   **정정본**을 가리킨다(2026-09-21 실측: 셀트리온 2016~2019 4분기 네 건이 모두 2022-05-12 —
   일괄 정정 접수일. 수집 10,554건 중 342건이 결산 후 180일 초과). 그대로 쓰면 몇 년 전
   분기가 정정일에 '새로 발표된' 것처럼 자격 창에 들어오고 그 종목의 최신 분기 시그널을
   끊는다. 공시검색(list.json)에서 결산월별 **최초** 접수일을 받아 min으로 클램프한다 —
   연간 재무의 available_from 오염(2026-08-04)과 같은 원인·같은 수리다. EPS 값 자체는
   API가 최신본만 돌려주므로 정정 후 값이다(한계).

가용 구간은 **2016년부터**다 — `fnlttSinglAcntAll`이 2015년 이전 분기보고서를 돌려주지
않는다(실측: 2010·2013·2015 모두 status 013 '조회된 데이타가 없습니다'). SUE가 직전
8개 분기를 요구하므로 시그널이 실제로 서는 것은 2018년경부터다.

연결/별도 기준 혼용 금지
------------------------
같은 종목인데 분기마다 CFS(연결)·OFS(별도)가 섞이면 EPS 수준 자체가 달라져 분기 간
차분(SUE의 분자)이 실적 변화가 아니라 **기준 변경**을 재는 값이 된다(실측: NAVER 2024
1분기는 연결 응답에 기본주당이익 계정이 없어 별도로 떨어졌다 — 1,488원 vs 반기 연결
3개월 2,224원). 그래서 종목 단위로 기준을 하나 고르고(연결이 하나라도 잡히면 연결),
고른 기준으로 못 얻은 분기는 **채우지 않고 비운다**(fail-closed).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .fundamental_fetcher import (
    DartQuotaExhausted,
    _fetch_dart_json,
    _get_dart_corp_code,
    dart_fiscal_month,
    dart_year_end,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = _PROJECT_ROOT / "data" / "quarterly-earnings"

# 분기보고서 코드 → 그 보고서가 끝나는 분기 번호. 4분기는 보고서가 없다(연간에서 역산).
_QUARTER_REPORT_CODES = {1: "11013", 2: "11012", 3: "11014"}
_ANNUAL_REPORT_CODE = "11011"

# 기본주당이익 계정 — 2019년 사업보고서부터 `ifrs-full_`, 그 이전은 `ifrs_`(구 택소노미).
# 희석주당이익은 쓰지 않는다(희석 가정이 회사·기간마다 달라 분기 차분을 오염시킨다).
_BASIC_EPS_ACCOUNT_IDS = {
    "ifrs-full_BasicEarningsLossPerShare",
    "ifrs_BasicEarningsLossPerShare",
}

# DART 분기 재무제표 API가 응답을 시작하는 사업연도(실측 2026-09-20).
QUARTERLY_YEAR_FLOOR = 2016

# 이 모듈이 쓴 DART 호출 수 — 백필이 일일 한도를 쪼개 쓰려면 예산을 알아야 한다.
# 종목 하나가 연도당 4회(분기 3 + 연간 1), 기준을 고르는 첫 연도만 최대 8회다.
_dart_calls = 0


def dart_calls_used() -> int:
    return _dart_calls


def reset_dart_calls() -> None:
    global _dart_calls
    _dart_calls = 0


def cache_path(symbol: str) -> Path:
    return _CACHE_DIR / f"{symbol}.json"


def _quarter_end(year_end: str, quarter: int) -> str:
    """결산일과 분기 번호 → 그 분기의 종료일.

    결산월이 12월이 아닌 회사(실측 42종목)도 결산일에서 3개월씩 역산하면 맞는다 —
    6월 결산 회사의 1분기는 9월 말이다.
    """
    end = pd.Timestamp(year_end) - pd.DateOffset(months=3 * (4 - quarter))
    return (end + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")


def _announce_date(rcept_no: str) -> Optional[str]:
    """공시 접수번호 → 발표일. 앞 8자리가 접수일(YYYYMMDD)이다."""
    digits = str(rcept_no or "").strip()[:8]
    if len(digits) != 8 or not digits.isdigit():
        return None
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"


# 정기보고서 이름의 결산월 — `분기보고서 (2024.09)`·`[기재정정]사업보고서 (2019.12)`.
_PERIODIC_REPORT_NAME = re.compile(r"(?:사업|반기|분기)보고서\s*\((\d{4})\.(\d{2})\)")


def fetch_original_filing_dates(corp_code: str) -> Dict[str, str]:
    """결산월별 정기보고서 **원공시** 접수일 ``{"YYYY-MM": "YYYY-MM-DD"}``.

    정정본까지 전부 받아(last_reprt_at=N) 결산월마다 최소 접수일을 고른다. 한도 소진은
    예외로 올리고, 그 밖의 실패는 빈 dict(클램프 생략 — 기존 날짜 유지)다.
    """
    global _dart_calls
    dates: Dict[str, str] = {}
    page = 1
    while True:
        _dart_calls += 1
        payload = _fetch_dart_json(
            "list.json",
            {
                "corp_code": corp_code,
                "bgn_de": f"{QUARTERLY_YEAR_FLOOR}0101",
                "end_de": pd.Timestamp.now().strftime("%Y%m%d"),
                "pblntf_ty": "A",
                "last_reprt_at": "N",
                "page_no": str(page),
                "page_count": "100",
            },
        )
        if payload.get("status") == "020":
            raise DartQuotaExhausted(corp_code)
        if payload.get("status") != "000":
            break
        for row in payload.get("list", []):
            match = _PERIODIC_REPORT_NAME.search(str(row.get("report_nm", "")))
            filed = _announce_date(row.get("rcept_dt"))
            if not match or not filed:
                continue
            key = f"{match.group(1)}-{match.group(2)}"
            if key not in dates or filed < dates[key]:
                dates[key] = filed
        if page * 100 >= int(payload.get("total_count") or 0):
            break
        page += 1
    return dates


def clamp_to_original_filing(records: List[dict], original_dates: Dict[str, str]) -> int:
    """레코드의 발표일을 원공시 접수일로 당긴다(min 클램프 — 재실행해도 결과 불변). 바뀐 건수."""
    changed = 0
    for record in records:
        original = original_dates.get(str(record.get("period_end", ""))[:7])
        if original and original < str(record.get("announce_date", "")):
            record["announce_date"] = original
            changed += 1
    return changed


def _to_amount(raw) -> Optional[float]:
    """DART 금액 문자열 → 실수. 빈 값·'-'는 없음이다(0이 아니다)."""
    text = str(raw or "").strip().replace(",", "")
    if not text or text in {"-", "—"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _eps_row(rows: list) -> Optional[dict]:
    for row in rows or []:
        if (row.get("account_id") or "").strip() in _BASIC_EPS_ACCOUNT_IDS:
            return row
    return None


# 분기 손익 3항목(v16.27, 2026-09-23) — 손익계산서(IS/CIS)의 매출·영업이익·당기순이익(원, 3개월).
# EPS와 같은 응답이라 추가 호출 0. 영업이익은 DART 고유 계정(dart_OperatingIncomeLoss).
INCOME_ITEMS: Dict[str, frozenset] = {
    "revenue": frozenset({"ifrs-full_Revenue", "ifrs_Revenue"}),
    "operating_income": frozenset({"dart_OperatingIncomeLoss"}),
    "net_income": frozenset({"ifrs-full_ProfitLoss", "ifrs_ProfitLoss"}),
}
_INCOME_SECTIONS = ("IS", "CIS")


def _income_rows(rows: list) -> Dict[str, dict]:
    """{항목: 행} — 손익계산서 섹션에서 계정ID 정확 일치·소계(account_detail 없음) 행만 첫 번째로."""
    found: Dict[str, dict] = {}
    for row in rows or []:
        if not isinstance(row, dict) or row.get("sj_div") not in _INCOME_SECTIONS:
            continue
        if str(row.get("account_detail", "-")).strip() not in ("", "-"):
            continue
        account_id = (row.get("account_id") or "").strip()
        for item, ids in INCOME_ITEMS.items():
            if item not in found and account_id in ids:
                found[item] = row
    return found


def _fetch_report(corp_code: str, year: int, reprt_code: str, fs_div: str) -> Optional[dict]:
    """한 보고서의 기본주당이익 행. 한도 소진은 '없음'이 아니라 예외로 올린다."""
    rows = _fetch_report_rows(corp_code, year, reprt_code, fs_div)
    return _eps_row(rows) if rows is not None else None


def _fetch_report_rows(corp_code: str, year: int, reprt_code: str, fs_div: str) -> Optional[list]:
    """한 보고서의 전체 계정 행(EPS·손익 3항목이 같은 응답에서 나온다). 한도 소진은 예외."""
    global _dart_calls
    _dart_calls += 1
    payload = _fetch_dart_json(
        "fnlttSinglAcntAll.json",
        {
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        },
    )
    if payload.get("status") == "020":
        raise DartQuotaExhausted(corp_code)
    if payload.get("status") != "000":
        return None
    return payload.get("list") or []


def _collect_year(corp_code: str, year: int, fs_div: str) -> Dict[int, dict]:
    """한 사업연도의 분기별 {분기: {eps, announce_date, cumulative, income, income_cumulative}}
    (고른 기준으로만). income은 {revenue, operating_income, net_income}(원, 3개월) 중 응답에 있는 것."""
    collected: Dict[int, dict] = {}
    for quarter, reprt_code in _QUARTER_REPORT_CODES.items():
        rows = _fetch_report_rows(corp_code, year, reprt_code, fs_div)
        row = _eps_row(rows) if rows is not None else None
        if row is None:
            continue
        eps = _to_amount(row.get("thstrm_amount"))
        announced = _announce_date(row.get("rcept_no"))
        if eps is None or not announced:
            continue
        income_rows = _income_rows(rows)
        collected[quarter] = {
            "eps": eps,
            "announce_date": announced,
            # 4분기 역산에 쓰는 누적치 — 3분기 누적이 없으면 그 해 4분기는 비운다.
            "cumulative": _to_amount(row.get("thstrm_add_amount")),
            "income": {k: _to_amount(r.get("thstrm_amount")) for k, r in income_rows.items()
                       if _to_amount(r.get("thstrm_amount")) is not None},
            "income_cumulative": {k: _to_amount(r.get("thstrm_add_amount")) for k, r in income_rows.items()
                                  if _to_amount(r.get("thstrm_add_amount")) is not None},
        }

    annual_rows = _fetch_report_rows(corp_code, year, _ANNUAL_REPORT_CODE, fs_div)
    annual_row = _eps_row(annual_rows) if annual_rows is not None else None
    if annual_row is not None:
        annual_eps = _to_amount(annual_row.get("thstrm_amount"))
        announced = _announce_date(annual_row.get("rcept_no"))
        third = collected.get(3) or {}
        third_cumulative = third.get("cumulative")
        if annual_eps is not None and announced and third_cumulative is not None:
            annual_income = {k: _to_amount(r.get("thstrm_amount")) for k, r in _income_rows(annual_rows).items()}
            third_income_cum = third.get("income_cumulative") or {}
            collected[4] = {
                "eps": annual_eps - third_cumulative,
                "announce_date": announced,
                "cumulative": annual_eps,
                # 4분기 손익 = 연간 − 3분기 누적(둘 다 있는 항목만).
                "income": {k: v - third_income_cum[k] for k, v in annual_income.items()
                           if v is not None and k in third_income_cum},
                "income_cumulative": {},
            }
    return collected


def fetch_quarterly_earnings(
    symbol: str,
    start_year: int = QUARTERLY_YEAR_FLOOR,
    end_year: Optional[int] = None,
) -> Optional[List[dict]]:
    """종목의 분기 EPS·발표일 목록(결산일 오름차순).

    반환 레코드: ``{"period_end", "eps", "announce_date", "fs_div"}``.
    연결·별도 기준은 종목 단위로 하나만 쓴다(모듈 docstring 참고).
    """
    corp_code = _get_dart_corp_code(symbol)
    if not corp_code:
        return None

    fiscal_month = dart_fiscal_month(symbol, corp_code)
    last_year = end_year if end_year is not None else pd.Timestamp.now().year
    years = range(max(start_year, QUARTERLY_YEAR_FLOOR), last_year + 1)

    # 기준은 **처음 분기가 잡힌 연도**에서 정해 그 뒤로 고정한다 — 연결을 먼저 보고,
    # 연결 재무제표를 내지 않는 회사만 별도로 떨어진다. 연도마다 다시 고르면 기준이
    # 섞여 분기 차분이 실적이 아닌 기준 변경을 재게 된다(모듈 docstring).
    fs_div: Optional[str] = None
    records: List[dict] = []
    for year in years:
        if fs_div is None:
            collected = _collect_year(corp_code, year, "CFS")
            if collected:
                fs_div = "CFS"
            else:
                collected = _collect_year(corp_code, year, "OFS")
                if collected:
                    fs_div = "OFS"
        else:
            collected = _collect_year(corp_code, year, fs_div)

        for quarter, data in sorted(collected.items()):
            record = {
                "period_end": _quarter_end(dart_year_end(year, fiscal_month), quarter),
                "eps": data["eps"],
                "announce_date": data["announce_date"],
                "fs_div": fs_div,
            }
            record.update({k: v for k, v in (data.get("income") or {}).items()})   # 분기 손익 3항목(v16.27)
            records.append(record)
    records.sort(key=lambda record: record["period_end"])
    if records:
        clamp_to_original_filing(records, fetch_original_filing_dates(corp_code))
    return records or None


def has_income_items(records: Optional[List[dict]]) -> bool:
    """수집분에 분기 손익 3항목이 하나라도 있는가(09-23 이전 EPS 전용 수집분 판별)."""
    return any(any(k in r for k in INCOME_ITEMS) for r in records or [])


# 분기 성장률 지표(v16.27) — 항목 × 기준(QoQ=직전 분기, YoY=전년 동기). data_resolver가 런타임 계산.
QUARTERLY_GROWTH_METRICS: Dict[str, tuple] = {
    f"{item}_growth_{mode}": (item, mode)
    for item in INCOME_ITEMS for mode in ("qoq", "yoy")
}


def quarterly_growth_events(records: List[dict], item: str, mode: str) -> List[tuple]:
    """분기 성장률 사건 목록 [(announce_date, 성장률 %)] — 결산일 오름차순.

    QoQ는 직전 분기(결산일 간격 2~4개월), YoY는 전년 동기(11~13개월)를 **날짜로** 찾는다(목록 위치가
    아니다 — 빠진 분기가 있으면 어긋난다). 기준 값이 0 이하(적자·매출 없음)면 성장률의 뜻이 없어 뺀다."""
    rows = []
    for r in records or []:
        v, pe, ad = r.get(item), r.get("period_end"), r.get("announce_date")
        if v is None or not pe or not ad:
            continue
        rows.append((pd.Timestamp(pe), pd.Timestamp(ad), float(v)))
    rows.sort()
    lo, hi = ((2, 4) if mode == "qoq" else (11, 13))
    out = []
    for pe, ad, v in rows:
        base = None
        for cpe, _cad, cv in rows:
            gap = (pe.year - cpe.year) * 12 + (pe.month - cpe.month)
            if lo <= gap <= hi:
                base = cv
        if base is None or base <= 0:
            continue
        out.append((ad, (v / base - 1.0) * 100.0))
    return out


def quarterly_growth_series(records: List[dict], item: str, mode: str, dates) -> "pd.Series":
    """거래일 배열에 맞춘 as-of 성장률 시리즈(발표일부터 다음 발표 전까지 이어짐, 없으면 NaN)."""
    events = quarterly_growth_events(records, item, mode)
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    if not events:
        return pd.Series(float("nan"), index=idx)
    ev = pd.Series([v for _, v in events], index=pd.DatetimeIndex([d for d, _ in events]))
    ev = ev[~ev.index.duplicated(keep="last")].sort_index()
    return ev.reindex(idx, method="ffill")


def load_quarterly_earnings(symbol: str) -> Optional[List[dict]]:
    """캐시된 분기 실적. 없으면 None(수집 전과 '분기 실적이 없는 회사'를 구분하지 않는다)."""
    try:
        payload = json.loads(cache_path(symbol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    quarters = payload.get("quarters")
    return quarters if isinstance(quarters, list) and quarters else None


def save_quarterly_earnings(symbol: str, records: Optional[List[dict]]) -> None:
    path = cache_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "symbol": symbol,
                "fetched_at": pd.Timestamp.now().isoformat(timespec="seconds"),
                "quarters": records or [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
