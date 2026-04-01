import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { inferStrategyType } from "@/lib/strategy-type";

// POST: 전략 DSL + 백테스트 결과를 한 번에 저장
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { name, description, dsl, backtestResult, aiSummary, aiScore, score } = body;

    if (!name?.trim()) {
      return NextResponse.json({ error: "전략 이름을 입력해주세요." }, { status: 400 });
    }
    if (!dsl) {
      return NextResponse.json({ error: "전략 설정 정보가 없습니다." }, { status: 400 });
    }

    // 전략 DSL에 이름/설명 반영
    const dslToSave = {
      ...dsl,
      name: name.trim(),
      description: description?.trim() || "",
      updated_at: new Date().toISOString(),
    };

    const strategyType = inferStrategyType(name.trim(), description?.trim() ?? "", dsl);

    // Strategy + BacktestResult 트랜잭션으로 함께 저장
    const result = await prisma.$transaction(async (tx) => {
      const strategy = await tx.strategy.create({
        data: {
          name: name.trim(),
          description: description?.trim() || null,
          settings: JSON.stringify(dslToSave),
          strategyType,
        },
      });

      let backtestRecord = null;
      if (backtestResult) {
        // 무거운 배열 데이터(equity, dates, tradesList)는 summary에 통째로 저장
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
          equity: backtestResult.equity,
          benchmarkEquity: backtestResult.benchmarkEquity,
          dates: backtestResult.dates,
          warnings: backtestResult.warnings,
          executionTime: backtestResult.executionTime,
          aiSummary: aiSummary ?? null,
          aiScore: aiScore ?? null,
        };

        backtestRecord = await tx.backtestResult.create({
          data: {
            strategyId: strategy.id,
            summary: JSON.stringify(summary),
            trades: JSON.stringify(backtestResult.tradesList ?? []),
          },
        });
      }

      return { strategy, backtestRecord };
    });

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
