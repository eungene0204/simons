import os
import sys
import json
import argparse
import re
from zoneinfo import ZoneInfo
import pandas as pd
import polars as pl
import FinanceDataReader as fdr
from tqdm import tqdm
from pathlib import Path
from datetime import datetime

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def _notify_backend(event: str, **kwargs):
    """백엔드 서버에 동기화 이벤트를 알린다. 서버가 꺼져 있으면 조용히 무시한다."""
    try:
        import requests
        requests.post(
            f"{BACKEND_URL}/internal/sync/event",
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

from backend.engine.data_fetcher import fetch_and_enrich
from backend.engine.sector_mapper import get_sector_from_industry
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
        print("  Falling back to FinanceDataReader StockListing...")
        try:
            kospi_df = fdr.StockListing("KOSPI")
            kosdaq_df = fdr.StockListing("KOSDAQ")
            for df, market in ((kospi_df, "KOSPI"), (kosdaq_df, "KOSDAQ")):
                for _, row in df.iterrows():
                    symbol = str(row.get("Code", "")).strip().zfill(6)
                    name = str(row.get("Name", "")).strip()
                    industry = str(row.get("Industry", "") or "").strip()
                    if not symbol or not name:
                        continue
                    if not symbol.isdigit() or len(symbol) != 6:
                        continue
                    sector = get_sector_from_industry(symbol, industry, name)
                    new_list.append({
                        "symbol": symbol,
                        "name": name,
                        "market": market,
                        "sector": sector,
                        "industry": industry,
                    })
        except Exception as e2:
            print(f"  FDR StockListing도 실패: {e2}")

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

def update_ohlcv_incremental(symbol, data_dir):
    """Update parquet file with latest data if exists, else full download."""
    file_path = os.path.join(data_dir, f"{symbol}.parquet")
    
    if not os.path.exists(file_path):
        return fetch_and_enrich(symbol, data_dir)
        
    try:
        # Load existing
        df_old = pl.read_parquet(file_path)
        last_date = df_old['date'].max()
        if isinstance(last_date, str):
            last_date = datetime.strptime(last_date, '%Y-%m-%d')
        
        # Fetch new data since last date
        start_date_str = last_date.strftime('%Y-%m-%d')
        df_new_pd = fdr.DataReader(symbol, start_date_str)
        
        if df_new_pd.empty:
            return True # Already up to date
            
        # Convert new data to Polars
        df_new_pd = df_new_pd.reset_index()
        df_new_pd.columns = [col.lower().replace(' ', '_') for col in df_new_pd.columns]

        # Cast columns to match typical schema
        float_cols = ['open', 'high', 'low', 'close', 'adj_close', 'change']
        for col in float_cols:
            if col in df_new_pd.columns:
                df_new_pd[col] = df_new_pd[col].astype(float)

        df_new = pl.from_pandas(df_new_pd)
        if 'date' in df_new.columns:
            df_new = df_new.with_columns(pl.col('date').cast(pl.Datetime('us')))

        # Normalize df_old date to same precision
        if 'date' in df_old.columns:
            df_old = df_old.with_columns(pl.col('date').cast(pl.Datetime('us')))

        # Ensure df_old types match
        df_old = df_old.with_columns([
            pl.col(c).cast(pl.Float64) for c in float_cols if c in df_old.columns
        ])
        if 'volume' in df_old.columns:
            df_old = df_old.with_columns(pl.col('volume').cast(pl.Float64))
        if 'volume' in df_new.columns:
            df_new = df_new.with_columns(pl.col('volume').cast(pl.Float64))

        # Preserve sector column from old data (new data won't have it)
        if 'sector' in df_old.columns and 'sector' not in df_new.columns:
            sector_val = df_old['sector'][0]
            df_new = df_new.with_columns(pl.lit(sector_val).alias('sector'))

        # Align columns: only keep columns present in df_old
        common_cols = [c for c in df_old.columns if c in df_new.columns]
        df_old = df_old.select(common_cols)
        df_new = df_new.select(common_cols)

        # Combine
        df_combined = pl.concat([df_old, df_new]).unique(subset=['date'], keep='last').sort('date')
        
        # Re-save
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

    if args.symbols_only:
        print(f"\n[--symbols-only] OHLCV 동기화 건너뜀. 종목 목록 업데이트 완료 ({len(stocks)}개)")
        if not symbol_sync_ok:
            print("[ERROR] 종목 목록 실시간 갱신 실패: 기존 korea-stocks.json으로 폴백했습니다.")
            return 2
        return 0

    # 3. Sync OHLCV
    print(f"Starting OHLCV synchronization for {len(stocks)} symbols...")
    success_count = 0
    fail_count = 0

    for s in tqdm(stocks, desc="Updating OHLCV"):
        symbol = s['symbol']
        if update_ohlcv_incremental(symbol, str(data_dir)):
            success_count += 1
        else:
            fail_count += 1

    print(f"\nFinal Summary:")
    print(f"- Total Stocks: {len(stocks)}")
    print(f"- New symbols added: {len(new_symbols)}")
    print(f"- Delisted symbols removed: {len(delisted_symbols)}")
    print(f"- OHLCV Update Success: {success_count}")
    print(f"- OHLCV Update Failure: {fail_count}")

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
    )

    if not symbol_sync_ok:
        print("[ERROR] 종목 목록 실시간 갱신 실패: 기존 korea-stocks.json으로 OHLCV만 갱신했습니다.")
        return 2

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
