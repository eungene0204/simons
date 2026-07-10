// 자동결제(빌링) 월 갱신 잡 — 스케줄러가 주기적으로 호출한다.
// nextBillingAt이 지난 구독을 찾아: 해지 예약이면 FREE 전환, 아니면 빌링키로 자동 청구한다.
// 청구 실패는 다음 날 재시도하고, 연속 실패 한도에 도달하면 FREE로 전환한다.
import crypto from "crypto";
import type { PrismaClient } from "@prisma/client";
import { PLANS, isValidPlanId } from "@/lib/plans";
import { addMonthsClamped } from "@/lib/server/planLimits";
import { TossPaymentError, chargeBillingKey } from "@/lib/server/tossPayments";

export const BILLING_MAX_FAIL_COUNT = 3; // 연속 실패 한도 (도달 시 FREE 전환)
export const BILLING_RETRY_DELAY_MS = 24 * 60 * 60 * 1000; // 실패 시 재시도 간격(1일)

export interface BillingRenewalSummary {
  renewed: number;
  retried: number;
  downgraded: number;
}

/** 구독을 FREE로 전환하고 빌링 상태를 모두 비운다 */
function freeDowngradeData() {
  return {
    planTier: "FREE",
    planStartDate: null,
    tossBillingKey: null,
    subscriptionPlanId: null,
    nextBillingAt: null,
    subscriptionCanceledAt: null,
    billingFailCount: 0,
  };
}

export async function processDueBillingRenewals(
  prisma: PrismaClient,
  now: Date = new Date()
): Promise<BillingRenewalSummary> {
  const summary: BillingRenewalSummary = { renewed: 0, retried: 0, downgraded: 0 };

  const due = await prisma.user.findMany({
    where: {
      subscriptionPlanId: { not: null },
      nextBillingAt: { lte: now },
    },
    select: {
      id: true,
      email: true,
      subscriptionPlanId: true,
      tossBillingKey: true,
      tossCustomerKey: true,
      subscriptionCanceledAt: true,
      billingFailCount: true,
      nextBillingAt: true,
    },
  });

  for (const user of due) {
    try {
      // 해지 예약 또는 청구 수단 결손 → 청구 없이 FREE 전환
      if (
        user.subscriptionCanceledAt ||
        !user.tossBillingKey ||
        !user.tossCustomerKey ||
        !isValidPlanId(user.subscriptionPlanId ?? "")
      ) {
        await prisma.user.update({ where: { id: user.id }, data: freeDowngradeData() });
        summary.downgraded += 1;
        continue;
      }

      const planId = user.subscriptionPlanId as keyof typeof PLANS;
      const plan = PLANS[planId];
      const order = await prisma.paymentOrder.create({
        data: {
          orderId: crypto.randomUUID(),
          userId: user.id,
          planId,
          amount: plan.monthlyPrice,
        },
      });

      try {
        const payment = await chargeBillingKey({
          billingKey: user.tossBillingKey,
          customerKey: user.tossCustomerKey,
          amount: order.amount,
          orderId: order.orderId,
          orderName: `널스탁 ${plan.name} 플랜 월 이용료`,
          customerEmail: user.email,
          idempotencyKey: order.orderId,
        });

        await prisma.$transaction([
          prisma.paymentOrder.update({
            where: { orderId: order.orderId },
            data: {
              status: "DONE",
              paymentKey: payment.paymentKey,
              approvedAt: payment.approvedAt ? new Date(payment.approvedAt) : now,
            },
          }),
          prisma.user.update({
            where: { id: user.id },
            data: {
              planTier: planId,
              // 다음 결제일은 예정 시각 기준으로 굴린다(재시도 지연으로 주기가 밀리지 않게)
              nextBillingAt: addMonthsClamped(user.nextBillingAt ?? now, 1),
              billingFailCount: 0,
            },
          }),
        ]);
        summary.renewed += 1;
      } catch (error) {
        const failReason =
          error instanceof TossPaymentError ? error.code : "RENEWAL_CHARGE_ERROR";
        await prisma.paymentOrder.update({
          where: { orderId: order.orderId },
          data: { status: "FAILED", failReason },
        });

        const failCount = user.billingFailCount + 1;
        if (failCount >= BILLING_MAX_FAIL_COUNT) {
          await prisma.user.update({ where: { id: user.id }, data: freeDowngradeData() });
          summary.downgraded += 1;
        } else {
          await prisma.user.update({
            where: { id: user.id },
            data: {
              billingFailCount: failCount,
              nextBillingAt: new Date(now.getTime() + BILLING_RETRY_DELAY_MS),
            },
          });
          summary.retried += 1;
        }
        console.error(
          `[BillingRenewal] 청구 실패 userId=${user.id} (${failCount}/${BILLING_MAX_FAIL_COUNT}): ${failReason}`
        );
      }
    } catch (error) {
      // 사용자 한 명의 실패가 나머지 갱신을 막지 않도록 개별 격리
      console.error(`[BillingRenewal] 갱신 처리 실패 userId=${user.id}:`, error);
    }
  }

  return summary;
}
