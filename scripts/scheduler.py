"""
Simons 데이터 + 주식 시장 스케줄러

[스케줄]
  00:00 KST        — OHLCV 데이터 동기화 (매일)
  09:00 KST        — 장 개장: auto 모드 계좌 자동 시작 (평일)
  09:05~15:25 KST  — 5분 간격 시세/시그널 새로고침 (평일)
  15:30 KST        — 장 마감: 실행 중인 계좌 일시정지 (평일)

[환경변수]
  APP_URL           — Next.js 서버 주소 (기본: http://localhost:3000)
  SCHEDULER_SECRET  — 스케줄러 API 인증 토큰 (선택)
"""

import time
import subprocess
import os
import sys
import urllib.request
import urllib.error
import json
from datetime import datetime
import pytz

APP_URL = os.environ.get("APP_URL", "http://localhost:3000")
SCHEDULER_SECRET = os.environ.get("SCHEDULER_SECRET", "")
REFRESH_INTERVAL_MIN = 5  # 장 중 새로고침 간격 (분)

KST = pytz.timezone("Asia/Seoul")


# ── 데이터 동기화 ─────────────────────────────────────────────────────────

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


# ── 스케줄러 API 호출 ─────────────────────────────────────────────────────

def call_scheduler_api(action: str):
    """POST /api/scheduler 호출."""
    url = f"{APP_URL}/api/scheduler"
    payload = json.dumps({"action": action}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if SCHEDULER_SECRET:
        headers["Authorization"] = f"Bearer {SCHEDULER_SECRET}"

    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            if action == "market-open":
                count = len(body.get("results", []))
                print(f"[{ts} KST] 장 개장 처리 완료 — {count}개 계좌")
            elif action == "market-refresh":
                count = len(body.get("results", []))
                print(f"[{ts} KST] 시세 새로고침 완료 — {count}개 계좌")
            elif action == "market-close":
                count = body.get("paused", 0)
                print(f"[{ts} KST] 장 마감 처리 완료 — {count}개 계좌 일시정지")
    except urllib.error.URLError as e:
        ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts} KST] 스케줄러 API 호출 실패 ({action}): {e}")
    except Exception as e:
        ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts} KST] 스케줄러 API 오류 ({action}): {e}")


# ── 메인 루프 ─────────────────────────────────────────────────────────────

def main():
    print("=== Simons 스케줄러 시작 ===")
    print(f"서버 시간: {datetime.now()}")
    print(f"APP_URL: {APP_URL}")
    print(f"새로고침 간격: {REFRESH_INTERVAL_MIN}분")
    print()

    fired_today: set = set()

    while True:
        now = datetime.now(KST)
        date_str = now.strftime("%Y-%m-%d")
        h, m = now.hour, now.minute
        weekday = now.weekday()  # 0=월 ~ 4=금, 5=토, 6=일

        # 자정에 fired_today 초기화
        if h == 0 and m == 0:
            fired_today.clear()

        # ── 00:00 KST: 데이터 동기화 (매일) ─────────────────────────────
        sync_key = f"{date_str}_sync"
        if h == 0 and m == 0 and sync_key not in fired_today:
            fired_today.add(sync_key)
            run_sync()

        if weekday < 5:  # 평일만
            # ── 09:00 KST: 장 개장 ───────────────────────────────────────
            open_key = f"{date_str}_market_open"
            if h == 9 and m == 0 and open_key not in fired_today:
                fired_today.add(open_key)
                print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')} KST] 장 개장 — auto 계좌 시작")
                call_scheduler_api("market-open")

            # ── 09:05~15:25 KST: 5분 간격 새로고침 ──────────────────────
            in_market_hours = (h == 9 and m >= 5) or (10 <= h <= 14) or (h == 15 and m < 30)
            if in_market_hours and m % REFRESH_INTERVAL_MIN == 0:
                refresh_key = f"{date_str}_{h:02d}{m:02d}_refresh"
                if refresh_key not in fired_today:
                    fired_today.add(refresh_key)
                    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')} KST] 시세 새로고침")
                    call_scheduler_api("market-refresh")

            # ── 15:30 KST: 장 마감 ───────────────────────────────────────
            close_key = f"{date_str}_market_close"
            if h == 15 and m == 30 and close_key not in fired_today:
                fired_today.add(close_key)
                print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')} KST] 장 마감 — 실행 중인 계좌 일시정지")
                call_scheduler_api("market-close")

        time.sleep(60)  # 1분마다 체크


if __name__ == "__main__":
    main()
