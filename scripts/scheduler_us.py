"""
미국 주식 데이터 스케줄러 — 한국 스케줄러(scripts/scheduler.py)와 **별도 프로세스**.

[역할 — 환경에 따라 분기 (한국 scheduler.py와 같은 방식)]
  · 정본(프로덕션, DATA_MIRROR_REMOTE 미설정): 아래 스케줄로 yfinance/EDGAR 수집
  · 미러(로컬, DATA_MIRROR_REMOTE 설정): 시작 시 + 매일 07:15 KST(정본 07:00 증분 완료
      여유 후) 프로덕션 data/ohlcv-us를 pull. 로컬이 독립 수집하면 EDGAR 재적용·소급
      수정 타이밍 차이로 정본과 어긋나므로 pull만 한다.

[스케줄 — 정본 모드]
  · 매일 07:00 KST — 시세 증분 sync (backfill_us_stocks.py --update, 수 분)
      미국 장 마감(16:00 ET)은 서머타임에 따라 05:00(EDT)/06:00(EST) KST다. 겨울 마감
      뒤에도 1시간 여유를 두고, 한국장 개장(09:00) 전에 끝나도록 07:00으로 잡는다.
      데이터가 이미 최신이면(주말·미국 휴장) 건너뛴다. 재무 컬럼은 증분이 갱신하지
      않는다 — 아래 전량 재수집이 담당한다.
  · 12주마다 일요일 09:00 KST — 전량 재수집 (--force, ~9시간)
      분기 재무·분할 소급 조정·15개월(STALE_CAP) 만료를 정식 반영한다. 일요일은 한·미
      모두 휴장이라 그날 새로 들어올 시세가 없다. 마지막 실행일은 마커 파일로 기억하고
      **성공했을 때만** 갱신해, 실패한 주는 12주를 통째로 미루지 않고 다음 일요일에
      재시도한다.

[왜 한국 스케줄러와 한 프로세스에 두지 않는가]
  _run()의 subprocess.run에는 타임아웃이 없다. 실제로 2026-08-04에 한국 스케줄러의
  rsync pull이 0바이트 임시파일에서 30시간 좀비가 된 적이 있다(scripts/mirror_data.py의
  스톨 방지 주석). 한 프로세스에 두면 미국 쪽 수집이 소켓에서 멈출 때 한국 21:00 sync도
  함께 죽는다. 프로덕션 compose에서도 scheduler(한국)와 scheduler-us(이 파일)는 별도
  서비스로 둔다.

[최초 시딩]
  파케이(data/ohlcv-us)가 없으면 아무것도 하지 않는다. 5,947종목 전량 백필(~9시간)은
  수동으로 돌린다: python scripts/backfill_us_stocks.py
  (프로덕션 최초 시딩은 2026-08-31 로컬 파케이 rsync push로 완료 — 전량 재수집 마커 포함)

실행: python scripts/scheduler_us.py
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytz
from dotenv import load_dotenv

KST = pytz.timezone("Asia/Seoul")

_REPO_ROOT = Path(__file__).resolve().parents[1]

# 시세 증분 sync 시각 (미 마감 이후·한국장 개장 이전 — 상단 docstring 참고).
_SYNC_HOUR, _SYNC_MINUTE = 7, 0
# 미러(로컬) pull 시각 — 정본 07:00 증분(수 분)이 끝났을 여유를 두고 15분 뒤.
_MIRROR_PULL_HOUR, _MIRROR_PULL_MINUTE = 7, 15

# 전량 재수집(분기 재무 갱신) — 일요일 09:00 KST 시작, 12주 간격.
# 12주(84일)는 일요일 정렬로 실행일이 밀려도 분기(약 13주)마다 한 번은 돌게 하는 하한이다.
_FULL_HOUR, _FULL_MINUTE = 9, 0
_FULL_REFRESH_MIN_DAYS = 84

# 데이터 신선도 판단용 대표 종목(애플) parquet.
_REP_PARQUET = _REPO_ROOT / "data" / "ohlcv-us" / "AAPL.parquet"
# 마지막 전량 재수집 날짜 마커(YYYY-MM-DD).
_FULL_MARKER = _REPO_ROOT / "data" / "ohlcv-us" / ".last_full_refresh"


def _is_mirror() -> bool:
    """미러 모드(로컬) 여부. DATA_MIRROR_REMOTE가 설정돼 있으면 프로덕션을 pull 한다."""
    return bool(os.environ.get("DATA_MIRROR_REMOTE", "").strip())


def _ts() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def _run(label: str, cmd: list[str], *, stream: bool = False) -> int:
    """명령을 실행하고 종료 코드를 반환한다(예외는 1).

    stream=True면 자식 출력을 그대로 흘려보낸다 — 9시간짜리 전량 재수집을 버퍼에 가둬
    두면 끝날 때까지 살아 있는지 알 수 없다.
    """
    print(f"[{_ts()} KST] {label} 시작...", flush=True)
    try:
        if stream:
            returncode = subprocess.run(cmd).returncode
        else:
            result = subprocess.run(cmd, capture_output=True, text=True)
            returncode = result.returncode
            if returncode != 0:
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr)
        if returncode == 0:
            print(f"[{_ts()} KST] {label} 완료.", flush=True)
        else:
            print(f"[{_ts()} KST] {label} 실패 (exit {returncode})", flush=True)
        return returncode
    except Exception as e:
        print(f"[{_ts()} KST] {label} 오류: {e}", flush=True)
        return 1


def run_update() -> int:
    """미러 모드면 프로덕션 pull, 정본 모드면 시세 증분 sync(재무 컬럼은 건드리지 않는다).

    정본 모드는 개별주 → ETF 순서로 돈다. ETF 증분(backfill_us_etf.py)은 파케이 없는
    티커를 건너뛰므로 ETF 시딩 전에도 안전하다.
    """
    if _is_mirror():
        return _run("프로덕션 미국 데이터 pull",
                    [sys.executable, "scripts/mirror_data.py", "--us"])
    rc_stocks = _run("미국 시세 증분 동기화",
                     [sys.executable, "scripts/backfill_us_stocks.py", "--update"])
    rc_etf = _run("미국 ETF 시세 증분 동기화",
                  [sys.executable, "scripts/backfill_us_etf.py", "--update"])
    return rc_stocks if rc_stocks != 0 else rc_etf


def run_full_refresh() -> int:
    """전량 재수집 — 분기 재무·분할·15개월 만료를 정식 반영한다(~9시간).

    자식도 -u(무버퍼)로 띄운다 — 로그가 파이프면 자식 stdout이 블록 버퍼링돼, 9시간 내내
    한 줄도 안 보이다가 끝나서야 쏟아진다(진행 중인지 멈춘 건지 구분할 수 없다).
    """
    rc = _run("미국 데이터 전량 재수집(분기 재무)",
              [sys.executable, "-u", "scripts/backfill_us_stocks.py", "--force"], stream=True)
    if rc == 0:
        # 전량 재수집은 파케이를 야후 데이터로 통째로 다시 쓰므로 EDGAR 재무 이력
        # (2009~, backfill_us_fundamentals_edgar.py)이 사라진다 — 반드시 재적용한다.
        # 재적용이 실패하면 rc에 반영해 마커를 막는다(재무 이력이 잘린 채 12주를
        # 방치하는 것이 재시도 비용보다 나쁘다).
        rc = _run("EDGAR 재무 이력 재적용",
                  [sys.executable, "-u", "scripts/backfill_us_fundamentals_edgar.py",
                   "--force"], stream=True)
    # 지수 구성종목(S&P500·나스닥100·다우30)은 분기 리밸런싱 주기로만 바뀐다 — 같은
    # 주기로 갱신한다. 실패해도 rc에 섞지 않는다: 위키/API 일시 장애 때문에 마커가
    # 안 찍혀 9시간짜리 전량 재수집을 다음 주에 통째로 다시 돌리게 하지 않는다.
    _run("미국 지수 구성종목 갱신",
         [sys.executable, "scripts/backfill_us_index_membership.py"])
    return rc


# ───────────────────────────── 시세 신선도 (일일 증분) ─────────────────────────────

def _newest_data_date():
    """대표 종목 parquet의 마지막 날짜. 파일이 없거나 읽기 실패 시 None(=미시딩)."""
    try:
        df = pd.read_parquet(_REP_PARQUET, columns=["date"])
    except Exception:
        return None
    if df.empty:
        return None
    return pd.Timestamp(df["date"].iloc[-1]).date()


def _last_expected_trading_day(now: datetime):
    """이 시점까지 적재했어야 할 가장 최근 미국 세션 날짜(ET 기준, 휴장 미고려).

    07:00 KST sync가 적재하는 것은 그날 새벽에 끝난 세션, 즉 ET 기준 **전날** 세션이다
    (07:00 KST = 전일 17:00 EDT / 18:00 EST — 두 서머타임 체제 모두 마감 이후).
    오늘 sync 시각 전이면 하루 더 물러난다. 주말은 금요일로 되돌린다.
    """
    d = now.date() - timedelta(days=1)
    if (now.hour, now.minute) < (_SYNC_HOUR, _SYNC_MINUTE):
        d -= timedelta(days=1)
    while d.weekday() >= 5:  # 5=토, 6=일
        d -= timedelta(days=1)
    return d


def _is_data_stale(now: datetime = None) -> bool:
    """OHLCV가 기대 세션보다 밀려 있으면 True. 주말·미국 휴장 다음 날은 자연히 False가
    되어 증분 sync를 건너뛴다. 미시딩(파일 없음)이면 False — 최초 시딩은 이 스케줄러의
    몫이 아니다(5,947종목 전량 백필 ~9시간은 수동으로 돌린다)."""
    now = now or datetime.now(KST)
    newest = _newest_data_date()
    if newest is None:
        return False
    return newest < _last_expected_trading_day(now)


# ─────────────────────────── 전량 재수집 기한 (분기 재무) ───────────────────────────

def _last_full_refresh_date():
    """마커 파일의 마지막 전량 재수집 날짜. 없거나 못 읽으면 None."""
    try:
        return datetime.strptime(_FULL_MARKER.read_text().strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _mark_full_refresh(d) -> None:
    _FULL_MARKER.write_text(d.isoformat())


def _ensure_marker(today) -> None:
    """파케이는 있는데 마커가 없으면(방금 시딩·백필된 상태) 오늘로 초기화한다.

    마커가 없으면 기한 계산의 기준일이 없어 전량 재수집이 영영 트리거되지 않는다.
    시딩이 이 스케줄러를 띄운 **뒤에** 끝날 수도 있으므로 시작 시 한 번이 아니라
    매일 확인한다.
    """
    if _newest_data_date() is not None and _last_full_refresh_date() is None:
        _mark_full_refresh(today)
        print(f"[{_ts()} KST] 전량 재수집 기준일을 오늘({today})로 초기화했습니다 "
              f"— 다음 전량 재수집은 {_FULL_REFRESH_MIN_DAYS // 7}주 뒤 일요일입니다.")


def _is_full_refresh_due(now: datetime) -> bool:
    """일요일 09:00 KST 이후이고 마지막 전량 재수집으로부터 12주가 지났으면 True.

    마커가 없으면 False — 미시딩이거나 기준일 초기화 전이므로 돌리지 않는다.
    """
    if now.weekday() != 6 or (now.hour, now.minute) < (_FULL_HOUR, _FULL_MINUTE):
        return False
    last = _last_full_refresh_date()
    if last is None:
        return False
    return (now.date() - last).days >= _FULL_REFRESH_MIN_DAYS


def main():
    # 로그가 파일·파이프로 나가면 stdout이 블록 버퍼링된다 — 하루에 몇 줄만 찍는
    # 스케줄러가 그러면 몇 시간째 아무것도 안 보인다. 줄 단위로 흘려보낸다.
    sys.stdout.reconfigure(line_buffering=True)
    # 로컬 .env 로드는 실행 시점에만(import 부작용으로 전역 env를 오염시키지 않도록).
    load_dotenv(_REPO_ROOT / ".env")
    mirror = _is_mirror()
    role = "미러(프로덕션 pull)" if mirror else "정본(yfinance/EDGAR 수집)"
    print("=== 미국 데이터 스케줄러 시작 ===")
    print(f"서버 시간: {datetime.now()}")
    print(f"역할: {role}")
    if mirror:
        print(f"스케줄: 시작 시 + 매일 {_MIRROR_PULL_HOUR:02d}:{_MIRROR_PULL_MINUTE:02d} KST "
              "프로덕션 data/ohlcv-us pull")
    else:
        print(f"스케줄: 매일 {_SYNC_HOUR:02d}:{_SYNC_MINUTE:02d} KST 시세 증분 · "
              f"{_FULL_REFRESH_MIN_DAYS // 7}주마다 일요일 "
              f"{_FULL_HOUR:02d}:{_FULL_MINUTE:02d} KST 전량 재수집(분기 재무)")
    print()

    now = datetime.now(KST)
    if not mirror:
        if _newest_data_date() is None:
            print(f"[{_ts()} KST] 미국 파케이 없음 — 시딩 전까지 대기합니다 "
                  "(시딩: python scripts/backfill_us_stocks.py).")
        _ensure_marker(now.date())

    # 시작 시 정합:
    #  · 미러: 항상 pull(차이만 전송, 저렴)로 프로덕션과 즉시 동일하게 맞춘다. 마커
    #    (.last_full_refresh)도 pull에 실려 오므로 여기서 만들지 않는다.
    #  · 정본: 기대 세션보다 밀렸을 때만 캐치업 sync. 오늘분을 방금 처리했으면
    #    last_sync_date를 오늘로 찍어, 아래 반복 트리거가 같은 날 다시 실행하지 않게 한다.
    last_sync_date = None
    last_full_date = None
    if mirror:
        print(f"[{_ts()} KST] 미러 모드 — 시작 시 프로덕션 데이터를 pull 합니다.")
        run_update()
        last_sync_date = now.strftime("%Y-%m-%d")
    elif _is_data_stale(now):
        print(f"[{_ts()} KST] 데이터가 밀려 있어 시작 시 캐치업 동기화를 실행합니다.")
        run_update()
        last_sync_date = now.strftime("%Y-%m-%d")

    # 정본은 07:00 증분, 미러는 07:15(정본 증분이 끝났을 여유를 둔 뒤) — 하루 1회.
    target = (_MIRROR_PULL_HOUR, _MIRROR_PULL_MINUTE) if mirror else (_SYNC_HOUR, _SYNC_MINUTE)

    while True:
        now = datetime.now(KST)
        today = now.strftime("%Y-%m-%d")

        # 시세 증분/pull — 정본은 신선도 검사가 주말·미국 휴장을 자연히 걸러 주므로(이미
        # 최신이면 False) 요일 계산 없이 매일 검사만 한다. 미러는 pull이 차이만 전송하므로
        # 검사 없이 매일 돈다. 정확히 그 '분'에 의존하지 않으므로 절전에서 늦게 깨어나도
        # 그 즉시 실행된다.
        if today != last_sync_date and (now.hour, now.minute) >= target:
            last_sync_date = today
            if mirror:
                run_update()
            else:
                _ensure_marker(now.date())
                if _is_data_stale(now):
                    run_update()

        # 전량 재수집(정본 전용) — 마커가 실행일을 기억하므로 절전·재시작으로 밀려도 다음
        # 일요일에 이어서 잡는다. 마커는 성공했을 때만 갱신하고, 같은 날 재진입은
        # last_full_date로 막는다(실패한 주가 12주를 통째로 미루지 않게).
        if not mirror and today != last_full_date and _is_full_refresh_due(now):
            last_full_date = today
            if run_full_refresh() == 0:
                _mark_full_refresh(now.date())

        time.sleep(60)


if __name__ == "__main__":
    main()
