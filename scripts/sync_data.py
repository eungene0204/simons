import os
import sys
import json
import argparse
import re
import time
from zoneinfo import ZoneInfo
import pandas as pd
import polars as pl
import pykrx.stock as pykrx
from tqdm import tqdm
from pathlib import Path
from datetime import datetime
import FinanceDataReader as fdr
from dotenv import load_dotenv

def _notify_backend(event: str, **kwargs):
    """백엔드 서버에 동기화 이벤트를 알린다. 서버가 꺼져 있으면 조용히 무시한다."""
    try:
        import requests
        backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
        requests.post(
            f"{backend_url}/internal/sync/event",
            json={"event": event, **kwargs},
            timeout=3,
        )
    except Exception:
        pass


def _now_kst() -> datetime:
    return datetime.now(KST)

# Add root and backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backend.engine.data_fetcher import fetch_and_enrich, enrich_existing_parquet
from backend.engine.sector_mapper import get_sector_from_industry
from backend.engine.fundamental_fetcher import _read_cache
from backend.engine.dart_client import fetch_recent_delisting_notices
from backend.universe_history import (
    build_universe_sync_log_lines,
    load_universe_history,
    record_universe_sync,
)

KST = ZoneInfo("Asia/Seoul")

# 알려진 주요 종목 — sync 후 데이터 정합성 검증에 사용
KNOWN_STOCKS = {
    "000100": ("유한양행", "KOSPI"),
    "005930": ("삼성전자", "KOSPI"),
    "000660": ("SK하이닉스", "KOSPI"),
    "035420": ("NAVER", "KOSPI"),
    "005380": ("현대자동차", "KOSPI"),
    "068270": ("셀트리온", "KOSPI"),
    "035720": ("카카오", "KOSPI"),
    "207940": ("삼성바이오로직스", "KOSPI"),
    "323410": ("카카오뱅크", "KOSPI"),
    "373220": ("LG에너지솔루션", "KOSPI"),
}

_ALNUM_SYMBOL_RE = re.compile(r"^[0-9A-Z]{6}$")


def _is_krx_symbol(symbol: str) -> bool:
    return bool(_ALNUM_SYMBOL_RE.fullmatch(symbol or ""))


def fetch_etf_symbols() -> list[str]:
    """FinanceDataReader로 KRX 전체 ETF 종목 코드를 반환한다.

    pykrx get_etf_ticker_list가 불안정하므로 fdr을 primary로 사용한다.
    실패 시 빈 리스트를 반환한다.
    """
    try:
        df = fdr.StockListing('ETF/KR')
        symbols = [str(s).zfill(6) for s in df['Symbol'].dropna().tolist()]
        symbols = [s for s in symbols if _is_krx_symbol(s)]
        print(f"  FinanceDataReader ETF/KR: {len(symbols)}개")
        return symbols
    except Exception as e:
        print(f"  [WARNING] ETF 목록 조회 실패 (fdr): {e}")
        return []

def _fetch_kind_market(market_type: str, market_label: str) -> list[dict]:
    """KRX KIND 상장법인 목록에서 종목 정보를 가져온다.
    market_type: 'stockMkt'(KOSPI) or 'kosdaqMkt'(KOSDAQ)
    market_label: 'KOSPI' or 'KOSDAQ'
    """
    import requests
    import io
    url = "https://kind.krx.co.kr/corpgeneral/corpList.do"
    params = {"method": "download", "searchType": "13", "marketType": market_type}
    r = requests.get(url, params=params, timeout=15)
    r.encoding = "euc-kr"
    df = pd.read_html(io.StringIO(r.text))[0]

    result = []
    for _, row in df.iterrows():
        raw_code = str(row.get("종목코드", "")).strip()
        symbol = raw_code.zfill(6)
        name = str(row.get("회사명", "")).strip()
        industry = str(row.get("업종", "")).strip()
        if not symbol or not name:
            continue
        # KIND 원본은 영문 포함 6자리 KRX 코드도 내려주므로 그대로 유지한다.
        if not _is_krx_symbol(symbol):
            continue
        sector = get_sector_from_industry(symbol, industry, name)
        result.append({
            "symbol": symbol,
            "name": name,
            "market": market_label,
            "sector": sector,
            "industry": industry,
        })
    return result


