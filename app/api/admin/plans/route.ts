import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { requireAdmin, writeAuditLog } from '@/lib/server/adminAuth'
import { PLANS, PLAN_ORDER, isValidPlanId } from '@/lib/plans'

export const dynamic = 'force-dynamic'

// 오버라이드 값 검증: null(기본값 복원) 또는 0 이상 정수. maxStrategies는 -1(무제한) 허용.
function parseLimit(value: unknown, allowUnlimited = false): number | null | undefined {
  if (value === undefined) return undefined
  if (value === null) return null
  const n = Number(value)
  if (!Number.isInteger(n)) return undefined
  if (n >= 0 || (allowUnlimited && n === -1)) return n
  return undefined
}

// GET: 플랜별 기본값 + 오버라이드 + 유효 한도
export async function GET() {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const overrides = await prisma.planConfig.findMany()
    const overrideMap = new Map(overrides.map((o) => [o.planId, o]))

    return NextResponse.json({
      plans: PLAN_ORDER.map((planId) => {
        const base = PLANS[planId]
        const o = overrideMap.get(planId)
        return {
          planId,
          name: base.name,
          monthlyPrice: base.monthlyPrice,
          defaults: {
            monthlyBacktestLimit: base.monthlyBacktestLimit,
            maxStrategies: base.isUnlimitedStrategies ? -1 : base.maxStrategies,
            maxVirtualAccounts: base.maxVirtualAccounts,
          },
          overrides: {
            monthlyBacktestLimit: o?.monthlyBacktestLimit ?? null,
            maxStrategies: o?.maxStrategies ?? null,
            maxVirtualAccounts: o?.maxVirtualAccounts ?? null,
          },
        }
      }),
    })
  } catch (error) {
    console.error('Admin plans error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}

// PATCH: 플랜 한도 오버라이드 변경 (null = 기본값 복원, maxStrategies -1 = 무제한)
export async function PATCH(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const body = await request.json()
    const planId = String(body.planId || '').toUpperCase()
    if (!isValidPlanId(planId)) {
      return NextResponse.json({ error: 'Invalid planId' }, { status: 400 })
    }

    const monthlyBacktestLimit = parseLimit(body.monthlyBacktestLimit)
    const maxStrategies = parseLimit(body.maxStrategies, true)
    const maxVirtualAccounts = parseLimit(body.maxVirtualAccounts)

    const data: Record<string, number | null> = {}
    if (monthlyBacktestLimit !== undefined) data.monthlyBacktestLimit = monthlyBacktestLimit
    if (maxStrategies !== undefined) data.maxStrategies = maxStrategies
    if (maxVirtualAccounts !== undefined) data.maxVirtualAccounts = maxVirtualAccounts

    if (Object.keys(data).length === 0) {
      return NextResponse.json({ error: 'No valid fields' }, { status: 400 })
    }

    const before = await prisma.planConfig.findUnique({ where: { planId } })
    const after = await prisma.planConfig.upsert({
      where: { planId },
      create: { planId, ...data },
      update: data,
    })

    await writeAuditLog(admin, {
      action: 'PLAN_LIMIT_CHANGE',
      targetType: 'PLAN',
      targetId: planId,
      before: before ?? undefined,
      after,
    })

    return NextResponse.json({ ok: true })
  } catch (error) {
    console.error('Admin plan change error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
