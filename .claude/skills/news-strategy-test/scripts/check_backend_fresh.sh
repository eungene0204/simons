#!/bin/bash
# 무인 실행(뉴스 12시·속설 13시)이 운영과 같은 코드로 해석하는지 확인한다(2026-11-26 사용자 결정: 뒤처졌으면 알림 후 그날 건너뛴다).
# 2026-11-25 사고: 8000번 백엔드가 v16.51로 떠 있어 v16.52(시장 지수 등락률, 11-24 배포) 문장이 '해석 단계에서 멈춤'으로 빠졌다 —
# 운영 결함이 아니라 옛 서버를 시험한 결과였다. 서버를 띄우거나 재시작하지 않는다(다른 세션의 요청을 끊는다).
# 사용: bash check_backend_fresh.sh   종료 코드 0=최신, 1=뒤처짐(이유 출력). git fetch 실패는 판정 없이 0(경고만).
REPO="/Users/eugene/nullalgo/simons"
cd "$REPO" || exit 0
if ! git fetch -q origin main 2>/dev/null; then
  echo "[경고] origin/main을 받지 못해 최신 여부를 확인하지 못했다"; exit 0
fi
# ① 로컬 checkout이 운영(origin/main)의 backend 변경을 아직 받지 않았다
behind=$(git rev-list --count HEAD..origin/main -- backend 2>/dev/null || echo 0)
if [ "${behind:-0}" -gt 0 ]; then
  echo "[중단] 로컬 checkout이 origin/main보다 backend 커밋 ${behind}개 뒤처졌다(git pull 후 백엔드 재시작 필요)"; exit 1
fi
# ② 백엔드가 마지막 backend 커밋보다 먼저 떴다(코드는 받았는데 재시작 안 함). --reload 서버는 스스로 다시 읽으므로 건너뛴다.
pid=$(lsof -tnP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | head -1)
[ -n "$pid" ] || exit 0   # 응답 여부는 check_servers.sh 소관
cmd=$(ps -o command= -p "$pid")
case "$cmd" in *--reload*) exit 0 ;; esac
started=$(LC_ALL=C date -j -f "%a %b %d %T %Y" "$(LC_ALL=C ps -o lstart= -p "$pid" | sed 's/  */ /g;s/^ //;s/ $//')" +%s 2>/dev/null) || exit 0
last=$(git log -1 --format=%ct HEAD -- backend)
if [ -n "$started" ] && [ -n "$last" ] && [ "$started" -lt "$last" ]; then
  echo "[중단] 8000번 백엔드(PID $pid)가 $(date -r "$started" '+%m-%d %H:%M')에 떠서 마지막 backend 커밋($(date -r "$last" '+%m-%d %H:%M'))을 반영하지 않았다(재시작 필요)"; exit 1
fi
exit 0