def needs_fundamental_enrichment(parquet_path, symbol) -> bool:
    """이 종목의 parquet에 재무 보강이 필요한지.

    종합 펀더멘털(roa=신규 팩터 sentinel)이 이미 있고 캐시가 유효하면 건너뛴다
    (roe만 보면 구버전 컬럼만 가진 종목이 영구 스킵되어 신규 팩터가 안 채워진다).

    판정은 **마지막 행** 기준이다(2026-08-08). `notna().any()`로 보면 한 행이라도 값이
    있는 순간 영구 스킵되는데, OHLCV 갱신이 새로 붙인 봉은 재무 컬럼이 null이라
    (pykrx 응답에 없어 `pl.lit(None)`로 맞춘다) 그 null이 **캐시 만료(90일) 전까지
    채워지지 않았다** — 최근 구간의 재무 필터·랭킹이 종목에 따라 통째로 비는 원인이다.
    마지막 행을 보면 매 동기화가 그날 붙인 봉을 그 자리에서 메운다. 보강은 결측만
    채우므로(merge_fundamentals=기존 값 우선) 반복해도 기존 값을 덮지 않는다.
    """
    df_check = pd.read_parquet(parquet_path)
    has_roa = (
        "roa" in df_check.columns
        and not df_check.empty
        and pd.notna(df_check["roa"].iloc[-1])
    )
    return not (has_roa and _read_cache(symbol) is not None)


def sync_symbols(stocks_path):
    """Fetch latest KOSPI/KOSDAQ symbols and update korea-stocks.json.

    데이터 소스 우선순위:
    1. KRX KIND 상장법인 목록 (kind.krx.co.kr) — 공식 + 올바른 이름-코드 매핑
    2. FinanceDataReader StockListing — fallback
    """
    print("Fetching latest stock listings from KRX KIND...")
    new_list = []

    try:
        kospi_list = _fetch_kind_market("stockMkt", "KOSPI")
        kosdaq_list = _fetch_kind_market("kosdaqMkt", "KOSDAQ")
        new_list = kospi_list + kosdaq_list
        print(f"  KRX KIND: KOSPI={len(kospi_list)}, KOSDAQ={len(kosdaq_list)}")
    except Exception as e:
        print(f"  KRX KIND 실패: {e}")
        print("  Falling back to pykrx StockListing...")
        try:
            for market_code, market_label in (("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ")):
                tickers = pykrx.get_market_ticker_list(market=market_code)
                for ticker in tickers:
                    name = pykrx.get_market_ticker_name(ticker)
                    if not name:
                        continue
                    sector = get_sector_from_industry(ticker, "", name)
                    new_list.append({
                        "symbol": ticker,
                        "name": name,
                        "market": market_label,
                        "sector": sector,
                        "industry": "",
                    })
        except Exception as e2:
            print(f"  pykrx StockListing도 실패: {e2}")

    if not new_list:
        return [], [], []

    # Compare with existing
    existing_stocks = []
    if os.path.exists(stocks_path):
        with open(stocks_path, 'r', encoding='utf-8') as f:
            existing_stocks = json.load(f)

    existing_symbols = {s['symbol'] for s in existing_stocks}
    new_symbols_set = {s['symbol'] for s in new_list}
    new_symbols_found = [s for s in new_list if s['symbol'] not in existing_symbols]
    delisted_symbols = [s for s in existing_stocks if s['symbol'] not in new_symbols_set]

    if new_symbols_found:
        print(f"Found {len(new_symbols_found)} new symbols!")
        for ns in new_symbols_found[:5]:
            print(f"  - {ns['name']} ({ns['symbol']})")
        if len(new_symbols_found) > 5:
            print("  ...")

    if delisted_symbols:
        print(f"Found {len(delisted_symbols)} delisted/removed symbols!")
        for ds in delisted_symbols[:5]:
            print(f"  - {ds['name']} ({ds['symbol']})")
        if len(delisted_symbols) > 5:
            print("  ...")

    # Atomic write (tmp → rename)
    tmp_path = stocks_path + ".tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(new_list, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, stocks_path)

    print(f"Updated {stocks_path} with {len(new_list)} symbols.")
    return new_list, new_symbols_found, delisted_symbols

