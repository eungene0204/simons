import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

function mapAccount(a: any) {
  const totalValue =
    a.currentCash +
    (a.positions ?? []).reduce(
      (sum: number, p: any) => sum + p.quantity * p.avgPrice,
      0
    );
  return {
    id: a.id,
    name: a.name,
    initialAmount: a.initialCash,
    currentBalance: a.currentCash,
    totalValue,
    strategyId: a.strategyId ?? undefined,
    strategyName: a.strategyName ?? undefined,
    createdAt: a.createdAt.toISOString(),
    updatedAt: a.updatedAt.toISOString(),
  };
}

// GET: 계좌 상세 조회
export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const account = await prisma.virtualAccount.findUnique({
      where: { id: params.id },
      include: { positions: true },
    });
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }
    return NextResponse.json(mapAccount(account));
  } catch (error) {
    console.error('Failed to fetch virtual account:', error);
    return NextResponse.json({ error: 'Failed to fetch account' }, { status: 500 });
  }
}

// PATCH: 계좌 업데이트 (현금 잔액 등)
export async function PATCH(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const body = await request.json();
    const account = await prisma.virtualAccount.update({
      where: { id: params.id },
      data: {
        ...(body.currentBalance !== undefined && { currentCash: body.currentBalance }),
      },
      include: { positions: true },
    });
    return NextResponse.json(mapAccount(account));
  } catch (error) {
    console.error('Failed to update virtual account:', error);
    return NextResponse.json({ error: 'Failed to update account' }, { status: 500 });
  }
}

// DELETE: 계좌 삭제 (positions, orders cascade)
export async function DELETE(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    await prisma.virtualAccount.delete({ where: { id: params.id } });
    return NextResponse.json({ message: 'Account deleted' });
  } catch (error) {
    console.error('Failed to delete virtual account:', error);
    return NextResponse.json({ error: 'Failed to delete account' }, { status: 500 });
  }
}
