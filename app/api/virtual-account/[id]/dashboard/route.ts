import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user';
import { buildDashboardStats } from '@/lib/server/virtualAccountDashboard';

export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext();
    const account = await prisma.virtualAccount.findFirst({
      where: withOwnership({ id: params.id }, userId),
    });
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }

    // 체결된 주문 전체 조회
    const orders = await prisma.virtualOrder.findMany({
      where: { accountId: params.id, status: 'FILLED' },
      orderBy: { filledAt: 'asc' },
    });

    const stats = buildDashboardStats(account, orders);

    return NextResponse.json(stats);
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to fetch dashboard stats:', error);
    return NextResponse.json({ error: 'Failed to fetch dashboard stats' }, { status: 500 });
  }
}
