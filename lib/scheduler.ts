/**
 * Next.js 내장 스케줄러
 *
 * Next.js 서버 프로세스 내에서 setInterval로 동작하며,
 * scripts/scheduler.py의 로직을 그대로 TypeScript로 이식.
 *
 * 스케줄:
 *   08:50 KST  — 장전 데이터 워밍 (평일)
 *   09:00 KST  — 장 개장: KRW auto 계좌 자동 시작 (running 전환, 평일)
 *   15:30 KST  — 장 마감: 실행 중인 KRW 계좌 일시정지 (paused 전환, 평일)
 *   09:30 ET   — 미국장 개장: USD auto 계좌 자동 시작 (평일, 서머타임 자동 반영)
 *   16:00 ET   — 미국장 마감: 실행 중인 USD 계좌 일시정지 (평일)
 *   04:00 KST  — 보존기간 지난 개인정보·운영 로그 파기 (매일)
 *
 * 장중 시그널 평가·체결(자동매매)은 이 스케줄러가 하지 않는다 — 정본은 FastAPI
 * 백엔드의 VirtualTrader(backend/engine/virtual_trader.py, 30초 간격)다.
 * 이 스케줄러는 계좌의 running/paused 생명주기와 캐시 워밍만 담당한다.
 * 미국 휴장일·조기 종료 판정도 여기서 하지 않는다 — 개장 이벤트가 휴장일에 계좌를
 * running 으로 돌려도 VirtualTrader 의 장 운영 달력 게이트가 매매를 막는다.
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

/** 뉴욕(ET) 현재 시각 파트 — 서머타임은 Intl 시간대 데이터가 자동 반영한다. */
function nowETParts(): { h: number; m: number; weekday: number; dateStr: string } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
  }).formatToParts(new Date());
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  const weekdayMap: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  return {
    // hour12:false 는 일부 엔진에서 자정을 "24"로 내놓는다
    h: Number(get("hour")) % 24,
    m: Number(get("minute")),
    weekday: weekdayMap[get("weekday")] ?? 0,
    dateStr: `${get("year")}-${get("month")}-${get("day")}`,
  };
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
    } else if (action === "us-market-open") {
      const count = Array.isArray(result.results) ? result.results.length : 0;
      console.log(`[Scheduler] ${ts} KST — 미국장 개장 처리 완료 — ${count}개 계좌`);
    } else if (action === "us-market-close") {
      const count = typeof result.paused === "number" ? result.paused : 0;
      console.log(`[Scheduler] ${ts} KST — 미국장 마감 처리 완료 — ${count}개 계좌 일시정지`);
    }
  } catch (e) {
    console.error(`[Scheduler] ${ts} KST — 스케줄러 액션 실패 (${action}):`, e);
  }
}

// 자동결제(빌링) 월 갱신 — 매시 정각에 nextBillingAt이 지난 구독을 청구/전환한다.
// 장 스케줄과 달리 주말에도 실행한다(결제 주기는 달력 기준).
async function runBillingRenewal(ts: string): Promise<void> {
  try {
    const [{ processDueBillingRenewals }, { processDuePaypalExpirations }, { prisma }] =
      await Promise.all([
        import("@/lib/server/billingRenewal"),
        import("@/lib/server/paypalSubscriptionExpiry"),
        import("@/lib/prisma"),
      ]);
    const result = await processDueBillingRenewals(prisma);
    if (result.renewed || result.retried || result.downgraded) {
      console.log(
        `[Scheduler] ${ts} KST — 구독 갱신: 결제 ${result.renewed}건, 재시도 예약 ${result.retried}건, FREE 전환 ${result.downgraded}건`
      );
    }

    // PayPal 구독은 PayPal이 갱신하므로 위 잡의 대상이 아니다 — 해지 예약분의 기간 만료만 처리한다
    const paypal = await processDuePaypalExpirations(prisma);
    if (paypal.downgraded) {
      console.log(
        `[Scheduler] ${ts} KST — PayPal 구독 만료: FREE 전환 ${paypal.downgraded}건`
      );
    }
  } catch (e) {
    console.error(`[Scheduler] ${ts} KST — 구독 갱신 잡 실패:`, e);
  }
}

// 보존기간 파기 — 기한이 지난 개인정보·운영 로그를 하루 한 번 지운다.
// 기간 표와 근거는 lib/server/dataRetention.ts 한 곳에만 둔다.
async function runRetentionPurge(ts: string): Promise<void> {
  try {
    const [{ purgeExpiredRecords }, { prisma }] = await Promise.all([
      import("@/lib/server/dataRetention"),
      import("@/lib/prisma"),
    ]);
    const summary = await purgeExpiredRecords(prisma);
    const deleted = Object.entries(summary).filter(([, n]) => n > 0);
    if (deleted.length > 0) {
      console.log(
        `[Scheduler] ${ts} KST — 보존기간 파기: ` +
          deleted.map(([target, n]) => `${target} ${n}건`).join(", ")
      );
    }
  } catch (e) {
    console.error(`[Scheduler] ${ts} KST — 보존기간 파기 잡 실패:`, e);
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

  // 매시 정각 — 자동결제(빌링) 구독 갱신 (주말 포함이라 평일 가드보다 먼저 체크)
  const billingRenewalKey = `${dateStr}_${h}_billing_renewal`;
  if (m === 0 && !firedToday.has(billingRenewalKey)) {
    firedToday.add(billingRenewalKey);
    void runBillingRenewal(formatKST(kst));
  }

  // 04:00 KST — 보존기간 파기 (주말 포함이라 평일 가드보다 먼저 체크)
  const retentionKey = `${dateStr}_retention_purge`;
  if (h === 4 && m === 0 && !firedToday.has(retentionKey)) {
    firedToday.add(retentionKey);
    void runRetentionPurge(formatKST(kst));
  }

  // 미국 정규장 개장·마감 — ET 기준, USD 계좌 전용.
  // 금요일 마감(16:00 ET)은 KST 로 토요일 새벽이므로 아래 KST 주말 가드보다 먼저 평가한다.
  const et = nowETParts();
  if (et.weekday >= 1 && et.weekday <= 5) {
    const usOpenKey = `${et.dateStr}_us_market_open`;
    if (et.h === 9 && et.m === 30 && !firedToday.has(usOpenKey)) {
      firedToday.add(usOpenKey);
      console.log(`[Scheduler] ${formatKST(kst)} KST — 미국장 개장(09:30 ET) — USD auto 계좌 시작`);
      callSchedulerAPI("us-market-open");
    }

    const usCloseKey = `${et.dateStr}_us_market_close`;
    if (et.h === 16 && et.m === 0 && !firedToday.has(usCloseKey)) {
      firedToday.add(usCloseKey);
      console.log(`[Scheduler] ${formatKST(kst)} KST — 미국장 마감(16:00 ET) — USD 계좌 일시정지`);
      callSchedulerAPI("us-market-close");
    }
  }

  // 평일만 (1=월 ~ 5=금) — 이하 한국장 이벤트
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
