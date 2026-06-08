import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user';

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
    const { userId } = await getOwnershipContext();
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);

    const [totalAccounts, runningCount, autoCount, todayOrders, totalPositions, dailyPnlAgg, accounts] =
      await Promise.all([
        prisma.virtualAccount.count({ where: withOwnership({}, userId) }),
        prisma.virtualMarketState.count({
          where: {
            status: 'running',
            ...(userId != null ? {
              VirtualAccount: {
                userId,
              },
            } : {}),
          },
        }),
        prisma.virtualAccount.count({ where: withOwnership({ tradingMode: 'auto' }, userId) }),
        prisma.virtualOrder.count({
          where: {
            status: 'FILLED',
            filledAt: { gte: todayStart },
            ...(userId != null ? {
              VirtualAccount: {
                userId,
              },
            } : {}),
          },
        }),
        prisma.virtualPosition.count({
          where: userId != null ? {
            VirtualAccount: {
              userId,
            },
          } : {},
        }),
        prisma.virtualOrder.aggregate({
          where: {
            status: 'FILLED',
            side: 'SELL',
            filledAt: { gte: todayStart },
            ...(userId != null ? {
              VirtualAccount: {
                userId,
              },
            } : {}),
          },
          _sum: { realizedPnl: true },
        }),
        prisma.virtualAccount.findMany({
          where: withOwnership({}, userId),
          select: {
            currentCash: true,
            VirtualPosition: {
              select: {
                quantity: true,
                avgPrice: true,
                currentPrice: true,
              },
            },
          },
        }),
      ]);

    const totalEvaluation = accounts.reduce((accountSum, account) => {
      const positionValue = account.VirtualPosition.reduce(
        (positionSum, position) =>
          positionSum + position.quantity * (position.currentPrice ?? position.avgPrice),
        0
      );
      return accountSum + account.currentCash + positionValue;
    }, 0);

    return NextResponse.json({
      totalAccounts,
      runningAccounts: runningCount,
      autoAccounts: autoCount,
      todayFilledOrders: todayOrders,
      totalPositions,
      dailyPnl: dailyPnlAgg._sum.realizedPnl ?? 0,
      totalEvaluation,
    } satisfies TradingStatusData);
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to fetch trading status:', error);
    return NextResponse.json({ error: 'Failed to fetch trading status' }, { status: 500 });
  }
}
