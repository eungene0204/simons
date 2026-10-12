#!/bin/bash
# 홍보 CF 2편(금융 모션그래픽 + 제품 화면) 한 번에 만들기: 재료 → 모션 렌더 → 조립(내레이션 TTS 포함) → 검수 시트.
# 사용: bash cf2_run.sh <녹화 폴더(cf_run.sh 작업 폴더)> <작업 폴더> [cf2_script.json] [출력 이름]
#   녹화 폴더: cf_run.sh가 만든 frames·marks.jsonl·result.json(제품 화면 원본). 작업 폴더에는 playwright node_modules 링크가 있어야 한다.
#   출력은 덮어쓰지 않도록 이름에 시각을 붙인다(10-12: 열린 QuickTime 파일을 덮어써 빈 화면 사고).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../../../.." && pwd)"
REC="$1"; W="$2"; SCRIPT="${3:-$HERE/cf2_script.json}"; NAME="${4:-nullstock_cf2_$(date +%m%d_%H%M).mp4}"
SCRIPT="$(cd "$(dirname "$SCRIPT")" && pwd)/$(basename "$SCRIPT")"
mkdir -p "$W"; [ -e "$W/node_modules" ] || { echo "[중단] $W/node_modules(playwright)가 없다 — SKILL.md ② 참고"; exit 1; }
(cd "$ROOT" && uv run --frozen --project backend python "$HERE/cf2_assets.py" "$W")
cp "$HERE/render_motion.mjs" "$W/"
S=$(python3 -c "import json;s=json.load(open('$SCRIPT'))['scenes'];print(f\"open:{s['open']} heat:{s['heat']} title:{s['title']} wf:{s['wf_motion']} mc:{s['mc_motion']} live:{s['live']} bg:10 end:{s['end']}\")")
cd "$W" && rm -rf motion
MOTION_HTML="$HERE/motion.html" MOTION_SCRIPT="$SCRIPT" node render_motion.mjs data.json logo.png motion $S
uv run --project "$ROOT" --with numpy python "$HERE/cf2_build.py" "$REC" motion "$NAME" --script "$SCRIPT" 2>&1 | grep -v "f$"
ffmpeg -v error -y -i "$NAME" -vf "fps=1,scale=480:-1,tile=8x8" -frames:v 1 "${NAME%.mp4}_sheet.png"
echo "완성: $W/$NAME · 검수 시트: $W/${NAME%.mp4}_sheet.png"
