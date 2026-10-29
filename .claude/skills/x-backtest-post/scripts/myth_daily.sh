#!/bin/bash
# 매일 13:00(launchd: ~/Library/LaunchAgents/im.nullstock.myth-daily.plist)에 속설 검증 시리즈를 무인으로 만들고 게시한다.
# 절차: references/myth_unattended.md   로그: ~/Library/Logs/nullstock-myth-daily.log   보고: ~/nullstock-cf/myth-daily-<날짜>.md
set -uo pipefail
export PATH="/Users/eugene/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="/Users/eugene/nullalgo/simons"
DAY="$(TZ=Asia/Seoul date +%F)"
REPORT="$HOME/nullstock-cf/myth-daily-$DAY.md"
notify() { osascript -e "display notification \"$1\" with title \"널스탁 속설 검증\"" >/dev/null 2>&1 || true; }
source "$REPO/.claude/skills/news-strategy-test/scripts/auto_lock.sh"

echo "=== $(date) 시작 ($DAY)"
srv_msg="$(bash "$REPO/.claude/skills/news-strategy-test/scripts/check_servers.sh" 2>&1)" || { echo "$srv_msg"; notify "앱 서버가 응답하지 않아 건너뛰었어요"; exit 0; }
acquire_auto_lock myth || { notify "다른 자동 작업이 끝나지 않아 건너뛰었어요"; exit 0; }
cd "$REPO"
claude -p "/x-backtest-post 속설 검증 무인 실행: 오늘($DAY) 편을 references/myth_unattended.md 절차대로 주제 선정부터 게시까지 진행하고 보고서는 $REPORT 에 남겨" \
  --permission-mode bypassPermissions --output-format text
code=$?
if [ -f "$REPORT" ]; then
  notify "$(head -1 "$REPORT" | cut -c1-80)"; open "$REPORT"
else
  notify "실행이 끝났지만 보고서가 없어요(코드 $code) — 로그 확인"
fi
echo "=== $(date) 끝 (코드 $code)"
