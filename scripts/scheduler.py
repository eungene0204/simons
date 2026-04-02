"""
Simons 데이터 스케줄러

[스케줄]
  00:00 KST — OHLCV 데이터 동기화 (매일)

※ 자동매매(장 개장/새로고침/마감)는 FastAPI 백엔드의 VirtualTrader가 직접 처리한다.
"""

import time
import subprocess
import sys
from datetime import datetime
import pytz

KST = pytz.timezone("Asia/Seoul")


def run_sync():
    """OHLCV 데이터 동기화 스크립트 실행."""
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} KST] 데이터 동기화 시작...")
    try:
        result = subprocess.run(
            [sys.executable, "scripts/sync_data.py"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} KST] 데이터 동기화 완료.")
        else:
            print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} KST] 데이터 동기화 실패 (exit {result.returncode})")
            print(result.stderr)
    except Exception as e:
        print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} KST] 데이터 동기화 오류: {e}")


def main():
    print("=== Simons 데이터 스케줄러 시작 ===")
    print(f"서버 시간: {datetime.now()}")
    print("역할: 자정 OHLCV 동기화 (자동매매는 FastAPI VirtualTrader 담당)")
    print()

    fired_today: set = set()

    while True:
        now = datetime.now(KST)
        date_str = now.strftime("%Y-%m-%d")
        h, m = now.hour, now.minute

        if h == 0 and m == 0:
            fired_today.clear()

        sync_key = f"{date_str}_sync"
        if h == 0 and m == 0 and sync_key not in fired_today:
            fired_today.add(sync_key)
            run_sync()

        time.sleep(60)


if __name__ == "__main__":
    main()
