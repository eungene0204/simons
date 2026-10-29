#!/bin/bash
# 앱 서버가 실제로 응답하는지 두 서버에 직접 요청해 확인한다(포트 점유를 보는 lsof는 자동 실행 환경에서 명령이 안 잡혀 오판했다 — 2026-10-29).
# 사용: bash check_servers.sh   종료 코드 0=둘 다 응답, 1=하나라도 아님(어느 쪽인지 출력).
ok=0
code() { curl -s -o /dev/null -w "%{http_code}" -m 8 "$1" 2>/dev/null; }
front="$(code http://localhost:3000/)"
back="$(code http://localhost:8000/docs)"   # FastAPI 기본 문서 — 백엔드에 /health가 없다
[ "$front" = "200" ] || { echo "[중단] 프론트(3000)가 응답하지 않는다 (HTTP $front)"; ok=1; }
[ "$back" = "200" ] || { echo "[중단] 백엔드(8000)가 응답하지 않는다 (HTTP $back)"; ok=1; }
exit $ok
