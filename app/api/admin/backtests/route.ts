import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { requireAdmin, writeAuditLog } from '@/lib/server/adminAuth'
import { currentUsageMonth, getEffectivePlan } from '@/lib/server/planLimits'

export const dynamic = 'force-dynamic'

const PAGE_SIZE = 20

// GET: 사용자별 백테스트 사용 현황. ?userId=N 이면 해당 사용자의 최근 실행 기록 포함
export async function GET(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const params = request.nextUrl.searchParams
    const detailUserId = Number(params.get('userId')) || null
    const page = Math.max(1, Number(params.get('page')) || 1)
    const month = currentUsageMonth()

    if (detailUserId) {
      const recent = await prisma.userBacktestHistory.findMany({
        where: { userId: detailUserId },
        orderBy: { savedAt: 'desc' },
        take: 10,
        select: {
          savedAt: true,
          BacktestHistory: {
            select: { id: true, strategyName: true, createdAt: true },
          },
        },
      })
      return NextResponse.json({
        recentRuns: recent.map((r) => ({
          id: r.BacktestHistory.id,
          strategyName: r.BacktestHistory.strategyName,
          savedAt: r.savedAt,
        })),
      })
    }

    const where = { status: { not: 'DELETED' } }
    const [total, users] = await Promise.all([
      prisma.user.count({ where }),
      prisma.user.findMany({
        where,
        orderBy: [{ backtestCountThisMonth: 'desc' }, { id: 'asc' }],
        skip: (page - 1) * PAGE_SIZE,
        take: PAGE_SIZE,
        select: {
          id: true,
          email: true,
          planTier: true,
          backtestUsageMonth: true,
          backtestCountThisMonth: true,
        },
      }),
    ])

    const tiers = Array.from(new Set(users.map((u) => u.planTier)))
    const limits: Record<string, number> = {}
    for (const tier of tiers) {
      limits[tier] = (await getEffectivePlan(prisma, tier)).monthlyBacktestLimit
    }

    return NextResponse.json({
      total,
      page,
      pageSize: PAGE_SIZE,
      month,
      users: users.map((u) => {
        const used = u.backtestUsageMonth === month ? u.backtestCountThisMonth : 0
        const limit = limits[u.planTier]
        return {
          id: u.id,
          email: u.email,
          planTier: u.planTier,
          used,
          limit,
          remaining: Math.max(0, limit - used),
        }
      }),
    })
  } catch (error) {
    console.error('Admin backtests list error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}

// PATCH: 사용량 조정 — reset | increase | decrease (amount 기본 1)
export async function PATCH(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const body = await request.json()
    const userId = Number(body.userId)
    const action = String(body.action || '')
    const amount = Math.max(1, Number(body.amount) || 1)

    if (!Number.isInteger(userId)) {
      return NextResponse.json({ error: 'Invalid userId' }, { status: 400 })
    }

    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { backtestUsageMonth: true, backtestCountThisMonth: true },
    })
    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 })
    }

    const month = currentUsageMonth()
    const used = user.backtestUsageMonth === month ? user.backtestCountThisMonth : 0

    let next: number
    if (action === 'reset') next = 0
    else if (action === 'increase') next = used + amount
    else if (action === 'decrease') next = Math.max(0, used - amount)
    else return NextResponse.json({ error: 'Invalid action' }, { status: 400 })

    await prisma.user.update({
      where: { id: userId },
      data: { backtestUsageMonth: month, backtestCountThisMonth: next },
    })
    await writeAuditLog(admin, {
      action: `BACKTEST_USAGE_${action.toUpperCase()}`,
      targetType: 'BACKTEST_USAGE',
      targetId: String(userId),
      targetUserId: userId,
      before: { used },
      after: { used: next },
    })

    return NextResponse.json({ ok: true, used: next })
  } catch (error) {
    console.error('Admin backtest usage error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
