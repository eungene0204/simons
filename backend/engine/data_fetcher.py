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
            from .fundamental_backfill import add_market_cap, apply_real_market_cap

            # 3b. 실측 일별 시가총액(억원) — 전 구간 1콜, 당시 실제 상장주식수 기준.
            #     실패·미커버(ETF 등) 날짜만 아래 add_market_cap 근사가 gap-fill로 메운다.
            try:
                mc = pykrx.get_market_cap_by_date(
                    df["date"].min().strftime("%Y%m%d"),
                    df["date"].max().strftime("%Y%m%d"),
                    symbol,
                )
                if mc is not None and not mc.empty and "시가총액" in mc.columns:
                    caps = mc["시가총액"].astype(float) / 1e8
                    caps.index = pd.to_datetime(caps.index)
                    df = apply_real_market_cap(df, caps)
            except Exception as e:
                print(f"[WARNING] real market cap fetch failed for {symbol}: {e}")

            # market_cap을 먼저 채워야 enrich가 같은 실행에서 PCR(시총/영업CF)을 계산한다.
            # 신생 parquet이 여기서 시총 없이 태어나면, 일일 enrichment 게이트(roa sentinel)가
            # 재무만 보고 건너뛰어 캐시 만료까지 market_cap(→PCR·시총 필터)이 빈다.
            df = add_market_cap(df, symbol)
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
    """기존 parquet에 펀더멘털(EPS/BPS/PER/PBR/PSR/ROE/ROA/부채·유동·당좌비율/성장률 등)과
    market_cap을 비파괴적으로 보강한다(기존 값 보존, 결측만 채움)."""
    target_path = os.path.join(data_dir, f"{symbol}.parquet")
    if not os.path.exists(target_path):
        print(f"[ERROR] Parquet file not found: {target_path}")
        return False

    try:
        from .fundamental_backfill import refresh_symbol, SENTINEL_COL

        df = pd.read_parquet(target_path)
        merged = refresh_symbol(df, symbol)
        # 연간 펀더멘털도 시총도 못 얻었으면 변화 없음 — 쓰지 않는다.
        got_annual = SENTINEL_COL in merged.columns and merged[SENTINEL_COL].notna().any()
        got_market_cap = "market_cap" in merged.columns and merged["market_cap"].notna().any()
        if not got_annual and not got_market_cap:
            print(f"[WARNING] Could not fetch fundamentals for {symbol}")
            return False

        merged.to_parquet(target_path)
        print(f"[INFO] Enriched existing parquet {symbol} with fundamentals + market_cap")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to enrich {symbol}: {e}")
        return False
