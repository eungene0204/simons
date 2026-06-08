import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { StrategyDSL } from '@/types/strategy';
import { inferStrategyType } from '@/lib/strategy-type';
import { computeStrategyIdFromDsl } from '@/lib/server/backtestCache';
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user';

function buildOwnedStrategyId(userId: number | null, data: StrategyDSL) {
  const baseId = computeStrategyIdFromDsl(data);
  return userId == null ? baseId : `${userId}:${baseId}`;
}

export async function POST(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    const data: StrategyDSL = await request.json();

    if (!data.name) {
      return NextResponse.json({ error: 'Strategy name is required' }, { status: 400 });
    }

    const strategyId = buildOwnedStrategyId(userId, data);
    const strategyType = inferStrategyType(data.name, data.description ?? "", data);
    const strategyToSave = {
      ...data,
      id: strategyId,
    };

    const strategy = await prisma.strategy.upsert({
      where: { id: strategyId },
      create: {
        id: strategyId,
        ...(userId != null && { userId }),
        name: data.name,
        description: data.description || null,
        settings: JSON.stringify(strategyToSave),
        strategyType,
      },
      update: {
        ...(userId != null && { userId }),
        name: data.name,
        description: data.description || null,
        settings: JSON.stringify(strategyToSave),
        strategyType,
      },
    });

    return NextResponse.json(strategy);
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to save strategy:', error);
    return NextResponse.json({ error: 'Failed to save strategy' }, { status: 500 });
  }
}

export async function GET() {
  try {
    const { userId } = await getOwnershipContext();
    const strategies = await prisma.strategy.findMany({
      where: withOwnership({}, userId),
      orderBy: { createdAt: 'desc' },
    });
    
    // Parse the settings JSON, but always use the DB id
    const parsedStrategies = strategies.map((s: any) => ({
      ...JSON.parse(s.settings),
      id: s.id,
    }));

    return NextResponse.json(parsedStrategies);
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to fetch strategies:', error);
    return NextResponse.json({ error: 'Failed to fetch strategies' }, { status: 500 });
  }
}

export async function DELETE(request: Request) {
    try {
        const { userId } = await getOwnershipContext();
        const { searchParams } = new URL(request.url);
        const id = searchParams.get('id');

        if (!id) {
            return NextResponse.json({ error: 'Strategy ID is required' }, { status: 400 });
        }

        await prisma.strategy.deleteMany({
            where: withOwnership({ id }, userId),
        });

        return NextResponse.json({ message: 'Strategy deleted successfully' });
    } catch (error) {
        if (isUnauthorizedAccessError(error)) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
        }
        console.error('Failed to delete strategy:', error);
        return NextResponse.json({ error: 'Failed to delete strategy' }, { status: 500 });
    }
}
