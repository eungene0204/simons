import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { StrategyDSL } from '@/types/strategy';

export async function POST(request: Request) {
  try {
    const data: StrategyDSL = await request.json();

    if (!data.name) {
      return NextResponse.json({ error: 'Strategy name is required' }, { status: 400 });
    }

    const strategy = await prisma.strategy.create({
      data: {
        id: data.id || undefined, // Prisma will generate an ID if undefined, but we can allow setting it if needed
        name: data.name,
        description: data.description || null,
        settings: JSON.stringify(data),
      },
    });

    return NextResponse.json(strategy);
  } catch (error) {
    console.error('Failed to save strategy:', error);
    return NextResponse.json({ error: 'Failed to save strategy' }, { status: 500 });
  }
}

export async function GET() {
  try {
    const strategies = await prisma.strategy.findMany({
      orderBy: { createdAt: 'desc' },
    });
    
    // Parse the settings JSON, but always use the DB id
    const parsedStrategies = strategies.map((s: any) => ({
      ...JSON.parse(s.settings),
      id: s.id,
    }));

    return NextResponse.json(parsedStrategies);
  } catch (error) {
    console.error('Failed to fetch strategies:', error);
    return NextResponse.json({ error: 'Failed to fetch strategies' }, { status: 500 });
  }
}

export async function DELETE(request: Request) {
    try {
        const { searchParams } = new URL(request.url);
        const id = searchParams.get('id');

        if (!id) {
            return NextResponse.json({ error: 'Strategy ID is required' }, { status: 400 });
        }

        await prisma.strategy.delete({
            where: { id },
        });

        return NextResponse.json({ message: 'Strategy deleted successfully' });
    } catch (error) {
        console.error('Failed to delete strategy:', error);
        return NextResponse.json({ error: 'Failed to delete strategy' }, { status: 500 });
    }
}
