import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

export async function PUT(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const { name, color } = await request.json()
  await prisma.watchlistGroup.update({
    where: { id: params.id },
    data: { name, color },
  })
  return NextResponse.json({ updated: true })
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  // Unassign symbols from this group before deleting
  await prisma.watchlistSymbol.updateMany({
    where: { groupId: params.id },
    data: { groupId: null },
  })
  await prisma.watchlistGroup.delete({ where: { id: params.id } })
  return NextResponse.json({ deleted: true })
}
