"""
OHLCV 데이터 수집 스크립트

- pykrx를 사용해 KRX 직접 조회 (숫자+알파벳 혼합 코드 지원)
- FDR/Yahoo Finance 방식은 알파벳 포함 종목 코드에서 404 발생하므로 사용하지 않음
- korea-stocks.json 기준으로 parquet 파일이 없는 종목만 수집
"""
import pykrx.stock as pykrx
import pandas as pd
import polars as pl
import json
import os
import glob
import logging
from datetime import datetime

logging.basicConfig(
    filename='data_collection.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

START_DATE = '20000101'


def collect_stock_data(symbol: str, name: str, target_dir: str) -> tuple[bool, str]:
    file_path = os.path.join(target_dir, f"{symbol}.parquet")
    if os.path.exists(file_path):
        return False, "Already exists"

    today = datetime.today().strftime('%Y%m%d')
    try:
        logging.info(f"Downloading {symbol} ({name})...")
        df = pykrx.get_market_ohlcv_by_date(START_DATE, today, symbol)
        if df is None or df.empty:
            logging.warning(f"Empty data for {symbol} ({name})")
            return False, "Empty data"

        df = df.reset_index()
        col_map = {
            '날짜': 'date', '시가': 'open', '고가': 'high',
            '저가': 'low', '종가': 'close', '거래량': 'volume', '등락률': 'change',
        }
        df = df.rename(columns=col_map)
        df['date'] = pd.to_datetime(df['date'])
        for col in ['open', 'high', 'low', 'close', 'volume', 'change']:
            if col in df.columns:
                df[col] = df[col].astype(float)

        for col in ['sector', 'eps', 'bps', 'roe_or_gpa', 'debt_ratio', 'per', 'pbr']:
            df[col] = None

        final_cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'change',
                      'sector', 'eps', 'bps', 'roe_or_gpa', 'debt_ratio', 'per', 'pbr']
        pl.from_pandas(df[final_cols]).write_parquet(file_path)
        logging.info(f"Success {symbol} ({len(df)} rows)")
        return True, "Success"
    except Exception as e:
        logging.error(f"Error downloading {symbol}: {e}")
        return False, str(e)


def load_missing_stocks(stocks_json: str, ohlcv_dir: str) -> list[dict]:
    with open(stocks_json, encoding='utf-8') as f:
        stocks = json.load(f)
    existing = {
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(os.path.join(ohlcv_dir, '*.parquet'))
    }
    return [s for s in stocks if s['symbol'] not in existing]


def main():
    base_dir = os.path.join(os.path.dirname(__file__), '..', '..')
    target_dir = os.path.join(base_dir, 'data', 'ohlcv')
    stocks_json = os.path.join(base_dir, 'data', 'korea-stocks.json')
    os.makedirs(target_dir, exist_ok=True)

    missing = load_missing_stocks(stocks_json, target_dir)
    print(f"수집 대상: {len(missing)}개 (parquet 없는 종목)")
    logging.info(f"Starting collection: {len(missing)} stocks to fetch")

    success_count = error_count = skipped_count = 0

    for i, stock in enumerate(missing, 1):
        sym = stock['symbol']
        name = stock['name']
        ok, msg = collect_stock_data(sym, name, target_dir)
        if ok:
            success_count += 1
            print(f"[{i:4}/{len(missing)}] {sym} ({name}): {msg}")
        elif msg == "Already exists":
            skipped_count += 1
        else:
            error_count += 1
            print(f"[{i:4}/{len(missing)}] {sym} ({name}): FAIL — {msg}")

    print(f"\n완료: 성공 {success_count} | 건너뜀 {skipped_count} | 오류 {error_count}")
    logging.info(f"Finished: S:{success_count} Sk:{skipped_count} E:{error_count}")


if __name__ == "__main__":
    main()
