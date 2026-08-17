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

from .fundamental_status import growth_and_status

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
# DART 일일 허용량(status 020) 소진으로 DART 단계를 못 마친 캐시(dart_pending)는 이 일수가
# 지나면 만료로 본다 — 한도는 매일 리셋되므로 다음 날 fetch가 KIS+DART를 다시 받아 완성한다.
# 당일에는 그대로 읽어 KIS 값을 쓰고 한도가 바닥난 DART를 다시 두드리지 않는다.
_DART_PENDING_RETRY_DAYS = 1

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CACHE_DIR = _PROJECT_ROOT / "data" / "fundamentals"
_DART_CORP_CODE_PATH = _PROJECT_ROOT / "data" / "dart_corpcode.json"
_DART_YEAR_FLOOR = 2015
_DART_ANNUAL_REPORT_CODE = "11011"


class DartQuotaExhausted(Exception):
    """DART 일일 허용량(status 020) 소진 — '데이터 없음'과 구분해 호출자가 미완성으로 다룬다."""
_DART_OPERATING_CASH_FLOW_ACCOUNT_ID = "ifrs-full_CashFlowsFromUsedInOperatingActivities"
_DART_OPERATING_CASH_FLOW_NAMES = {
    "영업활동현금흐름",
    "영업활동으로인한현금흐름",
    "영업활동으로부터의현금흐름",
    "영업활동으로인한순현금흐름",
    "영업활동순현금흐름",
}
# 투자·재무활동 현금흐름 총계 — 실측(2026-08-05, 삼성전자/SK하이닉스/현대차/카카오/셀트리온/
# 신한지주/SKT/포스코인터내셔널/클래시스/엘브이엠씨홀딩스/삼양식품 11종목)으로 확인. 11/11에서
# 아래 계정ID가 그대로 등장했고, account_nm은 "…현금흐름 / …으로인한현금흐름 / …순현금흐름"
# 세 표기로 갈렸다(계정ID가 없는 제출본 대비 폴백).
_DART_INVESTING_CASH_FLOW_ACCOUNT_ID = "ifrs-full_CashFlowsFromUsedInInvestingActivities"
_DART_INVESTING_CASH_FLOW_NAMES = {
    "투자활동현금흐름",
    "투자활동으로인한현금흐름",
    "투자활동으로부터의현금흐름",
    "투자활동으로인한순현금흐름",
    "투자활동순현금흐름",
}
_DART_FINANCING_CASH_FLOW_ACCOUNT_ID = "ifrs-full_CashFlowsFromUsedInFinancingActivities"
_DART_FINANCING_CASH_FLOW_NAMES = {
    "재무활동현금흐름",
    "재무활동으로인한현금흐름",
    "재무활동으로부터의현금흐름",
    "재무활동으로인한순현금흐름",
    "재무활동순현금흐름",
}
# CAPEX(FCF=OCF-CAPEX용) — 투자활동현금흐름의 유형·무형자산 취득. 실측(2026-07-21, 삼성전자/
# SK하이닉스/현대차 fnlttSinglAcntAll.json)으로 확인한 IFRS 표준 계정ID.
_DART_CAPEX_ACCOUNT_IDS = {
    "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    "ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
}
_DART_CAPEX_NAMES = {"유형자산의취득", "무형자산의취득"}
# 자본총계(자본잠식 판정용) — 재무상태표(BS) 섹션. 위와 동일 실측으로 확인.
_DART_TOTAL_EQUITY_ACCOUNT_ID = "ifrs-full_Equity"
_DART_TOTAL_EQUITY_NAMES = {"자본총계"}
# 지배기업 소유주 귀속 당기순이익(=지배주주순이익). 손익계산서(IS) 또는 포괄손익계산서(CIS)
# 섹션에 실리는데 어느 쪽인지는 제출본마다 갈린다(실측 2026-08-06, 12종목 2023년 CFS에서
# IS 5 / CIS 7) — 두 섹션을 모두 본다. 12/12가 아래 계정ID로 등장했다.
#
# 접두가 두 벌인 이유: IFRS 택소노미가 바뀌면서 2018년 사업보고서까지는 ``ifrs_``,
# 2019년부터는 ``ifrs-full_``을 쓴다(삼성전자 실측: 2018=ifrs_, 2019=ifrs-full_).
# 신형만 보면 2015~2018년이 조용히 결측된다 — 다른 DART 파서들은 이름 폴백이 있어 이 차이가
# 드러나지 않았다.
#
# **이름만으로는 절대 채택하지 않는다.** account_nm 표기가 회사마다 제각각인 데다("지배기업의
# 소유주에게 귀속되는 당기순이익(손실)" / "지배기업소유주지분" / "지배기업소유주" / "지배주주순이익"),
# 같은 CIS 섹션의 **총포괄손익** 귀속 행이 거의 같은 이름을 쓴다(SK하이닉스 실측: 순이익 귀속도
# 포괄손익 귀속도 "지배기업(의) 소유주지분"; 069330은 계정ID 없이 "지배기업소유주지분총포괄이익
# (손실)"). 이름으로 잡으면 포괄손익을 순이익으로 오인한다 — 계정ID 정확 일치가 1순위이고,
# 계정ID가 없는 제출본은 아래 **검산**(지배+비지배=당기순이익)을 통과할 때만 채택한다.
_DART_OWNER_NET_INCOME_ACCOUNT_IDS = {
    "ifrs-full_ProfitLossAttributableToOwnersOfParent",  # 2019년 사업보고서~
    "ifrs_ProfitLossAttributableToOwnersOfParent",       # ~2018년 사업보고서(구 택소노미)
}
_DART_OWNER_NET_INCOME_SECTIONS = ("IS", "CIS")
# 검산 폴백에 쓰는 계정들 — 정본 계정ID가 없는 제출본을 구제하되, 값이 실제로 '당기순이익의
# 귀속'인지 같은 응답 안에서 확인한 뒤에만 쓴다(2026-08-07 실측 90종목 표본에서 원인 분류).
#
#   ① 계속영업손익 귀속(003530·001270): 중단영업이 없으면 당기순이익 귀속과 **수치가 같다**.
#      부국증권 2024 실측 — 지배 30,945,550,007 + 비지배 7,004,743 = 당기순이익 30,952,554,750.
#      중단영업이 있으면 합이 어긋나므로 검산에서 자동 탈락한다(개념이 다른 값을 몰래 쓰지 않음).
#   ② 계정ID 미사용(005620·045660·066410): 이름으로 후보를 모으되 검산을 통과한 쌍만 쓴다.
#      총포괄손익 귀속 쌍은 합이 당기순이익이 아니라 여기서 걸러진다.
_DART_OWNER_CONTINUING_ACCOUNT_IDS = {
    "ifrs-full_IncomeFromContinuingOperationsAttributableToOwnersOfParent",
    "ifrs_IncomeFromContinuingOperationsAttributableToOwnersOfParent",
}
_DART_NCI_NET_INCOME_ACCOUNT_IDS = {
    "ifrs-full_ProfitLossAttributableToNoncontrollingInterests",
    "ifrs_ProfitLossAttributableToNoncontrollingInterests",
}
_DART_NCI_CONTINUING_ACCOUNT_IDS = {
    "ifrs-full_ProfitLossFromContinuingOperationsAttributableToNoncontrollingInterests",
    "ifrs_ProfitLossFromContinuingOperationsAttributableToNoncontrollingInterests",
}
_DART_PROFIT_LOSS_ACCOUNT_IDS = {"ifrs-full_ProfitLoss", "ifrs_ProfitLoss"}
_DART_EQUITY_OWNERS_ACCOUNT_IDS = {
    "ifrs-full_EquityAttributableToOwnersOfParent",
    "ifrs_EquityAttributableToOwnersOfParent",
}
_DART_NCI_EQUITY_ACCOUNT_IDS = {
    "ifrs-full_NoncontrollingInterests",
    "ifrs_NoncontrollingInterests",
}
_DART_EQUITY_ACCOUNT_IDS = {"ifrs-full_Equity", "ifrs_Equity"}
# 계정ID가 비어 있는 제출본의 표기(DART가 이 문자열을 그대로 실어 보낸다).
_DART_NO_ACCOUNT_ID = "-표준계정코드 미사용-"
_DART_CORP_CODES: Optional[Dict[str, str]] = None
# 종목별 결산월(MM) 캐시. DART 기업개황(company.json)의 acc_mt가 정본이며 바뀌는 일이 거의
# 없어 파일로 눌러 둔다 — 없으면 종목마다 매 갱신 때 1회씩 더 부르게 된다.
_DART_FISCAL_MONTH_PATH = _PROJECT_ROOT / "data" / "dart_fiscal_month.json"
_DART_FISCAL_MONTHS: Optional[Dict[str, str]] = None
_DEFAULT_FISCAL_MONTH = "12"

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
    """로컬 JSON 캐시에서 펀더멘털 데이터를 읽는다. 만료 시 None 반환.

    DART 한도 소진으로 미완성인 캐시(dart_pending)는 _DART_PENDING_RETRY_DAYS가 지나면
    만료로 본다 — 2026-08-04 백필에서 한도 소진 뒤 캐시된 약 420종목이 90일짜리 '완성본'으로
    남아 지배주주순이익·현금흐름·FCF가 통째로 비었던 사고의 재발 방지.
    """
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
            if data.get("dart_pending") and age >= _DART_PENDING_RETRY_DAYS:
                return None
        return data.get("fundamentals")
    except Exception:
        return None


