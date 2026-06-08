import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user'

export async function PUT(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext()
    const { name, color } = await request.json()
    await prisma.watchlistGroup.updateMany({
      where: withOwnership({ id: params.id }, userId),
      data: { name, color },
    })
    return NextResponse.json({ updated: true })
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return NextResponse.json({ error: 'Failed to update group' }, { status: 500 })
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext()
    await prisma.watchlistSymbol.updateMany({
      where: withOwnership({ groupId: params.id }, userId),
      data: { groupId: null },
    })
    await prisma.watchlistGroup.deleteMany({
      where: withOwnership({ id: params.id }, userId),
    })
    return NextResponse.json({ deleted: true })
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return NextResponse.json({ error: 'Failed to delete group' }, { status: 500 })
  }
}
