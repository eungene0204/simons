import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

function mapOrder(o: any) {
  const price = o.filledPrice ?? o.price;
  return {
    id: o.id,
    accountId: o.accountId,
    type: o.side.toLowerCase() as 'buy' | 'sell',
    symbol: o.symbol,
    name: o.name ?? o.symbol,
    quantity: o.quantity,
    price,
    totalAmount: o.quantity * price,
    timestamp: (o.filledAt ?? o.createdAt).toISOString(),
  };
}

// GET: 체결된 주문 이력 조회
export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const orders = await prisma.virtualOrder.findMany({
      where: { accountId: params.id, status: 'FILLED' },
      orderBy: { createdAt: 'desc' },
    });
    return NextResponse.json(orders.map(mapOrder));
  } catch (error) {
    console.error('Failed to fetch orders:', error);
    return NextResponse.json({ error: 'Failed to fetch orders' }, { status: 500 });
  }
}

// POST: 주문 실행 (매수/매도 — 포지션과 현금을 트랜잭션으로 원자 처리)
export async function POST(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { type, symbol, name, quantity, price } = await request.json();

    if (!type || !symbol || !quantity || !price) {
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
    }

    const qty = Number(quantity);
    const prc = Number(price);
    const totalAmount = qty * prc;

    const order = await prisma.$transaction(async (tx) => {
      const account = await tx.virtualAccount.findUnique({
        where: { id: params.id },
      });
      if (!account) throw new Error('ACCOUNT_NOT_FOUND');

      if (type === 'buy') {
        if (account.currentCash < totalAmount) throw new Error('INSUFFICIENT_BALANCE');

        // 기존 포지션 upsert — 평균단가 재계산
        const existing = await tx.virtualPosition.findUnique({
          where: { accountId_symbol: { accountId: params.id, symbol } },
        });
        if (existing) {
          const newQty = existing.quantity + qty;
          const newAvgPrice =
            (existing.avgPrice * existing.quantity + prc * qty) / newQty;
          await tx.virtualPosition.update({
            where: { accountId_symbol: { accountId: params.id, symbol } },
            data: { quantity: newQty, avgPrice: newAvgPrice, name: name ?? existing.name },
          });
        } else {
          await tx.virtualPosition.create({
            data: { accountId: params.id, symbol, name: name ?? symbol, quantity: qty, avgPrice: prc },
          });
        }

        await tx.virtualAccount.update({
          where: { id: params.id },
          data: { currentCash: account.currentCash - totalAmount },
        });

      } else {
        // sell
        const existing = await tx.virtualPosition.findUnique({
          where: { accountId_symbol: { accountId: params.id, symbol } },
        });
        if (!existing || existing.quantity < qty) throw new Error('INSUFFICIENT_POSITION');

        const newQty = existing.quantity - qty;
        if (newQty === 0) {
          await tx.virtualPosition.delete({
            where: { accountId_symbol: { accountId: params.id, symbol } },
          });
        } else {
          await tx.virtualPosition.update({
            where: { accountId_symbol: { accountId: params.id, symbol } },
            data: { quantity: newQty },
          });
        }

        await tx.virtualAccount.update({
          where: { id: params.id },
          data: { currentCash: account.currentCash + totalAmount },
        });
      }

      return tx.virtualOrder.create({
        data: {
          accountId: params.id,
          symbol,
          name: name ?? symbol,
          side: type.toUpperCase(),
          type: 'MARKET',
          quantity: qty,
          price: prc,
          filledPrice: prc,
          status: 'FILLED',
          filledAt: new Date(),
        },
      });
    });

    return NextResponse.json(mapOrder(order));
  } catch (error: any) {
    const msg = error?.message;
    if (msg === 'INSUFFICIENT_BALANCE')
      return NextResponse.json({ error: '잔액이 부족합니다.' }, { status: 400 });
    if (msg === 'INSUFFICIENT_POSITION')
      return NextResponse.json({ error: '보유 수량이 부족합니다.' }, { status: 400 });
    if (msg === 'ACCOUNT_NOT_FOUND')
      return NextResponse.json({ error: '계좌를 찾을 수 없습니다.' }, { status: 404 });
    console.error('Failed to execute order:', error);
    return NextResponse.json({ error: 'Failed to execute order' }, { status: 500 });
  }
}
