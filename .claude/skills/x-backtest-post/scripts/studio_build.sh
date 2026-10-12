#!/bin/bash
# 스튜디오 영상 빌드: 카드 → 편집 계획 → 렌더 → 검수 시트. 녹화 폴더(frames·marks.jsonl·result.json)에서 실행한다.
# 사용: bash studio_build.sh <meta.json> [out.mp4]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
META="$1"; OUT="${2:-final.mp4}"
uv run --project "$HERE/../../../.." python "$HERE/make_plan.py" . "$META"
# ESM은 스크립트 옆의 node_modules만 찾는다 — 작업 폴더(playwright 설치·링크)로 복사해 실행
[ -e node_modules ] || { echo "[중단] 작업 폴더에 node_modules(playwright)가 없다"; exit 1; }
cp "$HERE/card.mjs" ./card.mjs
node ./card.mjs title.json title.png >/dev/null
node ./card.mjs end.json end.png >/dev/null
uv run --project "$HERE/../../../.." python "$HERE/render_studio.py" plan.json "$OUT"
bash "$HERE/review_video.sh" "$OUT"