def _fetch_ohlcv_pykrx(symbol: str, start: str) -> pd.DataFrame:
    """pykrx로 start~오늘까지 OHLCV를 조회해 표준 컬럼명으로 반환한다.

    숫자+알파벳 혼합 KRX 코드(예: 0007C0)도 지원한다.
    반환 컬럼: date, open, high, low, close, volume, change
    """
    today = datetime.now(KST).strftime("%Y%m%d")
    start_str = start.replace("-", "")
    df = pykrx.get_market_ohlcv_by_date(start_str, today, symbol)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.reset_index()
    col_map = {
        "날짜": "date", "시가": "open", "고가": "high",
        "저가": "low", "종가": "close", "거래량": "volume", "등락률": "change",
    }
    df = df.rename(columns=col_map)
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume", "change"]:
        if col in df.columns:
            df[col] = df[col].astype(float)
    return df


def update_ohlcv_incremental(symbol, data_dir):
    """Update parquet file with latest data if exists, else full download.

    pykrx를 사용해 숫자 전용 코드와 숫자+알파벳 혼합 코드 모두 지원한다.
    """
    file_path = os.path.join(data_dir, f"{symbol}.parquet")

    if not os.path.exists(file_path):
        return fetch_and_enrich(symbol, data_dir)

    try:
        df_old = pl.read_parquet(file_path)
        last_date = df_old["date"].max()
        if isinstance(last_date, str):
            last_date = datetime.strptime(last_date, "%Y-%m-%d")

        df_new_pd = _fetch_ohlcv_pykrx(symbol, start=last_date.strftime("%Y-%m-%d"))
        if df_new_pd.empty:
            return True  # Already up to date

        df_new = pl.from_pandas(df_new_pd)
        df_old = df_old.with_columns(pl.col("date").cast(pl.Datetime("us")))
        df_new = df_new.with_columns(pl.col("date").cast(pl.Datetime("us")))

        # pykrx 응답에는 재무/섹터 컬럼이 없으므로 기존 parquet 컬럼 기준으로 맞춤
        for col in df_old.columns:
            if col not in df_new.columns:
                df_new = df_new.with_columns(pl.lit(None).cast(df_old[col].dtype).alias(col))
        df_new = df_new.select(df_old.columns)

        df_combined = (
            pl.concat([df_old, df_new])
            .unique(subset=["date"], keep="last")
            .sort("date")
        )
        df_combined.write_parquet(file_path)
        return True

    except Exception as e:
        print(f"[WARNING] Failed to update {symbol} incrementally: {e}")
        print(f"[INFO] Attempting full re-download for {symbol}...")
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            return fetch_and_enrich(symbol, data_dir)
        except Exception as e2:
            print(f"[ERROR] Full re-download failed for {symbol}: {e2}")
            return False

def validate_stock_list(stocks: list) -> list[str]:
    """알려진 주요 종목을 기준으로 데이터 정합성을 검증한다. 문제 목록을 반환한다."""
    stock_map = {s['symbol']: s for s in stocks}
    warnings = []
    for code, (expected_name_part, expected_market) in KNOWN_STOCKS.items():
        entry = stock_map.get(code)
        if entry is None:
            warnings.append(f"[MISSING] {code} ({expected_name_part}) 누락")
        elif entry['market'] != expected_market:
            warnings.append(f"[MARKET]  {code} 시장 오류: expected={expected_market}, got={entry['market']}")
        elif expected_name_part not in entry['name']:
            warnings.append(f"[NAME]    {code} 이름 불일치: expected≈{expected_name_part}, got={entry['name']}")
    return warnings


