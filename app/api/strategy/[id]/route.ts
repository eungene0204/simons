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
      // 필수 FK를 가진 연관 레코드 삭제 (BacktestResult는 SetNull이므로 보존됨)
      await tx.strategyEmbedding.deleteMany({ where: { strategyId: params.id } });
      await tx.adviceExperience.deleteMany({ where: { strategyId: params.id } });
      await tx.backtestRun.deleteMany({ where: { strategyId: params.id } });
      if (userId == null) {
        await tx.strategy.delete({ where: { id: params.id } });
      } else {
        await tx.strategy.deleteMany({ where: withOwnership({ id: params.id }, userId) });
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
        aiRisks: summary.aiRisks ?? [],
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
