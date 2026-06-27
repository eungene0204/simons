/**
 * 가상 계좌 전략 자동 실행 시작 핵심 로직 (in-process 호출 가능)
 *
 * HTTP 라우트(app/api/virtual-account/[id]/strategy/start)와
 * 인-프로세스 스케줄러(lib/server/scheduler-actions) 양쪽에서 직접 호출한다.
 * 소유권(userId)은 호출자가 이미 해석해서 넘긴다 — 라우트는 쿠키에서,
 * 스케줄러는 계좌 레코드의 userId 에서.
 */

import { prisma } from "@/lib/prisma";
import { loadStockList } from "@/lib/krx-stocks";
import { resolveTrackedSymbolsForStrategy } from "@/lib/strategy-tracked-symbols";

// 소유권 조건을 where 에 부여한다. userId 가 null(비로그인/테스트)이면 제약 없음.
// get-user.ts 의 withOwnership 과 동일하지만, 그 모듈은 next/headers(cookies)를
// import 하므로 instrumentation 그래프(스케줄러)에 끌어오면 서버 기동이 깨진다.
// 따라서 이 순수 헬퍼만 로컬에 둔다.
function withOwnership<T extends Record<string, unknown>>(
  where: T,
  userId: number | null
): T & Record<string, unknown> {
  return userId == null ? where : { ...where, userId };
}

export type StartAccountStrategyResult =
  | { ok: false; status: number; error: string }
  | {
      ok: true;
      state: Record<string, unknown>;
      symbols: string[];
      symbolNames: Record<string, string>;
      strategyName: string;
      symbolSource: string;
    };

export async function startAccountStrategy(params: {
  accountId: string;
  userId: number | null;
}): Promise<StartAccountStrategyResult> {
  const { accountId, userId } = params;

  const account = await prisma.virtualAccount.findFirst({
    where: withOwnership({ id: accountId }, userId),
  });
  if (!account) {
    return { ok: false, status: 404, error: "Account not found" };
  }
  if (!account.strategyId) {
    return {
      ok: false,
      status: 400,
      error: "전략이 연결되지 않은 계좌입니다. 계좌에 전략을 연결하세요.",
    };
  }

  const strategy = await prisma.strategy.findFirst({
    where: withOwnership({ id: account.strategyId }, userId),
  });
  if (!strategy) {
    return { ok: false, status: 404, error: "연결된 전략을 찾을 수 없습니다." };
  }

  const resolved = await resolveTrackedSymbolsForStrategy({
    strategyId: account.strategyId,
    strategyName: strategy.name,
    strategySettings: strategy.settings,
  });
  const symbols = resolved.symbols;
  const symbolSource = resolved.source;

  if (symbols.length === 0) {
    return {
      ok: false,
      status: 400,
      error: "전략 유니버스에서 종목을 가져올 수 없습니다.",
    };
  }

  // tradingMode를 auto로 설정
  await prisma.virtualAccount.update({
    where: { id: accountId },
    data: { tradingMode: "auto", updatedAt: new Date() },
  });

  const today = new Date().toISOString().split("T")[0];

  // 가상 계좌 상태 생성/업데이트 (running)
  const state = await prisma.virtualMarketState.upsert({
    where: { accountId },
    create: {
      id: crypto.randomUUID(),
      accountId,
      startDate: today,
      status: "running",
      symbols: JSON.stringify(symbols),
      updatedAt: new Date(),
    },
    update: {
      startDate: today,
      status: "running",
      symbols: JSON.stringify(symbols),
      updatedAt: new Date(),
    },
  });

  // 종목명 맵 조회
  const stocks = await loadStockList();
  const nameMap = Object.fromEntries(stocks.map((s) => [s.symbol, s.name]));
  const symbolNames: Record<string, string> = {};
  symbols.forEach((sym) => {
    if (nameMap[sym]) symbolNames[sym] = nameMap[sym];
  });

  console.log(
    `[전략 자동 실행] 계좌=${accountId} 전략="${strategy.name}" 종목=${symbols.length}개 시작 (출처: ${symbolSource})`,
    symbols
  );

  return {
    ok: true,
    state,
    symbols,
    symbolNames,
    strategyName: strategy.name,
    symbolSource, // "backtest" | "universe"
  };
}