def is_dart_pending(symbol: str) -> bool:
    """캐시가 DART 한도 소진으로 미완성 상태인지(수리 스크립트의 대상 선별용)."""
    path = _cache_path(symbol)
    if not path.exists():
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("dart_pending"))
    except Exception:
        return False


def _write_cache(symbol: str, fundamentals: List[Dict], *, dart_pending: bool = False) -> None:
    """펀더멘털 데이터를 로컬 JSON 캐시에 저장한다.

    dart_pending=True는 DART 단계를 한도 소진으로 못 마쳤다는 표시다 — 값 자체(KIS)는
    쓸 수 있되 _read_cache가 다음 날 만료로 취급해 재조회하게 한다.
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(symbol)
    payload = {
        "symbol": symbol,
        "fetched_at": pd.Timestamp.now().isoformat(),
        "fundamentals": fundamentals,
    }
    if dart_pending:
        payload["dart_pending"] = True
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
    # 영업이익(raw, income-statement bsop_prti), 자본총계(DART BS, 자본잠식 판정용),
    # CAPEX/FCF(DART CF), EV·EV/EBIT(ev_ebitda x ebitda로 역산 — fundamental_status.py 참고).
    "ebit", "total_equity", "capex", "fcf", "ev", "ev_ebit",
    # 로컬 재계산 성장률(부호 왜곡 방지 위해 KIS 원 증가율 대신 raw 값으로 직접 계산,
    # fundamental_fetcher._compute_derived_annual_metrics 참고). revenue_growth는 매출이
    # 항상 양수라는 전제로 KIS 원값을 그대로 쓴다(변경 없음).
    "eps_growth", "ebitda_growth", "ocf_growth", "fcf_growth",
    # 당기순이익(억원) — 순이익률 x 매출액 로컬 재계산(net_income_growth 재계산과 같은
    # 컴포넌트). 절대 금액 필터('당기순이익 1,000억 이상') 지원용(2026-08-03).
    "net_income",
    # 지배주주순이익(억원) — DART 손익계산서의 '지배기업 소유주 귀속 당기순이익'. 위
    # net_income은 KIS 순이익률x매출액이라 **비지배지분이 섞인 연결 전체 당기순이익**이다
    # (삼성전자 2023 실측: 전체 154,843억 = 지배 144,734 + 비지배 10,137). 지주회사·자회사
    # 비중이 큰 기업에서 둘은 크게 갈리므로 별도 지표로 둔다. DART 유래라 2015년 이전과
    # 별도재무제표(OFS)만 있는 종목은 결측이다(2026-08-06).
    "owner_net_income",
    # 투자·재무활동 현금흐름 총계(원 단위 raw — operating_cash_flow와 동일 기준). DART CF
    # 섹션에서 OCF와 같은 응답으로 파싱하므로 추가 API 호출은 없다(2026-08-05).
    "investing_cash_flow", "financing_cash_flow",
    # 위 3분류의 억원 환산본 — 조건 필터·배지가 쓰는 단위(raw는 PCR·FCF 계산 기준이라 유지).
    "operating_cf_amount", "investing_cf_amount", "financing_cf_amount",
]
# 위 성장률(+기존 operating_income_growth/net_income_growth)의 부호전환 상태코드. 문자열이라
# enrich_ohlcv_with_fundamentals에서 float 대신 object dtype 시리즈로 다뤄야 한다.
ANNUAL_FUNDAMENTAL_STATUS_KEYS = [
    "operating_income_growth_status", "net_income_growth_status",
    "eps_growth_status", "ebitda_growth_status", "ocf_growth_status", "fcf_growth_status",
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
    """KIS 손익계산서 rows → {year_end: {"operating_margin", "ebit", "_revenue"}}.

    ebit(raw 영업이익)은 EV/EBIT 계산에, _revenue(매출액)는 net_margin과 결합해 순이익을
    유도(_compute_derived_annual_metrics)하는 데 쓰인다 — _revenue는 내부용이라
    ANNUAL_FUNDAMENTAL_KEYS에 없고, 화면/필터에는 노출되지 않는다.
    """
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
            by_year[year_end] = {
                "operating_margin": round(op / sale * 100.0, 2),
                "ebit": op,
                "_revenue": sale,
            }
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


def _parse_dart_activity_cash_flow(
    rows: list, account_id_key: str, name_keys: set
) -> Optional[Dict]:
    """CF 섹션에서 활동별 현금흐름 '총계' 한 행을 뽑는다.

    계정ID 일치를 이름 일치보다 우선한다 — 이름만 비슷한 소계(예: 포스코인터내셔널의
    "영업활동에서창출된현금흐름" = 이자·법인세 차감 전 금액)를 총계로 오인하지 않기 위함.
    """
    if not isinstance(rows, list):
        return None

    candidates = []
    for row in rows:
        if not isinstance(row, dict) or row.get("sj_div") != "CF":
            continue
        account_id = str(row.get("account_id", "")).strip()
        normalized_name = re.sub(r"\s+", "", str(row.get("account_nm", "")))
        if account_id != account_id_key and normalized_name not in name_keys:
            continue
        amount = _parse_number(str(row.get("thstrm_amount", "")))
        available_from = _parse_dart_receipt_date(row.get("rcept_no"))
        if amount is None or not available_from:
            continue
        candidates.append((account_id == account_id_key, amount, available_from))

    if not candidates:
        return None
    _, amount, available_from = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
    return {"amount": amount, "available_from": available_from}


def _parse_dart_operating_cash_flow(rows: list) -> Optional[Dict]:
    """Extract net operating cash flow without matching operating-asset subtotals."""
    parsed = _parse_dart_activity_cash_flow(
        rows, _DART_OPERATING_CASH_FLOW_ACCOUNT_ID, _DART_OPERATING_CASH_FLOW_NAMES
    )
    if not parsed:
        return None
    return {
        "operating_cash_flow": parsed["amount"],
        "available_from": parsed["available_from"],
    }


def _parse_dart_capex(rows: list) -> Optional[float]:
    """CF 섹션의 유형자산·무형자산 취득(투자활동현금흐름)을 합산한 CAPEX(양수 금액)."""
    if not isinstance(rows, list):
        return None
    total = 0.0
    found = False
    for row in rows:
        if not isinstance(row, dict) or row.get("sj_div") != "CF":
            continue
        account_id = str(row.get("account_id", "")).strip()
        normalized_name = re.sub(r"\s+", "", str(row.get("account_nm", "")))
        if account_id not in _DART_CAPEX_ACCOUNT_IDS and normalized_name not in _DART_CAPEX_NAMES:
            continue
        amount = _parse_number(str(row.get("thstrm_amount", "")))
        if amount is None:
            continue
        total += abs(amount)
        found = True
    return total if found else None


def _parse_dart_total_equity(rows: list) -> Optional[float]:
    """BS 섹션의 자본총계(부호 그대로 반환 — 자본잠식이면 음수)."""
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict) or row.get("sj_div") != "BS":
            continue
        account_id = str(row.get("account_id", "")).strip()
        normalized_name = re.sub(r"\s+", "", str(row.get("account_nm", "")))
        if account_id != _DART_TOTAL_EQUITY_ACCOUNT_ID and normalized_name not in _DART_TOTAL_EQUITY_NAMES:
            continue
        amount = _parse_number(str(row.get("thstrm_amount", "")))
        if amount is not None:
            return amount
    return None


def _iter_dart_rows(rows: list, sections: tuple):
    """(account_id, 공백제거 account_nm, amount) — 지정 섹션의 파싱 가능한 행만."""
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict) or row.get("sj_div") not in sections:
            continue
        amount = _parse_number(str(row.get("thstrm_amount", "")))
        if amount is None:
            continue
        yield (
            str(row.get("account_id", "")).strip(),
            re.sub(r"\s+", "", str(row.get("account_nm", ""))),
            amount,
        )


def _dart_amount_by_ids(rows: list, sections: tuple, ids: set) -> Optional[float]:
    for account_id, _, amount in _iter_dart_rows(rows, sections):
        if account_id in ids:
            return amount
    return None


def _attribution_sums_to_profit(owner: float, nci: float, profit_loss: float) -> bool:
    """지배 + 비지배 = 당기순이익 검산. 원 단위 정수라 오차 허용치는 형식적이다."""
    return abs(owner + nci - profit_loss) <= max(1.0, abs(profit_loss) * 1e-9)


def _parse_dart_owner_net_income(rows: list) -> Optional[float]:
    """IS/CIS 섹션의 지배기업 소유주 귀속 당기순이익(부호 그대로 — 적자면 음수).

    1순위는 정본 계정ID 정확 일치다. 그 계정이 없는 제출본은 **같은 응답 안에서 검산이
    성립할 때만** 구제한다(_DART_OWNER_CONTINUING_ACCOUNT_IDS 주석의 원인 분류 참고):

      ② 계속영업손익 귀속 / ③ 계정ID 미사용 이름 후보
         → 지배 + 비지배 = 당기순이익(ProfitLoss)이면 채택, 아니면 버린다.
      ④ 귀속 행이 아예 없고 비지배지분이 0(자본총계 = 지배기업소유주지분)
         → 당기순이익 전액이 지배주주 귀속이다.

    검산이 하는 일은 "이름이 비슷한 다른 개념(총포괄손익·계속영업손익≠당기순이익)을
    조용히 집어넣지 않는 것"이다 — 통과하지 못하면 결측으로 남긴다.
    별도재무제표(OFS)에는 이 개념 자체가 없으므로 None이 정상이다.
    """
    sections = _DART_OWNER_NET_INCOME_SECTIONS

    canonical = _dart_amount_by_ids(rows, sections, _DART_OWNER_NET_INCOME_ACCOUNT_IDS)
    if canonical is not None:
        return canonical

    profit_loss = _dart_amount_by_ids(rows, sections, _DART_PROFIT_LOSS_ACCOUNT_IDS)
    if profit_loss is None:
        return None

    # ②③ 후보 x 비지배 후보를 검산에 걸어 통과한 쌍만 채택한다. '비지배'가 '지배'를 부분
    #     문자열로 포함하므로 소유주 후보에서 반드시 제외한다.
    untagged = [
        (name, amount)
        for account_id, name, amount in _iter_dart_rows(rows, sections)
        if account_id in ("", _DART_NO_ACCOUNT_ID) and "지배" in name
    ]
    owner_candidates = [
        amount for amount in
        (_dart_amount_by_ids(rows, sections, _DART_OWNER_CONTINUING_ACCOUNT_IDS),)
        if amount is not None
    ] + [amount for name, amount in untagged if "비지배" not in name]
    if not owner_candidates:
        # ④ 귀속 행이 아예 없는 제출본 — 비지배지분이 없으면 당기순이익 전액이 지배주주 귀속.
        if _dart_has_no_minority_interest(rows):
            return profit_loss
        return None

    nci_candidates = [
        amount for amount in (
            _dart_amount_by_ids(rows, sections, _DART_NCI_NET_INCOME_ACCOUNT_IDS),
            _dart_amount_by_ids(rows, sections, _DART_NCI_CONTINUING_ACCOUNT_IDS),
        ) if amount is not None
    ] + [amount for name, amount in untagged if "비지배" in name]
    # 비지배 귀속 행 자체가 없으면(003530 실측) 비지배가 0이라는 뜻이다 — 소유주 값 단독으로
    # 당기순이익과 일치하는지 검산한다.
    if not nci_candidates:
        nci_candidates = [0.0]

    for owner in owner_candidates:
        for nci in nci_candidates:
            if _attribution_sums_to_profit(owner, nci, profit_loss):
                return owner

    return None


def _dart_has_no_minority_interest(rows: list) -> bool:
    """재무상태표로 비지배지분이 없음을 확인한다(0으로 명시되거나 자본총계=지배지분)."""
    nci_equity = _dart_amount_by_ids(rows, ("BS",), _DART_NCI_EQUITY_ACCOUNT_IDS)
    if nci_equity is not None:
        return nci_equity == 0
    total_equity = _dart_amount_by_ids(rows, ("BS",), _DART_EQUITY_ACCOUNT_IDS)
    owners_equity = _dart_amount_by_ids(rows, ("BS",), _DART_EQUITY_OWNERS_ACCOUNT_IDS)
    return (
        total_equity is not None
        and owners_equity is not None
        and total_equity == owners_equity
    )


def _get_dart_corp_code(symbol: str) -> Optional[str]:
    global _DART_CORP_CODES
    if _DART_CORP_CODES is None:
        try:
            payload = json.loads(_DART_CORP_CODE_PATH.read_text(encoding="utf-8"))
            _DART_CORP_CODES = payload if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            _DART_CORP_CODES = {}
    return _DART_CORP_CODES.get(symbol)


def dart_fiscal_month(symbol: str, corp_code: str) -> str:
    """종목의 결산월(MM). DART 기업개황 acc_mt가 정본이고, 조회 실패 시 '12'로 둔다.

    12월 결산이 아닌 회사(효성오앤비 06, 금비 09 등 실측 42종목)를 12월로 가정하면 DART
    레코드가 엉뚱한 날짜에 붙어 같은 회계연도의 KIS 값과 다른 레코드로 갈라진다.
    """
    global _DART_FISCAL_MONTHS
    if _DART_FISCAL_MONTHS is None:
        try:
            payload = json.loads(_DART_FISCAL_MONTH_PATH.read_text(encoding="utf-8"))
            _DART_FISCAL_MONTHS = payload if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            _DART_FISCAL_MONTHS = {}

    cached = _DART_FISCAL_MONTHS.get(symbol)
    if cached:
        return cached

    payload = _fetch_dart_json("company.json", {"corp_code": corp_code})
    month = str(payload.get("acc_mt", "")).strip().zfill(2)
    if payload.get("status") != "000" or not month.isdigit() or not 1 <= int(month) <= 12:
        return _DEFAULT_FISCAL_MONTH  # 실패는 캐시하지 않는다 — 다음에 다시 시도한다

    _DART_FISCAL_MONTHS[symbol] = month
    try:
        _DART_FISCAL_MONTH_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DART_FISCAL_MONTH_PATH.write_text(
            json.dumps(_DART_FISCAL_MONTHS, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        pass
    return month


def dart_year_end(bsns_year: int, month: str) -> str:
    """DART bsns_year + 결산월 → 결산일('YYYY-MM-DD').

    bsns_year는 **그 결산기가 끝나는 달력 연도**다(실측 2026-08-07: 효성오앤비 bsns_year
    2023의 당기순이익 12.3억 = KIS 2023-06 레코드 12.4억, 금비 2024 = KIS 2024-09).
    """
    return (
        pd.Timestamp(year=int(bsns_year), month=int(month), day=1) + pd.offsets.MonthEnd(0)
    ).strftime("%Y-%m-%d")


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


# 사업보고서 이름에서 결산연도와 **결산월**을 함께 뽑는다 — "사업보고서 (2020.12)".
# 괄호 연도는 bsns_year와 같고 괄호 월은 그 사업연도의 결산월이다(실측 2026-08-07:
# 효성오앤비 '사업보고서 (2025.06)' 접수 2025-09-19, 금비 '(2025.09)' 접수 2025-12-15).
# `[기재정정]사업보고서 (2023.06)`도 같은 이름이라 search()에 걸리지만, 연도별 min()이
# 원공시를 고르므로 정정일로 밀리지 않는다.
_DART_ANNUAL_REPORT_NAME = re.compile(r"사업보고서\s*\((\d{4})\.(\d{2})\)")


def _fetch_dart_annual_report_periods(corp_code: str) -> Dict[int, Tuple[str, str]]:
    """{결산연도: (결산월 'MM', 원공시 접수일 'YYYY-MM-DD')}.

    두 가지를 한 번의 조회로 얻는다.
      · 원공시 접수일 — fnlttSinglAcntAll의 rcept_no는 정정공시가 있으면 정정본을 가리켜
        available_from이 정정일로 밀린다(PIT 왜곡, 최대 수년). 연도별 최초 접수일로 클램프.
      · **연도별** 결산월 — 기업개황 acc_mt는 '현재' 결산월 하나뿐이라 결산기를 변경한
        회사의 변경 이전 연도를 틀리게 만든다(유유제약: 2017년 3월→12월 전환, 그 이전
        연도의 DART 값이 12-31에 붙어 KIS 3월 레코드와 갈라졌다). 사업보고서 이름은
        연도마다 그 해의 결산월을 달고 있어 이 문제가 없다.

    조회 시작을 결산연도 하한 그 해로 잡는다 — 12월 결산은 이듬해 3월에 제출하지만
    비12월 결산은 같은 해에 제출하므로(6월 결산 → 9월 제출) 이듬해부터 훑으면 빠진다.
    실패·쿼터 초과 시 빈 dict(클램프·연도별 결산월 생략 = acc_mt 폴백)."""
    periods: Dict[int, Tuple[str, str]] = {}
    page = 1
    while True:
        payload = _fetch_dart_json(
            "list.json",
            {
                "corp_code": corp_code,
                "bgn_de": f"{_DART_YEAR_FLOOR}0101",
                "end_de": pd.Timestamp.now().strftime("%Y%m%d"),
                "pblntf_detail_ty": "A001",
                "last_reprt_at": "N",
                "page_no": str(page),
                "page_count": "100",
            },
        )
        if payload.get("status") != "000":
            break
        for row in payload.get("list", []):
            match = _DART_ANNUAL_REPORT_NAME.search(str(row.get("report_nm", "")))
            rcept_dt = re.sub(r"\D", "", str(row.get("rcept_dt", "")))
            if not match or len(rcept_dt) != 8:
                continue
            year, month = int(match.group(1)), match.group(2)
            date = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:]}"
            existing = periods.get(year)
            # 원공시(최소 접수일)의 월을 그 해의 결산월로 삼는다 — 정정본과 짝을 맞춘다.
            if existing is None or date < existing[1]:
                periods[year] = (month, date)
        if page * 100 >= int(payload.get("total_count") or 0):
            break
        page += 1
    return periods


def _fetch_dart_original_filing_dates(corp_code: str) -> Dict[int, str]:
    """연도별 사업보고서 **원공시** 접수일 {결산연도: 'YYYY-MM-DD'}."""
    return {year: date for year, (_, date) in _fetch_dart_annual_report_periods(corp_code).items()}


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

    # 결산월 — 12월로 고정하면 비12월 결산 회사(실측 23종목)의 DART 값이 실제 결산일과
    # 다른 날짜에 붙어 같은 회계연도의 KIS 값과 다른 레코드로 갈라진다. 사업보고서 이름에서
    # **연도별** 결산월을 얻어(결산기 변경 회사 대응) 원공시 접수일과 한 번에 가져온다.
    periods = _fetch_dart_annual_report_periods(corp_code)
    fallback_month: Optional[str] = None

    def _fiscal_month_for(year: int) -> str:
        """그 해의 결산월. 공시 목록에 없으면 기업개황 acc_mt로 떨어진다(조회는 1회만)."""
        nonlocal fallback_month
        known = periods.get(year)
        if known:
            return known[0]
        if fallback_month is None:
            fallback_month = dart_fiscal_month(symbol, corp_code)
        return fallback_month

    last_year = end_year if end_year is not None else pd.Timestamp.now().year - 1
    results = []
    for year in range(max(start_year, _DART_YEAR_FLOOR), last_year + 1):
        cash_flow = None
        rows: list = []
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
                # 한도 소진은 '없음'이 아니다. 부분 결과를 돌려주면 호출자가 완성본으로
                # 캐시한다(2026-08-04 사고: 뒤쪽 ~420종목이 DART 없이 90일 캐시됨).
                raise DartQuotaExhausted(symbol)
            if payload.get("status") == "000":
                rows = payload.get("list", [])
                cash_flow = _parse_dart_operating_cash_flow(rows)
                if cash_flow:
                    break
        if not cash_flow:
            continue
        record = {
            "year_end": dart_year_end(year, _fiscal_month_for(year)),
            "available_from": cash_flow["available_from"],
            "operating_cash_flow": cash_flow["operating_cash_flow"],
        }
        # 투자·재무활동 현금흐름 총계도 같은 응답에서 파싱(추가 호출 0).
        for key, account_id, names in (
            ("investing_cash_flow",
             _DART_INVESTING_CASH_FLOW_ACCOUNT_ID, _DART_INVESTING_CASH_FLOW_NAMES),
            ("financing_cash_flow",
             _DART_FINANCING_CASH_FLOW_ACCOUNT_ID, _DART_FINANCING_CASH_FLOW_NAMES),
        ):
            parsed = _parse_dart_activity_cash_flow(rows, account_id, names)
            if parsed is not None:
                record[key] = parsed["amount"]
        # 같은 응답(rows)에서 CAPEX(FCF용)·자본총계(자본잠식 판정용)도 추가 API 호출 없이 파싱.
        capex = _parse_dart_capex(rows)
        if capex is not None:
            record["capex"] = capex
        total_equity = _parse_dart_total_equity(rows)
        if total_equity is not None:
            record["total_equity"] = total_equity
        # 지배주주순이익도 같은 응답에서 파싱한다(추가 호출 0). raw 원 단위라 억원 환산은
        # _compute_derived_annual_metrics가 맡는다 — 내부 키(_ 접두)는 저장되지 않는다.
        owner_net_income = _parse_dart_owner_net_income(rows)
        if owner_net_income is not None:
            record["_owner_net_income_raw"] = owner_net_income
        # 당기순이익 총액(연결 전체) — KIS 순이익률x매출 재계산본을 대체할 정본이다.
        # 같은 손익계산서에서 나오므로 owner_net_income과 정합하고(지배+비지배=이 값),
        # 저마진 연도에 순이익률 반올림(소수 2자리)이 절대금액을 흔들던 문제가 사라진다.
        profit_loss = _dart_amount_by_ids(
            rows, _DART_OWNER_NET_INCOME_SECTIONS, _DART_PROFIT_LOSS_ACCOUNT_IDS
        )
        if profit_loss is not None:
            record["_profit_loss_raw"] = profit_loss
        results.append(record)

    # available_from을 원공시 접수일로 클램프(min) — 정정공시 접수일로 밀린 값 교정.
    # 위에서 이미 받아 둔 periods를 재사용한다(추가 호출 0).
    for record in results:
        known = periods.get(int(record["year_end"][:4]))
        if known and known[1] < record["available_from"]:
            record["available_from"] = known[1]

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


# 연간 레코드로 인정하는 최소 간격(개월). 결산 주기는 12개월이고 KIS가 끼워 보내는 분기
# 누적 행은 직전 결산으로부터 3·6·9개월 뒤라 여기에 못 미친다. 11로 둬 결산일이 며칠
# 흔들리는 경우(예: 2월 말 결산)를 흡수한다.
_ANNUAL_PERIOD_MIN_MONTHS = 11


def _months_between(earlier: object, later: object) -> Optional[int]:
    """'YYYY-MM-DD' 두 개의 개월 차이. 파싱 불가면 None."""
    try:
        a, b = str(earlier), str(later)
        return (int(b[:4]) - int(a[:4])) * 12 + (int(b[5:7]) - int(a[5:7]))
    except (TypeError, ValueError, IndexError):
        return None


def fiscal_month(year_ends) -> Optional[str]:
    """레코드들의 결산월(MM) — 월 최빈값. 12월 결산이 아닌 회사도 자동으로 맞는다."""
    months = [str(y)[5:7] for y in year_ends if len(str(y)) >= 7]
    if not months:
        return None
    return max(sorted(set(months)), key=months.count)


def drop_kis_interim_records(records: List[Dict]) -> List[Dict]:
    """KIS 응답에 끼어드는 **최신 분기 누적** 레코드를 걷어낸다.

    KIS 재무 엔드포인트는 연간(FID_DIV_CLS_CODE=0)을 요청해도 맨 앞에 최신 분기 한 행을
    끼워 보낸다(실측 2026-08-07, 현대차: stac_yymm 202603, 202512, 202412, 202312 …).
    파라미터로 뺄 수 없어 우리가 걸러야 한다.

    그 행의 **비율**은 연환산돼 정상이지만 **유량**은 기중 누적이라 1분기치다(현대차 실측:
    ROE 89%·부채비율 101%·BPS 104%인데 EPS 25%·영업이익 22%·EBITDA 23%·당기순이익 25%).
    게다가 성장률은 앞뒤 레코드 비교라 분기 행이 직전 '연간'과 비교되면서 순이익증가율
    -75%·영업이익증가율 -78%로 오염되고, PER은 종가÷EPS라 약 4배로 부푼다.

    지표별로 골라 버리지 않고 **레코드째** 버리는 이유: 레지스트리·인터프리터 프롬프트·SRS가
    모두 이 데이터를 "최근 연간 결산 기준"이라고 설명하는 단일 계약이고, 성장률 체인에 분기
    행이 남아 있으면 계속 오염되며, 지표마다 기준 시점이 갈리면 배지·리포트에서 "언제 값인가"를
    설명할 수 없기 때문이다.

    KIS가 끼워 보내는 행은 **정확히 하나, 맨 앞(최신)** 이므로 최신 레코드 하나만 후보로 본다.

    판정은 월이 아니라 **직전 레코드와의 간격**으로 한다. 연간 레코드는 12개월 간격이고
    분기 행은 직전 결산으로부터 3·6·9개월 뒤라 간격이 짧다(현대차: 2025-12 → 2026-03 = 3개월).
    월 최빈값과 비교하는 방식은 결산기를 바꾼 회사에서 깨진다 — 옛 체제 레코드가 아직 더
    많으면 새 체제의 첫 연간 레코드(12월 무리 3건 + 3월 무리 3건에서 최신 3월 행)를 분기로
    오인해 버린다(회귀 테스트 있음). 간격으로 보면 결산기 변경은 12개월을 넘어 살아남는다.
    """
    if len(records) <= 1:
        return records
    ordered = sorted(records, key=lambda r: str(r.get("year_end", "")))
    gap = _months_between(ordered[-2].get("year_end"), ordered[-1].get("year_end"))
    if gap is None or gap >= _ANNUAL_PERIOD_MIN_MONTHS:
        return records
    interim = ordered[-1]
    return [r for r in records if r is not interim]  # 입력 순서 보존


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

    # ev_ebitda의 0.00은 '데이터 없음' 센티널(2010년 이전 등) — 0.00만 제거한다. 진짜 음수
    # (적자 EBITDA로 인한 유효한 음수)는 보존해 fundamental_status.ev_ebitda_status가 노출
    # 여부를 판정하게 한다(이전엔 비양수를 통째로 지워 진짜 음수 정보까지 손실됐었다).
    for vals in merged.values():
        if "ev_ebitda" in vals and vals["ev_ebitda"] == 0:
            del vals["ev_ebitda"]

    result = [{"year_end": d, **vals} for d, vals in sorted(merged.items(), reverse=True) if vals]
    # 5개 엔드포인트를 다 병합한 **한 자리에서** 분기 행을 거른다 — 엔드포인트마다 흩어 놓으면
    # 하나를 빠뜨린다. DART 유래 레코드는 이 함수를 거치지 않으므로 영향받지 않는다.
    result = drop_kis_interim_records(result)
    return result or None


def _compute_derived_annual_metrics(records: List[Dict]) -> List[Dict]:
    """연도별 병합 레코드에 FCF·EV·EV/EBIT과 로컬 재계산 성장률(+상태)을 추가한다.

    KIS가 직접 제공하는 영업이익/순이익 증가율은 흑자<->적자 전환기에 부호가 왜곡될 수 있어
    신뢰하지 않고, 이미 확보한 raw 컴포넌트(ebit, _revenue x net_margin, ebitda, ocf, fcf,
    eps)로 연도별 로컬 재계산한다. revenue_growth는 매출이 항상 양수라는 전제로 KIS 원값을
    그대로 둔다(변경 없음). 상태코드(TURNAROUND 등)는 두 연도의 raw 값이 있어야만 판정할 수
    있어 — 일별로 전진충전되고 나면 '직전 연도' 값이 더 이상 보이지 않으므로 — 이 시점에 함께
    계산해 growth 컬럼과 나란히 저장한다(비율 지표의 상태코드는 반대로 매 시점 단일 값만
    있으면 판정 가능해 fundamental_status.py에서 즉석 계산하고 저장하지 않는다).
    """
    sorted_records = sorted(
        (r for r in records if r.get("year_end")), key=lambda r: r["year_end"]
    )

    for rec in sorted_records:
        revenue = rec.get("_revenue")
        net_margin = rec.get("net_margin")
        if revenue is not None and net_margin is not None:
            # 당기순이익(억원) — 성장률 재계산 컴포넌트였다가 절대 금액 필터 지원으로
            # 저장 승격(2026-08-03). revenue(sale_account)가 억원이라 결과도 억원.
            rec["net_income"] = round(net_margin / 100.0 * revenue, 1)

        ocf = rec.get("operating_cash_flow")
        capex = rec.get("capex")
        if ocf is not None and capex is not None:
            rec["fcf"] = ocf - capex

        # 현금흐름 3분류 절대금액(억원) — DART 유래 raw 원 값을 필터 단위로 환산한다.
        # raw 컬럼은 PCR(market_cap x 1e8 / ocf)·FCF 계산 기준이라 그대로 두고, 조건
        # 필터·배지는 억원 컬럼을 쓴다(net_income·market_cap과 같은 관례, 2026-08-05).
        for amount_key, raw_key in (
            ("operating_cf_amount", "operating_cash_flow"),
            ("investing_cf_amount", "investing_cash_flow"),
            ("financing_cf_amount", "financing_cash_flow"),
        ):
            raw_amount = rec.get(raw_key)
            if raw_amount is not None:
                rec[amount_key] = round(raw_amount / 1e8, 1)

        # 지배주주순이익(억원) — DART raw 원 단위를 금액 관례(억원)로 환산한다.
        owner_raw = rec.get("_owner_net_income_raw")
        if owner_raw is not None:
            rec["owner_net_income"] = round(owner_raw / 1e8, 1)

        # 당기순이익은 DART 원값이 있으면 그것이 이긴다(위 KIS 재계산본을 덮어쓴다).
        # KIS본은 net_margin(소수 2자리 반올림) x 매출이라 저마진 연도에 절대금액 오차가
        # 크다 — 순이익 10억 규모에서 수백 %까지 벌어진 실측이 있다. DART가 없는 구간
        # (2015년 이전·별도재무제표만 제출)은 KIS 재계산본을 그대로 남긴다.
        profit_loss_raw = rec.get("_profit_loss_raw")
        if profit_loss_raw is not None:
            rec["net_income"] = round(profit_loss_raw / 1e8, 1)

        ebitda = rec.get("ebitda")
        ev_ebitda_ratio = rec.get("ev_ebitda")
        if ebitda is not None and ebitda > 0 and ev_ebitda_ratio is not None:
            ev = ev_ebitda_ratio * ebitda
            rec["ev"] = ev
            ebit = rec.get("ebit")
            if ebit is not None and ebit > 0:
                rec["ev_ebit"] = ev / ebit

    prior: Optional[Dict] = None
    for rec in sorted_records:
        if prior is not None:
            for growth_key, status_key, driver_key in (
                ("eps_growth", "eps_growth_status", "eps"),
                ("ebitda_growth", "ebitda_growth_status", "ebitda"),
                ("ocf_growth", "ocf_growth_status", "operating_cash_flow"),
                ("fcf_growth", "fcf_growth_status", "fcf"),
                ("operating_income_growth", "operating_income_growth_status", "ebit"),
                ("net_income_growth", "net_income_growth_status", "net_income"),
            ):
                growth, status = growth_and_status(prior.get(driver_key), rec.get(driver_key))
                if growth is not None:
                    rec[growth_key] = growth
                elif growth_key in rec:
                    del rec[growth_key]  # KIS 원 증가율(operating/net) 대신 로컬 재계산으로 대체
                if status is not None and status != "MISSING_DATA":
                    rec[status_key] = status
        prior = rec

    for rec in sorted_records:
        rec.pop("_revenue", None)
        rec.pop("_owner_net_income_raw", None)
        rec.pop("_profit_loss_raw", None)

    return sorted_records


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

    # DART 한도 소진은 KIS 값을 버릴 이유는 아니지만 완성본도 아니다 — dart_pending으로
    # 캐시해 당일은 KIS 값을 쓰고, 다음 날 _read_cache가 만료로 취급해 다시 받게 한다.
    dart_pending = False
    try:
        cash_flow = _fetch_cash_flow_from_dart(symbol)
    except DartQuotaExhausted:
        logger.warning("[DART] %s: 일일 허용량 소진 — DART 항목 없이 dart_pending 캐시", symbol)
        cash_flow = None
        dart_pending = True
    result = _merge_fundamental_records(result, cash_flow)
    if result:
        result = _compute_derived_annual_metrics(result)

    if result:
        _write_cache(symbol, result, dart_pending=dart_pending)
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
    # 추가 지표는 데이터에 존재할 때만 컬럼을 만든다. 성장률 상태코드(*_growth_status)는
    # 문자열이라 float 시리즈가 아닌 object 시리즈로 다룬다.
    _base = ["eps", "bps", "roe_or_gpa", "debt_ratio"]
    present_keys = list(dict.fromkeys(
        _base
        + [k for k in ANNUAL_FUNDAMENTAL_KEYS if k in fund_df.columns]
        + [k for k in ANNUAL_FUNDAMENTAL_STATUS_KEYS if k in fund_df.columns]
    ))
    series = {
        k: pd.Series(index=df.index, dtype=(object if k in ANNUAL_FUNDAMENTAL_STATUS_KEYS else float))
        for k in present_keys
    }

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

    # 가격 기반 밸류에이션 비율: PER=close/EPS, PBR=close/BPS, PSR=close/SPS. PER/PBR은
    # 분모(순이익/지배주주지분)가 음수(적자·자본잠식)면 금융적으로 무의미해 null 처리한다
    # (PSR은 매출이 항상 양수라는 전제로 기존 방식 유지 — 요구사항대로 변경하지 않음).
    close = df["close"].astype(float)
    for ratio, denom, positive_only in (
        ("per", "eps", True),
        ("pbr", "bps", True),
        ("psr", "sps", False),
    ):
        if denom in df.columns:
            denom_ok = (df[denom] > 0) if positive_only else (df[denom] != 0)
            valid = df[denom].notna() & denom_ok
            df[ratio] = (close / df[denom]).where(valid).replace([_np.inf, -_np.inf], _np.nan)

    # ROE는 KIS가 직접 제공하는 비율이라 여기서 재계산하지 않지만, 자기자본(total_equity
    # 우선, 없으면 BPS로 근사)이 음수(자본잠식)면 값 자체가 금융적으로 무의미해 null 처리한다.
    if "roe_or_gpa" in df.columns:
        equity_col = df["total_equity"] if "total_equity" in df.columns else df.get("bps")
        if equity_col is not None:
            df.loc[equity_col.notna() & (equity_col <= 0), "roe_or_gpa"] = _np.nan

    # PCR = 시가총액 / 영업활동현금흐름. OHLCV 종가는 기업행사 조정 가격이므로,
    # 과거 비조정 주식 수로 CFPS를 만들면 액면분할 전 기간이 왜곡된다. parquet의
    # 일별 market_cap(억원)을 사용해 동일한 가격 조정 기준을 유지한다.
    df = recompute_pcr(df)

    return _add_dividend_metrics(df)


def recompute_pcr(df: pd.DataFrame) -> pd.DataFrame:
    """PCR(=market_cap 억원×1e8 / 영업활동현금흐름 raw 원)을 현재 컬럼 기준으로 재계산한다.

    enrich와 시총 재구축(scripts/rebuild_market_cap.py)이 같은 정의를 공유하는
    유일한 자리다. 두 컬럼 중 하나라도 없으면 no-op, 분모(OCF)가 비양수면 null.
    """
    if "market_cap" not in df.columns or "operating_cash_flow" not in df.columns:
        return df
    import numpy as _np
    valid = (
        df["market_cap"].notna()
        & df["operating_cash_flow"].notna()
        & (df["operating_cash_flow"] > 0)
    )
    df = df.copy()
    df["pcr"] = (
        df["market_cap"].astype(float) * 1e8 / df["operating_cash_flow"]
    ).where(valid).replace([_np.inf, -_np.inf], _np.nan)
    return df


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
