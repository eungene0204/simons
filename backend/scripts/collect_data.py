import FinanceDataReader as fdr
import pandas as pd
import os
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    filename='data_collection.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_naver_tickers(sosok):
    tickers = []
    page = 1
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'}
    
    while True:
        url = f'https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}'
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            found = False
            for a in soup.select('a.tltle'):
                ticker = a['href'].split('=')[-1]
                name = a.get_text(strip=True)
                tickers.append({'Code': ticker, 'Name': name})
                found = True
                
            if not found or page > 50:
                break
            page += 1
        except Exception as e:
            logging.error(f"Error fetching naver page {page}: {e}")
            break
    return tickers

def collect_stock_data(symbol, name, market, target_dir):
    file_path = os.path.join(target_dir, f"{symbol}.parquet")
    if os.path.exists(file_path):
        return False, "Already exists"

    try:
        logging.info(f"Downloading {symbol} ({name})...")
        df = fdr.DataReader(symbol, '1970-01-01', '2024-12-31')
        if df.empty:
            logging.warning(f"Empty data for {symbol}")
            return False, "Empty data"
        df = df.reset_index()
        df.columns = [col.lower() for col in df.columns]
        df.to_parquet(file_path)
        logging.info(f"Success {symbol}")
        return True, "Success"
    except Exception as e:
        logging.error(f"Error downloading {symbol}: {e}")
        return False, str(e)

def main():
    target_dir = "../data/ohlcv"
    os.makedirs(target_dir, exist_ok=True)
    
    logging.info("Starting collection script")
    print("Fetching KOSPI tickers from Naver...")
    kospi = get_naver_tickers(0)
    print("Fetching KOSDAQ tickers from Naver...")
    kosdaq = get_naver_tickers(1)
    
    all_stocks = pd.DataFrame(kospi + kosdaq)
    all_stocks['Market'] = ['KOSPI']*len(kospi) + ['KOSDAQ']*len(kosdaq)
    
    print(f"Total stocks found: {len(all_stocks)}")
    logging.info(f"Total stocks found: {len(all_stocks)}")
    
    success_count = 0
    error_count = 0
    skipped_count = 0
    
    max_workers = 3 # Reduced for stability
    
    with tqdm(total=len(all_stocks), desc="Downloading data") as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(collect_stock_data, row['Code'], row['Name'], row['Market'], target_dir): row 
                for _, row in all_stocks.iterrows()
            }
            
            for future in tqdm(futures, desc="Processing downloads", leave=False):
                try:
                    success, msg = future.result()
                    if success:
                        success_count += 1
                    elif msg == "Already exists":
                        skipped_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logging.error(f"Unhandled error in thread: {e}")
                    error_count += 1
                pbar.update(1)
                
    print(f"\nCollection finished!")
    print(f"Success: {success_count} | Skipped: {skipped_count} | Errors: {error_count}")
    logging.info(f"Finished: S:{success_count} Sk:{skipped_count} E:{error_count}")

if __name__ == "__main__":
    main()
