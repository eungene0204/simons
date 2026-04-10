"""
기존 parquet 파일 전체에 EPS/BPS/PER/PBR enrichment 일괄 실행.
Naver Finance rate limit 방지: 종목 간 0.8초 대기.
"""

import os
import sys
import time
from pathlib import Path

# backend/ 기준으로 PYTHONPATH 설정
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.data_fetcher import enrich_existing_parquet

DATA_DIR = str(Path(__file__).resolve().parent.parent.parent / "data" / "ohlcv")
DELAY = 0.8   # 종목 간 대기 (초)
LOG_FILE = str(Path(__file__).resolve().parent / "enrich_log.txt")


def main():
    parquet_files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".parquet"))
    total = len(parquet_files)
    print(f"[START] 총 {total}개 종목 enrichment 시작 (딜레이 {DELAY}s/종목)")
    print(f"[LOG] {LOG_FILE}")

    success, fail, skip = 0, 0, 0
    failed_symbols = []

    start_time = time.time()

    with open(LOG_FILE, "w", encoding="utf-8") as log:
        log.write(f"START {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        for i, fname in enumerate(parquet_files, 1):
            symbol = fname.replace(".parquet", "")

            try:
                ok = enrich_existing_parquet(symbol, DATA_DIR)
                if ok:
                    success += 1
                    status = "OK"
                else:
                    fail += 1
                    status = "FAIL"
                    failed_symbols.append(symbol)
            except Exception as e:
                fail += 1
                status = f"ERROR: {e}"
                failed_symbols.append(symbol)

            log.write(f"{symbol}\t{status}\n")
            log.flush()

            elapsed = time.time() - start_time
            eta = elapsed / i * (total - i)
            if i % 50 == 0 or i <= 5:
                print(
                    f"[{i}/{total}] {symbol} → {status} | "
                    f"성공 {success} 실패 {fail} | "
                    f"경과 {elapsed/60:.1f}분 ETA {eta/60:.1f}분"
                )

            time.sleep(DELAY)

        log.write(f"\nEND {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"성공: {success}, 실패: {fail}\n")
        if failed_symbols:
            log.write("실패 종목:\n" + "\n".join(failed_symbols) + "\n")

    elapsed_total = time.time() - start_time
    print(f"\n[DONE] 성공 {success} / 실패 {fail} / 총 {total}")
    print(f"[DONE] 소요시간 {elapsed_total/60:.1f}분")
    if failed_symbols:
        print(f"[FAIL] 실패 종목 ({len(failed_symbols)}개): {failed_symbols[:10]} ...")


if __name__ == "__main__":
    main()
