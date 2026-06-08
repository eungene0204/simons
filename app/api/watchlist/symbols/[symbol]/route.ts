import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user'

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { symbol: string } }
) {
  try {
    const { userId } = await getOwnershipContext()
    await prisma.watchlistSymbol.deleteMany({
      where: withOwnership({ symbol: params.symbol }, userId),
    })
    return NextResponse.json({ deleted: true })
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return NextResponse.json({ error: 'Failed to delete symbol' }, { status: 500 })
  }
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { symbol: string } }
) {
  try {
    const { userId } = await getOwnershipContext()
    const { groupId } = await request.json()
    await prisma.watchlistSymbol.updateMany({
      where: withOwnership({ symbol: params.symbol }, userId),
      data: { groupId: groupId ?? null },
    })
    return NextResponse.json({ updated: true })
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return NextResponse.json({ error: 'Failed to update symbol' }, { status: 500 })
  }
}
