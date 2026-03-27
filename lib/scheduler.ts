/**
 * Next.js 내장 스케줄러
 *
 * Next.js 서버 프로세스 내에서 setInterval로 동작하며,
 * scripts/scheduler.py의 로직을 그대로 TypeScript로 이식.
 *
 * 스케줄:
 *   08:50 KST  — 장전 데이터 워밍 (평일)
 *   09:00 KST  — 장 개장: auto 모드 계좌 자동 시작 (평일)
 *   09:05~15:25 KST — 1분 간격 시세/시그널 새로고침 (평일)
 *   15:30 KST  — 장 마감: 실행 중인 계좌 일시정지 (평일)
 */

const REFRESH_INTERVAL_MIN = 1;
const CHECK_INTERVAL_MS = 60_000; // 1분마다 체크

const APP_URL = process.env.APP_URL || "http://localhost:3000";

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

async function callSchedulerAPI(action: string): Promise<void> {
  const url = `${APP_URL}/api/scheduler`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    const body = await res.json();
    const ts = formatKST(nowKST());

    if (action === "market-open") {
      const count = body.results?.length ?? 0;
      console.log(`[Scheduler] ${ts} KST — 장 개장 처리 완료 — ${count}개 계좌`);
    } else if (action === "market-refresh") {
      const count = body.results?.length ?? 0;
      console.log(`[Scheduler] ${ts} KST — 시세 새로고침 완료 — ${count}개 계좌`);
    } else if (action === "market-close") {
      const count = body.paused ?? 0;
      console.log(`[Scheduler] ${ts} KST — 장 마감 처리 완료 — ${count}개 계좌 일시정지`);
    }
  } catch (e) {
    const ts = formatKST(nowKST());
    console.error(`[Scheduler] ${ts} KST — API 호출 실패 (${action}):`, e);
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

  // 09:05~15:25 KST — 5분 간격 새로고침
  const inMarketHours =
    (h === 9 && m >= 5) || (h >= 10 && h <= 14) || (h === 15 && m < 30);
  if (inMarketHours && m % REFRESH_INTERVAL_MIN === 0) {
    const refreshKey = `${dateStr}_${String(h).padStart(2, "0")}${String(m).padStart(2, "0")}_refresh`;
    if (!firedToday.has(refreshKey)) {
      firedToday.add(refreshKey);
      console.log(`[Scheduler] ${formatKST(kst)} KST — 시세 새로고침`);
      callSchedulerAPI("market-refresh");
    }
  }

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
  console.log(`[Scheduler] APP_URL: ${APP_URL}`);
  console.log(`[Scheduler] 새로고침 간격: ${REFRESH_INTERVAL_MIN}분`);

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
