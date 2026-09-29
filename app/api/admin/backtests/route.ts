import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { requireAdmin, writeAuditLog } from '@/lib/server/adminAuth'
import { backtestUsageInCurrentPeriod, getEffectivePlan } from '@/lib/server/planLimits'

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

    // 사용량 주기는 사용자마다 다르다(구독 시작일·가입일 기준 롤링 1개월). 저장된 카운터가
    // 지난 주기 값일 수 있어 DB 정렬로는 순서를 정할 수 없으므로 전원을 읽어 현재 주기
    // 사용량으로 정렬한 뒤 자른다.
    const allUsers = await prisma.user.findMany({
      where: { status: { not: 'DELETED' } },
      select: {
        id: true,
        email: true,
        planTier: true,
        planStartDate: true,
        createdAt: true,
        backtestUsageMonth: true,
        backtestCountThisMonth: true,
      },
    })
    const ranked = allUsers
      .map((u) => ({ ...u, usage: backtestUsageInCurrentPeriod(u) }))
      .sort((a, b) => b.usage.used - a.usage.used || a.id - b.id)
    const total = ranked.length
    const users = ranked.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

    const tiers = Array.from(new Set(users.map((u) => u.planTier)))
    const limits: Record<string, number> = {}
    for (const tier of tiers) {
      limits[tier] = (await getEffectivePlan(prisma, tier)).monthlyBacktestLimit
    }

    return NextResponse.json({
      total,
      page,
      pageSize: PAGE_SIZE,
      users: users.map((u) => {
        const used = u.usage.used
        const limit = limits[u.planTier] + u.usage.carry
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
      select: {
        planStartDate: true,
        createdAt: true,
        backtestUsageMonth: true,
        backtestCountThisMonth: true,
      },
    })
    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 })
    }

    // 한도 소비(consumeBacktestQuota)가 읽는 현재 주기 키로 적어야 조정이 실제 한도에 반영된다.
    // 음수 카운터(업그레이드 이월분)는 보존한다 — 초기화·감소는 이월분 아래로 내리지 않는다.
    const { periodKey, raw, used } = backtestUsageInCurrentPeriod(user)
    const floor = Math.min(0, raw)

    let nextRaw: number
    if (action === 'reset') nextRaw = floor
    else if (action === 'increase') nextRaw = raw + amount
    else if (action === 'decrease') nextRaw = Math.max(floor, raw - amount)
    else return NextResponse.json({ error: 'Invalid action' }, { status: 400 })
    const next = Math.max(0, nextRaw)

    await prisma.user.update({
      where: { id: userId },
      data: { backtestUsageMonth: periodKey, backtestCountThisMonth: nextRaw },
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
