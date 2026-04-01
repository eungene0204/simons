import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function DELETE(_req: Request, { params }: { params: { id: string } }) {
  try {
    // 자동매매 중인 연결 계좌 조회
    const autoTradingAccounts = await prisma.virtualAccount.findMany({
      where: { strategyId: params.id, tradingMode: { not: "manual" } },
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
      await tx.backtestResult.deleteMany({ where: { strategyId: params.id } });
      await tx.strategy.delete({ where: { id: params.id } });
    });

    return NextResponse.json({ ok: true, stoppedAccounts: autoTradingAccounts });
  } catch (error) {
    console.error("Failed to delete strategy:", error);
    return NextResponse.json({ error: "Failed to delete strategy" }, { status: 500 });
  }
}

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  try {
    const strategy = await prisma.strategy.findUnique({
      where: { id: params.id },
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
        warnings: summary.warnings ?? [],
        aiSummary: summary.aiSummary ?? null,
        aiScore: summary.aiScore ?? null,
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
    console.error("Failed to fetch strategy:", error);
    return NextResponse.json({ error: "Failed to fetch strategy" }, { status: 500 });
  }
}
