"""
기존 parquet 파일에 EPS/BPS/PER/PBR/PSR/ROE/EBITDA/EV-EBITDA 등 펀더멘털 enrichment 일괄 실행.

EV/EBITDA·EBITDA는 KIS other-major-ratios에서 조회해 결산 스냅샷으로 전진충전된다.
이미 roa까지 백필된 종목도 재실행하면 ev_ebitda/ebitda 컬럼이 combine_first로 추가된다
(기존 값은 보존).

사용법:
    python scripts/enrich_all_fundamentals.py              # 전체 종목
    python scripts/enrich_all_fundamentals.py --roe-only   # ROE 미보유 종목만
    python scripts/enrich_all_fundamentals.py --cache-only  # 캐시만 사용 (네트워크 요청 없음)
    python scripts/enrich_all_fundamentals.py --symbols 005930,000660  # 특정 종목만

Naver Finance rate limit 방지: 종목 간 0.8초 대기.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd

# backend/ 기준으로 PYTHONPATH 설정
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.data_fetcher import enrich_existing_parquet
from engine.fundamental_fetcher import _read_cache

DATA_DIR = str(Path(__file__).resolve().parent.parent.parent / "data" / "ohlcv")
DELAY = 0.8   # 종목 간 대기 (초)
LOG_FILE = str(Path(__file__).resolve().parent / "enrich_log.txt")


def _needs_roe(symbol: str) -> bool:
    """parquet 파일에 roe_or_gpa 컬럼이 없거나 전부 NaN인지 확인."""
    path = os.path.join(DATA_DIR, f"{symbol}.parquet")
    if not os.path.exists(path):
        return False
    try:
        df = pd.read_parquet(path)
        if "roe_or_gpa" not in df.columns:
            return True
        return df["roe_or_gpa"].isna().all()
    except Exception:
        return True


def main():
    parser = argparse.ArgumentParser(description="펀더멘털 데이터 일괄 enrichment")
    parser.add_argument("--roe-only", action="store_true", help="ROE 미보유 종목만 처리")
    parser.add_argument("--cache-only", action="store_true", help="캐시만 사용 (네트워크 요청 없음)")
    parser.add_argument("--symbols", type=str, help="쉼표로 구분한 종목 코드 목록")
    parser.add_argument("--delay", type=float, default=DELAY, help="종목 간 대기 시간(초)")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
    else:
        symbols = sorted(f.replace(".parquet", "") for f in os.listdir(DATA_DIR) if f.endswith(".parquet"))

    if args.roe_only:
        print("[FILTER] ROE 미보유 종목만 필터링 중...")
        symbols = [s for s in symbols if _needs_roe(s)]
        print(f"[FILTER] ROE 필요 종목: {len(symbols)}개")

    total = len(symbols)
    if total == 0:
        print("[DONE] 처리할 종목이 없습니다.")
        return

    print(f"[START] 총 {total}개 종목 enrichment 시작 (딜레이 {args.delay}s/종목)")
    print(f"[LOG] {LOG_FILE}")

    success, fail, cache_hit = 0, 0, 0
    failed_symbols = []
    start_time = time.time()

    with open(LOG_FILE, "w", encoding="utf-8") as log:
        log.write(f"START {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        if args.roe_only:
            log.write("MODE: ROE-only\n")
        if args.cache_only:
            log.write("MODE: cache-only\n")

        for i, symbol in enumerate(symbols, 1):
            try:
                if args.cache_only:
                    cached = _read_cache(symbol)
                    if cached:
                        ok = enrich_existing_parquet(symbol, DATA_DIR)
                        cache_hit += 1
                    else:
                        ok = False
                else:
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
                    f"성공 {success} 실패 {fail} "
                    f"{'캐시 ' + str(cache_hit) + ' ' if args.cache_only else ''}| "
                    f"경과 {elapsed/60:.1f}분 ETA {eta/60:.1f}분"
                )

            if not args.cache_only:
                time.sleep(args.delay)

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
