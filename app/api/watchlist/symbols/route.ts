import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user'

export async function GET() {
  try {
    const { userId } = await getOwnershipContext()
    const symbols = await prisma.watchlistSymbol.findMany({
      where: withOwnership({}, userId),
      orderBy: { addedAt: 'asc' },
    })
    return NextResponse.json(symbols)
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return NextResponse.json({ error: 'Failed to fetch symbols' }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const { userId } = await getOwnershipContext()
    const { symbol, name, groupId } = await request.json()
    const existing = await prisma.watchlistSymbol.findFirst({
      where: withOwnership({ symbol }, userId),
    })
    if (existing) return NextResponse.json({ added: false })
    const item = await prisma.watchlistSymbol.create({
      data: {
        id: crypto.randomUUID(),
        ...(userId != null && { userId }),
        symbol,
        name,
        groupId: groupId ?? null,
      },
    })
    return NextResponse.json({ added: true, item })
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return NextResponse.json({ error: 'Failed to add symbol' }, { status: 500 })
  }
}
