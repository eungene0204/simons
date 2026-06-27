/**
 * 스케줄러 액션 핵심 로직 (in-process 호출 가능)
 *
 *   pre-market     — 08:50 KST: 추적 종목 시세 캐시 사전 로드
 *   market-open    — 09:00 KST: auto 모드 계좌 전체 시작
 *   market-refresh — 09:05~15:25 KST: 실행 중인 계좌 전체 새로고침
 *   market-close   — 15:30 KST: 실행 중인 계좌 전체 일시정지
 *
 * HTTP 라우트(app/api/scheduler)와 인-프로세스 스케줄러(lib/scheduler) 양쪽에서
 * 이 함수를 직접 호출한다. 내부에서 다른 라우트를 HTTP 로 self-fetch 하지 않고
 * lib 함수(refreshVirtualMarket / startAccountStrategy)를 직접 호출하므로,
 * dev 모드의 HMR 라우트 재컴파일과 무관하게 안정적으로 동작한다.
 */

import { prisma } from "@/lib/prisma";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";
import { refreshVirtualMarket } from "@/lib/server/virtual-market-refresh";
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

  // ── market-refresh: 09:05 ~ 15:25 KST ───────────────────────────────────
  if (action === "market-refresh") {
    const states = await prisma.virtualMarketState.findMany({
      where: { status: "running" },
    });

    const results = [];
    for (const state of states) {
      try {
        // refresh 로직 직접 호출 (HTTP self-fetch 제거)
        const data = await refreshVirtualMarket(state.accountId);
        results.push({
          accountId: state.accountId,
          refreshed: data.refreshed ?? false,
          logs: data.refreshed ? data.logs.length : 0,
        });
      } catch (e) {
        results.push({ accountId: state.accountId, refreshed: false, error: String(e) });
      }
    }

    console.log(`[Scheduler] market-refresh ${now} — ${results.length}개 계좌 새로고침`);
    return { action, processedAt: now, results };
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
