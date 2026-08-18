"""
로컬 ↔ 프로덕션 OHLCV parquet 미러.

정본(source of truth)은 **프로덕션**이다. 로컬은 프로덕션을 pull 하여 항상 동일한
parquet을 유지한다. 양쪽이 각자 FDR/pykrx에서 독립적으로 받으면 깊은 과거(KIS 백필)·
보정(sanitize)·enrichment 타이밍 차이로 절대 동일해지지 않으므로, 반드시 rsync 미러로 맞춘다.

사용:
  python scripts/mirror_data.py            # pull: 프로덕션 → 로컬 (기본)
  python scripts/mirror_data.py --check    # 차이만 출력(전송 안 함, --dry-run)
  python scripts/mirror_data.py --push     # push: 로컬 → 프로덕션 (백필 반영 등, 주의해서)

환경변수(.env):
  DATA_MIRROR_REMOTE   예) root@137.220.41.38:/opt/simons   (필수, 로컬 전용 설정)
  DATA_MIRROR_SSH_KEY  예) ~/.ssh/vultr_simons              (선택, 없으면 기본 ssh 설정)

주의: DATA_MIRROR_REMOTE는 **로컬에서만** 설정한다. 프로덕션(정본)에 설정하면
자기 자신을 미러하려 하므로 절대 설정하지 않는다.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LOCAL_OHLCV = _REPO_ROOT / "data" / "ohlcv"
# 미러 대상 하위 경로(정본 기준 상대경로). 현재는 OHLCV parquet만 미러한다.
_REMOTE_SUBPATH = "data/ohlcv"
# rsync 무전송 중단(초)과 재시도. 스톨로 끊겨도(exit 10/12/30/35 — 소켓 I/O·프로토콜·타임아웃)
# 이미 옮긴 파일은 원자적으로 완성돼 있으므로(임시파일→rename, --partial 안 씀) 다시 돌리면
# 남은 파일만 이어간다. 큰 델타에서 한 번에 안 끝나는 일이 잦아 최대 _RSYNC_MAX_ATTEMPTS회.
_RSYNC_STALL_TIMEOUT_S = 300
_RSYNC_MAX_ATTEMPTS = 5
_RSYNC_RETRYABLE_EXIT_CODES = {10, 12, 30, 35}
_RSYNC_RETRY_DELAY_S = 15


def build_rsync_cmd(
    *,
    remote: str,
    ssh_key: str | None,
    push: bool,
    dry_run: bool,
    local_dir: Path = _LOCAL_OHLCV,
) -> list[str]:
    """rsync argv를 구성한다. 미러이므로 trailing slash로 디렉터리 내용만 동기화한다."""
    if not remote:
        raise ValueError("DATA_MIRROR_REMOTE가 설정되지 않았습니다.")

    # 스톨 방지: SSH 행으로 전송이 무기한 멈추는 사고 방지(2026-08-04, 스케줄러 pull이
    # 0바이트 임시파일에서 30시간 좀비). keepalive는 죽은 연결을 ~60초에 감지하고,
    # rsync --timeout은 연결이 살아 있어도 데이터가 그 시간 동안 안 흐르면 중단한다.
    # 120초는 큰 델타(수천 파일·1GB+)에서 정상 전송 중에도 걸렸다(2026-08-17 실측 4회
    # 'poll: timeout', 매번 수백 파일씩은 진행) — 300초로 늘리고 main()이 재시도한다.
    ssh_opts = "-o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4"
    ssh = f"ssh {ssh_opts}"
    if ssh_key:
        ssh = f"ssh -i {os.path.expanduser(ssh_key)} {ssh_opts}"

    local = f"{str(local_dir).rstrip('/')}/"
    remote_path = f"{remote.rstrip('/')}/{_REMOTE_SUBPATH}/"

    cmd = ["rsync", "-a", f"--timeout={_RSYNC_STALL_TIMEOUT_S}", "-e", ssh]
    if dry_run:
        cmd += ["--dry-run", "--itemize-changes"]
    if push:
        cmd += [local, remote_path]
    else:
        cmd += [remote_path, local]
    return cmd


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="로컬↔프로덕션 OHLCV parquet 미러 (정본=프로덕션)")
    parser.add_argument("--push", action="store_true", help="로컬 → 프로덕션 (기본은 pull)")
    parser.add_argument("--check", action="store_true", help="차이만 출력하고 전송하지 않음(dry-run)")
    args = parser.parse_args(argv)

    # 로컬 .env의 DATA_MIRROR_* 로드(컨테이너는 env_file 주입돼 no-op). 실행 시점에만 로드.
    load_dotenv(_REPO_ROOT / ".env")
    remote = os.environ.get("DATA_MIRROR_REMOTE", "").strip()
    ssh_key = os.environ.get("DATA_MIRROR_SSH_KEY", "").strip() or None
    if not remote:
        print("[mirror] DATA_MIRROR_REMOTE 미설정 — 미러를 건너뜁니다(로컬 .env에 설정 필요).")
        return 2

    _LOCAL_OHLCV.mkdir(parents=True, exist_ok=True)
    cmd = build_rsync_cmd(remote=remote, ssh_key=ssh_key, push=args.push, dry_run=args.check)
    direction = "로컬 → 프로덕션(push)" if args.push else "프로덕션 → 로컬(pull)"
    print(f"[mirror] {direction}{' [check]' if args.check else ''}: {remote}/{_REMOTE_SUBPATH}")
    return run_with_retries(cmd)


def run_with_retries(cmd: list[str], *, max_attempts: int = _RSYNC_MAX_ATTEMPTS,
                     delay_s: float = _RSYNC_RETRY_DELAY_S) -> int:
    """rsync를 돌리고, 스톨·네트워크 계열 종료코드면 이어서 재시도한다. 최종 종료코드 반환."""
    import time
    returncode = 1
    for attempt in range(1, max_attempts + 1):
        returncode = subprocess.run(cmd).returncode
        if returncode == 0:
            print(f"[mirror] 완료.{f' (재시도 {attempt - 1}회)' if attempt > 1 else ''}")
            return 0
        if returncode not in _RSYNC_RETRYABLE_EXIT_CODES or attempt == max_attempts:
            break
        print(f"[mirror] rsync exit {returncode} — {delay_s:.0f}초 후 재시도 ({attempt}/{max_attempts})")
        time.sleep(delay_s)
    print(f"[mirror] 실패 (rsync exit {returncode})")
    return returncode


if __name__ == "__main__":
    sys.exit(main())
