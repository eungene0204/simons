import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { requireAdmin, writeAuditLog } from '@/lib/server/adminAuth'
import {
  loadRefundPreview,
  RefundSettlementError,
  settleFullRefund,
  settleRefund,
} from '@/lib/server/refundSettlement'
import { TossPaymentError } from '@/lib/server/tossPayments'
import { PRORATED_REFUND_ENABLED } from '@/lib/plans'

export const dynamic = 'force-dynamic'

// 환불 집행 — 고객센터 접수 건을 관리자가 처리한다. 두 가지 모드:
//   prorated: 중도 해지 일할 정산(약관 제12조 제9항, 토스 부분 취소)
//   full:     미사용 전액 환불(약관 제12조 제2항, 토스 전액 취소) — 2항 해당 여부는
//             관리자가 미리보기의 사용 흔적을 보고 판단한다
// GET으로 금액을 확인하고, 그 금액을 그대로 POST로 되돌려 보내야 집행된다.

// GET: 정산 미리보기 (돈이 나가지 않는다)
export async function GET(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const userId = Number(request.nextUrl.searchParams.get('userId'))
    if (!Number.isInteger(userId)) {
      return NextResponse.json({ error: 'Invalid userId' }, { status: 400 })
    }

    const preview = await loadRefundPreview(prisma, userId)
    if (preview.status !== 'ready') {
      return NextResponse.json({ available: false, reason: preview.reason })
    }
    return NextResponse.json({
      available: true,
      planId: preview.order.planId,
      billingCycle: preview.order.cycle,
      paidAmount: preview.settlement.paidAmount,
      paidAt: preview.settlement.paidAt,
      periodEnd: preview.settlement.periodEnd,
      totalDays: preview.settlement.totalDays,
      usedDays: preview.settlement.usedDays,
      remainingDays: preview.settlement.remainingDays,
      refundAmount: preview.settlement.refundAmount,
      usage: preview.usage,
    })
  } catch (error) {
    console.error('Admin refund preview error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}

// POST: 환불 집행 — 토스 취소가 성공한 뒤에만 우리 기록을 바꾼다.
export async function POST(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const body = await request.json()
    const userId = Number(body.userId)
    const expectedRefundAmount = Number(body.expectedRefundAmount)
    if (!Number.isInteger(userId)) {
      return NextResponse.json({ error: 'Invalid userId' }, { status: 400 })
    }
    if (!Number.isInteger(expectedRefundAmount) || expectedRefundAmount <= 0) {
      return NextResponse.json({ error: '확인한 환불액을 함께 보내야 합니다.' }, { status: 400 })
    }
    const mode = body.mode === undefined ? 'prorated' : body.mode
    if (mode !== 'prorated' && mode !== 'full') {
      return NextResponse.json({ error: 'Invalid mode' }, { status: 400 })
    }
    // 일할 정산은 약관에 없는 동안 집행하지 않는다(lib/plans.ts 스위치). 전액 환불(12조 2항)은 유지.
    if (mode === 'prorated' && !PRORATED_REFUND_ENABLED) {
      return NextResponse.json(
        { error: '일할 정산 환불은 현재 약관에 없어 집행할 수 없습니다.' },
        { status: 400 }
      )
    }

    const before = await prisma.user.findUnique({
      where: { id: userId },
      select: { planTier: true, subscriptionPlanId: true, billingCycle: true, nextBillingAt: true },
    })

    const settle = mode === 'full' ? settleFullRefund : settleRefund
    const result = await settle(prisma, userId, {
      expectedRefundAmount,
      reason: typeof body.reason === 'string' ? body.reason : undefined,
    })

    await writeAuditLog(admin, {
      action: mode === 'full' ? 'USER_REFUND_FULL' : 'USER_REFUND_SETTLEMENT',
      targetType: 'PAYMENT_ORDER',
      targetId: result.order.orderId,
      targetUserId: userId,
      before,
      after: {
        planTier: 'FREE',
        mode,
        refundAmount: result.refundedAmount,
        paidAmount: result.settlement.paidAmount,
        usedDays: result.settlement.usedDays,
        totalDays: result.settlement.totalDays,
        billingCycle: result.order.cycle,
      },
    })

    return NextResponse.json({ ok: true, mode, refundAmount: result.refundedAmount })
  } catch (error) {
    if (error instanceof RefundSettlementError) {
      return NextResponse.json({ error: error.message }, { status: error.httpStatus })
    }
    // 토스가 거절하면 우리 기록은 그대로다 — 실패 사유를 그대로 보여준다.
    if (error instanceof TossPaymentError) {
      return NextResponse.json(
        { error: `결제사 환불 실패: ${error.message}` },
        { status: error.httpStatus >= 500 ? 502 : 400 }
      )
    }
    console.error('Admin refund settlement error:', error)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
