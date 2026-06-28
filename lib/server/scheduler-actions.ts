/**
 * 스케줄러 액션 핵심 로직 (in-process 호출 가능)
 *
 *   pre-market     — 08:50 KST: 추적 종목 시세 캐시 사전 로드
 *   market-open    — 09:00 KST: auto 모드 계좌 전체 시작 (running 전환)
 *   market-refresh — (비활성) 시그널 평가·체결은 VirtualTrader 로 일원화됨
 *   market-close   — 15:30 KST: 실행 중인 계좌 전체 일시정지 (paused 전환)
 *
 * 자동매매(시그널 평가·체결)의 정본은 FastAPI 백엔드의 VirtualTrader 단일 엔진이다
 * (backend/engine/virtual_trader.py, 30초 간격). 이 TS 스케줄러는 계좌의
 * running/paused 생명주기(개장 시작·마감 정지)와 캐시 워밍만 담당한다.
 *
 * HTTP 라우트(app/api/scheduler)와 인-프로세스 스케줄러(lib/scheduler) 양쪽에서
 * 이 함수를 직접 호출한다. 내부에서 다른 라우트를 HTTP 로 self-fetch 하지 않고
 * lib 함수(startAccountStrategy)를 직접 호출하므로,
 * dev 모드의 HMR 라우트 재컴파일과 무관하게 안정적으로 동작한다.
 */

import { prisma } from "@/lib/prisma";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";
import { startAccountStrategy } from "@/lib/server/strategy-start";

export type SchedulerActionResult = Record<string, unknown>;

export async function runSchedulerAction(
  action: string
): Promise<SchedulerActionResult> {
  const now = new Date().toISOString();

  // ── pre-market: 08:50 KST — 캐시 사전 워밍 ───────────────────────────────
  if (action === "pre-market") {
    const states = await prisma.virtualMarketState.findMany({
      where: { status: { in: ["running", "paused"] } },
    });

    const allSymbols = new Set<string>();
    for (const state of states) {
      try {
        const symbols: string[] = JSON.parse(state.symbols);
        symbols.forEach((s) => allSymbols.add(s));
      } catch { /* ignore */ }
    }

    if (allSymbols.size > 0) {
      try {
        await fetchStockPriceSnapshots(Array.from(allSymbols), {
          subscribe: true,
          mode: "standard",
        });
      } catch (e) {
        console.error(`[Scheduler] pre-market cache warming failed:`, e);
      }
    }

    console.log(`[Scheduler] pre-market ${now} — ${allSymbols.size}개 종목 캐시 워밍`);
    return { action, processedAt: now, symbolCount: allSymbols.size };
  }

  // ── market-open: 09:00 KST ──────────────────────────────────────────────
  if (action === "market-open") {
    const accounts = await prisma.virtualAccount.findMany({
      where: {
        tradingMode: "auto",
        strategyId: { not: null },
      },
    });

    const results = [];
    for (const account of accounts) {
      const state = await prisma.virtualMarketState.findUnique({
        where: { accountId: account.id },
      });

      // 이미 실행 중이면 건너뜀
      if (state?.status === "running") {
        results.push({ accountId: account.id, result: "already_running" });
        continue;
      }

      // paused 상태면 resume (symbols 유지, startDate 갱신 없이)
      if (state?.status === "paused") {
        await prisma.virtualMarketState.update({
          where: { accountId: account.id },
          data: { status: "running", updatedAt: new Date() },
        });
        results.push({ accountId: account.id, result: "resumed" });
        continue;
      }

      // 상태 없음 → 전략 자동 실행 로직 직접 호출 (HTTP self-fetch 제거)
      try {
        const data = await startAccountStrategy({
          accountId: account.id,
          userId: account.userId,
        });
        results.push({
          accountId: account.id,
          result: data.ok ? "started" : "error",
          detail: data,
        });
      } catch (e) {
        results.push({ accountId: account.id, result: "error", detail: String(e) });
      }
    }

    console.log(`[Scheduler] market-open ${now} — ${results.length}개 계좌 처리`);
    return { action, processedAt: now, results };
  }

  // ── market-refresh: 비활성화됨 (정본 = VirtualTrader) ────────────────────
  // 과거에는 이 액션이 매분 refreshVirtualMarket 로 running 계좌를 매매했으나,
  // FastAPI 백엔드의 VirtualTrader(30초 간격)와 이중으로 같은 계좌를 체결해
  // 이중 디스패치/TOCTOU 이중 체결 위험이 있었다. 트레이드 실행을 VirtualTrader 로
  // 일원화하면서 이 액션은 no-op 으로 둔다. tick·HTTP 라우트 양쪽이 이 함수를
  // 거치므로 여기서 한 번 차단하면 모든 자동 경로가 막힌다.
  // (브라우저 수동 새로고침은 /api/virtual-market/[id]/refresh 가
  //  refreshVirtualMarket 를 직접 호출한다 — 그 경로는 그대로 유지.)
  if (action === "market-refresh") {
    return {
      action,
      processedAt: now,
      skipped: true,
      reason: "trade execution consolidated to VirtualTrader",
    };
  }

  // ── market-close: 15:30 KST ─────────────────────────────────────────────
  if (action === "market-close") {
    const updated = await prisma.virtualMarketState.updateMany({
      where: { status: "running" },
      data: { status: "paused", updatedAt: new Date() },
    });

    console.log(`[Scheduler] market-close ${now} — ${updated.count}개 계좌 일시정지`);
    return { action, processedAt: now, paused: updated.count };
  }

  return { error: `Unknown action: ${action}` };
}
