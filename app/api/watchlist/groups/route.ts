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
    const groups = await prisma.watchlistGroup.findMany({
      where: withOwnership({}, userId),
      orderBy: { createdAt: 'asc' },
    })
    return NextResponse.json(groups)
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return NextResponse.json({ error: 'Failed to fetch groups' }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const { userId } = await getOwnershipContext()
    const { name, color } = await request.json()
    const group = await prisma.watchlistGroup.create({
      data: {
        id: crypto.randomUUID(),
        ...(userId != null && { userId }),
        name,
        color: color || '#3B82F6',
      },
    })
    return NextResponse.json(group)
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return NextResponse.json({ error: 'Failed to create group' }, { status: 500 })
  }
}
