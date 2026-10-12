#!/usr/bin/env bash
#
# 세션 격리 워크트리 — 병렬 세션이 같은 워킹 디렉터리를 공유해서 생긴 사고를 끊는다.
#   · git add -A가 남의 미커밋 작업을 쓸어 담아 푸시·배포 직전까지 감(2026-09-21)
#   · 남의 backend/ 편집이 uvicorn --reload로 내 진행 중 요청·게이트를 끊음
#
# git이 추적하지 않는 무거운 자원(data parquet·node_modules·.venv·.env·SQLite·logs)은
# 복사하지 않고 원본으로 심볼릭 링크한다. 그래서:
#   · 코드·문서·테스트는 워크트리마다 독립이다.
#   · 데이터·의존성·Trace(backend/logs)는 원본과 **공유**한다 — 워크트리에서 데이터를 쓰면
#     원본도 바뀐다(parquet 방향 규칙은 그대로 적용).
#
# 사용:
#   scripts/worktree.sh new <slug> [base]   # ../simons-wt/<slug>, 브랜치 wt/<slug> (base 기본: 현재 HEAD)
#   scripts/worktree.sh link <path>         # 이미 만든 워크트리(EnterWorktree 등)에 자원만 연결
#   scripts/worktree.sh list
#   scripts/worktree.sh rm <slug>           # 미커밋 변경이 있으면 git이 거부한다(브랜치는 남긴다)
set -euo pipefail

MAIN="$(git rev-parse --path-format=absolute --git-common-dir)"
MAIN="${MAIN%/.git}"
WT_ROOT="$(dirname "$MAIN")/simons-wt"

# 링크하지 않는 무시 경로 — 도구 캐시·OS 찌꺼기·빌드 산출물(워크트리마다 따로 생겨야 한다).
skip() {
  case "$1" in
    *.DS_Store|*__pycache__*|*.pyc|*.pytest_cache*|.next/*|.next|.vscode*|*/.vitest*|tsconfig.tsbuildinfo) return 0 ;;
  esac
  return 1
}

# 링크 대신 복사하는 경로 — QA 하니스 캐시(scripts/.qa_*·.template_parse_cache)는 입력이자 결과라
# 링크하면 워크트리의 측정이 원본을 덮어써, 다른 세션의 조사가 이쪽 코드의 결과를 읽는다
# (2026-10-13 발견). 워크트리마다 독립 사본을 갖는다.
copy_instead() {
  case "$1" in
    scripts/.qa_*|scripts/.template_parse_cache*) return 0 ;;
  esac
  return 1
}

link_resources() {
  local wt="$1" n=0
  [ -d "$wt" ] || { echo "워크트리가 없습니다: $wt" >&2; exit 1; }
  # .gitignore의 'dir/' 패턴은 디렉터리 심볼릭 링크를 못 잡는다 — 링크 경로를 저장소 로컬
  # 제외 목록(info/exclude, 워크트리 공용)에 슬래시 없이 올려 git status·add에서 숨긴다.
  local exclude; exclude="$(git -C "$wt" rev-parse --path-format=absolute --git-path info/exclude)"
  mkdir -p "$(dirname "$exclude")"; touch "$exclude"
  while IFS= read -r rel; do
    rel="${rel%/}"
    [ -n "$rel" ] || continue
    skip "$rel" && continue
    local src="$MAIN/$rel" dst="$wt/$rel"
    [ -e "$src" ] || continue
    if [ -L "$dst" ]; then
      grep -qxF "/$rel" "$exclude" || echo "/$rel" >> "$exclude"
      continue
    fi
    [ -e "$dst" ] && continue
    # 상위 디렉터리가 이미 링크면 그 안은 이미 보인다.
    local parent; parent="$(dirname "$dst")"
    [ -L "$parent" ] && continue
    mkdir -p "$parent"
    if copy_instead "$rel"; then
      cp -pR "$src" "$dst"
    else
      ln -s "$src" "$dst"
    fi
    grep -qxF "/$rel" "$exclude" || echo "/$rel" >> "$exclude"
    n=$((n + 1))
  done < <(git -C "$MAIN" ls-files --others --ignored --exclude-standard --directory)
  echo "자원 링크 ${n}개 → $wt"
}

cmd="${1:-}"
case "$cmd" in
  new)
    slug="${2:?slug 필요}"
    base="${3:-HEAD}"
    path="$WT_ROOT/$slug"
    mkdir -p "$WT_ROOT"
    git -C "$MAIN" worktree add "$path" -b "wt/$slug" "$base"
    link_resources "$path"
    echo "준비됨: cd $path"
    ;;
  link)
    link_resources "$(cd "${2:?경로 필요}" && pwd)"
    ;;
  list)
    git -C "$MAIN" worktree list
    ;;
  rm)
    slug="${2:?slug 필요}"
    path="$WT_ROOT/$slug"
    # 이 스크립트가 만든 링크(원본을 가리키는 심볼릭 링크)만 먼저 걷는다 — 나머지 미커밋
    # 변경이 있으면 git이 제거를 거부한다(그게 의도다).
    find "$path" -type l -lname "$MAIN/*" -not -path "$path/node_modules/*" -delete
    git -C "$MAIN" worktree remove "$path"
    echo "제거됨(브랜치 wt/${slug}는 남김): $WT_ROOT/$slug"
    ;;
  *)
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
