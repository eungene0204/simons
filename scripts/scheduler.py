"""
Simons 데이터 스케줄러

[역할 — 환경에 따라 분기]
  · 정본(프로덕션, DATA_MIRROR_REMOTE 미설정):
      21:00 KST 매일 FDR/KIS 권위 sync, 시작 시 밀렸으면 캐치업 sync
  · 미러(로컬, DATA_MIRROR_REMOTE 설정):
      시작 시 + 매일 21:15 KST(프로덕션 sync 완료 여유 확보 후) 프로덕션 parquet을 pull
      하여 정본과 항상 동일하게 유지
      (로컬이 독립적으로 FDR sync 하면 깊은 과거·보정 차이로 정본과 어긋나므로 pull만 한다)

※ 자동매매(장 개장/새로고침/마감)는 FastAPI 백엔드의 VirtualTrader가 직접 처리한다.
"""

import os
import time
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import pytz
from dotenv import load_dotenv

KST = pytz.timezone("Asia/Seoul")

# 정본 sync 시각 — 장 마감(15:30 KST) 이후 당일 시세가 FDR/KIS에 정착할 시간을 넉넉히
# 두고 21:00으로 잡는다. 미러 pull은 정본 sync가 끝났을 여유(15분)를 두고 그 직후 실행한다.
_SYNC_HOUR, _SYNC_MINUTE = 21, 0
_MIRROR_PULL_HOUR, _MIRROR_PULL_MINUTE = 21, 15

# 데이터 신선도 판단용 대표 종목(삼성전자) parquet.
_REP_PARQUET = Path(__file__).resolve().parents[1] / "data" / "ohlcv" / "005930.parquet"


def _is_mirror() -> bool:
    """미러 모드(로컬) 여부. DATA_MIRROR_REMOTE가 설정돼 있으면 프로덕션을 pull 한다."""
    return bool(os.environ.get("DATA_MIRROR_REMOTE", "").strip())


def _ts() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def _run(label: str, cmd: list[str]) -> None:
    print(f"[{_ts()} KST] {label} 시작...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[{_ts()} KST] {label} 완료.")
        else:
            print(f"[{_ts()} KST] {label} 실패 (exit {result.returncode})")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
    except Exception as e:
        print(f"[{_ts()} KST] {label} 오류: {e}")


def run_update():
    """미러 모드면 프로덕션 pull, 정본 모드면 FDR/KIS sync."""
    if _is_mirror():
        _run("프로덕션 데이터 pull", [sys.executable, "scripts/mirror_data.py"])
    else:
        _run("데이터 동기화", [sys.executable, "scripts/sync_data.py"])


def _newest_data_date():
    """대표 종목 parquet의 마지막(가장 최근) 날짜. 파일이 없거나 읽기 실패 시 None."""
    try:
        df = pd.read_parquet(_REP_PARQUET, columns=["date"])
    except Exception:
        return None
    if df.empty:
        return None
    return pd.Timestamp(df["date"].iloc[-1]).date()


def _last_expected_trading_day(now: datetime):
    """이 시점까지 sync가 완료됐어야 할 가장 최근 거래일(근사). 공휴일은 고려하지 않는다.

    21:00 동기화는 '당일 종가'까지 적재한다(장 마감 15:30 이후 시세가 정착하는 21:00에
    당일 데이터를 받는다) — 00:00 동기화가 '직전 거래일'을 기대하던 것과 다르다. 오늘이
    평일이고 아직 오늘의 sync 시각(21:00)을 지나지 않았다면 데이터는 아직 어제 것이 최신
    이어도 정상이므로, 그 경우에만 하루 전으로 물러난다. 공휴일이 끼면 실제보다 하루 더
    최신을 기대할 수 있으나, 그 경우 캐치업이 한 번 더 도는 것뿐이라 무해하다.
    """
    d = now.date()
    before_today_sync = (now.hour, now.minute) < (_SYNC_HOUR, _SYNC_MINUTE)
    if before_today_sync or d.weekday() >= 5:  # 5=토, 6=일
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _is_data_stale(now: datetime = None) -> bool:
    """로컬 OHLCV가 기대 거래일(`_last_expected_trading_day`)보다 밀려 있으면 True.
    데이터가 없으면 True(받아야 함)."""
    now = now or datetime.now(KST)
    newest = _newest_data_date()
    if newest is None:
        return True
    return newest < _last_expected_trading_day(now)


def main():
    # 로컬 .env 로드는 실행 시점에만(import 부작용으로 전역 env를 오염시키지 않도록).
    # 컨테이너는 env_file로 주입되므로 .env가 없어도 무해(no-op).
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    mirror = _is_mirror()
    role = "미러(프로덕션 pull)" if mirror else "정본(FDR/KIS sync)"
    print("=== Simons 데이터 스케줄러 시작 ===")
    print(f"서버 시간: {datetime.now()}")
    print(f"역할: {role} + 시작 시 정합 (자동매매는 FastAPI VirtualTrader 담당)")
    print()

    # 시작 시 정합:
    #  · 미러 모드: 항상 pull(차이만 전송, 저렴)로 프로덕션과 즉시 동일하게 맞춘다.
    #  · 정본 모드: 직전 기대 거래일보다 밀렸을 때만 캐치업 sync(무거운 작업이라 게이트).
    # 시작 시 이미 오늘분을 처리했으면 last_sync_date를 오늘로 찍어, 아래 반복 트리거가
    # 같은 날 target 시각을 다시 만났을 때 중복 실행하지 않게 한다.
    last_sync_date = None
    if mirror:
        print(f"[{_ts()} KST] 미러 모드 — 시작 시 프로덕션 데이터를 pull 합니다.")
        run_update()
        last_sync_date = datetime.now(KST).strftime("%Y-%m-%d")
    elif _is_data_stale():
        print(f"[{_ts()} KST] 데이터가 밀려 있어 시작 시 캐치업 동기화를 실행합니다.")
        run_update()
        last_sync_date = datetime.now(KST).strftime("%Y-%m-%d")

    # 정본은 21:00, 미러는 21:15(정본 sync가 끝났을 여유를 둔 뒤) — 하루 1회.
    target_hour, target_minute = (
        (_MIRROR_PULL_HOUR, _MIRROR_PULL_MINUTE) if mirror else (_SYNC_HOUR, _SYNC_MINUTE)
    )

    while True:
        now = datetime.now(KST)
        today = now.strftime("%Y-%m-%d")
        # 오늘 아직 안 돌았고 target 시각을 지났으면 실행. 정확히 그 '분'에 의존하지
        # 않으므로 절전에서 늦게 깨어나도(예: target 이후 아무 때나) 그 즉시 실행된다.
        if today != last_sync_date and (now.hour, now.minute) >= (target_hour, target_minute):
            last_sync_date = today
            run_update()
        time.sleep(60)


if __name__ == "__main__":
    main()
