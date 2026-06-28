/**
 * Next.js 내장 스케줄러
 *
 * Next.js 서버 프로세스 내에서 setInterval로 동작하며,
 * scripts/scheduler.py의 로직을 그대로 TypeScript로 이식.
 *
 * 스케줄:
 *   08:50 KST  — 장전 데이터 워밍 (평일)
 *   09:00 KST  — 장 개장: auto 모드 계좌 자동 시작 (running 전환, 평일)
 *   15:30 KST  — 장 마감: 실행 중인 계좌 일시정지 (paused 전환, 평일)
 *
 * 장중 시그널 평가·체결(자동매매)은 이 스케줄러가 하지 않는다 — 정본은 FastAPI
 * 백엔드의 VirtualTrader(backend/engine/virtual_trader.py, 30초 간격)다.
 * 이 스케줄러는 계좌의 running/paused 생명주기와 캐시 워밍만 담당한다.
 */

import { runSchedulerAction } from "@/lib/server/scheduler-actions";

const CHECK_INTERVAL_MS = 60_000; // 1분마다 체크

const firedToday = new Set<string>();
let intervalId: ReturnType<typeof setInterval> | null = null;

/** KST 현재 시각 */
function nowKST(): Date {
  // UTC + 9시간
  const utc = new Date();
  return new Date(utc.getTime() + 9 * 60 * 60 * 1000);
}

function formatKST(d: Date): string {
  return d.toISOString().replace("T", " ").slice(0, 19);
}

// 스케줄러 액션을 인-프로세스로 직접 실행한다.
// 예전에는 자기 자신의 /api/scheduler 라우트를 HTTP 로 self-fetch 했는데,
// dev 모드에서 HMR 재컴파일이 일어나면 그 라우트가 일시적으로 404(HTML)를 반환해
// "Unexpected token '<'" SyntaxError 가 반복 발생했다. 이제 로직(runSchedulerAction)을
// 직접 호출하므로 HTTP 왕복도, 라우트 재컴파일 의존성도 없다.
export async function callSchedulerAPI(action: string): Promise<void> {
  const ts = formatKST(nowKST());
  try {
    const result = await runSchedulerAction(action);

    if (action === "market-open") {
      const count = Array.isArray(result.results) ? result.results.length : 0;
      console.log(`[Scheduler] ${ts} KST — 장 개장 처리 완료 — ${count}개 계좌`);
    } else if (action === "market-close") {
      const count = typeof result.paused === "number" ? result.paused : 0;
      console.log(`[Scheduler] ${ts} KST — 장 마감 처리 완료 — ${count}개 계좌 일시정지`);
    }
  } catch (e) {
    console.error(`[Scheduler] ${ts} KST — 스케줄러 액션 실패 (${action}):`, e);
  }
}

function tick(): void {
  const kst = nowKST();
  const h = kst.getUTCHours();
  const m = kst.getUTCMinutes();
  const weekday = kst.getUTCDay(); // 0=일 ~ 6=토
  const dateStr = kst.toISOString().slice(0, 10);

  // 자정에 fired 초기화
  if (h === 0 && m === 0) {
    firedToday.clear();
  }

  // 평일만 (1=월 ~ 5=금)
  if (weekday < 1 || weekday > 5) return;

  // 08:50 KST — 장전 데이터 워밍 (캐시 사전 로드)
  const preMarketKey = `${dateStr}_pre_market`;
  if (h === 8 && m === 50 && !firedToday.has(preMarketKey)) {
    firedToday.add(preMarketKey);
    console.log(`[Scheduler] ${formatKST(kst)} KST — 장전 데이터 워밍`);
    callSchedulerAPI("pre-market");
  }

  // 09:00 KST — 장 개장
  const openKey = `${dateStr}_market_open`;
  if (h === 9 && m === 0 && !firedToday.has(openKey)) {
    firedToday.add(openKey);
    console.log(`[Scheduler] ${formatKST(kst)} KST — 장 개장 — auto 계좌 시작`);
    callSchedulerAPI("market-open");
  }

  // 장중 시세/시그널 새로고침은 더 이상 여기서 트리거하지 않는다.
  // 자동매매 체결의 정본은 FastAPI 백엔드의 VirtualTrader(30초 간격)다.

  // 15:30 KST — 장 마감
  const closeKey = `${dateStr}_market_close`;
  if (h === 15 && m === 30 && !firedToday.has(closeKey)) {
    firedToday.add(closeKey);
    console.log(`[Scheduler] ${formatKST(kst)} KST — 장 마감 — 실행 중인 계좌 일시정지`);
    callSchedulerAPI("market-close");
  }
}

export function startScheduler(): void {
  if (intervalId) return; // 이미 실행 중

  const kst = nowKST();
  console.log(`[Scheduler] 스케줄러 시작 (KST: ${formatKST(kst)})`);
  console.log(`[Scheduler] 인-프로세스 직접 실행 (HTTP self-fetch 제거됨)`);
  console.log(`[Scheduler] 자동매매 체결은 VirtualTrader(백엔드)가 담당 — 생명주기/캐시만 관리`);

  // 시작 직후 한 번 실행 (서버 재시작 시 놓친 이벤트 처리)
  tick();

  intervalId = setInterval(tick, CHECK_INTERVAL_MS);
}

export function stopScheduler(): void {
  if (intervalId) {
    clearInterval(intervalId);
    intervalId = null;
    console.log("[Scheduler] 스케줄러 중지");
  }
}
