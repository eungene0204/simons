"""backfill_us_stocks.py — 미국 주식(S&P 500) OHLCV+기본 재무 파케이 백필 (무료 소스: yfinance).

한국 파케이(data/ohlcv/*.parquet)와 **동일 스키마·동일 컬럼 순서**로 data/ohlcv-us/*.parquet를
생성한다. 종목 마스터는 data/us-stocks.json (korea-stocks.json과 같은 구조).

데이터 소스 (전부 무료):
  - 유니버스: Wikipedia "List of S&P 500 companies" (GICS sector/sub-industry + CIK 포함)
  - 발행주식수: yfinance 실측(2015-10~) + SEC EDGAR XBRL(2009~) — 최초 실측 이전은 채우지
    않는다(후대 주식수로 과거 시총을 지어내지 않는다)
  - OHLCV/배당/분할: yfinance history(auto_adjust=False)
      → Yahoo 시세는 분할 수정주가(배당 미반영)라 한국 KIS 수정주가와 같은 의미다.
  - 수준(level) 재무: yfinance 분기 재무제표 (최근 ~5분기 제공)
  - 성장률(YoY): yfinance 연간 재무제표 (4~5개년) — 분기 깊이로는 TTM YoY를 못 만든다
  - 환율: yfinance `<통화>=X` — 외국 기업의 재무 금액·성장률을 **모두 달러 기준**으로 환산

단위·의미 규약 — 한국 파케이가 컬럼마다 단위가 다르므로 **그 규약을 그대로 복제**한다
(한국의 "원/억원"에 대응하는 "USD/억달러"):
  - 억 단위(1e8): market_cap, net_income, owner_net_income, ebitda, ebit, ev, revenue,
    operating_cf_amount, investing_cf_amount, financing_cf_amount
  - 원단위(raw): total_equity, capex, fcf, operating/investing/financing_cash_flow
  - eps·bps·sps·dividends = 주당 값(달러). change = 전일 대비 등락률(%).
  - dividends = **배당락일에만 찍히는 주당 현금배당(그 외 0)** — engine/dividends.py가
    롤링 합으로 TTM을 만들고 총수익 역조정에 쓴다. 매일 TTM을 넣으면 배당이 중복 계상된다.
  - sector = GICS Sector 영문명.
  - 엔진이 조건으로 노출하는 현금흐름 지표는 *_cash_flow가 아니라 *_cf_amount다
    (engine/signals.py::FUNDAMENTAL_AMOUNT_CIDS).

룩어헤드 방지:
  - 분기 재무는 회계기간 종료일 + LAG_DAYS(60일), 연간 재무(성장률)는 + ANNUAL_LAG_DAYS(90일)
    부터 반영한다 (yfinance에 공시일이 없어 美 공시 기한을 보수적으로 가정). 반영 후
    15개월(456일) 넘게 새 자료가 없으면 NaN (한국 파이프라인의 15개월 fill cap과 동일).

시총 분할 보정:
  - market_cap(t) = 분할수정 종가(t) × 분할수정 주식수(t).
    실제 주식수(get_shares_full·재무제표)는 당시 액면 기준이므로, t 이후 발생한 분할
    비율을 곱해 현재 기준으로 환산한 뒤 종가와 곱한다.

사용:
  python scripts/backfill_us_stocks.py                 # S&P 500 전체 (기존 파일 스킵)
  python scripts/backfill_us_stocks.py --symbols AAPL,MSFT
  python scripts/backfill_us_stocks.py --limit 5 --force
  python scripts/backfill_us_stocks.py --update        # 일일 증분 (scheduler_us.py가 매일 07:00 KST 실행)

일일 증분(--update):
  전량 재수집(--force)은 종목당 ~5초 × 5,947종목 ≈ 9시간이라 매일 돌릴 수 없다. --update는
  벌크 다운로드(yf.download, 배치당 1요청)로 최근 구간만 받아 기존 파케이 뒤에 이어 붙인다.
  - 가격 파생 컬럼(change·market_cap·per·pbr·psr·pcr·ev*·배당 4종)은 새 종가로 재계산,
    재무 컬럼은 마지막 행을 이어 쓴다(전량 백필의 분기 사이 ffill과 같은 의미).
  - 새 구간에 분할이 있거나 겹침일 종가가 저장분과 어긋나면(소급 수정) 그 종목만 전량 재수집.
  - 새 분기 재무 반영과 STALE_CAP_DAYS 만료는 증분이 못 한다 — 재무는 분기 주기로 갱신한다:
    미국 스케줄러(scripts/scheduler_us.py)가 12주마다 일요일 09:00 KST에 --force를 돌린다.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from engine.fundamental_status import growth_and_status  # noqa: E402

OUT_DIR = ROOT / "data" / "ohlcv-us"
MASTER_PATH = ROOT / "data" / "us-stocks.json"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# companyconcept 엔드포인트는 일부 기업에 대해 200 + 0건을 반환한다(KO: concept 0건 vs
# facts 71건). companyfacts는 한 요청으로 전 개념을 주고 그런 누락이 없어 이쪽을 쓴다.
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
# SEC는 요청자 식별용 User-Agent를 요구한다(미설정 시 403). 필요하면 환경변수로 덮어쓴다.
SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT", "nullstock-backfill/1.0 (contact via https://nullstock.im)"
)
# 발행주식수 개념 — 우선순위 순. 둘 다 "유통주식수(outstanding)"라 병합해도 안전하다.
# CommonStockSharesIssued(발행총수)는 자기주식을 포함해 시총을 부풀리므로 쓰지 않는다
# (KO 기준 issued 70.4억주 vs outstanding 43억주 — 60% 과대).
SEC_SHARE_CONCEPTS = [
    ("dei", "EntityCommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesOutstanding"),
]

LAG_DAYS = 60          # 분기(10-Q) 회계기간 종료 → 반영까지 보수적 지연
ANNUAL_LAG_DAYS = 90   # 연간(10-K)은 제출 기한이 더 길다
STALE_CAP_DAYS = 456   # 15개월: 이후 새 분기 없으면 재무 NaN
EOK = 1e8              # 억달러 단위 변환

# 한국 파케이와 동일한 컬럼 순서 (data/ohlcv/*.parquet 기준)
COLUMNS = [
    "date", "open", "high", "low", "close", "volume", "change", "sector",
    "eps", "bps", "roe_or_gpa", "debt_ratio", "per", "pbr", "sps",
    "revenue_growth", "operating_income_growth", "net_income_growth",
    "reserve_ratio", "roa", "net_margin", "gross_margin", "current_ratio",
    "quick_ratio", "psr", "market_cap", "operating_margin",
    "operating_cash_flow", "pcr", "ebitda", "ev_ebitda", "ebit",
    "total_equity", "capex", "fcf", "ev", "ev_ebit", "eps_growth",
    "ebitda_growth", "ocf_growth", "fcf_growth",
    "operating_income_growth_status", "net_income_growth_status",
    "eps_growth_status", "ebitda_growth_status", "ocf_growth_status",
    "fcf_growth_status", "dividend_yield", "payout_rate", "dividend_growth",
    "net_income", "dividends", "investing_cash_flow", "financing_cash_flow",
    "operating_cf_amount", "investing_cf_amount", "financing_cf_amount",
    "owner_net_income", "revenue",
]
STATUS_COLUMNS = [c for c in COLUMNS if c.endswith("_status")]

EXCHANGE_MAP = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
    "NYQ": "NYSE", "ASE": "NYSE AMEX", "PCX": "NYSE ARCA", "BTS": "CBOE",
}

# 전체 상장 목록(무료). ETF·테스트종목·워런트·우선주는 걸러 보통주만 남긴다.
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
OTHER_EXCHANGE_MAP = {"N": "NYSE", "A": "NYSE AMEX", "P": "NYSE ARCA", "Z": "CBOE", "V": "IEX"}
# 보통주가 아닌 증권을 이름으로 걸러낸다(심볼 접미사 규칙은 거래소마다 달라 이름이 더 안전).
# ① 이름 어디든 나오면 보통주가 아닌 낱말 — 복수형까지 잡는다.
NON_COMMON_NAME = re.compile(
    r"\b(?:Warrants?|Rights?|Notes?|Debentures?|Bonds?|Preferred|Subordinated)\b", re.I)
# ② "Units"는 증권 종류 자리(이름 끝의 " - " 뒤, 없으면 이름 전체)에 올 때만 배제한다.
#    SPAC 유닛("Aldel Financial II Inc. - Units")은 걸러야 하지만, MLP 보통유닛
#    ("Alliance Resource Partners, L.P. - Common Units …", "Energy Transfer LP Common Units")은
#    정상 상장 지분이라 남겨야 한다.
UNIT_SECURITY_TYPE = re.compile(r"^Units?\b", re.I)

# Yahoo 섹터 어휘 → GICS 정본(위키 S&P 500 표와 같은 어휘로 통일한다.
# 섞이면 같은 섹터가 두 이름으로 갈려 섹터 필터가 조용히 반쪽만 잡는다).
YAHOO_TO_GICS = {
    "Technology": "Information Technology",
    "Financial Services": "Financials",
    "Healthcare": "Health Care",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Basic Materials": "Materials",
    "Industrials": "Industrials",
    "Energy": "Energy",
    "Real Estate": "Real Estate",
    "Utilities": "Utilities",
    "Communication Services": "Communication Services",
}


# ---------------------------------------------------------------- 유니버스

def fetch_sp500_master() -> list[dict]:
    """Wikipedia S&P 500 표 → [{symbol, name, market, sector, industry}] (yfinance 표기: BRK.B→BRK-B)."""
    import requests

    resp = requests.get(WIKI_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    table = pd.read_html(io.StringIO(resp.text))[0]
    out = []
    for _, row in table.iterrows():
        out.append({
            "symbol": str(row["Symbol"]).strip().replace(".", "-"),
            "name": str(row["Security"]).strip(),
            "market": "US",  # 백필 중 거래소로 갱신
            "sector": str(row["GICS Sector"]).strip(),
            "industry": str(row["GICS Sub-Industry"]).strip(),
            "cik": str(row["CIK"]).strip().zfill(10),  # SEC EDGAR 조회 키
        })
    return out


def fetch_edgar_shares(cik: str) -> pd.Series:
    """SEC EDGAR XBRL에서 발행주식수 시계열을 가져온다 (무료, ~2009년부터).

    yfinance의 ``get_shares_full``은 전 종목 2015-10월부터만 제공해 그 이전 시총을 만들 수
    없다. EDGAR는 10-Q/10-K 표지의 발행주식수를 2009년경부터 제공하므로 6년을 더 소급한다.

    인덱스는 **제출일(filed)** 이다 — 그 수치가 공개된 시점이라 룩어헤드가 없다(회계기간
    종료일 end를 쓰면 아직 공시되지 않은 주식수를 미리 쓰게 된다). 값은 당시 액면 기준
    (분할 미조정)이라 ``split_adjust_factor``로 현재 기준 환산이 필요하다 — yfinance 실측과
    같은 성질이므로 두 소스를 그대로 이어 붙일 수 있다.
    """
    import requests

    try:
        resp = requests.get(
            SEC_FACTS_URL.format(cik=cik), headers={"User-Agent": SEC_USER_AGENT}, timeout=60
        )
    except Exception:
        return pd.Series(dtype=float)
    if resp.status_code != 200:
        return pd.Series(dtype=float)
    facts = resp.json().get("facts", {})

    points: dict = {}
    for ns, tag in SEC_SHARE_CONCEPTS:
        rows = facts.get(ns, {}).get(tag, {}).get("units", {}).get("shares", [])
        for row in rows:
            filed, val = row.get("filed"), row.get("val")
            if not filed or val is None:
                continue
            # 개념을 병합한다 — 기업마다 쓰는 개념이 달라 하나만 보면 커버리지를 잃는다
            # (KO는 dei만, 다른 기업은 us-gaap만 쓴다). 같은 제출일이면 표지(dei) 우선.
            points.setdefault(pd.Timestamp(filed), float(val))
    return pd.Series(points).sort_index() if points else pd.Series(dtype=float)


def merge_share_sources(yf_shares: pd.Series, edgar_shares: pd.Series) -> pd.Series:
    """실측 주식수 두 소스를 잇는다 — 겹치는 구간은 더 촘촘한 yfinance, 그 이전은 EDGAR.

    겹치는 구간에서 소스를 섞으면 분기(EDGAR)와 주간(yfinance) 관측이 번갈아 들어가
    글리치 필터가 오작동할 수 있어, 경계를 기준으로 한쪽만 쓴다.
    """
    yf_shares = yf_shares if yf_shares is not None else pd.Series(dtype=float)
    edgar_shares = edgar_shares if edgar_shares is not None else pd.Series(dtype=float)
    if yf_shares.empty:
        return edgar_shares.sort_index()
    if edgar_shares.empty:
        return yf_shares.sort_index()
    cutoff = yf_shares.index.min()
    return pd.concat([edgar_shares[edgar_shares.index < cutoff], yf_shares]).sort_index()


_FX_CACHE: dict = {}

# build_quarterly 산출물 중 통화 금액인 컬럼(주식수 shares_bs와 무단위 비율은 제외).
# eps_ttm도 주당 '금액'이라 환산 대상이다.
MONETARY_QUARTERLY_COLS = (
    "revenue_ttm", "ni_ttm", "ni_common_ttm", "gp_ttm", "oi_ttm", "eps_ttm",
    "ebitda_ttm", "ebit_ttm", "ocf_ttm", "icf_ttm", "fincf_ttm", "capex_ttm", "fcf_ttm",
    "equity", "total_assets", "total_liab", "curr_assets", "curr_liab", "inventory",
    "retained", "capital_stock", "total_debt", "cash",
)


def fetch_fx_rates(currency: str) -> pd.Series:
    """USD 1단위당 현지 통화의 일별 시계열(예: TWD=X). 통화당 한 번만 받아 캐시한다."""
    if currency in _FX_CACHE:
        return _FX_CACHE[currency]
    import yfinance as yf

    try:
        hist = yf.Ticker(f"{currency}=X").history(period="max", auto_adjust=False)
        rates = hist["Close"].dropna().astype(float)
        idx = rates.index
        rates.index = pd.DatetimeIndex(idx.tz_localize(None) if idx.tz else idx).normalize()
        rates = rates[~rates.index.duplicated(keep="last")].sort_index()
    except Exception:
        rates = pd.Series(dtype=float)
    _FX_CACHE[currency] = rates
    return rates


def to_usd(values: pd.Series, fx: pd.Series) -> pd.Series:
    """현지 통화 금액을 각 시점 환율로 달러 환산.

    yfinance는 **주가는 달러로, 재무제표는 현지 통화로** 준다(TSM은 TWD, HDB는 INR).
    환산하지 않으면 PER = 달러주가 ÷ 현지통화EPS가 되어 TSMC PER이 31 대신 1.14로 나오고,
    저PER 스크리닝이 저평가가 아니라 환율 때문에 이런 종목만 골라낸다.

    환율을 모르는 시점은 NaN으로 둔다 — 지어내지 않는다.
    """
    if fx is None or fx.empty or values.empty:
        return pd.Series(np.nan, index=values.index)
    rate = fx.reindex(fx.index.union(values.index)).sort_index().ffill().reindex(values.index)
    return (values / rate).where(rate > 0)


def convert_quarterly_to_usd(q: pd.DataFrame, fx: pd.Series) -> pd.DataFrame:
    """분기 지표의 금액 컬럼만 달러로 환산한다(주식수·무단위 비율은 그대로)."""
    if q.empty:
        return q
    out = q.copy()
    for col in MONETARY_QUARTERLY_COLS:
        if col in out:
            out[col] = to_usd(out[col], fx)
    return out


def filter_common_stocks(listed: pd.DataFrame) -> pd.DataFrame:
    """상장 목록에서 보통주만 남긴다 — ETF·테스트종목·워런트·권리·유닛·우선주·채권 제외.

    입력 컬럼: symbol, name, etf, test_issue, market.
    """
    out = listed[(listed["etf"] == "N") & (listed["test_issue"] == "N")].copy()
    names = out["name"].astype(str)
    security_type = names.str.rsplit(" - ", n=1).str[-1].str.strip()
    out = out[~names.str.contains(NON_COMMON_NAME, na=False)
              & ~security_type.str.contains(UNIT_SECURITY_TYPE, na=False)]
    # $·+·= 가 붙은 심볼은 우선주·워런트 표기라 시세 조회가 되지 않는다
    out = out[~out["symbol"].astype(str).str.contains(r"[\$\+\=]", na=False)]
    return out.drop_duplicates("symbol").sort_values("symbol").reset_index(drop=True)


def fetch_listed_symbols() -> pd.DataFrame:
    """Nasdaq Trader 상장 디렉터리(무료) → 보통주 유니버스 [symbol, name, market]."""
    import requests

    headers = {"User-Agent": SEC_USER_AGENT}
    frames = []
    for url, sym_col in [(NASDAQ_LISTED_URL, "Symbol"), (OTHER_LISTED_URL, "ACT Symbol")]:
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        # keep_default_na=False: Nano Labs의 티커 "NA"가 결측으로 읽혀 심볼이 'nan'이 된다
        df = pd.read_csv(io.StringIO(resp.text), sep="|", keep_default_na=False)
        df = df[~df[sym_col].astype(str).str.startswith("File Creation")]
        df = df.rename(columns={sym_col: "symbol", "Security Name": "name",
                                "ETF": "etf", "Test Issue": "test_issue"})
        df["market"] = ("NASDAQ" if sym_col == "Symbol"
                        else df["Exchange"].map(OTHER_EXCHANGE_MAP).fillna("US"))
        frames.append(df[["symbol", "name", "etf", "test_issue", "market"]])
    return filter_common_stocks(pd.concat(frames, ignore_index=True))


def fetch_sec_cik_map() -> dict:
    """SEC 공식 ticker→CIK 매핑(무료, 한 번 요청). 미등록 종목(일부 ADR)은 빠진다."""
    import requests

    resp = requests.get(SEC_TICKERS_URL, headers={"User-Agent": SEC_USER_AGENT}, timeout=60)
    resp.raise_for_status()
    return {v["ticker"].replace(".", "-"): str(v["cik_str"]).zfill(10)
            for v in resp.json().values()}


def fetch_us_master(universe: str) -> list[dict]:
    """종목 마스터를 만든다. universe='sp500'이면 S&P 500만, 'all'이면 전체 보통주.

    S&P 500 종목은 위키의 GICS 섹터를 그대로 쓰고, 나머지는 섹터를 비워 둔 뒤 백필 중
    yfinance에서 받아 GICS 어휘로 정규화해 채운다.
    """
    sp500 = {m["symbol"]: m for m in fetch_sp500_master()}
    if universe == "sp500":
        return list(sp500.values())

    cik_map = fetch_sec_cik_map()
    listed = fetch_listed_symbols()
    out = []
    for _, row in listed.iterrows():
        sym = str(row["symbol"]).strip().replace(".", "-")
        if sym in sp500:
            out.append(sp500[sym])
            continue
        out.append({
            "symbol": sym,
            "name": str(row["name"]).split(" - ")[0].strip(),
            "market": row["market"],
            "sector": "",      # 백필 중 yfinance → GICS로 채움
            "industry": "",
            "cik": cik_map.get(sym, ""),
        })
    # S&P 500인데 상장 목록에 없는 종목(표기 차이)도 유실 없이 포함
    listed_syms = {str(x["symbol"]).replace(".", "-") for x in out}
    out.extend(m for sym, m in sp500.items() if sym not in listed_syms)
    return sorted(out, key=lambda m: m["symbol"])


# ---------------------------------------------------------------- 순수 변환 (테스트 대상)

def split_adjust_factor(splits: pd.Series, at: pd.DatetimeIndex) -> pd.Series:
    """각 시점 t에 대해 t **이후** 발생한 분할 비율의 곱 (현재 기준 주식수 환산 계수).

    splits: 분할 발생일 인덱스, 값=비율(4:1이면 4.0). at: 계수를 구할 시점들.
    """
    s = splits[splits > 0].sort_index()
    factors = pd.Series(1.0, index=at)
    for dt, ratio in s.items():
        factors[factors.index < dt] *= float(ratio)
    return factors


def ttm_sum(quarterly: pd.Series) -> pd.Series:
    """분기 시계열(오름차순)의 4분기 이동합. 4분기 미만 구간은 NaN."""
    return quarterly.rolling(4, min_periods=4).sum()


def apply_with_lag(
    dates: pd.DatetimeIndex,
    qdf: pd.DataFrame,
    lag_days: int = LAG_DAYS,
    stale_cap_days: int = STALE_CAP_DAYS,
) -> pd.DataFrame:
    """분기 지표(index=회계기간 종료일)를 일별로 전개.

    종료일+lag_days부터 반영하고, 마지막 반영일로부터 stale_cap_days가 지나면 NaN.
    """
    if qdf.empty:
        return pd.DataFrame(index=dates, columns=qdf.columns, dtype=float)
    avail = qdf.copy()
    avail.index = avail.index + pd.Timedelta(days=lag_days)
    avail = avail.sort_index()
    left = pd.DataFrame({"date": dates})
    merged = pd.merge_asof(
        left, avail.reset_index().rename(columns={"index": "avail"}),
        left_on="date", right_on="avail",
        direction="backward", tolerance=pd.Timedelta(days=stale_cap_days),
    )
    merged = merged.drop(columns=["avail"]).set_index("date")
    return merged


def safe_div(num, den, scale: float = 1.0):
    """den이 0·음수·NaN이면 NaN인 나눗셈 (PER 등 가격배수용)."""
    num = pd.Series(num) if not isinstance(num, pd.Series) else num
    den = pd.Series(den) if not isinstance(den, pd.Series) else den
    with np.errstate(divide="ignore", invalid="ignore"):
        out = num / den * scale
    return out.where(den > 0)


# ---------------------------------------------------------------- 분기 재무 조립

def _row(stmt: pd.DataFrame, *names: str) -> pd.Series:
    """재무제표에서 첫 번째로 존재하는 행을 (기간 종료일 오름차순) Series로. 없으면 빈 Series."""
    for n in names:
        if n in stmt.index:
            return pd.to_numeric(stmt.loc[n], errors="coerce").sort_index()
    return pd.Series(dtype=float)


def build_quarterly(inc: pd.DataFrame, bs: pd.DataFrame, cf: pd.DataFrame) -> pd.DataFrame:
    """yfinance 분기 3표 → 회계기간 종료일 index의 지표 프레임 (금액=USD 원단위)."""
    revenue_q = _row(inc, "Total Revenue", "Operating Revenue")
    ni_q = _row(inc, "Net Income", "Net Income Common Stockholders")
    ni_common_q = _row(inc, "Net Income Common Stockholders", "Net Income")
    gp_q = _row(inc, "Gross Profit")
    oi_q = _row(inc, "Operating Income", "Total Operating Income As Reported")
    eps_q = _row(inc, "Basic EPS", "Diluted EPS")
    ebitda_q = _row(inc, "EBITDA", "Normalized EBITDA")
    ebit_q = _row(inc, "EBIT")
    ocf_q = _row(cf, "Operating Cash Flow")
    icf_q = _row(cf, "Investing Cash Flow")
    fincf_q = _row(cf, "Financing Cash Flow")
    capex_q = _row(cf, "Capital Expenditure")
    fcf_q = _row(cf, "Free Cash Flow")

    idx = revenue_q.index.union(ni_q.index).union(_row(bs, "Stockholders Equity").index)
    if idx.empty:
        return pd.DataFrame()
    q = pd.DataFrame(index=idx.sort_values())

    # 유량(flow)은 TTM 합
    for name, series in [
        ("revenue_ttm", revenue_q), ("ni_ttm", ni_q), ("ni_common_ttm", ni_common_q),
        ("gp_ttm", gp_q), ("oi_ttm", oi_q), ("eps_ttm", eps_q),
        ("ebitda_ttm", ebitda_q), ("ebit_ttm", ebit_q),
        ("ocf_ttm", ocf_q), ("icf_ttm", icf_q), ("fincf_ttm", fincf_q),
        ("capex_ttm", capex_q), ("fcf_ttm", fcf_q),
    ]:
        q[name] = ttm_sum(series).reindex(q.index) if not series.empty else np.nan

    # 저량(stock)은 기말 값
    q["equity"] = _row(bs, "Stockholders Equity", "Common Stock Equity").reindex(q.index)
    q["total_assets"] = _row(bs, "Total Assets").reindex(q.index)
    q["total_liab"] = _row(bs, "Total Liabilities Net Minority Interest").reindex(q.index)
    q["curr_assets"] = _row(bs, "Current Assets").reindex(q.index)
    q["curr_liab"] = _row(bs, "Current Liabilities").reindex(q.index)
    q["inventory"] = _row(bs, "Inventory").reindex(q.index)
    q["shares_bs"] = _row(bs, "Ordinary Shares Number", "Share Issued").reindex(q.index)
    q["retained"] = _row(bs, "Retained Earnings").reindex(q.index)
    q["capital_stock"] = _row(bs, "Capital Stock", "Common Stock").reindex(q.index)
    q["total_debt"] = _row(bs, "Total Debt").reindex(q.index)
    q["cash"] = _row(bs, "Cash And Cash Equivalents",
                     "Cash Cash Equivalents And Short Term Investments").reindex(q.index)

    # 주가 무관 비율 (분기 기준으로 미리 계산; 주당지표는 일별 조정 주식수로 별도 계산)
    # ROE는 지배주주 기준 — 분자 ni_common_ttm(비지배지분 제외)과 분모 Stockholders Equity
    # (비지배지분 제외)의 레벨을 맞춘다. 총 순이익을 쓰면 ARES처럼 비지배지분이 큰 회사에서
    # ROE가 부풀려진다. 한국 파이프라인의 EPS/BPS×100 규약과 동일한 정의.
    # ROA는 반대로 전사 기준(총 순이익 ÷ 총자산)으로 레벨을 맞춘다.
    q["roe"] = safe_div(q["ni_common_ttm"], q["equity"], 100.0)
    q["roa"] = safe_div(q["ni_ttm"], q["total_assets"], 100.0)
    q["debt_ratio"] = safe_div(q["total_liab"], q["equity"], 100.0)
    q["current_ratio"] = safe_div(q["curr_assets"], q["curr_liab"], 100.0)
    q["quick_ratio"] = safe_div(q["curr_assets"] - q["inventory"].fillna(np.nan), q["curr_liab"], 100.0)
    q["reserve_ratio"] = safe_div(q["retained"], q["capital_stock"], 100.0)
    q["net_margin"] = (q["ni_ttm"] / q["revenue_ttm"] * 100.0).where(q["revenue_ttm"] > 0)
    q["gross_margin"] = (q["gp_ttm"] / q["revenue_ttm"] * 100.0).where(q["revenue_ttm"] > 0)
    q["operating_margin"] = (q["oi_ttm"] / q["revenue_ttm"] * 100.0).where(q["revenue_ttm"] > 0)
    return q


# 성장률 컬럼 ↔ (상태 컬럼, 연간 재무 행 이름들). revenue_growth/dividend_growth는 상태 컬럼이 없다.
GROWTH_SPECS = [
    ("revenue_growth", None, "inc", ("Total Revenue", "Operating Revenue")),
    ("operating_income_growth", "operating_income_growth_status", "inc",
     ("Operating Income", "Total Operating Income As Reported")),
    ("net_income_growth", "net_income_growth_status", "inc",
     ("Net Income", "Net Income Common Stockholders")),
    ("eps_growth", "eps_growth_status", "inc", ("Basic EPS", "Diluted EPS")),
    ("ebitda_growth", "ebitda_growth_status", "inc", ("EBITDA", "Normalized EBITDA")),
    ("ocf_growth", "ocf_growth_status", "cf", ("Operating Cash Flow",)),
    ("fcf_growth", "fcf_growth_status", "cf", ("Free Cash Flow",)),
]


def build_annual_growth(inc: pd.DataFrame, cf: pd.DataFrame,
                        fx: pd.Series | None = None) -> pd.DataFrame:
    """yfinance **연간** 재무제표 → 회계연도 종료일 index의 전년대비 증가율(%)+상태코드.

    분기 재무는 yfinance가 ~5분기만 주므로 TTM YoY(8분기 필요)를 만들 수 없다. 연간표는
    4~5개년을 주므로 성장률은 연간 기준으로 계산한다 — 한국 파이프라인(DART 연간 기준)과
    같은 정의다. 부호 전환(적자→흑자 등)은 엔진의 ``growth_and_status``가 값 대신
    상태코드로 분류한다(값과 상태는 상호배타). 데이터가 없어 생기는 MISSING_DATA는
    상태로 남기지 않는다 — 증가율 NaN 자체가 "데이터 없음"을 뜻하고, 커버리지 로그가 고지한다.

    fx가 주어지면(외국 기업) 연간 금액을 **달러로 환산한 뒤** 증가율을 낸다. 현지통화
    증가율을 그대로 두면 종목 간 비교가 깨진다 — 아르헨티나 기업의 페소 매출 성장률에는
    초인플레이션이 섞여 있어, 성장률 스크리닝이 실제 성장이 아니라 통화 가치 하락을
    고른다(PER 환산과 같은 유형의 오류).
    """
    stmts = {"inc": inc, "cf": cf}
    idx = pd.DatetimeIndex([])
    for stmt in stmts.values():
        if stmt is not None and not stmt.empty:
            idx = idx.union(pd.DatetimeIndex(stmt.columns))
    if idx.empty:
        return pd.DataFrame()

    out = pd.DataFrame(index=idx.sort_values())
    for growth_col, status_col, which, names in GROWTH_SPECS:
        stmt = stmts[which]
        series = _row(stmt, *names) if stmt is not None and not stmt.empty else pd.Series(dtype=float)
        values = series.reindex(out.index) if not series.empty else pd.Series(np.nan, index=out.index)
        if fx is not None:
            values = to_usd(values, fx)  # 달러 환산 후 증가율 — 통화 하락을 성장으로 세지 않는다
        growths, statuses = [], []
        prior = None
        for value in values:
            current = None if pd.isna(value) else float(value)
            growth, status = growth_and_status(prior, current)
            growths.append(np.nan if growth is None else growth)
            statuses.append(None if status == "MISSING_DATA" else status)
            prior = current
        out[growth_col] = growths
        if status_col:
            out[status_col] = statuses
    return out


# ---------------------------------------------------------------- 일별 프레임 조립

def build_daily_frame(
    hist: pd.DataFrame,
    qdf: pd.DataFrame,
    shares_actual: pd.Series,
    sector: str,
    adf: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """OHLCV 히스토리 + 분기 지표 + 실제 주식수 → 한국 스키마 일별 프레임."""
    hist = hist.copy()
    hist.index = pd.DatetimeIndex(hist.index.tz_localize(None) if hist.index.tz else hist.index).normalize()
    hist = hist[~hist.index.duplicated(keep="last")].sort_index()
    # 가격이 없는 날(Yahoo의 구멍 — OHLC 전부 NaN, 거래량 0)은 유효한 거래일이 아니다.
    # 한국 파케이는 close 결측이 0건이므로 같은 규약을 따른다(HUBB 1977-08-08 사례).
    hist = hist[hist["Close"].notna()]
    dates = hist.index

    df = pd.DataFrame(index=dates)
    df["open"] = hist["Open"].astype(float)
    df["high"] = hist["High"].astype(float)
    df["low"] = hist["Low"].astype(float)
    df["close"] = hist["Close"].astype(float)
    df["volume"] = hist["Volume"].astype(float)
    df["change"] = df["close"].pct_change() * 100.0
    df["sector"] = sector

    # 분할수정 주식수: 실제 주식수 × (t 이후 분할비율의 곱).
    # 재무제표 주식수(shares_bs)는 실측(get_shares_full)이 전무할 때만 사용 —
    # BRK-B처럼 A/B 클래스가 갈리면 재무제표 주식수(A 기준)가 시세(B 기준)와 어긋난다.
    splits = hist.get("Stock Splits", pd.Series(dtype=float))
    shares_points = pd.Series(dtype=float)
    if shares_actual is not None and not shares_actual.empty:
        sa = shares_actual.copy()
        sa.index = pd.DatetimeIndex(sa.index.tz_localize(None) if sa.index.tz else sa.index).normalize()
        shares_points = sa.astype(float).sort_index()  # 중복 날짜 유지 — 스무딩에서 정리
    elif not qdf.empty and "shares_bs" in qdf:
        shares_points = qdf["shares_bs"].dropna().astype(float).sort_index()
    if not shares_points.empty:
        factor = split_adjust_factor(splits, pd.DatetimeIndex(shares_points.index))
        # 중복 인덱스 정렬-곱은 카티션 폭발 → 위치 기반 곱
        adj = pd.Series(shares_points.to_numpy() * factor.to_numpy(), index=shares_points.index)
        # Yahoo는 분할 당일에 신·구 기준 주식수를 함께 내려주기도 한다(스테일 관측).
        # 이웃 중앙값 대비 20% 넘게 벗어난 고립 글리치만 중앙값으로 교체 (경계 점은 유지).
        med = adj.rolling(3, center=True).median()
        adj = adj.where(med.isna() | ((adj - med).abs() <= med * 0.2), med)
        adj = adj[~adj.index.duplicated(keep="last")]
        # 최초 실측 이전은 채우지 않는다 — 후대의 주식수로 과거 시총을 지어내면(bfill)
        # 자사주 소각·증자를 무시해 조용히 틀린다(AAPL 2009년 주식수는 분할조정 시
        # 현재보다 72% 많아, 역채움은 당시 시총을 42% 과소평가했다). NaN은 엔진 커버리지
        # 로그가 '미해결 데이터'로 고지하므로 최소한 눈에 보인다.
        shares_adj = adj.reindex(dates, method="ffill")
        df["market_cap"] = df["close"] * shares_adj / EOK  # 억달러
    else:
        shares_adj = pd.Series(np.nan, index=dates)
        df["market_cap"] = np.nan

    # 배당: dividends는 **배당락일에만 찍히는 주당 현금배당(그 외 0)** — 한국 파케이 규약이며
    # 엔진(engine/dividends.py)이 롤링 합으로 TTM을 만들고 총수익 역조정에 쓴다. 매일 TTM을
    # 넣으면 총수익 지수가 배당을 4중 계상한다.
    div = hist.get("Dividends", pd.Series(0.0, index=dates)).fillna(0.0)
    df["dividends"] = div
    div_ttm = div.rolling("365D").sum()
    df["dividend_yield"] = (div_ttm / df["close"] * 100.0).where(df["close"] > 0)
    prior_ttm = div_ttm.reindex(dates.shift(-365, freq="D"), method="ffill")
    prior_ttm.index = dates
    df["dividend_growth"] = ((div_ttm / prior_ttm - 1.0) * 100.0).where(prior_ttm > 0)

    # 분기 재무 전개 (공시 지연 + 15개월 cap)
    daily_q = apply_with_lag(dates, qdf) if not qdf.empty else pd.DataFrame(index=dates)

    def col(name):
        return daily_q[name] if name in daily_q else pd.Series(np.nan, index=dates)

    # 주당지표는 재무 총액 ÷ 일별 조정 주식수로 통일 (클래스 불일치·분할에 안전).
    # 조정 주식수가 없을 때만 손익계산서 Basic EPS(TTM)로 폴백.
    eps = safe_div(col("ni_common_ttm"), shares_adj).fillna(col("eps_ttm"))
    df["eps"] = eps
    df["bps"] = safe_div(col("equity"), shares_adj)
    df["sps"] = safe_div(col("revenue_ttm"), shares_adj)
    df["roe_or_gpa"] = col("roe")
    df["roa"] = col("roa")
    df["debt_ratio"] = col("debt_ratio")
    df["current_ratio"] = col("current_ratio")
    df["quick_ratio"] = col("quick_ratio")
    df["reserve_ratio"] = col("reserve_ratio")
    df["net_margin"] = col("net_margin")
    df["gross_margin"] = col("gross_margin")
    df["operating_margin"] = col("operating_margin")

    df["per"] = safe_div(df["close"], eps)
    df["pbr"] = safe_div(df["close"], df["bps"])
    df["psr"] = safe_div(df["close"], df["sps"])
    df["pcr"] = safe_div(df["market_cap"] * EOK, col("ocf_ttm"))
    df["payout_rate"] = safe_div(div_ttm, eps, 100.0)

    # 금액 컬럼 — 한국 파케이는 컬럼마다 단위가 다르다. 그 규약을 그대로 따른다:
    #   억 단위(1e8): market_cap, net_income, owner_net_income, ebitda, ebit, ev, *_cf_amount
    #   원단위(raw):  total_equity, capex, fcf, operating/investing/financing_cash_flow
    # 엔진이 조건으로 노출하는 현금흐름 지표는 *_cash_flow가 아니라 **_cf_amount**다
    # (engine/signals.py::FUNDAMENTAL_AMOUNT_CIDS) — 비우면 조건이 조용히 통과된다.
    df["revenue"] = col("revenue_ttm") / EOK
    df["net_income"] = col("ni_ttm") / EOK
    df["owner_net_income"] = col("ni_common_ttm") / EOK
    df["ebitda"] = col("ebitda_ttm") / EOK
    df["ebit"] = col("ebit_ttm") / EOK
    df["total_equity"] = col("equity")
    # capex는 한국 파케이가 **양수 규모**로 저장한다(전수 확인: 음수 0행). yfinance의
    # Capital Expenditure는 현금유출이라 음수이므로 부호를 뒤집어 규약을 맞춘다.
    df["capex"] = col("capex_ttm").abs()
    df["fcf"] = col("fcf_ttm")
    df["operating_cash_flow"] = col("ocf_ttm")
    df["investing_cash_flow"] = col("icf_ttm")
    df["financing_cash_flow"] = col("fincf_ttm")
    df["operating_cf_amount"] = col("ocf_ttm") / EOK
    df["investing_cf_amount"] = col("icf_ttm") / EOK
    df["financing_cf_amount"] = col("fincf_ttm") / EOK
    ev = df["market_cap"] + (col("total_debt") - col("cash")) / EOK
    df["ev"] = ev
    df["ev_ebitda"] = safe_div(ev, df["ebitda"])
    df["ev_ebit"] = safe_div(ev, df["ebit"])

    # 성장률·상태코드: 연간 재무 기준, 회계연도 종료 + ANNUAL_LAG_DAYS부터 반영
    if adf is not None and not adf.empty:
        daily_a = apply_with_lag(dates, adf, lag_days=ANNUAL_LAG_DAYS)
        for c in daily_a.columns:
            df[c] = daily_a[c]

    df.index.name = "date"  # yfinance 인덱스명("Date") 무관하게 고정
    df = df.reset_index()
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = None if c in STATUS_COLUMNS else np.nan
    df["date"] = df["date"].astype("datetime64[us]")
    # 상태 컬럼은 값이 하나도 없어도 문자열 타입으로 고정한다 — 전부 None이면 parquet에
    # Null 타입으로 굳어 한국 파케이(String)와 dtype이 어긋난다(폴라스 문자열 연산·프레임
    # 결합에서 터지는 스키마 드리프트).
    for c in STATUS_COLUMNS:
        df[c] = df[c].astype("string")
    return df[COLUMNS]


# ---------------------------------------------------------------- 수집 루프

def fetch_symbol(symbol: str, cik: str | None = None):
    """한 종목의 (hist, qdf, shares_actual, meta, adf)를 가져온다.

    주식수는 yfinance 실측(2015~)에 SEC EDGAR(2009~)를 이어 붙여 커버리지를 넓힌다.
    """
    import yfinance as yf

    t = yf.Ticker(symbol)
    hist = t.history(period="max", auto_adjust=False)
    if hist is None or hist.empty:
        raise RuntimeError("empty history")
    meta = {"market": "US", "sector": "", "industry": "", "financial_currency": ""}
    try:
        info = t.info
        meta["market"] = EXCHANGE_MAP.get(info.get("exchange"), info.get("exchange") or "US")
        # Yahoo 섹터는 GICS 정본 어휘로 정규화한다. 매핑에 없는 값은 버린다 —
        # 어휘가 섞이면 섹터 필터가 같은 섹터를 두 이름으로 갈라 반쪽만 잡는다.
        meta["sector"] = YAHOO_TO_GICS.get(info.get("sector"), "")
        meta["industry"] = info.get("industry") or ""
        meta["financial_currency"] = (info.get("financialCurrency") or "").upper()
    except Exception:
        pass

    # 재무제표 통화가 달러가 아니면 금액·성장률을 모두 달러 기준으로 만든다(주가는 항상 달러).
    currency = meta.get("financial_currency", "")
    fx = None
    if currency and currency != "USD":
        fx = fetch_fx_rates(currency)
        if fx.empty:
            print(f"    {currency} 환율 조회 실패 — 재무를 비웁니다(환율 없이 쓰면 비율·성장률이 틀린다)")

    try:
        qdf = build_quarterly(t.quarterly_income_stmt, t.quarterly_balance_sheet, t.quarterly_cashflow)
        if fx is not None:
            qdf = convert_quarterly_to_usd(qdf, fx)
    except Exception as exc:  # 재무 없는 종목도 OHLCV는 저장
        print(f"    분기 재무 수집 실패({exc}) — OHLCV만 저장")
        qdf = pd.DataFrame()
    try:
        adf = build_annual_growth(t.income_stmt, t.cashflow, fx)
    except Exception as exc:
        print(f"    연간 재무 수집 실패({exc}) — 성장률 없이 저장")
        adf = pd.DataFrame()
    try:
        shares = t.get_shares_full(start="1990-01-01")
        if shares is not None and not shares.empty:
            idx = shares.index
            shares = pd.Series(
                shares.astype(float).to_numpy(),
                index=pd.DatetimeIndex(idx.tz_localize(None) if idx.tz else idx).normalize(),
            )
    except Exception:
        shares = None
    if cik:
        try:
            shares = merge_share_sources(shares, fetch_edgar_shares(cik))
        except Exception as exc:
            print(f"    EDGAR 주식수 조회 실패({exc}) — yfinance 실측만 사용")
    return hist, qdf, shares, meta, adf


def detect_currencies(master: list, by_symbol: dict, symbols: list, sleep_s: float) -> int:
    """재무제표 통화만 조사해 마스터에 기록한다(시세·재무는 받지 않아 훨씬 가볍다).

    이미 기록된 종목은 건너뛰므로 중단 후 이어받을 수 있다.
    """
    import yfinance as yf

    todo = [s for s in symbols if not by_symbol.get(s, {}).get("financial_currency")]
    print(f"통화 조사 대상 {len(todo)} / 전체 {len(symbols)}")
    done = 0
    for i, sym in enumerate(todo, 1):
        try:
            currency = (yf.Ticker(sym).info.get("financialCurrency") or "").upper()
        except Exception:
            currency = ""
        if currency and sym in by_symbol:
            by_symbol[sym]["financial_currency"] = currency
            done += 1
        if i % 50 == 0:
            MASTER_PATH.write_text(json.dumps(master, ensure_ascii=False, indent=1))
            print(f"[{i}/{len(todo)}] 기록 {done}건")
        time.sleep(sleep_s)
    MASTER_PATH.write_text(json.dumps(master, ensure_ascii=False, indent=1))
    non_usd = sorted(m["symbol"] for m in master
                     if m.get("financial_currency") and m["financial_currency"] != "USD")
    print(f"\n통화 조사 완료: 기록 {done}건 | 비USD {len(non_usd)}종목")
    print("비USD 종목:", ",".join(non_usd))
    return 0


# ---------------------------------------------------------------- 일일 증분 갱신

UPDATE_WINDOW_DAYS = 45   # 벌크 다운로드 조회 구간 — 겹침 검증·배당 TTM 이어붙이기에 충분한 길이
UPDATE_BATCH_SIZE = 100   # yf.download 배치당 종목 수
DRIFT_TOL = 0.001         # 겹침일 종가 상대 오차 허용치 — 초과면 소급 조정으로 보고 전량 재수집
_DIV_TAIL_DAYS = 800      # 배당 TTM·전년 TTM 재계산에 필요한 저장분 꼬리(365+365+여유)


def append_daily_rows(stored: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame | None:
    """저장 파케이 뒤에 새 일봉을 이어 붙인 프레임을 돌려준다.

    가격 파생 컬럼은 재계산하고 재무 컬럼은 마지막 행을 이어 쓴다(분기 사이 ffill과 동일).
    새 구간에 분할이 있거나 겹침일 종가가 어긋나면(소급 수정) None — 호출자가 전량 재수집한다.
    새 봉이 없으면 stored를 그대로 반환한다.
    """
    bars = bars.copy()
    idx = pd.DatetimeIndex(bars.index.tz_localize(None) if getattr(bars.index, "tz", None) else bars.index)
    bars.index = idx.normalize()
    bars = bars[~bars.index.duplicated(keep="last")].sort_index()
    bars = bars[bars["Close"].notna()]  # Yahoo 구멍(OHLC 전부 NaN)은 거래일이 아니다 — 전량 백필과 같은 규약

    last_date = pd.Timestamp(stored["date"].iloc[-1])
    last = stored.iloc[-1]
    new_bars = bars[bars.index > last_date]
    if new_bars.empty:
        return stored

    # 새 구간에 분할이 있으면 과거 전체가 소급 조정된다(주식수·종가 모두) — 이어붙이기 불가.
    splits = new_bars.get("Stock Splits")
    if splits is not None and (splits.fillna(0.0) > 0).any():
        return None
    # 겹침일 검증: 저장분 마지막 거래일이 다운로드 구간에 있어야 하고 종가가 일치해야 한다.
    # 어긋나면 분할·소급 수정이 있었던 것이므로 이어붙이면 과거와 새 구간의 기준이 갈린다.
    if last_date not in bars.index:
        return None
    last_close = float(last["close"])
    if last_close <= 0 or abs(float(bars.loc[last_date, "Close"]) - last_close) > last_close * DRIFT_TOL:
        return None

    new = pd.DataFrame(index=new_bars.index)
    new["open"] = new_bars["Open"].astype(float)
    new["high"] = new_bars["High"].astype(float)
    new["low"] = new_bars["Low"].astype(float)
    new["close"] = new_bars["Close"].astype(float)
    new["volume"] = new_bars["Volume"].astype(float)
    closes = pd.concat([pd.Series([last_close], index=[last_date]), new["close"]])
    new["change"] = (closes.pct_change() * 100.0).iloc[1:]
    new["sector"] = last["sector"]

    def const(v) -> pd.Series:
        return pd.Series(v, index=new.index, dtype=float)

    # 시총: 마지막 행에서 역산한 분할수정 주식수 × 새 종가 (분할은 위에서 전량 재수집으로 빠졌다).
    last_mc = float(last["market_cap"]) if pd.notna(last["market_cap"]) else np.nan
    shares = last_mc * EOK / last_close if np.isfinite(last_mc) else np.nan
    new["market_cap"] = new["close"] * shares / EOK

    # 배당: 저장분 꼬리 + 새 배당락으로 TTM·수익률·성장률을 전량 백필과 같은 식으로 재계산.
    div_new = new_bars.get("Dividends")
    div_new = div_new.fillna(0.0).astype(float) if div_new is not None else pd.Series(0.0, index=new.index)
    new["dividends"] = div_new
    tail = stored[stored["date"] > last_date - pd.Timedelta(days=_DIV_TAIL_DAYS)]
    div_all = pd.concat([
        pd.Series(tail["dividends"].fillna(0.0).to_numpy(), index=pd.DatetimeIndex(tail["date"])),
        div_new,
    ])
    div_ttm_all = div_all.rolling("365D").sum()
    div_ttm = div_ttm_all.reindex(new.index)
    new["dividend_yield"] = (div_ttm / new["close"] * 100.0).where(new["close"] > 0)
    prior_ttm = div_ttm_all.reindex(new.index.shift(-365, freq="D"), method="ffill")
    prior_ttm.index = new.index
    new["dividend_growth"] = ((div_ttm / prior_ttm - 1.0) * 100.0).where(prior_ttm > 0)

    # 가격배수: 재무(분모)는 마지막 행 값 그대로, 가격(분자)만 갱신 — build_daily_frame과 같은 식.
    new["per"] = safe_div(new["close"], const(last["eps"]))
    new["pbr"] = safe_div(new["close"], const(last["bps"]))
    new["psr"] = safe_div(new["close"], const(last["sps"]))
    new["pcr"] = safe_div(new["market_cap"] * EOK, const(last["operating_cash_flow"]))
    new["payout_rate"] = safe_div(div_ttm, const(last["eps"]), 100.0)
    # EV = 시총 + 순부채. 순부채(= 저장분 ev − 시총)는 분기 사이 상수다.
    net_debt = float(last["ev"]) - last_mc if pd.notna(last["ev"]) and np.isfinite(last_mc) else np.nan
    new["ev"] = new["market_cap"] + net_debt
    new["ev_ebitda"] = safe_div(new["ev"], const(last["ebitda"]))
    new["ev_ebit"] = safe_div(new["ev"], const(last["ebit"]))

    # 나머지(재무·성장률·상태 컬럼)는 마지막 행을 이어 쓴다.
    for c in COLUMNS:
        if c != "date" and c not in new.columns:
            new[c] = last[c]

    new.index.name = "date"
    new = new.reset_index()
    new["date"] = new["date"].astype("datetime64[us]")
    out = pd.concat([stored, new[COLUMNS]], ignore_index=True)
    for c in STATUS_COLUMNS:
        out[c] = out[c].astype("string")
    return out


def _full_refresh(sym: str, by_symbol: dict) -> int:
    """한 종목을 전량 재수집해 저장한다. 저장한 행 수 반환(실패는 예외)."""
    hist, qdf, shares, meta, adf = fetch_symbol(sym, by_symbol.get(sym, {}).get("cik"))
    sector = by_symbol.get(sym, {}).get("sector", "")
    df = build_daily_frame(hist, qdf, shares, sector or meta["sector"], adf)
    df.to_parquet(OUT_DIR / f"{sym}.parquet", index=False)
    return len(df)


def update_existing(symbols: list[str], by_symbol: dict, sleep_s: float) -> int:
    """기존 파케이 전체에 최근 시세를 이어 붙인다(일일 증분). 파케이 없는 종목은 건너뛴다."""
    import yfinance as yf

    targets = [s for s in symbols if (OUT_DIR / f"{s}.parquet").exists()]
    no_file = len(symbols) - len(targets)
    start = (pd.Timestamp.now().normalize() - pd.Timedelta(days=UPDATE_WINDOW_DAYS)).date().isoformat()
    print(f"일일 증분 시작: 대상 {len(targets)}종목 (파케이 없음 {no_file}종목 제외), {start}~")

    appended = unchanged = refreshed = 0
    no_data: list[str] = []
    failed: list[str] = []
    for pos in range(0, len(targets), UPDATE_BATCH_SIZE):
        batch = targets[pos:pos + UPDATE_BATCH_SIZE]
        data = None
        for attempt in range(3):
            try:
                data = yf.download(batch, start=start, auto_adjust=False, actions=True,
                                   group_by="ticker", progress=False, threads=True)
                break
            except Exception as exc:
                wait = 30 * (attempt + 1)
                print(f"  배치 다운로드 실패({exc}) — {wait}초 후 재시도 {attempt + 1}/3")
                time.sleep(wait)
        if data is None or data.empty:
            failed.extend(batch)
            continue
        multi = isinstance(data.columns, pd.MultiIndex)
        for sym in batch:
            try:
                bars = data[sym] if multi else data
            except KeyError:
                no_data.append(sym)
                continue
            if bars["Close"].dropna().empty:
                no_data.append(sym)  # 상폐·거래정지 등 — 구간에 시세 없음
                continue
            out_path = OUT_DIR / f"{sym}.parquet"
            try:
                stored = pd.read_parquet(out_path)
                updated = append_daily_rows(stored, bars)
                if updated is None:
                    rows = _full_refresh(sym, by_symbol)
                    refreshed += 1
                    print(f"  {sym}: 분할·소급 수정 감지 — 전량 재수집({rows}행)")
                elif len(updated) == len(stored):
                    unchanged += 1
                else:
                    updated.to_parquet(out_path, index=False)
                    appended += 1
            except Exception as exc:
                failed.append(sym)
                print(f"  {sym}: 실패({exc})")
        done = min(pos + UPDATE_BATCH_SIZE, len(targets))
        print(f"[{done}/{len(targets)}] 추가 {appended} · 최신 {unchanged} · 재수집 {refreshed} "
              f"· 시세없음 {len(no_data)} · 실패 {len(failed)}")
        time.sleep(sleep_s)

    print(f"\n증분 완료: 추가 {appended} · 이미 최신 {unchanged} · 전량 재수집 {refreshed} "
          f"· 시세없음 {len(no_data)} · 실패 {len(failed)}")
    if no_data:
        print("시세없음(상폐·정지 추정):", ", ".join(no_data[:30]) + (" …" if len(no_data) > 30 else ""))
    if failed:
        print("실패 종목:", ", ".join(failed))
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", help="쉼표 구분 티커 (기본: 마스터 전체)")
    ap.add_argument("--universe", choices=("sp500", "all"), default="sp500",
                    help="sp500=S&P 500만, all=미국 전 상장 보통주(ETF·우선주 제외)")
    ap.add_argument("--limit", type=int, help="앞에서 N종목만")
    ap.add_argument("--force", action="store_true", help="기존 파케이 덮어쓰기")
    ap.add_argument("--update", action="store_true",
                    help="일일 증분: 기존 파케이에 최근 시세만 이어 붙인다(재무는 마지막 값 유지)")
    ap.add_argument("--sleep", type=float, default=0.6, help="종목 간 대기(초)")
    ap.add_argument("--detect-currency", action="store_true",
                    help="시세·재무를 받지 않고 재무제표 통화만 조사해 마스터에 기록(이어받기 가능)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    master = json.loads(MASTER_PATH.read_text()) if MASTER_PATH.exists() else None
    needs_rebuild = (
        not master
        or not all("cik" in m for m in master)
        or (args.universe == "all" and len(master) < 1000)  # sp500 마스터로는 전체를 못 돈다
    )
    if needs_rebuild:
        print(f"유니버스 수집 중 (universe={args.universe})…")
        master = fetch_us_master(args.universe)
        MASTER_PATH.write_text(json.dumps(master, ensure_ascii=False, indent=1))
        print(f"  마스터 {len(master)}종목")
    by_symbol = {m["symbol"]: m for m in master}

    symbols = [s.strip().upper().replace(".", "-") for s in args.symbols.split(",")] \
        if args.symbols else [m["symbol"] for m in master]
    if args.limit:
        symbols = symbols[: args.limit]

    if args.detect_currency:
        return detect_currencies(master, by_symbol, symbols, args.sleep)

    if args.update:
        return update_existing(symbols, by_symbol, args.sleep)

    ok = skip = fail = 0
    failed: list[str] = []
    for i, sym in enumerate(symbols, 1):
        out_path = OUT_DIR / f"{sym}.parquet"
        if out_path.exists() and not args.force:
            skip += 1
            continue
        sector = by_symbol.get(sym, {}).get("sector", "")
        for attempt in range(3):
            try:
                hist, qdf, shares, meta, adf = fetch_symbol(sym, by_symbol.get(sym, {}).get("cik"))
                # 마스터에 섹터가 없는 종목(S&P 500 외)은 yfinance에서 받은 GICS 섹터를 쓴다
                df = build_daily_frame(hist, qdf, shares, sector or meta["sector"], adf)
                df.to_parquet(out_path, index=False)
                if sym in by_symbol:
                    by_symbol[sym]["market"] = meta["market"]
                    for key in ("sector", "industry"):
                        if not by_symbol[sym].get(key) and meta[key]:
                            by_symbol[sym][key] = meta[key]
                    if meta.get("financial_currency"):
                        by_symbol[sym]["financial_currency"] = meta["financial_currency"]
                ok += 1
                print(f"[{i}/{len(symbols)}] {sym}: {len(df)}행 "
                      f"({df['date'].iloc[0].date()}~{df['date'].iloc[-1].date()})")
                break
            except Exception as exc:
                wait = 30 * (attempt + 1)
                print(f"[{i}/{len(symbols)}] {sym}: 실패({exc}) — {wait}초 후 재시도 {attempt + 1}/3")
                time.sleep(wait)
        else:
            fail += 1
            failed.append(sym)
        if i % 25 == 0:  # 마스터(market 갱신) 중간 저장
            MASTER_PATH.write_text(json.dumps(master, ensure_ascii=False, indent=1))
        time.sleep(args.sleep)

    MASTER_PATH.write_text(json.dumps(master, ensure_ascii=False, indent=1))
    print(f"\n완료: 성공 {ok} · 스킵 {skip} · 실패 {fail}")
    if failed:
        print("실패 종목:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
