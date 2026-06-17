import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import {
  calcFee, calcTransactionTax, calcSellProceeds, calcRealizedPnl,
} from '@/lib/order-engine';
import { isSellAllowed } from '@/lib/listing-status';
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user';
import { moneyToNumber, toMoney } from '@/lib/server/assetService';

// POST /api/virtual-account/[id]/liquidate
// body: { symbol: string }
// 상장폐지/거래정지 종목의 보유 포지션 강제청산
export async function POST(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext();
    const account = await prisma.virtualAccount.findFirst({
      where: withOwnership({ id: params.id }, userId),
      select: { id: true },
    });
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }

    const { symbol } = await request.json();
    if (!symbol) {
      return NextResponse.json({ error: '종목 코드가 필요합니다.' }, { status: 400 });
    }

    const [position, stockRecord] = await Promise.all([
      prisma.virtualPosition.findUnique({
        where: { accountId_symbol: { accountId: params.id, symbol } },
      }),
      prisma.stock.findUnique({ where: { symbol }, select: { listingStatus: true } }),
    ]);

    if (!position) {
      return NextResponse.json({ error: '보유 포지션 없음' }, { status: 404 });
    }

    const listingStatus = stockRecord?.listingStatus ?? 'NORMAL';

    // TRADING_SUSPENDED는 강제청산 불가 (거래소 규정)
    if (listingStatus === 'TRADING_SUSPENDED') {
      return NextResponse.json(
        { error: '매매거래정지 종목은 강제청산이 불가합니다. 거래 재개 후 청산하세요.' },
        { status: 403 }
      );
    }

    // DELISTED: 평가 0원으로 전환 (sell로 청산 불가, 포지션만 제거)
    if (listingStatus === 'DELISTED') {
      await prisma.$transaction(async (tx) => {
        await tx.virtualPosition.delete({
          where: { accountId_symbol: { accountId: params.id, symbol } },
        });
        await tx.delistingAuditLog.create({
          data: {
            accountId: params.id, symbol,
            actionType: 'AUTO_LIQUIDATE',
            previousStatus: listingStatus,
            quantity: position.quantity,
            executionPrice: 0,
            reason: '상장폐지 종목 — 평가금액 0원 처리',
          },
        });
      });
      return NextResponse.json({
        success: true, symbol, quantity: position.quantity,
        executionPrice: 0, proceeds: 0, note: '상장폐지 종목은 0원 처리됩니다.',
      });
    }

    // DELISTING_SCHEDULED 등: 마지막 유효 시세 기준 청산
    const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
    let executionPrice = moneyToNumber(position.currentPrice ?? position.avgPrice);
    try {
      const priceRes = await fetch(`${BACKEND_URL}/market/price/${symbol}`);
      if (priceRes.ok) {
        const data = await priceRes.json();
        if (data.price > 0) executionPrice = data.price;
      }
    } catch {}

    const qty = position.quantity;
    const filledPrice = Math.round(executionPrice * 0.9995); // 슬리피지
    const fee = calcFee(filledPrice, qty);
    const tax = calcTransactionTax(filledPrice, qty);
    const proceeds = calcSellProceeds(filledPrice, qty);
    const avgPrice = moneyToNumber(position.avgPrice);
    const realizedPnl = calcRealizedPnl(filledPrice, avgPrice, qty, fee, tax);

    await prisma.$transaction(async (tx) => {
      await tx.virtualOrder.create({
        data: {
          id: crypto.randomUUID(),
          accountId: params.id, symbol, name: position.name,
          side: 'SELL', type: 'MARKET',
          quantity: qty, price: toMoney(executionPrice), filledPrice: toMoney(filledPrice),
          fee: toMoney(fee), tax: toMoney(tax), avgBuyPrice: toMoney(avgPrice), realizedPnl: toMoney(realizedPnl),
          status: 'FILLED', filledAt: new Date(),
        },
      });

      await tx.virtualAccount.update({
        where: { id: params.id },
        data: { currentCash: { increment: toMoney(proceeds) }, updatedAt: new Date() },
      });

      await tx.virtualPosition.delete({
        where: { accountId_symbol: { accountId: params.id, symbol } },
      });

      await tx.delistingAuditLog.create({
        data: {
          accountId: params.id, symbol,
          actionType: 'AUTO_LIQUIDATE',
          previousStatus: listingStatus,
          quantity: qty,
          executionPrice: filledPrice,
          reason: `강제청산 (상장 상태: ${listingStatus})`,
        },
      });
    });

    return NextResponse.json({ success: true, symbol, quantity: qty, executionPrice: filledPrice, proceeds });
  } catch (error: any) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Forced liquidation failed:', error);
    return NextResponse.json({ error: 'Failed to liquidate position' }, { status: 500 });
  }
}
