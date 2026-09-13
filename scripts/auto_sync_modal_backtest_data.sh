#!/usr/bin/env bash
# 일일 데이터 갱신 → Modal Volume 자동 동기화 감지기 (prod 박스 호스트 cron 전용).
#
# 스케줄러(KR 21:00 KST·US 07:00 KST)나 수동 백필이 /opt/simons/data 를 갱신해도
# Modal 워커가 읽는 Volume(simons-backtest-data)은 별도 복사본이라 자동 반영되지 않는다.
# 이 스크립트를 cron이 30분마다 돌려, 감시 대상(ohlcv/ohlcv-us/fundamentals/최상위 *.json)의
# 최신 mtime이 ① 지난 동기화 이후이고 ② 15분 이상 잠잠하면(갱신 진행 중 절단 방지)
# sync_modal_backtest_data.sh 를 실행한다. 변경 없으면 아무것도 안 한다.
#
# 설치(박스, 1회):  /etc/cron.d/simons-modal-sync 참고 — docs/deployment.md
#   */30 * * * * root flock -n /var/lock/simons-modal-sync.lock \
#     bash /opt/simons/scripts/auto_sync_modal_backtest_data.sh >> /var/log/simons-modal-sync.log 2>&1
set -euo pipefail

DATA_DIR="${1:-/opt/simons/data}"
STAMP="${STAMP:-/var/lib/simons-modal-sync.stamp}"
QUIESCE_S="${QUIESCE_S:-900}"          # 마지막 변경 후 이만큼 잠잠해야 동기화(쓰기 도중 절단 방지)
export MODAL_BIN="${MODAL_BIN:-/opt/modal-cli/bin/modal}"
SYNC="$(dirname "$0")/sync_modal_backtest_data.sh"

ts() { date "+%F %T"; }

# 최댓값은 awk로 구한다 — `sort | head -1`은 head가 먼저 종료하면 sort가 SIGPIPE(141)를
# 받고, pipefail 아래에서 스크립트 전체가 로그 한 줄 없이 죽는다(실제 사고).
newest=$(
  {
    find "$DATA_DIR/ohlcv" "$DATA_DIR/ohlcv-us" "$DATA_DIR/fundamentals" "$DATA_DIR/index" -type f -printf '%T@\n' 2>/dev/null
    find "$DATA_DIR" -maxdepth 1 -name '*.json' -not -name '*.progress.json' -type f -printf '%T@\n' 2>/dev/null
  } | awk '$1>max{max=$1} END{if(max=="")exit 1; printf "%d\n", max}'
) || { echo "[$(ts)] ERROR: 감시 대상 파일이 없음 ($DATA_DIR)"; exit 1; }

last=$(cat "$STAMP" 2>/dev/null || echo 0)
now=$(date +%s)

if [ "$newest" -le "$last" ]; then
  exit 0                                # 변경 없음 — 조용히 종료(로그 오염 방지)
fi
if [ $((now - newest)) -lt "$QUIESCE_S" ]; then
  echo "[$(ts)] 변경 감지됐지만 아직 쓰는 중(${QUIESCE_S}s 미경과) — 다음 주기로 미룸"
  exit 0
fi

echo "[$(ts)] 변경 감지(newest=$(date -d "@$newest" "+%F %T")) → Volume 동기화 시작"
if bash "$SYNC" "$DATA_DIR"; then
  echo "$newest" > "$STAMP"
  echo "[$(ts)] 동기화 완료 — stamp 갱신"
else
  echo "[$(ts)] ERROR: 동기화 실패 — stamp 미갱신(다음 주기 재시도)"
  exit 1
fi
