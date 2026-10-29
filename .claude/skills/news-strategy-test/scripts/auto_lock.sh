# 매일 자동 작업(12:00 뉴스 전략·13:00 속설 게시)이 같은 데모 계정·9222 포트를 동시에 쓰지 않게 하는 잠금.
# 사용: source auto_lock.sh; acquire_auto_lock <이름> || exit   — 최대 90분 기다리고, 끝나면 자동으로 푼다.
AUTO_LOCK="$HOME/nullstock-cf/.auto.lock"
acquire_auto_lock() {
  for i in $(seq 1 90); do
    if mkdir "$AUTO_LOCK" 2>/dev/null; then
      echo "$1 $$" > "$AUTO_LOCK/owner"; trap 'rm -rf "$AUTO_LOCK"' EXIT; return 0
    fi
    # 주인이 죽은 잠금은 치운다
    pid="$(awk '{print $2}' "$AUTO_LOCK/owner" 2>/dev/null)"
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then rm -rf "$AUTO_LOCK"; continue; fi
    echo "[대기] $(cat "$AUTO_LOCK/owner" 2>/dev/null) 작업이 잠금을 쥐고 있다 (${i}분)"; sleep 60
  done
  echo "[중단] 90분 기다려도 잠금이 안 풀렸다"; return 1
}
