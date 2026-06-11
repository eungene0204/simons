import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from "@/lib/get-user";

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
