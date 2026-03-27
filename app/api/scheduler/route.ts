/**
 * POST /api/scheduler
 *
 * 스케줄러 전용 배치 엔드포인트.
 * scripts/scheduler.py 에서 KST 시간에 맞춰 호출한다.
 *
 * action:
 *   pre-market     — 08:50 KST: 추적 종목 시세 캐시 사전 로드
 *   market-open    — 09:00 KST: auto 모드 계좌 전체 시작
 *   market-refresh — 09:05~15:25 KST 1분 간격: 실행 중인 계좌 전체 새로고침
 *   market-close   — 15:30 KST: 실행 중인 계좌 전체 일시정지
 *
 * 보안: SCHEDULER_SECRET 환경변수가 설정된 경우 Authorization 헤더 검증
 */

import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

const APP_URL = process.env.APP_URL || "http://localhost:3000";
const SCHEDULER_SECRET = process.env.SCHEDULER_SECRET;

function isAuthorized(request: Request): boolean {
  if (!SCHEDULER_SECRET) return true; // 미설정 시 개발 편의상 허용
  const auth = request.headers.get("Authorization");
  return auth === `Bearer ${SCHEDULER_SECRET}`;
}

export async function POST(request: Request) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
  const { action } = await request.json();
  const now = new Date().toISOString();

  // ── pre-market: 08:50 KST — 캐시 사전 워밍 ───────────────────────────────
  if (action === "pre-market") {
    // 모든 running/paused 계좌의 추적 종목을 모아 시세 사전 조회
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
        await fetch(`${BACKEND_URL}/market/prices`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbols: Array.from(allSymbols) }),
        });
      } catch (e) {
        console.error(`[Scheduler] pre-market cache warming failed:`, e);
      }
    }

    console.log(`[Scheduler] pre-market ${now} — ${allSymbols.size}개 종목 캐시 워밍`);
    return NextResponse.json({ action, processedAt: now, symbolCount: allSymbols.size });
  }

  // ── market-open: 09:00 KST ──────────────────────────────────────────────
  if (action === "market-open") {
    // tradingMode=auto && strategyId 있는 계좌 전체
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

      // 상태 없음 → strategy/start 로 초기화
      try {
        const res = await fetch(
          `${APP_URL}/api/virtual-account/${account.id}/strategy/start`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          }
        );
        const data = await res.json();
        results.push({
          accountId: account.id,
          result: res.ok ? "started" : "error",
          detail: data,
        });
      } catch (e) {
        results.push({ accountId: account.id, result: "error", detail: String(e) });
      }
    }

    console.log(`[Scheduler] market-open ${now} — ${results.length}개 계좌 처리`);
    return NextResponse.json({ action, processedAt: now, results });
  }

  // ── market-refresh: 5분 간격 (09:05 ~ 15:25 KST) ───────────────────────
  if (action === "market-refresh") {
    const states = await prisma.virtualMarketState.findMany({
      where: { status: "running" },
    });

    const results = [];
    for (const state of states) {
      try {
        const res = await fetch(
          `${APP_URL}/api/virtual-market/${state.accountId}/refresh`,
          { method: "POST" }
        );
        const data = await res.json();
        results.push({
          accountId: state.accountId,
          refreshed: data.refreshed ?? false,
          logs: data.logs?.length ?? 0,
        });
      } catch (e) {
        results.push({ accountId: state.accountId, refreshed: false, error: String(e) });
      }
    }

    console.log(`[Scheduler] market-refresh ${now} — ${results.length}개 계좌 새로고침`);
    return NextResponse.json({ action, processedAt: now, results });
  }

  // ── market-close: 15:30 KST ─────────────────────────────────────────────
  if (action === "market-close") {
    const updated = await prisma.virtualMarketState.updateMany({
      where: { status: "running" },
      data: { status: "paused", updatedAt: new Date() },
    });

    console.log(`[Scheduler] market-close ${now} — ${updated.count}개 계좌 일시정지`);
    return NextResponse.json({ action, processedAt: now, paused: updated.count });
  }

  return NextResponse.json({ error: `Unknown action: ${action}` }, { status: 400 });
}