def main(argv=None):
    # .env 로드는 실행 시점에만(import 부작용으로 전역 env를 오염시키지 않도록).
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    parser = argparse.ArgumentParser(description="Sync Korean stock data")
    parser.add_argument(
        "--symbols-only",
        action="store_true",
        help="종목 목록(korea-stocks.json)만 업데이트하고 OHLCV 다운로드는 건너뜀",
    )
    args = parser.parse_args(argv)

    base_dir = Path(os.getcwd())
    stocks_path = base_dir / "data" / "korea-stocks.json"
    data_dir = base_dir / "data" / "ohlcv"

    if not data_dir.exists():
        data_dir.mkdir(parents=True)

    _notify_backend("start")

    # 1. Sync Symbols
    stocks, new_symbols, delisted_symbols = sync_symbols(str(stocks_path))

    if not stocks:
        print("[WARNING] Symbol sync failed. Falling back to existing korea-stocks.json...")
        if stocks_path.exists():
            with open(stocks_path, 'r', encoding='utf-8') as f:
                stocks = json.load(f)
            new_symbols = []
            delisted_symbols = []
            symbol_sync_ok = False
        else:
            print("[ERROR] No existing stock list found. Aborting.")
            return 1
    else:
        symbol_sync_ok = True

    # 2. Validate
    warnings = validate_stock_list(stocks)
    if warnings:
        print(f"\n[WARN] 데이터 검증 경고 {len(warnings)}건:")
        for w in warnings:
            print(f"  {w}")
    else:
        print("[OK] 주요 종목 검증 통과")

    now_kst = _now_kst()
    kospi_count = sum(1 for s in stocks if s.get("market") == "KOSPI")
    kosdaq_count = sum(1 for s in stocks if s.get("market") == "KOSDAQ")
    history_entry = record_universe_sync(
        date=now_kst.strftime("%Y-%m-%d"),
        synced_at=now_kst.isoformat(),
        total_count=len(stocks),
        kospi_count=kospi_count,
        kosdaq_count=kosdaq_count,
        added=new_symbols,
        delisted=delisted_symbols,
    )
    print(
        "[OK] 유니버스 이력 기록 완료 "
        f"({history_entry['date']} total={history_entry['totalCount']}, "
        f"added={history_entry['addedCount']}, delisted={history_entry['delistedCount']})"
    )
    for line in build_universe_sync_log_lines(history_entry, load_universe_history()):
        print(line)

    # 3. DART 상장폐지 공시 체크 (KRX 스냅샷 비교와 독립적으로 실행)
    _CONFIRMED_DELIST_KEYWORDS = ["상장폐지결정", "상장폐지 결정", "정리매매", "상장폐지예고"]
    print("\nChecking OpenDART for delisting notices (past 7 days)...")
    try:
        dart_notices = fetch_recent_delisting_notices(days=7)
        print(f"  DART 상장폐지 관련 공시 {len(dart_notices)}건 발견")
        dart_confirmed = []
        for notice in dart_notices:
            code = notice["stock_code"]
            name = notice["corp_name"]
            report = notice["report_nm"]
            date = notice["rcept_dt"]
            print(f"  - [{date}] {name} ({code}): {report}")
            # 상장폐지 확정 건만 DelistedSymbolStore에 등록
            if any(kw in report for kw in _CONFIRMED_DELIST_KEYWORDS):
                try:
                    import requests as req_lib
                    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
                    r = req_lib.post(f"{backend_url}/market/delist/{code}", timeout=3)
                    if r.status_code == 200 and r.json().get("added"):
                        dart_confirmed.append({"symbol": code, "name": name})
                        print(f"    → 상장폐지 등록 완료: {code}")
                except Exception:
                    pass
        if dart_confirmed:
            _notify_backend("dart_delist", delisted_symbols=dart_confirmed)
        if not dart_notices:
            print("  DART 상장폐지 공시 없음")
    except Exception as e:
        print(f"  [WARNING] DART 공시 조회 실패: {e}")

    if args.symbols_only:
        print(f"\n[--symbols-only] OHLCV 동기화 건너뜀. 종목 목록 업데이트 완료 ({len(stocks)}개)")
        if not symbol_sync_ok:
            print("[ERROR] 종목 목록 실시간 갱신 실패: 기존 korea-stocks.json으로 폴백했습니다.")
            return 2
        return 0

    # 4. Sync OHLCV (일반 종목)
    print(f"Starting OHLCV synchronization for {len(stocks)} symbols...")
    success_count = 0
    fail_count = 0

    for s in tqdm(stocks, desc="Updating OHLCV"):
        symbol = s['symbol']
        if update_ohlcv_incremental(symbol, str(data_dir)):
            success_count += 1
        else:
            fail_count += 1

    # 4b. Sync ETF OHLCV (Korea ETF — KIND API에 미포함되어 별도 처리)
    print("\nFetching ETF symbol list...")
    etf_symbols = fetch_etf_symbols()
    etf_success, etf_fail = 0, 0
    if etf_symbols:
        print(f"Starting ETF OHLCV synchronization for {len(etf_symbols)} ETFs...")
        for sym in tqdm(etf_symbols, desc="Updating ETF OHLCV"):
            if update_ohlcv_incremental(sym, str(data_dir)):
                etf_success += 1
            else:
                etf_fail += 1
    else:
        print("[WARNING] ETF 목록 조회 실패 — ETF OHLCV 업데이트 건너뜀")

    # 5. Fundamental Enrichment (EPS/BPS/PER/PBR/ROE)
    #    캐시 미보유 또는 만료된 종목만 네트워크 요청, 나머지는 캐시 사용
    print(f"\nStarting fundamental enrichment for {len(stocks)} symbols...")
    fund_success, fund_fail, fund_skip = 0, 0, 0

    for s in tqdm(stocks, desc="Enriching fundamentals"):
        symbol = s['symbol']
        parquet_path = os.path.join(str(data_dir), f"{symbol}.parquet")
        if not os.path.exists(parquet_path):
            fund_skip += 1
            continue

        try:
            if not needs_fundamental_enrichment(parquet_path, symbol):
                fund_skip += 1
                continue
        except Exception:
            pass

        try:
            if enrich_existing_parquet(symbol, str(data_dir)):
                fund_success += 1
            else:
                fund_fail += 1
        except Exception:
            fund_fail += 1

        time.sleep(0.3)

    print(f"Fundamental Enrichment Summary:")
    print(f"- Success: {fund_success}")
    print(f"- Failed: {fund_fail}")
    print(f"- Skipped (already up-to-date): {fund_skip}")

    print(f"\nFinal Summary:")
    print(f"- Total Stocks: {len(stocks)}")
    print(f"- New symbols added: {len(new_symbols)}")
    print(f"- Delisted symbols removed: {len(delisted_symbols)}")
    print(f"- OHLCV Update Success: {success_count}")
    print(f"- OHLCV Update Failure: {fail_count}")
    print(f"- ETF OHLCV Success: {etf_success}, Failed: {etf_fail} (total ETFs: {len(etf_symbols)})")
    print(f"- Fundamental Enriched: {fund_success}, Failed: {fund_fail}, Skipped: {fund_skip}")

    _notify_backend(
        "end",
        date=history_entry["date"],
        total=len(stocks),
        kospi=kospi_count,
        kosdaq=kosdaq_count,
        new_symbols=len(new_symbols),
        added_symbols=new_symbols,
        delisted_symbols=delisted_symbols,
        success=success_count,
        fail=fail_count,
        fundamental_success=fund_success,
        fundamental_fail=fund_fail,
        fundamental_skip=fund_skip,
    )

    if not symbol_sync_ok:
        print("[ERROR] 종목 목록 실시간 갱신 실패: 기존 korea-stocks.json으로 OHLCV만 갱신했습니다.")
        return 2

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
