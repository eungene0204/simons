import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { calcBuyCost } from '@/lib/order-engine';
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user';
import { moneyToNumber, toMoney } from '@/lib/server/assetService';

// DELETE: PENDING 주문 취소 (매수의 경우 예약 현금 환급)
export async function DELETE(
  _request: Request,
  { params }: { params: { id: string; orderId: string } }
) {
  try {
    const { userId } = await getOwnershipContext();
    const cancelled = await prisma.$transaction(async (tx) => {
      const account = await tx.virtualAccount.findFirst({
        where: withOwnership({ id: params.id }, userId),
        select: { id: true },
      });
      if (!account) throw new Error('ACCOUNT_NOT_FOUND');

      const order = await tx.virtualOrder.findFirst({
        where: { id: params.orderId, accountId: params.id },
      });

      if (!order) throw new Error('ORDER_NOT_FOUND');
      if (order.status !== 'PENDING') throw new Error('NOT_PENDING');

      // 매수 지정가 취소 → 예약 현금 환급
      if (order.side === 'BUY') {
        const refund = calcBuyCost(moneyToNumber(order.price), order.quantity);
        const account = await tx.virtualAccount.findUnique({ where: { id: params.id } });
        if (!account) throw new Error('ACCOUNT_NOT_FOUND');
        await tx.virtualAccount.update({
          where: { id: params.id },
          data: { currentCash: toMoney(moneyToNumber(account.currentCash) + refund) },
        });
      }

      return tx.virtualOrder.update({
        where: { id: params.orderId },
        data: { status: 'CANCELLED' },
      });
    });

    return NextResponse.json({ success: true, id: cancelled.id });
  } catch (error: any) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    const msg = error?.message;
    if (msg === 'ACCOUNT_NOT_FOUND')
      return NextResponse.json({ error: '계좌를 찾을 수 없습니다.' }, { status: 404 });
    if (msg === 'ORDER_NOT_FOUND')
      return NextResponse.json({ error: '주문을 찾을 수 없습니다.' }, { status: 404 });
    if (msg === 'NOT_PENDING')
      return NextResponse.json({ error: '취소 가능한 주문이 아닙니다.' }, { status: 400 });
    console.error('Failed to cancel order:', error);
    return NextResponse.json({ error: 'Failed to cancel order' }, { status: 500 });
  }
}
