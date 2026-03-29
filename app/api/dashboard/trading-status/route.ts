import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export interface TradingStatusData {
  totalAccounts: number;
  runningAccounts: number;
  autoAccounts: number;
  todayFilledOrders: number;
  totalPositions: number;
  dailyPnl: number;
  totalEvaluation: number;
}

export async function GET() {
  try {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);

    const [totalAccounts, runningCount, autoCount, todayOrders, totalPositions, dailyPnlAgg, evalAgg] =
      await Promise.all([
        prisma.virtualAccount.count(),
        prisma.virtualMarketState.count({ where: { status: 'running' } }),
        prisma.virtualAccount.count({ where: { tradingMode: 'auto' } }),
        prisma.virtualOrder.count({ where: { status: 'FILLED', filledAt: { gte: todayStart } } }),
        prisma.virtualPosition.count(),
        prisma.virtualOrder.aggregate({
          where: { status: 'FILLED', side: 'SELL', filledAt: { gte: todayStart } },
          _sum: { realizedPnl: true },
        }),
        prisma.virtualAccount.aggregate({ _sum: { totalValue: true } }),
      ]);

    return NextResponse.json({
      totalAccounts,
      runningAccounts: runningCount,
      autoAccounts: autoCount,
      todayFilledOrders: todayOrders,
      totalPositions,
      dailyPnl: dailyPnlAgg._sum.realizedPnl ?? 0,
      totalEvaluation: evalAgg._sum.totalValue ?? 0,
    } satisfies TradingStatusData);
  } catch (error) {
    console.error('Failed to fetch trading status:', error);
    return NextResponse.json({ error: 'Failed to fetch trading status' }, { status: 500 });
  }
}
