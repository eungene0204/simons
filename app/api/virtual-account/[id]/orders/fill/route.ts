import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import {
  isPendingFillable,
  calcFee,
  calcTransactionTax,
  calcSellProceeds,
  calcRealizedPnl,
} from '@/lib/order-engine';
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user';
import { moneyToNumber, toMoney } from '@/lib/server/assetService';

// POST: 현재가 기준으로 해당 계좌의 PENDING 주문 체결 시도
// body: { symbol: string, currentPrice: number }
export async function POST(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext();
    const { symbol, currentPrice } = await request.json();
    if (!symbol || !currentPrice) {
      return NextResponse.json({ error: 'Missing symbol or currentPrice' }, { status: 400 });
    }

    const price = Number(currentPrice);
    const account = await prisma.virtualAccount.findFirst({
      where: withOwnership({ id: params.id }, userId),
      select: { id: true },
    });
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }

    // 해당 계좌의 해당 종목 PENDING 주문 전체 조회
    const pendingOrders = await prisma.virtualOrder.findMany({
      where: { accountId: params.id, symbol, status: 'PENDING' },
      orderBy: { createdAt: 'asc' }, // 먼저 들어온 주문 우선 체결
    });

    const filled: string[] = [];

    for (const order of pendingOrders) {
      const orderPrice = moneyToNumber(order.price);
      if (!isPendingFillable(order.side as 'BUY' | 'SELL', orderPrice, price)) continue;

      try {
        const didFill = await prisma.$transaction(async (tx) => {
          const account = await tx.virtualAccount.findUnique({ where: { id: params.id } });
          if (!account) throw new Error('ACCOUNT_NOT_FOUND');

          const filledPrice = orderPrice; // 지정가로 체결
          const fee = calcFee(filledPrice, order.quantity);

          if (order.side === 'BUY') {
            // VirtualTrader(백엔드 30초 루프)와의 이중 체결 방지:
            // status=PENDING 조건부 updateMany로 원자적으로 선점, 실패하면 skip
            const claimed = await tx.virtualOrder.updateMany({
              where: { id: order.id, status: 'PENDING' },
              data: { status: 'FILLED', filledPrice: toMoney(filledPrice), filledAt: new Date(), fee: toMoney(fee) },
            });
            if (claimed.count === 0) return false;

            // 예약금으로 이미 현금 차감됨 → 포지션만 추가
            const pos = await tx.virtualPosition.findUnique({
              where: { accountId_symbol: { accountId: params.id, symbol: order.symbol } },
            });
            if (pos) {
              const newQty = pos.quantity + order.quantity;
              const avgPrice = moneyToNumber(pos.avgPrice);
              const newAvgPrice = (avgPrice * pos.quantity + filledPrice * order.quantity) / newQty;
              await tx.virtualPosition.update({
                where: { accountId_symbol: { accountId: params.id, symbol: order.symbol } },
                data: { quantity: newQty, avgPrice: toMoney(newAvgPrice) },
              });
            } else {
              await tx.virtualPosition.create({
                data: {
                  id: crypto.randomUUID(),
                  accountId: params.id,
                  symbol: order.symbol,
                  name: order.name ?? order.symbol,
                  quantity: order.quantity,
                  avgPrice: toMoney(filledPrice),
                  updatedAt: new Date(),
                },
              });
            }
            // 수수료 정산 (예약금에서 추정 수수료를 포함해 차감했으므로 실제 수수료와 차이는 무시)
            return true;
          }

          // 매도: 포지션 차감 + 현금 추가
          const pos = await tx.virtualPosition.findUnique({
            where: { accountId_symbol: { accountId: params.id, symbol: order.symbol } },
          });
          if (!pos || pos.quantity < order.quantity) {
            // 포지션 부족 → 주문 취소 처리
            await tx.virtualOrder.updateMany({
              where: { id: order.id, status: 'PENDING' },
              data: { status: 'CANCELLED' },
            });
            return false;
          }

          const avgBuyPrice = moneyToNumber(pos.avgPrice);
          const tax = calcTransactionTax(filledPrice, order.quantity);
          const realizedPnl = calcRealizedPnl(filledPrice, avgBuyPrice, order.quantity, fee, tax);

          const claimed = await tx.virtualOrder.updateMany({
            where: { id: order.id, status: 'PENDING' },
            data: { status: 'FILLED', filledPrice: toMoney(filledPrice), filledAt: new Date(), fee: toMoney(fee), tax: toMoney(tax), avgBuyPrice: toMoney(avgBuyPrice), realizedPnl: toMoney(realizedPnl) },
          });
          if (claimed.count === 0) return false;

          const newQty = pos.quantity - order.quantity;
          if (newQty === 0) {
            await tx.virtualPosition.delete({
              where: { accountId_symbol: { accountId: params.id, symbol: order.symbol } },
            });
          } else {
            await tx.virtualPosition.update({
              where: { accountId_symbol: { accountId: params.id, symbol: order.symbol } },
              data: { quantity: newQty },
            });
          }

          const proceeds = calcSellProceeds(filledPrice, order.quantity);
          await tx.virtualAccount.update({
            where: { id: params.id },
            data: { currentCash: toMoney(moneyToNumber(account.currentCash) + proceeds) },
          });
          return true;
        });

        if (didFill) filled.push(order.id);
      } catch {
        // 개별 주문 체결 실패는 무시하고 다음 주문 처리
      }
    }

    return NextResponse.json({ filled, count: filled.length });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to fill pending orders:', error);
    return NextResponse.json({ error: 'Failed to fill pending orders' }, { status: 500 });
  }
}
