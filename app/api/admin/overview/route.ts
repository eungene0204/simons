import { NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { requireAdmin } from '@/lib/server/adminAuth'
import { currentUsageMonth } from '@/lib/server/planLimits'

export const dynamic = 'force-dynamic'

// GET: 관리자 콘솔 Overview 통계
export async function GET() {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  const month = currentUsageMonth()

  // 오늘 0시 (KST) 기준
  const kst = new Date(Date.now() + 9 * 60 * 60 * 1000)
  const todayStartKst = new Date(
    Date.UTC(kst.getUTCFullYear(), kst.getUTCMonth(), kst.getUTCDate()) -
      9 * 60 * 60 * 1000
  )

  try {
    const [
      totalUsers,
      todaySignups,
      planCounts,
      backtestAgg,
      activeAccounts,
      totalStrategies,
      recentAudit,
    ] = await Promise.all([
      prisma.user.count({ where: { status: { not: 'DELETED' } } }),
      prisma.user.count({
        where: { status: { not: 'DELETED' }, createdAt: { gte: todayStartKst } },
      }),
      prisma.user.groupBy({
        by: ['planTier'],
        where: { status: { not: 'DELETED' } },
        _count: { _all: true },
      }),
      prisma.user.aggregate({
        where: { backtestUsageMonth: month },
        _sum: { backtestCountThisMonth: true },
      }),
      prisma.virtualAccount.count({ where: { status: 'ACTIVE' } }),
      prisma.strategy.count({ where: { isSaved: true, deletedAt: null } }),
      prisma.adminAuditLog.findMany({
        orderBy: { createdAt: 'desc' },
        take: 5,
        select: {
          id: true,
          adminEmail: true,
          action: true,
          targetType: true,
          targetId: true,
          createdAt: true,
        },
      }),
    ])

    const usersByPlan: Record<string, number> = { FREE: 0, PRO: 0, PREMIUM: 0 }
    for (const row of planCounts) {
      usersByPlan[row.planTier] = row._count._all
    }

    return NextResponse.json({
      totalUsers,
      todaySignups,
      usersByPlan,
      backtestsThisMonth: backtestAgg._sum.backtestCountThisMonth ?? 0,
      activeVirtualAccounts: activeAccounts,
      totalStrategies,
      recentAdminActions: recentAudit,
    })
  } catch (error) {
    console.error('Admin overview error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
