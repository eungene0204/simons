#!/bin/bash
# 전략 생성 영상 한 번에 만들기(비게시 표준 워크플로, 2026-10-19). 같은 spec이면 같은 모양이 나온다.
# 사용: bash studio_make.sh <slug>
#   사전: ~/nullstock-cf/<slug>/spec.json
#     {"prompt": "<문장 그대로>", "answers": ["<칩 글자>", ...], "post_name": "<글 첫 줄에 쓸 전략 이름>", "aiShot": "ai.png"}
#   선택: ~/nullstock-cf/<slug>/meta.json (생략하면 기본값 — make_plan.py with_defaults)
# 하는 일: 앱 서버 확인 → 녹화(studio_record) → 편집 계획·카드·렌더·BGM·검수(studio_build) → 게시용 해석 글(make_post)
#          → ~/nullstock-cf/<slug>/ 에 final.mp4·post1.txt 등 저장 → 글을 클립보드에 복사 → 폴더 열기. X에는 올리지 않는다.
set -euo pipefail
SLUG="$1"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
OUT="$HOME/nullstock-cf/$SLUG"
WORK="$HOME/nullstock-cf/.work/$SLUG"
PW="$HOME/nullstock-cf/.pw"
[ -f "$OUT/spec.json" ] || { echo "[중단] $OUT/spec.json 이 없다"; exit 1; }

# 1) 앱 서버 — 프론트(3000)·백엔드(8000)가 떠 있어야 한다(스킬은 서버를 띄우지 않는다)
bash "$HERE/../../news-strategy-test/scripts/check_servers.sh" || exit 1

# 2) Playwright(저장소 의존성은 건드리지 않는다)
if [ ! -d "$PW/node_modules/playwright" ]; then
  mkdir -p "$PW" && (cd "$PW" && echo '{"name":"nullstock-pw","private":true}' > package.json && npm i playwright >/dev/null 2>&1 && npx playwright install chromium >/dev/null 2>&1)
fi

# 3) 작업 폴더는 매번 새로 만든다 — 이전 녹화의 marks.jsonl이 남으면 편집이 영상 전체를 홈 화면으로 만든다(10-13 실측)
case "$WORK" in "$HOME/nullstock-cf/.work/"*) rm -rf "$WORK";; *) echo "[중단] 작업 폴더 경로 이상"; exit 1;; esac
mkdir -p "$WORK" && cd "$WORK"
ln -s "$PW/node_modules" node_modules
cp "$HERE"/{studio_server,studio_lib,studio_record,studio_step,ai_shot,card}.mjs .
cp "$OUT/spec.json" spec.json
[ -f "$OUT/meta.json" ] && cp "$OUT/meta.json" meta.json || echo '{}' > meta.json

# 4) 녹화 — 로그인은 데모 게스트(guest_5312). 비밀번호는 출력하지 않는다
export GUEST_PW="$(cd "$REPO" && python3 -c "import json;print([x for x in json.load(open('guest-accounts.local.json')) if x['guestId']=='guest_5312'][0]['password'])")"
(nohup node studio_server.mjs > server.log 2>&1 &)
trap 'pkill -TERM -f "node studio_server.mjs" || true' EXIT
for i in $(seq 1 60); do grep -q "^ready" server.log 2>/dev/null && break; sleep 1; done
grep -q "^ready" server.log || { echo "[중단] 녹화 브라우저가 안 떴다"; cat server.log; exit 1; }
node studio_record.mjs spec.json 2>&1 | tee record.log
pkill -TERM -f "node studio_server.mjs" || true; sleep 4

# 5) 편집·렌더·BGM·검수 (studio_build.sh가 BGM까지 입힌다)
bash "$HERE/studio_build.sh" meta.json final.mp4

# 6) 게시용 해석 글 + 보관 + 복사 + 폴더 열기(게시는 하지 않는다)
(cd "$REPO" && uv run python "$HERE/make_post.py" "$WORK" >/dev/null)
cp final.mp4 result.json plan.json post1.txt spec.json "$OUT/"
[ -f ai.png ] && cp ai.png "$OUT/" || true
[ "${KEEP_FRAMES:-0}" = "1" ] || rm -rf frames    # 프레임은 약 1GB — 영상이 나왔으면 지운다(다시 편집하려면 KEEP_FRAMES=1)
pbcopy < "$OUT/post1.txt"
open "$OUT"
echo "[완료] $OUT — final.mp4, post1.txt(클립보드에 복사됨). 검수 자료: $WORK/review_sheet.png"
