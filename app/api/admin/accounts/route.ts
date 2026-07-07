import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { requireAdmin, writeAuditLog } from '@/lib/server/adminAuth'

export const dynamic = 'force-dynamic'

const PAGE_SIZE = 20

// GET: 가상계좌 목록 (평가금은 캐시된 포지션 현재가 기준 근사치)
export async function GET(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const params = request.nextUrl.searchParams
    const q = params.get('q')?.trim() || ''
    const status = params.get('status') || ''
    const page = Math.max(1, Number(params.get('page')) || 1)

    const where: Record<string, unknown> = {}
    if (status) where.status = status
    if (q) where.User = { email: { contains: q } }

    const [total, accounts] = await Promise.all([
      prisma.virtualAccount.count({ where }),
      prisma.virtualAccount.findMany({
        where,
        orderBy: { createdAt: 'desc' },
        skip: (page - 1) * PAGE_SIZE,
        take: PAGE_SIZE,
        select: {
          id: true,
          name: true,
          status: true,
          initialCash: true,
          currentCash: true,
          strategyName: true,
          createdAt: true,
          User: { select: { id: true, email: true } },
          VirtualPosition: { select: { quantity: true, currentPrice: true, avgPrice: true } },
          _count: { select: { VirtualOrder: true } },
        },
      }),
    ])

    return NextResponse.json({
      total,
      page,
      pageSize: PAGE_SIZE,
      accounts: accounts.map((a) => {
        const positionsValue = a.VirtualPosition.reduce(
          (sum, p) =>
            sum + p.quantity * Number(p.currentPrice ?? p.avgPrice),
          0
        )
        const initialCash = Number(a.initialCash)
        const totalValue = Number(a.currentCash) + positionsValue
        return {
          id: a.id,
          name: a.name,
          status: a.status,
          userEmail: a.User?.email ?? null,
          userId: a.User?.id ?? null,
          strategyName: a.strategyName,
          initialCash,
          totalValue,
          returnPct: initialCash > 0 ? ((totalValue - initialCash) / initialCash) * 100 : 0,
          orderCount: a._count.VirtualOrder,
          createdAt: a.createdAt,
        }
      }),
    })
  } catch (error) {
    console.error('Admin accounts list error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}

// PATCH: 계좌 작업 — pause | resume | reset | delete
export async function PATCH(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const body = await request.json()
    const accountId = String(body.accountId || '')
    const action = String(body.action || '')

    const account = await prisma.virtualAccount.findUnique({
      where: { id: accountId },
      select: { id: true, name: true, status: true, userId: true, initialCash: true },
    })
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 })
    }

    const audit = {
      targetType: 'VIRTUAL_ACCOUNT',
      targetId: accountId,
      targetUserId: account.userId ?? undefined,
    }

    if (action === 'pause' || action === 'resume') {
      if (account.status === 'CLOSED') {
        return NextResponse.json({ error: 'Account is closed' }, { status: 400 })
      }
      const nextStatus = action === 'pause' ? 'PAUSED' : 'ACTIVE'
      await prisma.virtualAccount.update({
        where: { id: accountId },
        data: { status: nextStatus },
      })
      await writeAuditLog(admin, {
        ...audit,
        action: `ACCOUNT_${action.toUpperCase()}`,
        before: { status: account.status },
        after: { status: nextStatus },
      })
    } else if (action === 'reset') {
      // 초기화: 포지션/주문 삭제 + 현금을 초기 시뮬레이션 자금으로 복원
      await prisma.$transaction([
        prisma.virtualPosition.deleteMany({ where: { accountId } }),
        prisma.virtualOrder.deleteMany({ where: { accountId } }),
        prisma.virtualAccount.update({
          where: { id: accountId },
          data: { currentCash: account.initialCash },
        }),
      ])
      await writeAuditLog(admin, {
        ...audit,
        action: 'ACCOUNT_RESET',
        after: { currentCash: Number(account.initialCash) },
      })
    } else if (action === 'delete') {
      await prisma.$transaction([
        prisma.virtualMarketLog.deleteMany({ where: { accountId } }),
        prisma.virtualAccount.delete({ where: { id: accountId } }),
      ])
      await writeAuditLog(admin, {
        ...audit,
        action: 'ACCOUNT_DELETE',
        before: { name: account.name, status: account.status },
      })
    } else {
      return NextResponse.json({ error: 'Invalid action' }, { status: 400 })
    }

    return NextResponse.json({ ok: true })
  } catch (error) {
    console.error('Admin account action error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
