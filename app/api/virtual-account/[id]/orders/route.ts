import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { getStockNameMap } from '@/lib/krx-stocks';
import {
  calcMarketFilledPrice,
  calcFee,
  calcTransactionTax,
  calcBuyCost,
  calcSellProceeds,
  calcRealizedPnl,
  isImmediateFill,
  roundToTick,
} from '@/lib/order-engine';


function mapOrder(o: any, nameMap: Record<string, string>) {
  const filledPrice = o.filledPrice ?? undefined;
  const fee = o.fee ?? (filledPrice ? calcFee(filledPrice, o.quantity) : undefined);
  // name이 없거나 symbol과 동일한 경우 korea-stocks.json에서 조회
  const storedName = o.name as string | null | undefined;
  const resolvedName = storedName && storedName !== o.symbol ? storedName : (nameMap[o.symbol] ?? o.symbol);
  return {
    id: o.id,
    accountId: o.accountId,
    type: o.side.toLowerCase() as 'buy' | 'sell',
    symbol: o.symbol,
    name: resolvedName,
    quantity: o.quantity,
    price: o.price,
    filledPrice,
    fee,
    tax: o.tax ?? undefined,
    avgBuyPrice: o.avgBuyPrice ?? undefined,
    realizedPnl: o.realizedPnl ?? undefined,
    totalAmount: filledPrice ? filledPrice * o.quantity : o.price * o.quantity,
    orderType: o.type as 'MARKET' | 'LIMIT',
    status: o.status as 'PENDING' | 'FILLED' | 'CANCELLED',
    timestamp: o.createdAt.toISOString(),
    filledAt: o.filledAt?.toISOString(),
  };
}

// GET: 주문 조회 (?status=PENDING|FILLED|CANCELLED|ALL, 기본 FILLED)
export async function GET(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { searchParams } = new URL(request.url);
    const statusFilter = searchParams.get('status')?.toUpperCase();

    const where: any = { accountId: params.id };
    if (!statusFilter || statusFilter === 'FILLED') {
      where.status = 'FILLED';
    } else if (statusFilter !== 'ALL') {
      where.status = statusFilter;
    }

    const [orders, nameMap] = await Promise.all([
      prisma.virtualOrder.findMany({ where, orderBy: { createdAt: 'desc' } }),
      getStockNameMap(),
    ]);
    return NextResponse.json(orders.map((o) => mapOrder(o, nameMap)));
  } catch (error) {
    console.error('Failed to fetch orders:', error);
    return NextResponse.json({ error: 'Failed to fetch orders' }, { status: 500 });
  }
}

