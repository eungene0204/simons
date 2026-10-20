import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { getOwnershipContext, isUnauthorizedAccessError } from '@/lib/get-user';
import { getAccountSettlementValues } from '@/lib/server/assetService';
import { buildSharedStrategyCards } from '@/lib/server/sharedStrategies';

// '전략공유' 목록 — 사용자들이 공개로 전환한 저장 전략과, 그 전략을 쓰는 공개 계좌의 수익률.
export async function GET() {
  try {
    await getOwnershipContext();
    const strategies = await prisma.strategy.findMany({
      where: { isPublic: true, isSaved: true, deletedAt: null },
      orderBy: { updatedAt: 'desc' },
      select: { id: true, userId: true, name: true, description: true, settings: true },
    });
    const accounts =
      strategies.length > 0
        ? await prisma.virtualAccount.findMany({
            where: { isPublic: true, strategyId: { in: strategies.map((s) => s.id) } },
            include: { VirtualPosition: true },
          })
        : [];
    const settlementValues = await getAccountSettlementValues(prisma, accounts.map((a) => a.id));

    return NextResponse.json({ strategies: buildSharedStrategyCards(strategies, accounts, settlementValues) });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to fetch shared strategies:', error);
    return NextResponse.json({ error: 'Failed to fetch shared strategies' }, { status: 500 });
  }
}
