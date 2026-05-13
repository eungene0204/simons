import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { inferStrategyType } from "@/lib/strategy-type";
import { getTopAssetStats } from "@/lib/backtest-top-symbols";
import { computeStrategyIdFromDsl, triggerVectorMemoryBacktestUpsert } from "@/lib/server/backtestCache";

// POST: 전략 DSL + 백테스트 결과를 한 번에 저장
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { name, description, dsl, backtestResult, aiSummary, aiScore, aiStrengths, aiRisks, score } = body;

    if (!name?.trim()) {
      return NextResponse.json({ error: "전략 이름을 입력해주세요." }, { status: 400 });
    }
    if (!dsl) {
      return NextResponse.json({ error: "전략 설정 정보가 없습니다." }, { status: 400 });
    }

    const strategyId = computeStrategyIdFromDsl(dsl);

    // 전략 DSL에 이름/설명 반영
    const dslToSave = {
      ...dsl,
      id: strategyId,
      name: name.trim(),
      description: description?.trim() || "",
      updated_at: new Date().toISOString(),
    };

    const strategyType = inferStrategyType(name.trim(), description?.trim() ?? "", dsl);

    // Strategy + BacktestResult 트랜잭션으로 함께 저장
    const result = await prisma.$transaction(async (tx) => {
      const strategy =
        typeof tx.strategy.upsert === "function"
          ? await tx.strategy.upsert({
              where: { id: strategyId },
              create: {
                id: strategyId,
                name: name.trim(),
                description: description?.trim() || null,
                settings: JSON.stringify(dslToSave),
                strategyType,
              },
              update: {
                name: name.trim(),
                description: description?.trim() || null,
                settings: JSON.stringify(dslToSave),
                strategyType,
              },
            })
          : await tx.strategy.create({
              data: {
                id: strategyId,
                name: name.trim(),
                description: description?.trim() || null,
                settings: JSON.stringify(dslToSave),
                strategyType,
              },
            });

      let backtestRecord = null;
      if (backtestResult) {
        // 무거운 배열 데이터(equity, dates, tradesList)는 summary에 통째로 저장
        const topAssetStats = getTopAssetStats(backtestResult.perAssetStats, 10);
        const summary = {
          totalReturn: backtestResult.totalReturn,
          cagr: backtestResult.cagr,
          maxDrawdown: backtestResult.maxDrawdown,
          score: score ?? null,
          profitFactor: backtestResult.profitFactor,
          sharpe: backtestResult.sharpe,
          sortino: backtestResult.sortino,
          kelly: backtestResult.kelly,
          volatility: backtestResult.volatility,
          buyAndHoldReturn: backtestResult.buyAndHoldReturn,
          trades: backtestResult.trades,
          avgProfit: backtestResult.avgProfit,
          avgLoss: backtestResult.avgLoss,
          maxConsecutiveWins: backtestResult.maxConsecutiveWins,
          maxConsecutiveLosses: backtestResult.maxConsecutiveLosses,
          initialCapital: backtestResult.initialCapital,
          finalEquity: backtestResult.finalEquity,
          symbols: backtestResult.symbols,
          perAssetStats: backtestResult.perAssetStats,
          topSymbols: topAssetStats.map((stat) => stat.symbol),
          topAssetStats,
          equity: backtestResult.equity,
          benchmarkEquity: backtestResult.benchmarkEquity,
          dates: backtestResult.dates,
          warnings: backtestResult.warnings,
          executionTime: backtestResult.executionTime,
          aiSummary: aiSummary ?? null,
          aiScore: aiScore ?? null,
          aiStrengths: aiStrengths ?? [],
          aiRisks: aiRisks ?? [],
        };

        if (
          typeof tx.backtestResult.findFirst === "function" &&
          typeof tx.backtestResult.update === "function"
        ) {
          const existingBacktestRecord = await tx.backtestResult.findFirst({
            where: { strategyId: strategy.id },
            orderBy: { createdAt: "desc" },
          });

          if (existingBacktestRecord) {
            backtestRecord = await tx.backtestResult.update({
              where: { id: existingBacktestRecord.id },
              data: {
                summary: JSON.stringify(summary),
                trades: JSON.stringify(backtestResult.tradesList ?? []),
              },
            });
          } else {
            backtestRecord = await tx.backtestResult.create({
              data: {
                strategyId: strategy.id,
                summary: JSON.stringify(summary),
                trades: JSON.stringify(backtestResult.tradesList ?? []),
              },
            });
          }
        } else {
          backtestRecord = await tx.backtestResult.create({
            data: {
              strategyId: strategy.id,
              summary: JSON.stringify(summary),
              trades: JSON.stringify(backtestResult.tradesList ?? []),
            },
          });
        }

        const metrics = {
          totalReturn: backtestResult.totalReturn ?? 0,
          cagr: backtestResult.cagr ?? 0,
          mdd: backtestResult.maxDrawdown ?? 0,
          winRate: backtestResult.winRate ?? 0,
          profitFactor: backtestResult.profitFactor ?? 0,
          buyHold: backtestResult.buyAndHoldReturn ?? 0,
          trades: backtestResult.trades ?? 0,
          executionTime: backtestResult.executionTime ?? 0,
          score: score ?? null,
          aiSummary: aiSummary ?? null,
          aiScore: aiScore ?? null,
          aiStrengths: aiStrengths ?? [],
          aiRisks: aiRisks ?? [],
          perAssetStats: backtestResult.perAssetStats ?? null,
          topSymbols: topAssetStats.map((stat) => stat.symbol),
        };

        if (tx.backtestHistory) {
          const existingHistory =
            backtestResult.cacheKey && typeof tx.backtestHistory.findUnique === "function"
              ? await tx.backtestHistory.findUnique({ where: { cacheKey: backtestResult.cacheKey } })
              : typeof tx.backtestHistory.findFirst === "function"
                ? await tx.backtestHistory.findFirst({
                    where: { strategyId: strategy.id },
                    orderBy: { createdAt: "desc" },
                  })
                : null;

          const historyData = {
            strategyId: strategy.id,
            strategyName: name.trim(),
            universe: dslToSave?.universe?.id ?? (backtestResult.symbols ?? []).slice(0, 3).join(","),
            conditions: JSON.stringify({ entry: dslToSave.entry ?? null, exit: dslToSave.exit ?? null }),
            metrics: JSON.stringify(metrics),
            result: JSON.stringify({
              ...backtestResult,
              strategyId: strategy.id,
            }),
            cacheKey: backtestResult.cacheKey ?? strategy.id,
            isVisible: true,
          };

          if (existingHistory && typeof tx.backtestHistory.update === "function") {
            await tx.backtestHistory.update({
              where: { id: existingHistory.id },
              data: historyData,
            });
          } else if (typeof tx.backtestHistory.create === "function") {
            await tx.backtestHistory.create({
              data: historyData,
            });
          }
        }
      }

      return { strategy, backtestRecord };
    });

    if (result.backtestRecord) {
      triggerVectorMemoryBacktestUpsert();
    }

    return NextResponse.json({
      strategyId: result.strategy.id,
      backtestResultId: result.backtestRecord?.id ?? null,
      message: "전략과 백테스트 결과가 저장되었습니다.",
    });
  } catch (error) {
    console.error("Failed to save strategy with backtest:", error);
    return NextResponse.json(
      { error: "저장에 실패했습니다." },
      { status: 500 }
    );
  }
}
