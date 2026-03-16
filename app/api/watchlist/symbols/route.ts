import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

export async function GET() {
  const symbols = await prisma.watchlistSymbol.findMany({
    orderBy: { addedAt: 'asc' },
  })
  return NextResponse.json(symbols)
}

export async function POST(request: NextRequest) {
  const { symbol, name, groupId } = await request.json()
  const existing = await prisma.watchlistSymbol.findUnique({ where: { symbol } })
  if (existing) return NextResponse.json({ added: false })
  const item = await prisma.watchlistSymbol.create({
    data: { symbol, name, groupId: groupId ?? null },
  })
  return NextResponse.json({ added: true, item })
}
