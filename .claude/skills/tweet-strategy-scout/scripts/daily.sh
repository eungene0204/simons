#!/bin/bash
# 매일 12:00·18:00(launchd: ~/Library/LaunchAgents/im.nullstock.tweet-scout-{1200,1800}.plist)에 tweet-strategy-scout 스킬을 무인 실행한다.
# 로그: ~/Library/Logs/nullstock-tweets-daily.log   결과: ~/nullstock-tweets/<날짜>-<HHMM>/report.md
# 1단계 후보 고르기(앱 불필요) → 2단계 백테스트(앱 서버·데모 계정 사용: 서버 점검 + 자동 작업 잠금) → 3단계 결과 검수·보고서 합치기.
set -uo pipefail
export PATH="/Users/eugene/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="/Users/eugene/nullalgo/simons"
NEWS="$REPO/.claude/skills/news-strategy-test/scripts"
STAMP="$(TZ=Asia/Seoul date +%F-%H%M)"
OUT="$HOME/nullstock-tweets/$STAMP"
notify() { osascript -e "display notification \"$1\" with title \"널스탁 트윗 전략 후보\"" >/dev/null 2>&1 || true; }
claude_run() { claude -p "$1" --permission-mode bypassPermissions --output-format text; }

echo "=== $(date) 시작 ($STAMP)"
cd "$REPO"

# 1단계 — 새 트윗을 읽고 후보를 고른다. 후보마다 $OUT/NN-slug/spec.json과 report.md를 쓴다.
claude_run "/tweet-strategy-scout 무인 실행 1단계: 계정 @Jaemyung_Lee, 산출 폴더 $OUT, 후보 선정·spec.json·report.md 작성까지만 하고 백테스트는 돌리지 않는다"
[ -f "$OUT/report.md" ] || { notify "report.md가 없어요 — 로그 확인"; echo "=== $(date) 끝 (report 없음)"; exit 0; }

specs=("$OUT"/*/spec.json)
if [ ! -e "${specs[0]}" ]; then
  notify "새 트윗 확인 완료 — 후보 없음"; echo "=== $(date) 끝 (후보 없음)"; exit 0
fi

# 2단계 — 백테스트. 서브셸에서 잠금을 쥐어 끝나면 바로 풀린다(트랩이 남의 잠금을 지우지 않게).
(
  source "$NEWS/auto_lock.sh"
  srv_msg="$(bash "$NEWS/check_servers.sh" 2>&1)" || { echo "$srv_msg"; echo "[건너뜀] 앱 서버가 응답하지 않는다" > "$OUT/backtest_skipped.txt"; exit 0; }
  acquire_auto_lock tweets || { echo "[건너뜀] 자동 작업 잠금을 못 얻었다" > "$OUT/backtest_skipped.txt"; exit 0; }
  for s in "${specs[@]}"; do
    d="$(dirname "$s")"
    bash "$NEWS/run_test.sh" "$d" > "$d/run_test.log" 2>&1 || echo "[실패] $d" | tee -a "$OUT/backtest_failed.txt"
  done
)

# 3단계 — 결과 검수(해석 요약이 문장과 같은지)와 보고서 합치기
claude_run "/tweet-strategy-scout 무인 실행 3단계: 산출 폴더 $OUT, 백테스트 결과를 검수하고 report.md에 합친다(backtest_skipped.txt·backtest_failed.txt가 있으면 그 사실을 적는다)"
if grep -q '후보 [1-9]' "$OUT/report.md"; then notify "전략 후보·백테스트 결과가 준비됐어요 — report.md"; open "$OUT/report.md"
else notify "새 트윗 확인 완료 — 후보 없음"; fi
echo "=== $(date) 끝"
