#!/bin/bash
# 홍보 CF 한 번에 만들기: 녹화 브라우저 → 백테스트(studio_record) → 검증·모의투자(cf_tail) → 편집·믹스(cf_build).
# 사용: GUEST_PW=<비밀번호> bash cf_run.sh <작업 폴더> <spec.json> [--demo-quotes]
#   spec.json: studio_record.mjs 명세 + "accountName"(cf_tail). 예: cf_spec.example.json
#   --demo-quotes: 장이 닫혀 있을 때 시세 움직임을 연출한다(영상에 '시연용 연출 화면' 표기). 없으면 실제 시세로 찍고 표기를 뺀다.
# 사전: OpenRouter 한도가 남아 있어야 한다(소진되면 9B로 넘어가 해석이 수 분 걸리거나 끊긴다 — 09:00 KST 초기화).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; SK="$HERE/.."
W="$1"; SPEC="$2"; DEMO="${3:-}"
[ -n "${GUEST_PW:-}" ] || { echo "[중단] GUEST_PW가 없다"; exit 1; }
[ -e "$W/node_modules" ] || { echo "[중단] $W/node_modules(playwright)가 없다 — SKILL.md ② 참고"; exit 1; }
cp "$SK"/{studio_lib,studio_record,studio_step}.mjs "$HERE"/{cf_server,cf_tail}.mjs "$W"/
cp "$SPEC" "$W/spec.json"
cd "$W"
rm -rf frames marks.jsonl cursor.json
# 연출 시세로 찍었는지 녹화 폴더에 남긴다 — cf2_build.py가 이 표시를 보고 가상계좌 장면에 '시연용 연출 화면'을 얹는다
if [ "$DEMO" = "--demo-quotes" ]; then export DEMO_LIVE_QUOTES=1; NOTE=""; touch demo_quotes.flag; else NOTE="--no-demo-note"; rm -f demo_quotes.flag; fi
(nohup node cf_server.mjs > server.log 2>&1 &)
for i in $(seq 1 30); do grep -q ready server.log 2>/dev/null && break; sleep 2; done
grep -q ready server.log || { cat server.log; exit 1; }
trap 'pkill -TERM -f "node cf_server.mjs" || true' EXIT
node studio_record.mjs spec.json
node cf_tail.mjs spec.json
pkill -TERM -f "node cf_server.mjs"; sleep 5; trap - EXIT
echo "── 해석 요약(문장과 같은지 확인) ──"; python3 -c "import json;d=json.load(open('result.json'));print(d['summary']);print(d['metrics'])"
uv run --project "$SK/../../../.." --with numpy python "$HERE/cf_build.py" . . nullstock_cf.mp4 $NOTE
ffmpeg -v error -y -i nullstock_cf.mp4 -vf "fps=1,scale=480:-1,tile=8x8" -frames:v 1 cf_sheet.png
echo "완성: $W/nullstock_cf.mp4 · 검수 시트: $W/cf_sheet.png"
