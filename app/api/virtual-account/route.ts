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

// GET: 모든 가상계좌 목록
export async function GET() {
  try {
    const accounts = await prisma.virtualAccount.findMany({
      include: { positions: true },
      orderBy: { createdAt: 'desc' },
    });
    return NextResponse.json(accounts.map(mapAccount));
  } catch (error) {
    console.error('Failed to fetch virtual accounts:', error);
    return NextResponse.json({ error: 'Failed to fetch accounts' }, { status: 500 });
  }
}

// POST: 가상계좌 생성
export async function POST(request: Request) {
  try {
    const { name, initialAmount, strategyId, strategyName } = await request.json();

    if (!name || !initialAmount) {
      return NextResponse.json(
        { error: 'name and initialAmount are required' },
        { status: 400 }
      );
    }

    const account = await prisma.virtualAccount.create({
      data: {
        name,
        initialCash: initialAmount,
        currentCash: initialAmount,
        strategyId: strategyId || null,
        strategyName: strategyName || null,
      },
      include: { positions: true },
    });

    return NextResponse.json(mapAccount(account));
  } catch (error) {
    console.error('Failed to create virtual account:', error);
    return NextResponse.json({ error: 'Failed to create account' }, { status: 500 });
  }
}
