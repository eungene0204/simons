#!/bin/bash
# 매일 12:00(launchd: ~/Library/LaunchAgents/im.nullstock.news-strategy-test.plist)에 news-strategy-test 스킬을 무인 실행한다.
# 로그: ~/Library/Logs/nullstock-news-daily.log   결과: ~/nullstock-news/<날짜>/report.md
set -uo pipefail
export PATH="/Users/eugene/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="/Users/eugene/nullalgo/simons"
DAY="$(TZ=Asia/Seoul date +%F)"
notify() { osascript -e "display notification \"$1\" with title \"널스탁 뉴스 전략 테스트\"" >/dev/null 2>&1 || true; }
source "$REPO/.claude/skills/news-strategy-test/scripts/auto_lock.sh"

echo "=== $(date) 시작 ($DAY)"
# 앱 서버는 띄우지 않는다 — 꺼져 있으면 알리고 끝낸다
srv_msg="$(bash "$REPO/.claude/skills/news-strategy-test/scripts/check_servers.sh" 2>&1)" || { echo "$srv_msg"; notify "앱 서버가 응답하지 않아 건너뛰었어요"; exit 0; }
acquire_auto_lock news || { notify "다른 자동 작업이 끝나지 않아 건너뛰었어요"; exit 0; }
cd "$REPO"
# 연구노트에 싣는 엔진 버전 — 로컬 앱이 이 checkout으로 돌므로 실행 시각의 값을 남긴다(build_news_notes.py가 읽는다)
mkdir -p "$HOME/nullstock-news/$DAY"
sed -n 's/^ENGINE_VERSION = "\(.*\)"/\1/p' backend/engine/version.py > "$HOME/nullstock-news/$DAY/engine.txt"
claude -p "/news-strategy-test 무인 실행: 오늘($DAY) 뉴스로 진행하고 보고는 report.md로 남겨" \
  --permission-mode bypassPermissions --output-format text
code=$?
REPORT="$HOME/nullstock-news/$DAY/report.md"
if [ -f "$REPORT" ]; then
  # 연구노트 게시(2026-11-08 사용자 지시 — 뉴스 전략을 만들면 노트까지 자동으로). 13시 속설 작업도 노트를 시드하므로 잠금을 쥔 채 한다.
  pub_log="$(bash "$REPO/.claude/skills/news-strategy-test/scripts/publish_news_notes.sh" 2>&1)"; pub=$?
  echo "$pub_log"
  { echo; echo "## 연구노트 게시"; echo; echo '```'; echo "$pub_log" | tail -15; echo '```'; } >> "$REPORT"
  [ $pub = 0 ] && notify "오늘 결과가 준비됐어요 — 연구노트 게시까지 끝" || notify "결과는 준비됐지만 연구노트 게시가 실패했어요 — report.md"
  open "$REPORT"
else
  notify "실행이 끝났지만 report.md가 없어요(코드 $code) — 로그 확인"
fi
echo "=== $(date) 끝 (코드 $code)"
