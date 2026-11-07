#!/bin/bash
# 뉴스 전략 결과(~/nullstock-news) → 퀀트 연구노트 게시. 무인 실행(daily.sh)이 report.md 뒤에 부르고, 손으로도 같은 명령을 쓴다.
#   bash .claude/skills/news-strategy-test/scripts/publish_news_notes.sh [--allow-changed]
#
# 1) origin/main 임시 워크트리에서 build_news_notes.py로 데이터·사진을 다시 만든다(공유 checkout은 건드리지 않는다).
# 2) 새 편이 없으면 끝. 이미 올라간 편의 내용이 바뀌면 멈춘다(DB 본문과 어긋난다 — 의도한 수리면 --allow-changed).
# 3) 편 수 테스트를 올리고 vitest(lib/notes components/notes) → 시드 dry-run에서 신규 = 새 편 수인지 본다.
# 4) 데이터·사진·테스트 세 경로만 커밋해 main에 푸시하고 CI(배포 포함) 성공을 기다린다 — 사진은 배포로만 나간다.
# 5) 배포가 성공한 뒤에만 시드 --apply(news- 접두사, create-only) → 운영 주소가 200인지 확인한다.
# 어느 단계든 실패하면 그 단계를 출력하고 0이 아닌 코드로 끝낸다(시드 전이면 운영 DB는 그대로다).
set -euo pipefail
export PATH="/Users/eugene/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="/Users/eugene/nullalgo/simons"
SITE="https://www.nullstock.im"
DATA="lib/notes/newsNotes.data.json"
TEST="lib/notes/notes.test.ts"
ALLOW_CHANGED="${1:-}"
WT="$HOME/nullstock-news/.publish-wt"

fail() { echo "[연구노트 실패] $1"; exit 1; }
cleanup() { cd "$REPO"; git worktree remove --force "$WT" >/dev/null 2>&1 || true; }

cd "$REPO"
git fetch -q origin main
[ -e "$WT" ] && git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1; rm -rf "$WT"
git -C "$REPO" worktree add -q --detach "$WT" origin/main
trap cleanup EXIT
bash "$REPO/scripts/worktree.sh" link "$WT" >/dev/null
cd "$WT"

cp "$DATA" /tmp/news-notes-before.$$.json
uv run --frozen python .claude/skills/news-strategy-test/scripts/build_news_notes.py || fail "build_news_notes.py"
read -r ADDED CHANGED NEW_SLUGS < <(python3 - /tmp/news-notes-before.$$.json "$DATA" <<'EOF'
import json, sys
before = {e["slug"]: e for e in json.load(open(sys.argv[1]))}
after = {e["slug"]: e for e in json.load(open(sys.argv[2]))}
added = [s for s in after if s not in before]
changed = [s for s in before if s not in after or before[s] != after[s]]
print(len(added), len(changed), ",".join(added) or "-")
EOF
)
rm -f /tmp/news-notes-before.$$.json
echo "새 편 $ADDED · 바뀐 기존 편 $CHANGED"
if [ "$CHANGED" != 0 ] && [ "$ALLOW_CHANGED" != "--allow-changed" ]; then
  fail "이미 올라간 편 ${CHANGED}개의 내용이 바뀐다 — 스크립트가 바뀐 것이면 사람이 확인하고 --allow-changed로 다시 돌린다"
fi
[ "$ADDED" = 0 ] && [ "$CHANGED" = 0 ] && { echo "[연구노트] 새 편 없음"; exit 0; }

TOTAL=$(python3 -c "import json; print(len(json.load(open('$DATA'))))")
sed -i '' -E "s/expect\(NEWS_NOTES\)\.toHaveLength\([0-9]+\)/expect(NEWS_NOTES).toHaveLength($TOTAL)/" "$TEST"
npx vitest run lib/notes components/notes >/tmp/news-notes-vitest.$$.log 2>&1 || { tail -30 /tmp/news-notes-vitest.$$.log; fail "vitest"; }

DRY=$(npx ts-node --project tsconfig.scripts.json scripts/seed-research-notes.ts --slug-prefix=news- 2>&1) || fail "시드 dry-run 오류: $(echo "$DRY" | tail -3)"
DRY=$(echo "$DRY" | head -1)
echo "$DRY"
[[ "$DRY" == *"신규 $ADDED · 덮어쓰기 0"* ]] || fail "시드 dry-run 신규 수가 새 편 수($ADDED)와 다르다: $DRY"

git add -- "$DATA" "$TEST" public/notes/news
git commit -q -m "feat(notes): 뉴스 전략 연구노트 ${ADDED}편 추가(무인 게시)" -m "새 편: ${NEW_SLUGS}"
git push -q origin HEAD:main || { git pull -q --rebase origin main && git push -q origin HEAD:main; } || fail "main 푸시"
SHA=$(git rev-parse HEAD)
echo "푸시 $SHA — CI·배포를 기다린다"

RUN=""
for _ in $(seq 1 20); do
  RUN=$(gh run list --workflow ci.yml --commit "$SHA" --json databaseId -q '.[0].databaseId' 2>/dev/null || true)
  [ -n "$RUN" ] && break; sleep 15
done
[ -n "$RUN" ] || fail "CI 실행을 찾지 못했다($SHA) — 시드하지 않았다"
gh run watch "$RUN" --exit-status --interval 60 >/dev/null \
  || fail "CI/배포 실패(run $RUN) — 시드하지 않았다. 커밋은 main에 남아 있다"

APPLIED=$(npx ts-node --project tsconfig.scripts.json scripts/seed-research-notes.ts --slug-prefix=news- --apply 2>&1) \
  || fail "배포는 됐지만 시드 --apply 오류(사진만 있고 글이 없다 — 같은 명령으로 다시 돌린다): $(echo "$APPLIED" | tail -3)"
echo "$APPLIED" | head -1
for slug in ${NEW_SLUGS//,/ }; do
  [ "$slug" = "-" ] && continue
  page=$(curl -s -o /dev/null -w '%{http_code}' "$SITE/notes/$slug")
  img=$(curl -s -o /dev/null -w '%{http_code}' "$SITE/notes/news/$slug/overview.webp")
  echo "$slug: 글 $page · 사진 $img"
  [ "$page" = 200 ] && [ "$img" = 200 ] || fail "$slug 운영 주소 확인 실패(글 $page · 사진 $img)"
done
echo "[연구노트] ${ADDED}편 게시 완료"
