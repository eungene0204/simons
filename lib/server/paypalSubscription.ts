// PayPal 정기구독의 서버 반영 — 플랜 승격·결제 이력·해지·강등이 전부 여기를 거친다.
//
// 승인 복귀 화면과 웹훅 두 경로가 같은 사실을 알려오므로 모든 함수는 멱등이다.
// (정본은 웹훅이고, 승인 복귀는 사용자가 결과를 즉시 보게 하기 위한 보조 경로다.)
import crypto from "crypto";
import type { PrismaClient } from "@prisma/client";
import type { PlanId } from "@/lib/plans";
import { usdCentsFor } from "@/lib/payment/paypalPlans";
import { addMonthsClamped } from "@/lib/server/planLimits";

export interface ActivateInput {
  userId: number;
  planId: PlanId;
  subscriptionId: string;
  payerId?: string;
  /** PayPal이 알려준 다음 청구 예정 시각(ISO). 없으면 +1개월로 둔다. */
  nextBillingTime?: string;
}

/** 구독을 활성 상태로 반영한다. 이미 같은 구독으로 활성이면 아무것도 하지 않고 false. */
export async function activatePaypalSubscription(
  prisma: PrismaClient,
  input: ActivateInput
): Promise<boolean> {
  const current = await prisma.user.findUnique({
    where: { id: input.userId },
    select: {
      planTier: true,
      paypalSubscriptionId: true,
      subscriptionPlanId: true,
      subscriptionCanceledAt: true,
      nextBillingAt: true,
    },
  });
  const nextBillingMatches =
    !input.nextBillingTime ||
    current?.nextBillingAt?.getTime() === new Date(input.nextBillingTime).getTime();
  if (
    current?.paypalSubscriptionId === input.subscriptionId &&
    current?.subscriptionPlanId === input.planId &&
    current?.planTier === input.planId &&
    current?.subscriptionCanceledAt == null &&
    // 날짜가 PayPal 값과 어긋나 있으면 맞춘다 — 조회 경로가 드리프트를 고칠 수 있어야 한다
    nextBillingMatches
  ) {
    return false;
  }

  const now = new Date();
  await prisma.user.update({
    where: { id: input.userId },
    data: {
      planTier: input.planId,
      planStartDate: now,
      paymentProvider: "paypal",
      paypalSubscriptionId: input.subscriptionId,
      ...(input.payerId ? { paypalPayerId: input.payerId } : {}),
      subscriptionPlanId: input.planId,
      nextBillingAt: input.nextBillingTime
        ? new Date(input.nextBillingTime)
        : addMonthsClamped(now, 1),
      subscriptionCanceledAt: null,
      billingFailCount: 0,
    },
  });
  return true;
}

/**
 * 월 청구 성공을 기록하고 다음 결제일을 PayPal이 알려준 값으로 맞춘다.
 *
 * 다음 청구일을 우리가 계산하지 않는다 — 갱신 주체가 PayPal이기 때문이다. 종전엔 저장값에
 * +1개월을 더했는데, 활성화 통지가 이미 PayPal의 정본 값을 넣어 둔 뒤라 첫 결제에서 한 달이
 * 밀렸다(2026-08-31 prod E2E: PayPal 9/30 vs 우리 10/30). nextBillingTime이 없으면 기존
 * 값을 그대로 둔다 — 모르는 값을 지어내지 않는다.
 *
 * saleId가 결제의 고유 키라 같은 결제가 두 번 통지돼도 이력이 겹쳐 쌓이지 않는다(paymentKey unique).
 */
export async function recordPaypalSubscriptionPayment(
  prisma: PrismaClient,
  input: {
    userId: number;
    planId: PlanId;
    saleId: string;
    approvedAt?: string;
    /** PayPal이 알려준 다음 청구 예정 시각(ISO) */
    nextBillingTime?: string;
  }
): Promise<boolean> {
  const existing = await prisma.paymentOrder.findUnique({
    where: { paymentKey: input.saleId },
    select: { id: true },
  });
  if (existing) return false;

  const now = new Date();

  await prisma.$transaction([
    prisma.paymentOrder.create({
      data: {
        orderId: crypto.randomUUID(),
        userId: input.userId,
        planId: input.planId,
        provider: "paypal",
        currency: "USD",
        amount: usdCentsFor(input.planId),
        status: "DONE",
        paymentKey: input.saleId,
        approvedAt: input.approvedAt ? new Date(input.approvedAt) : now,
      },
    }),
    prisma.user.update({
      where: { id: input.userId },
      data: {
        ...(input.nextBillingTime ? { nextBillingAt: new Date(input.nextBillingTime) } : {}),
        billingFailCount: 0,
      },
    }),
  ]);
  return true;
}

/**
 * 해지 예약 — 즉시 FREE로 내리지 않고 남은 기간까지 유료 플랜을 유지한다(약관 제12조 8항).
 * 기간이 끝나면 만료 스윕(processDuePaypalExpirations)이 FREE로 내린다.
 */
export async function markPaypalSubscriptionCanceled(
  prisma: PrismaClient,
  userId: number,
  canceledAt: Date = new Date()
): Promise<void> {
  await prisma.user.update({
    where: { id: userId },
    data: { subscriptionCanceledAt: canceledAt },
  });
}

/** FREE 전환 + 구독 상태 비우기 — 잔존 구독 ID로 다시 청구가 반영되지 않게 한다. */
export async function downgradePaypalSubscriber(
  prisma: PrismaClient,
  userId: number
): Promise<void> {
  await prisma.user.update({
    where: { id: userId },
    data: {
      planTier: "FREE",
      planStartDate: null,
      paypalSubscriptionId: null,
      subscriptionPlanId: null,
      nextBillingAt: null,
      subscriptionCanceledAt: null,
      billingFailCount: 0,
    },
  });
}
