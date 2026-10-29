#!/bin/bash
# 뉴스 전략 하나를 로컬 앱에서 백테스트하고 결과 사진·해설을 남긴다(영상 없음, X에 올리지 않는다).
# 사용: bash run_test.sh <전략 폴더>       폴더에 spec.json이 있어야 한다:
#   {"prompt": "<문장>", "answers": ["<칩 글자>", ...], "post_name": "<전략 이름>",
#    "news": {"title", "link", "published"}, "why": "<뉴스와 전략의 연결 한 줄>"}
# 출력(같은 폴더): result.json(해석 요약·지표·로그), shot_*.png(결과 사진), note.txt(해설), trades.txt(매매 기록 탭), run.log
# 녹화·캡처 스크립트는 x-backtest-post 스킬의 것을 그대로 쓴다(복사본을 두지 않는다).
set -euo pipefail
DIR="$(cd "$1" && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
XB="$HERE/../../x-backtest-post/scripts"
REPO="$(cd "$HERE/../../../.." && pwd)"
PW="$HOME/nullstock-cf/.pw"
[ -f "$DIR/spec.json" ] || { echo "[중단] $DIR/spec.json 이 없다"; exit 1; }

bash "$HERE/check_servers.sh" || exit 1
if [ ! -d "$PW/node_modules/playwright" ]; then
  mkdir -p "$PW" && (cd "$PW" && echo '{"name":"nullstock-pw","private":true}' > package.json && npm i playwright >/dev/null 2>&1 && npx playwright install chromium >/dev/null 2>&1)
fi

cd "$DIR"
rm -f marks.jsonl result.json shot_*.png note.txt ai.png
[ -e node_modules ] || ln -s "$PW/node_modules" node_modules
cp "$XB"/{browser_server,studio_lib,studio_record,capture}.mjs .

# 녹화 없는 브라우저(browser_server)로 표준 흐름을 돈다 — 전략마다 새로 띄워 이전 대화가 이어지지 않게 한다
# 같은 계정을 다른 세션(영상 녹화 등)이 동시에 쓰면 활성 대화가 서로 덮인다(10-29 실측: 남의 '현대자동차 관련주' 대화로 화면이 바뀜)
export GUEST_ID="${GUEST_ID:-guest_5312}"
export GUEST_PW="$(cd "$REPO" && python3 -c "import json,os;print([x for x in json.load(open('guest-accounts.local.json')) if x['guestId']==os.environ['GUEST_ID']][0]['password'])")"
# 앞 실행의 브라우저가 아직 9222를 쥐고 닫히는 중이면 새 실행이 그 브라우저에 붙어 죽는다(10-29 실측) — 포트가 빌 때까지 기다린다
for i in $(seq 1 30); do lsof -iTCP:9222 -sTCP:LISTEN >/dev/null 2>&1 || break; sleep 1; done
lsof -iTCP:9222 -sTCP:LISTEN >/dev/null 2>&1 && { echo "[중단] 9222 포트를 다른 브라우저가 쓰고 있다(녹화 세션?)"; exit 1; }
(nohup node browser_server.mjs > server.log 2>&1 &)
trap 'pkill -TERM -f "node browser_server.mjs" || true; rm -f "$DIR"/{browser_server,studio_lib,studio_record,capture}.mjs "$DIR/node_modules"' EXIT
for i in $(seq 1 60); do grep -q "^ready" server.log 2>/dev/null && break; sleep 1; done
grep -q "^ready" server.log || { echo "[중단] 브라우저가 안 떴다"; cat server.log; exit 1; }

node studio_record.mjs spec.json 2>&1 | tee run.log
node capture.mjs shot 2>&1 | tee -a run.log
python3 "$HERE/make_note.py" "$DIR" >/dev/null
rm -f marks.jsonl cursor.json server.log ai.png   # ai.png는 shot_i_ai.png와 같은 카드
echo "[완료] $DIR"
