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
claude -p "/news-strategy-test 무인 실행: 오늘($DAY) 뉴스로 진행하고 보고는 report.md로 남겨" \
  --permission-mode bypassPermissions --output-format text
code=$?
if [ -f "$HOME/nullstock-news/$DAY/report.md" ]; then
  notify "오늘 결과가 준비됐어요 — report.md"; open "$HOME/nullstock-news/$DAY/report.md"
else
  notify "실행이 끝났지만 report.md가 없어요(코드 $code) — 로그 확인"
fi
echo "=== $(date) 끝 (코드 $code)"
