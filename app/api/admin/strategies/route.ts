import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { requireAdmin, writeAuditLog } from '@/lib/server/adminAuth'

export const dynamic = 'force-dynamic'

const PAGE_SIZE = 20

// settings JSON에서 지표 이름 후보('indicator'/'type' 키의 문자열 값)를 수집한다.
function extractIndicators(settings: string): string[] {
  try {
    const found = new Set<string>()
    const visit = (node: unknown) => {
      if (Array.isArray(node)) return node.forEach(visit)
      if (node && typeof node === 'object') {
        for (const [key, value] of Object.entries(node)) {
          if ((key === 'indicator' || key === 'type') && typeof value === 'string') {
            found.add(value)
          }
          visit(value)
        }
      }
    }
    visit(JSON.parse(settings))
    return Array.from(found).slice(0, 8)
  } catch {
    return []
  }
}

// GET: 전략 목록
export async function GET(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const params = request.nextUrl.searchParams
    const q = params.get('q')?.trim() || ''
    const page = Math.max(1, Number(params.get('page')) || 1)

    const where: Record<string, unknown> = { deletedAt: null }
    if (q) {
      where.OR = [{ name: { contains: q } }, { User: { email: { contains: q } } }]
    }

    const [total, strategies] = await Promise.all([
      prisma.strategy.count({ where }),
      prisma.strategy.findMany({
        where,
        orderBy: { createdAt: 'desc' },
        skip: (page - 1) * PAGE_SIZE,
        take: PAGE_SIZE,
        select: {
          id: true,
          name: true,
          strategyType: true,
          isSaved: true,
          settings: true,
          createdAt: true,
          updatedAt: true,
          User: { select: { id: true, email: true } },
          _count: { select: { BacktestResult: true, BacktestHistory: true } },
        },
      }),
    ])

    // VirtualAccount.strategyId는 FK 관계가 없어 별도 집계
    const ids = strategies.map((s) => s.id)
    const accountCounts = ids.length
      ? await prisma.virtualAccount.groupBy({
          by: ['strategyId'],
          where: { strategyId: { in: ids } },
          _count: { _all: true },
        })
      : []
    const accountCountMap = new Map(
      accountCounts.map((row) => [row.strategyId, row._count._all])
    )

    return NextResponse.json({
      total,
      page,
      pageSize: PAGE_SIZE,
      strategies: strategies.map((s) => ({
        id: s.id,
        name: s.name,
        strategyType: s.strategyType,
        isSaved: s.isSaved,
        indicators: extractIndicators(s.settings),
        userEmail: s.User?.email ?? null,
        userId: s.User?.id ?? null,
        linkedAccounts: accountCountMap.get(s.id) ?? 0,
        backtestCount: s._count.BacktestResult + s._count.BacktestHistory,
        createdAt: s.createdAt,
        updatedAt: s.updatedAt,
      })),
    })
  } catch (error) {
    console.error('Admin strategies list error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}

// PATCH: 전략 작업 — deactivate | delete (soft delete, 프로젝트 관례)
export async function PATCH(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const body = await request.json()
    const strategyId = String(body.strategyId || '')
    const action = String(body.action || '')

    const strategy = await prisma.strategy.findUnique({
      where: { id: strategyId },
      select: { id: true, name: true, isSaved: true, userId: true, deletedAt: true },
    })
    if (!strategy || strategy.deletedAt) {
      return NextResponse.json({ error: 'Strategy not found' }, { status: 404 })
    }

    if (action === 'deactivate') {
      await prisma.strategy.update({
        where: { id: strategyId },
        data: { isSaved: false },
      })
    } else if (action === 'delete') {
      await prisma.strategy.update({
        where: { id: strategyId },
        data: { isSaved: false, deletedAt: new Date() },
      })
    } else {
      return NextResponse.json({ error: 'Invalid action' }, { status: 400 })
    }

    await writeAuditLog(admin, {
      action: `STRATEGY_${action.toUpperCase()}`,
      targetType: 'STRATEGY',
      targetId: strategyId,
      targetUserId: strategy.userId ?? undefined,
      before: { name: strategy.name, isSaved: strategy.isSaved },
    })

    return NextResponse.json({ ok: true })
  } catch (error) {
    console.error('Admin strategy action error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
