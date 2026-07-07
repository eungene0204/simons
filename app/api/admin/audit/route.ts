import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { requireAdmin } from '@/lib/server/adminAuth'

export const dynamic = 'force-dynamic'

const PAGE_SIZE = 50

// GET: 관리자 감사 로그 조회 (삭제 API는 의도적으로 제공하지 않는다)
export async function GET(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const params = request.nextUrl.searchParams
    const page = Math.max(1, Number(params.get('page')) || 1)
    const action = params.get('action')?.trim() || ''
    const targetUserId = Number(params.get('targetUserId')) || null

    const where: Record<string, unknown> = {}
    if (action) where.action = { contains: action }
    if (targetUserId) where.targetUserId = targetUserId

    const [total, logs] = await Promise.all([
      prisma.adminAuditLog.count({ where }),
      prisma.adminAuditLog.findMany({
        where,
        orderBy: { createdAt: 'desc' },
        skip: (page - 1) * PAGE_SIZE,
        take: PAGE_SIZE,
      }),
    ])

    return NextResponse.json({ total, page, pageSize: PAGE_SIZE, logs })
  } catch (error) {
    console.error('Admin audit list error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
