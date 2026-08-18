import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from "@/lib/get-user";
import { buildHistorySummary, historySummaryHasContent } from "@/lib/backtest-history";

function parseJsonField(value: string | null | undefined, fallback: any) {
  if (!value) return fallback;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function historyToSummary(history: any, settings?: Record<string, unknown> | null) {
  if (!history) return null;
  const conditions = parseJsonField(history.conditions, {});
  // 기간·초기 자본은 conditions(2026-08-18부터 저장)에서, 그 전 행은 원천 Strategy.settings
  // (실행 요청과 같은 키: period/startDate/endDate/risk.init_cash)에서 되살린다.
  const summary = buildHistorySummary({
    conditions,
    universeName: history.universe,
    strategyName: history.strategyName,
    executedRequest: settings ?? null,
  });
  // 표시용 배지를 만들지 못하는 행(raw DSL conditions만 가진 save-with-backtest 행 등)은
  // SOT로 채택하지 않고 다음 후보(표시용 names를 가진 auto-save 행)로 넘긴다.
  if (!historySummaryHasContent(summary)) return null;

  return { id: history.id, ...summary, conditions };
}

async function findBacktestHistorySummary(
  strategy: any,
  strategyId: string,
  userId: number | null,
  settings: Record<string, unknown> | null
) {
  const directHistory = await prisma.backtestHistory.findFirst({
    where: { OR: [{ strategyId }, { cacheKey: strategyId }] },
    orderBy: { createdAt: "desc" },
  });
  const directSummary = historyToSummary(directHistory, settings);
  if (directSummary) return directSummary;

  if (userId != null) {
    const userHistoryLink = await prisma.userBacktestHistory.findFirst({
      where: {
        userId,
        BacktestHistory: {
          strategyName: strategy.name,
          isVisible: true,
        },
      },
      orderBy: { savedAt: "desc" },
      include: { BacktestHistory: true },
    });
    const userSummary = historyToSummary(userHistoryLink?.BacktestHistory, settings);
    if (userSummary) return userSummary;
  }

  const visibleHistory = await prisma.backtestHistory.findFirst({
    where: {
      strategyName: strategy.name,
      isVisible: true,
    },
    orderBy: { createdAt: "desc" },
  });
  return historyToSummary(visibleHistory, settings) ?? historyToSummary(directHistory, settings);
}

export async function DELETE(_req: Request, { params }: { params: { id: string } }) {
  try {
    const { userId } = await getOwnershipContext()
    if (userId != null) {
      const strategy = await prisma.strategy.findFirst({
        where: withOwnership({ id: params.id }, userId),
        select: { id: true },
      })

      if (!strategy) {
        return NextResponse.json({ error: "Strategy not found" }, { status: 404 })
      }
    }

    // 자동매매 중인 연결 계좌 조회
    const autoTradingAccounts = await prisma.virtualAccount.findMany({
      where:
        userId == null
          ? { strategyId: params.id, tradingMode: { not: "manual" } }
          : withOwnership({ strategyId: params.id, tradingMode: { not: "manual" } }, userId),
      select: { id: true, name: true },
    });

    await prisma.$transaction(async (tx) => {
      // 연결 계좌 자동매매 중지
      if (autoTradingAccounts.length > 0) {
        const accountIds = autoTradingAccounts.map((a) => a.id);
        await tx.virtualMarketState.deleteMany({ where: { accountId: { in: accountIds } } });
        await tx.virtualAccount.updateMany({
          where: { id: { in: accountIds } },
          data: { tradingMode: "manual" },
        });
      }
      // 소프트 삭제: 사용자 목록에서만 숨기고(isSaved=false) DB 레코드는 보존한다.
      // 백테스트 결과(BacktestHistory/BacktestResult/BacktestRun)는 공유 캐시이자
      // 코칭 agent 학습 데이터이므로 절대 삭제하지 않는다.
      if (userId == null) {
        await tx.strategy.update({
          where: { id: params.id },
          data: { isSaved: false, deletedAt: new Date() },
        });
      } else {
        await tx.strategy.updateMany({
          where: withOwnership({ id: params.id }, userId),
          data: { isSaved: false, deletedAt: new Date() },
        });
      }
    }, { timeout: 15000 });

    return NextResponse.json({ ok: true, stoppedAccounts: autoTradingAccounts });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to delete strategy:", error);
    return NextResponse.json({ error: "Failed to delete strategy" }, { status: 500 });
  }
}

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  try {
    const { userId } = await getOwnershipContext()
    const strategy =
      userId == null
        ? await prisma.strategy.findUnique({
            where: { id: params.id },
            include: {
              BacktestResult: {
                orderBy: { createdAt: "desc" },
                take: 1,
              },
            },
          })
        : await prisma.strategy.findFirst({
            where: withOwnership({ id: params.id }, userId),
            include: {
              BacktestResult: {
                orderBy: { createdAt: "desc" },
                take: 1,
              },
            },
          });

    if (!strategy) {
      return NextResponse.json({ error: "Strategy not found" }, { status: 404 });
    }

    let settings: any = null;
    try {
      settings = JSON.parse(strategy.settings);
    } catch {}
    const historySummary = await findBacktestHistorySummary(strategy, strategy.id, userId, settings);

    let backtestResult = null;
    if (strategy.BacktestResult.length > 0) {
      const record = strategy.BacktestResult[0];
      let summary: any = {};
      let tradesList: any[] = [];
      try { summary = JSON.parse(record.summary); } catch {}
      try { tradesList = JSON.parse(record.trades ?? "[]"); } catch {}
      backtestResult = {
        ...summary,
        executionId: record.id,
        strategyId: strategy.id,
        tradesList,
        monthlyReturns: summary.monthlyReturns ?? {},
        yearlyReturns: summary.yearlyReturns ?? {},
        signals: summary.signals ?? tradesList.map((t: any) => ({
          date: t.date,
          symbol: t.symbol,
          type: t.type === "buy" ? "entry" : "exit",
          condition: t.reason ?? "",
          price: t.price,
          quantity: t.quantity,
          amount: t.amount,
        })),
        perAssetStats: summary.perAssetStats ?? null,
        topSymbols: summary.topSymbols ?? [],
        topAssetStats: summary.topAssetStats ?? [],
        warnings: summary.warnings ?? [],
        aiSummary: summary.aiSummary ?? null,
        aiScore: summary.aiScore ?? null,
        aiStrengths: summary.aiStrengths ?? [],
        aiWeaknesses: summary.aiWeaknesses ?? [],
        aiImprovements: summary.aiImprovements ?? [],
        aiRisks: summary.aiRisks ?? [],
        advisorScore: summary.advisorScore ?? null,
        riskScore: summary.riskScore ?? null,
        overfitRisk: summary.overfitRisk ?? null,
      };
    }

    return NextResponse.json({
      id: strategy.id,
      name: strategy.name,
      description: strategy.description,
      settings,
      historySummary,
      backtestResult,
    });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch strategy:", error);
    return NextResponse.json({ error: "Failed to fetch strategy" }, { status: 500 });
  }
}
