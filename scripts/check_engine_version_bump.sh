#!/usr/bin/env bash
#
# 백테스트 엔진 버전 갱신 리마인더 (A안).
#
# 엔진 핵심 파일이 바뀌었는데 backend/engine/version.py의 ENGINE_VERSION은
# 그대로이면 실패시켜, 버전 올리는 걸 잊지 않도록 상기시킨다.
# (major/minor 판단은 사람이 하므로 자동으로 올리지는 않는다.)
#
# 사용법:  scripts/check_engine_version_bump.sh <base_ref> <head_ref>
# 로컬 예:  scripts/check_engine_version_bump.sh HEAD~1 HEAD
#
# 우회: 결과값에 영향 없는 리팩터/주석/로깅 변경이면 범위 내 커밋 메시지에
#       [skip-version-bump] 를 넣으면 통과한다.
set -euo pipefail

BASE="${1:?base ref required}"
HEAD="${2:?head ref required}"

# 백테스트 결과값을 바꿀 수 있는 엔진 핵심 파일. 새 핵심 파일이 생기면 여기 추가한다.
CORE_FILES=(
  "backend/backtest_engine.py"
  "backend/engine/simulator.py"
  "backend/engine/signals.py"
  "backend/engine/indicators.py"
  "backend/engine/result_handler.py"
  "backend/engine/rebalance.py"
  "backend/engine/rank_exit.py"
  "backend/engine/vectorbt_native.py"
  "backend/engine/loader.py"
  "backend/engine/universe_pit.py"
)

VERSION_FILE="backend/engine/version.py"

changed="$(git diff --name-only "$BASE" "$HEAD")"

touched=()
for f in "${CORE_FILES[@]}"; do
  if grep -qxF "$f" <<<"$changed"; then
    touched+=("$f")
  fi
done

if [ ${#touched[@]} -eq 0 ]; then
  echo "✓ 엔진 핵심 파일 변경 없음 — 버전 확인 불필요."
  exit 0
fi

# ENGINE_VERSION 값이 실제로 바뀌었는지 확인 (ENGINE_VERSION_LABEL 은 제외).
ver_at() { git show "$1:$VERSION_FILE" 2>/dev/null | sed -n 's/^ENGINE_VERSION = //p'; }
base_ver="$(ver_at "$BASE" || true)"
head_ver="$(ver_at "$HEAD" || true)"

if [ -n "$head_ver" ] && [ "$base_ver" != "$head_ver" ]; then
  echo "✓ 엔진 핵심 파일 변경 + ENGINE_VERSION 갱신됨 (${base_ver:-없음} → $head_ver)."
  exit 0
fi

if git log --format=%B "$BASE".."$HEAD" | grep -q '\[skip-version-bump\]'; then
  echo "⚠ 엔진 핵심 파일이 바뀌었지만 [skip-version-bump] 표기로 버전 갱신을 건너뜀."
  exit 0
fi

echo "✗ 엔진 핵심 파일이 바뀌었는데 ENGINE_VERSION(${base_ver:-없음})이 그대로입니다."
echo "  변경된 핵심 파일:"
printf '    - %s\n' "${touched[@]}"
echo ""
echo "  → 백테스트 결과값이 바뀌는 변경이면 $VERSION_FILE 의 ENGINE_VERSION 을 올리고"
echo "     CHANGELOG 에 한 줄 추가하세요 (큰 변경=MAJOR vX, 작은 수정=MINOR vX.Y)."
echo "  → 결과에 영향 없는 리팩터/주석/로깅이면 커밋 메시지에 [skip-version-bump] 를 넣으세요."
exit 1
