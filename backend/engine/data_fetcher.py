import pykrx.stock as pykrx
import pandas as pd
import os
import json
from datetime import datetime
from pathlib import Path
from .sector_mapper import get_sector_from_industry
from .fundamental_fetcher import fetch_fundamentals, enrich_ohlcv_with_fundamentals


def _fetch_ohlcv_pykrx(symbol: str, start: str = "20000101") -> pd.DataFrame:
    """pykrx로 OHLCV 데이터를 조회해 표준 컬럼명으로 반환한다.

    pykrx는 숫자 전용 코드뿐 아니라 숫자+알파벳 혼합 KRX 코드도 지원한다.
    반환 컬럼: date, open, high, low, close, volume, change
    """
    today = datetime.today().strftime("%Y%m%d")
    df = pykrx.get_market_ohlcv_by_date(start, today, symbol)
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


def fetch_and_enrich(symbol, data_dir, skip_fundamentals=False):
    """
    pykrx로 OHLCV 데이터를 다운로드하고 섹터·재무 데이터를 enrichment한 뒤 parquet으로 저장한다.
    숫자+알파벳 혼합 KRX 코드(예: 0007C0)도 지원한다.
    """
    try:
        # 1. Download data via pykrx
        df = _fetch_ohlcv_pykrx(symbol)
        if df.empty:
            print(f"[ERROR] pykrx returned empty data for {symbol}")
            return False

        # 2. Get Sector from krx-stocks.json
        # Resolve project root relative to this file (backend/engine/data_fetcher.py → ../../)
        base_path = Path(__file__).resolve().parent.parent.parent
        stocks_json_path = base_path / "data" / "korea-stocks.json"

        sector = None
        if stocks_json_path.exists():
            with open(stocks_json_path, 'r', encoding='utf-8') as f:
                stocks = json.load(f)
                for s in stocks:
                    if s['symbol'] == symbol:
                        industry = s.get('industry')
                        name = s.get('name', '')
                        sector = get_sector_from_industry(symbol, industry, name)
                        break

        # 3. Add sector column if found
        if sector:
            df["sector"] = sector
            print(f"[INFO] Enriched {symbol} with sector: {sector}")
        else:
            print(f"[WARNING] Could not determine sector for {symbol}")

        # 4. Fundamental enrichment (EPS/BPS/ROE/debt_ratio → PER/PBR)
        if not skip_fundamentals:
            fundamentals = fetch_fundamentals(symbol)
            if fundamentals:
                df = enrich_ohlcv_with_fundamentals(df, fundamentals)
                print(f"[INFO] Enriched {symbol} with fundamentals: EPS/BPS/PER/PBR/ROE/debt_ratio")
            else:
                print(f"[WARNING] Could not fetch fundamentals for {symbol}")

        # 5. Save to parquet
        target_path = os.path.join(data_dir, f"{symbol}.parquet")
        df.to_parquet(target_path)
        print(f"[INFO] Successfully downloaded and saved {symbol} to {target_path}")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to fetch data for {symbol}: {e}")
        return False


def enrich_existing_parquet(symbol, data_dir):
    """기존 parquet 파일에 재무 데이터(EPS/BPS/PER/PBR/ROE/debt_ratio)를 추가한다."""
    target_path = os.path.join(data_dir, f"{symbol}.parquet")
    if not os.path.exists(target_path):
        print(f"[ERROR] Parquet file not found: {target_path}")
        return False

    try:
        df = pd.read_parquet(target_path)
        fundamentals = fetch_fundamentals(symbol)
        if not fundamentals:
            print(f"[WARNING] Could not fetch fundamentals for {symbol}")
            return False

        df = enrich_ohlcv_with_fundamentals(df, fundamentals)
        df.to_parquet(target_path)
        print(f"[INFO] Enriched existing parquet {symbol} with fundamentals")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to enrich {symbol}: {e}")
        return False
