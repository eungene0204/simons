import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

export async function GET() {
  const groups = await prisma.watchlistGroup.findMany({
    orderBy: { createdAt: 'asc' },
  })
  return NextResponse.json(groups)
}

export async function POST(request: NextRequest) {
  const { name, color } = await request.json()
  const group = await prisma.watchlistGroup.create({
    data: { name, color: color || '#3B82F6' },
  })
  return NextResponse.json(group)
}