// POST: 주문 실행 (시장가/지정가 분기)
export async function POST(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { type, symbol, name, quantity, price, orderType = 'MARKET' } = await request.json();

    if (!type || !symbol || !quantity || !price) {
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
    }

    const side = type.toUpperCase() as 'BUY' | 'SELL';
    const qty = Number(quantity);
    const prc = Number(price); // 주문가 (시장가: 현재가, 지정가: 지정한 가격)
    const oType = (orderType as string).toUpperCase() as 'MARKET' | 'LIMIT';

    if (qty <= 0 || prc <= 0) {
      return NextResponse.json({ error: '올바른 수량/가격을 입력하세요.' }, { status: 400 });
    }

    const result = await prisma.$transaction(async (tx) => {
      const account = await tx.virtualAccount.findUnique({ where: { id: params.id } });
      if (!account) throw new Error('ACCOUNT_NOT_FOUND');

      // ── 시장가 주문 ───────────────────────────────────────────────────────
      if (oType === 'MARKET') {
        const filledPrice = calcMarketFilledPrice(prc, side);
        const fee = calcFee(filledPrice, qty);

        if (side === 'BUY') {
          const cost = calcBuyCost(filledPrice, qty);
          if (account.currentCash < cost) throw new Error('INSUFFICIENT_BALANCE');

          await upsertPosition(tx, params.id, symbol, name, qty, filledPrice);
          await tx.virtualAccount.update({
            where: { id: params.id },
            data: { currentCash: account.currentCash - cost },
          });

          return tx.virtualOrder.create({
            data: {
              id: crypto.randomUUID(),
              accountId: params.id, symbol, name: name ?? symbol,
              side, type: 'MARKET', quantity: qty,
              price: prc, filledPrice, fee, status: 'FILLED', filledAt: new Date(),
            },
          });
        } else {
          const pos = await tx.virtualPosition.findUnique({
            where: { accountId_symbol: { accountId: params.id, symbol } },
          });
          const avgBuyPrice = pos?.avgPrice ?? filledPrice;
          const tax = calcTransactionTax(filledPrice, qty);
          const realizedPnl = calcRealizedPnl(filledPrice, avgBuyPrice, qty, fee, tax);
          const proceeds = calcSellProceeds(filledPrice, qty);
          await reducePosition(tx, params.id, symbol, qty);
          await tx.virtualAccount.update({
            where: { id: params.id },
            data: { currentCash: account.currentCash + proceeds },
          });

          return tx.virtualOrder.create({
            data: {
              id: crypto.randomUUID(),
              accountId: params.id, symbol, name: name ?? symbol,
              side, type: 'MARKET', quantity: qty,
              price: prc, filledPrice, fee, tax, avgBuyPrice, realizedPnl,
              status: 'FILLED', filledAt: new Date(),
            },
          });
        }
      }

      // ── 지정가 주문 ───────────────────────────────────────────────────────
      const limitPrice = roundToTick(prc);
      const immediateFill = isImmediateFill(side, limitPrice, prc);

      if (immediateFill) {
        // 즉시 체결: 지정가격으로 체결 (슬리피지 없음)
        const filledPrice = limitPrice;
        const fee = calcFee(filledPrice, qty);

        if (side === 'BUY') {
          const cost = calcBuyCost(filledPrice, qty);
          if (account.currentCash < cost) throw new Error('INSUFFICIENT_BALANCE');
          await upsertPosition(tx, params.id, symbol, name, qty, filledPrice);
          await tx.virtualAccount.update({
            where: { id: params.id },
            data: { currentCash: account.currentCash - cost },
          });

          return tx.virtualOrder.create({
            data: {
              id: crypto.randomUUID(),
              accountId: params.id, symbol, name: name ?? symbol,
              side, type: 'LIMIT', quantity: qty,
              price: limitPrice, filledPrice, fee, status: 'FILLED', filledAt: new Date(),
            },
          });
        } else {
          const pos = await tx.virtualPosition.findUnique({
            where: { accountId_symbol: { accountId: params.id, symbol } },
          });
          const avgBuyPrice = pos?.avgPrice ?? filledPrice;
          const tax = calcTransactionTax(filledPrice, qty);
          const realizedPnl = calcRealizedPnl(filledPrice, avgBuyPrice, qty, fee, tax);
          const proceeds = calcSellProceeds(filledPrice, qty);
          await reducePosition(tx, params.id, symbol, qty);
          await tx.virtualAccount.update({
            where: { id: params.id },
            data: { currentCash: account.currentCash + proceeds },
          });

          return tx.virtualOrder.create({
            data: {
              id: crypto.randomUUID(),
              accountId: params.id, symbol, name: name ?? symbol,
              side, type: 'LIMIT', quantity: qty,
              price: limitPrice, filledPrice, fee, tax, avgBuyPrice, realizedPnl,
              status: 'FILLED', filledAt: new Date(),
            },
          });
        }
      }

      // PENDING 등록
      if (side === 'BUY') {
        // 매수 지정가: 예약 현금 차감 (수수료 추정 포함)
        const reserved = calcBuyCost(limitPrice, qty);
        if (account.currentCash < reserved) throw new Error('INSUFFICIENT_BALANCE');
        await tx.virtualAccount.update({
          where: { id: params.id },
          data: { currentCash: account.currentCash - reserved },
        });
      } else {
        // 매도 지정가: 포지션 수량만 검증 (잠금 없이)
        const pos = await tx.virtualPosition.findUnique({
          where: { accountId_symbol: { accountId: params.id, symbol } },
        });
        if (!pos || pos.quantity < qty) throw new Error('INSUFFICIENT_POSITION');
      }

      return tx.virtualOrder.create({
        data: {
          id: crypto.randomUUID(),
          accountId: params.id, symbol, name: name ?? symbol,
          side, type: 'LIMIT', quantity: qty,
          price: limitPrice, filledPrice: null, status: 'PENDING',
        },
      });
    });

    const nameMap = await getStockNameMap();
    return NextResponse.json(mapOrder(result, nameMap));
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

// ── 공통 헬퍼 ──────────────────────────────────────────────────────────────────

async function upsertPosition(
  tx: any,
  accountId: string,
  symbol: string,
  name: string,
  qty: number,
  filledPrice: number
) {
  const existing = await tx.virtualPosition.findUnique({
    where: { accountId_symbol: { accountId, symbol } },
  });
  if (existing) {
    const newQty = existing.quantity + qty;
    const newAvgPrice = (existing.avgPrice * existing.quantity + filledPrice * qty) / newQty;
    await tx.virtualPosition.update({
      where: { accountId_symbol: { accountId, symbol } },
      data: { quantity: newQty, avgPrice: newAvgPrice, name: name ?? existing.name },
    });
  } else {
    await tx.virtualPosition.create({
      data: {
        id: crypto.randomUUID(),
        accountId,
        symbol,
        name: name ?? symbol,
        quantity: qty,
        avgPrice: filledPrice,
        updatedAt: new Date(),
      },
    });
  }
}

async function reducePosition(
  tx: any,
  accountId: string,
  symbol: string,
  qty: number
) {
  const pos = await tx.virtualPosition.findUnique({
    where: { accountId_symbol: { accountId, symbol } },
  });
  if (!pos || pos.quantity < qty) throw new Error('INSUFFICIENT_POSITION');
  const newQty = pos.quantity - qty;
  if (newQty === 0) {
    await tx.virtualPosition.delete({ where: { accountId_symbol: { accountId, symbol } } });
  } else {
    await tx.virtualPosition.update({
      where: { accountId_symbol: { accountId, symbol } },
      data: { quantity: newQty },
    });
  }
}
