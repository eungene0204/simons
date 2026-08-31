#!/usr/bin/env bash
# 백테스트 데이터 → Modal Volume(simons-backtest-data) 동기화.
#
# 데이터 정본은 prod 박스(/opt/simons/data)이므로 **박스에서 실행**한다.
# 일일 데이터 갱신(sync_data.py) 뒤에도 다시 실행해야 Modal 워커가 새 데이터를 본다.
#
# 사용:  bash scripts/sync_modal_backtest_data.sh [DATA_DIR]
# 전제:  modal CLI 인증(MODAL_TOKEN_ID/MODAL_TOKEN_SECRET env 또는 ~/.modal.toml)
#
# 올리는 것: 백테스트 엔진이 읽는 항목만.
#   ohlcv/ ohlcv-us/ fundamentals/ 그리고 최상위 *.json 메타(종목·유니버스·상폐 등)
# 제외: advisor-learning/(코치), cache/(런타임 캐시), training_data_v3.parquet(AI 학습),
#       *.progress.json(백필 진행 상태)
set -euo pipefail

DATA_DIR="${1:-/opt/simons/data}"
VOL="simons-backtest-data"
MODAL="${MODAL_BIN:-modal}"

if [ ! -d "$DATA_DIR/ohlcv" ]; then
  echo "ERROR: $DATA_DIR/ohlcv 가 없습니다 — DATA_DIR 확인" >&2
  exit 1
fi

echo "[SYNC] $DATA_DIR → modal volume $VOL"

for dir in ohlcv ohlcv-us fundamentals; do
  if [ -d "$DATA_DIR/$dir" ]; then
    echo "[SYNC] dir $dir ($(du -sh "$DATA_DIR/$dir" | cut -f1))"
    "$MODAL" volume put --force "$VOL" "$DATA_DIR/$dir" "/$dir"
  else
    echo "[SYNC] skip $dir (없음)"
  fi
done

for f in "$DATA_DIR"/*.json; do
  base="$(basename "$f")"
  case "$base" in
    *.progress.json) continue ;;
  esac
  "$MODAL" volume put --force "$VOL" "$f" "/$base" >/dev/null
  echo "[SYNC] json $base"
done

echo "[SYNC] 완료"
