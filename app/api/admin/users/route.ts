import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { requireAdmin, writeAuditLog } from '@/lib/server/adminAuth'
import { currentUsageMonth, getEffectivePlan } from '@/lib/server/planLimits'
import { isValidPlanId } from '@/lib/plans'

export const dynamic = 'force-dynamic'

const PAGE_SIZE = 20

// GET: 사용자 목록 (검색/필터/정렬/페이지네이션)
export async function GET(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const params = request.nextUrl.searchParams
    const q = params.get('q')?.trim() || ''
    const plan = params.get('plan') || ''
    const status = params.get('status') || ''
    const sort = params.get('sort') || 'createdAt'
    const page = Math.max(1, Number(params.get('page')) || 1)

    const where: Record<string, unknown> = {}
    if (q) where.email = { contains: q }
    if (plan) where.planTier = plan
    if (status) where.status = status

    const orderBy =
      sort === 'lastLoginAt'
        ? { lastLoginAt: 'desc' as const }
        : sort === 'email'
          ? { email: 'asc' as const }
          : { createdAt: 'desc' as const }

    const [total, users] = await Promise.all([
      prisma.user.count({ where }),
      prisma.user.findMany({
        where,
        orderBy,
        skip: (page - 1) * PAGE_SIZE,
        take: PAGE_SIZE,
        select: {
          id: true,
          email: true,
          name: true,
          planTier: true,
          role: true,
          status: true,
          createdAt: true,
          lastLoginAt: true,
          backtestUsageMonth: true,
          backtestCountThisMonth: true,
          _count: {
            select: {
              Strategy: { where: { isSaved: true, deletedAt: null } },
              VirtualAccount: { where: { status: { not: 'CLOSED' } } },
            },
          },
        },
      }),
    ])

    const month = currentUsageMonth()
    // 플랜 티어별 유효 한도(PlanConfig 오버라이드 반영) — 티어는 3개뿐이라 미리 계산
    const tiers = Array.from(new Set(users.map((u) => u.planTier)))
    const limits: Record<string, number> = {}
    for (const tier of tiers) {
      limits[tier] = (await getEffectivePlan(prisma, tier)).monthlyBacktestLimit
    }

    return NextResponse.json({
      total,
      page,
      pageSize: PAGE_SIZE,
      users: users.map((u) => ({
        id: u.id,
        email: u.email,
        name: u.name,
        planTier: u.planTier,
        role: u.role,
        status: u.status,
        createdAt: u.createdAt,
        lastLoginAt: u.lastLoginAt,
        strategyCount: u._count.Strategy,
        accountCount: u._count.VirtualAccount,
        backtestsUsed:
          u.backtestUsageMonth === month ? u.backtestCountThisMonth : 0,
        backtestLimit: limits[u.planTier],
      })),
    })
  } catch (error) {
    console.error('Admin users list error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}

// PATCH: 사용자 작업 — changePlan | suspend | activate | delete
export async function PATCH(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const body = await request.json()
    const userId = Number(body.userId)
    const action = String(body.action || '')

    if (!Number.isInteger(userId)) {
      return NextResponse.json({ error: 'Invalid userId' }, { status: 400 })
    }

    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { id: true, email: true, planTier: true, status: true, role: true },
    })
    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 })
    }

    // 자기 자신 정지/삭제는 콘솔 잠금 사고로 이어지므로 차단
    if (userId === admin.id && action !== 'changePlan') {
      return NextResponse.json(
        { error: '자기 자신에게는 수행할 수 없는 작업입니다.' },
        { status: 400 }
      )
    }

    if (action === 'changePlan') {
      const planTier = String(body.planTier || '').toUpperCase()
      if (!isValidPlanId(planTier)) {
        return NextResponse.json({ error: 'Invalid planTier' }, { status: 400 })
      }
      await prisma.user.update({ where: { id: userId }, data: { planTier } })
      await writeAuditLog(admin, {
        action: 'USER_PLAN_CHANGE',
        targetType: 'USER',
        targetId: String(userId),
        targetUserId: userId,
        before: { planTier: user.planTier },
        after: { planTier },
      })
    } else if (action === 'suspend' || action === 'activate' || action === 'delete') {
      const nextStatus =
        action === 'suspend' ? 'SUSPENDED' : action === 'activate' ? 'ACTIVE' : 'DELETED'
      await prisma.user.update({
        where: { id: userId },
        data: { status: nextStatus },
      })
      await writeAuditLog(admin, {
        action: `USER_${action.toUpperCase()}`,
        targetType: 'USER',
        targetId: String(userId),
        targetUserId: userId,
        before: { status: user.status },
        after: { status: nextStatus },
      })
    } else {
      return NextResponse.json({ error: 'Invalid action' }, { status: 400 })
    }

    return NextResponse.json({ ok: true })
  } catch (error) {
    console.error('Admin user action error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
