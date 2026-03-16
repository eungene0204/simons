import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { symbol: string } }
) {
  await prisma.watchlistSymbol.deleteMany({ where: { symbol: params.symbol } })
  return NextResponse.json({ deleted: true })
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { symbol: string } }
) {
  const { groupId } = await request.json()
  await prisma.watchlistSymbol.update({
    where: { symbol: params.symbol },
    data: { groupId: groupId ?? null },
  })
  return NextResponse.json({ updated: true })
}
