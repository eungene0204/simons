// PayPal 정기구독의 서버 반영 — 플랜 승격·결제 이력·해지·강등이 전부 여기를 거친다.
//
// 승인 복귀 화면과 웹훅 두 경로가 같은 사실을 알려오므로 모든 함수는 멱등이다.
// (정본은 웹훅이고, 승인 복귀는 사용자가 결과를 즉시 보게 하기 위한 보조 경로다.)
import crypto from "crypto";
import type { PrismaClient } from "@prisma/client";
import {
  backtestUsageCarryOnDowngrade,
  USAGE_CARRY_SELECT,
  type UsageCarry,
} from "@/lib/server/planDowngrade";
import type { PlanId } from "@/lib/plans";
import { usdCentsFor } from "@/lib/payment/paypalPlans";
import {
  addMonthsClamped,
  currentUsagePeriodKey,
  getEffectivePlan,
} from "@/lib/server/planLimits";

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
      planStartDate: true,
      paypalSubscriptionId: true,
      paypalPriorSubscriptionId: true,
      subscriptionPlanId: true,
      subscriptionCanceledAt: true,
      nextBillingAt: true,
      backtestUsageMonth: true,
      backtestCountThisMonth: true,
    },
  });
  const nextBillingMatches =
    !input.nextBillingTime ||
    current?.nextBillingAt?.getTime() === new Date(input.nextBillingTime).getTime();
  const sameBinding =
    current?.paypalSubscriptionId === input.subscriptionId &&
    current?.subscriptionPlanId === input.planId &&
    current?.subscriptionCanceledAt == null;
  if (sameBinding) {
    // 예약된 플랜 변경 상태: 청구 플랜은 이미 input.planId인데 등급(planTier)은 이전 유료
    // 플랜이다. 등급 전환은 다음 결제(recordPaypalSubscriptionPayment)가 수행한다 — 여기서
    // 앞당기면 남은 기간의 상위 플랜을 빼앗는다(sync 재호출 등 조회 경로가 이 상태를 지나간다).
    // 단, 업그레이드 전환 중(이전 구독 보관 상태)은 예약이 아니라 즉시 전환이다 — 이미
    // 새 구독으로 결제가 일어났으므로 등급을 지금 올린다.
    const isUpgradeCompletion = current.paypalPriorSubscriptionId != null;
    if (current.planTier !== input.planId && current.planTier !== "FREE" && !isUpgradeCompletion) {
      return false;
    }
    // 등급까지 이미 일치하면(업그레이드 완료 직후 웹훅 재활성화 포함) 멱등 처리한다 —
    // 여기서 풀 업데이트로 흘리면 planStartDate가 다시 이동해 사용량 주기 키가 이월
    // 기록(backtestUsageMonth)과 어긋나고, 병합해 둔 잔여 횟수가 조용히 증발한다
    // (2026-08-31 재검증에서 sync·웹훅 이중 활성화로 실제 발생 — 8초 차이).
    if (current.planTier === input.planId) {
      if (nextBillingMatches) return false;
      // 날짜가 PayPal 값과 어긋나 있으면 맞춘다 — 조회 경로가 드리프트를 고칠 수 있어야 한다
      await prisma.user.update({
        where: { id: input.userId },
        data: { nextBillingAt: new Date(input.nextBillingTime as string) },
      });
      return true;
    }
  }

  const now = new Date();

  // 업그레이드 병합(2026-08-31 정책): 갱신일·사용량 주기가 변경일로 리셋되므로, 옛 플랜의
  // 미사용 백테스트 횟수를 버리지 않고 새 주기에 보너스로 이월한다(음수 카운터 = 이월분).
  // 예: PRO 500회 중 100회 사용 → 잔여 400 → PREMIUM 새 주기 한도 1000+400.
  let backtestCarry: { backtestUsageMonth: string; backtestCountThisMonth: number } | null = null;
  if (
    current?.paypalPriorSubscriptionId != null &&
    current.planTier !== "FREE" &&
    current.planTier !== input.planId
  ) {
    const oldPlan = await getEffectivePlan(prisma, current.planTier);
    const oldPeriodKey = currentUsagePeriodKey(current.planStartDate, now);
    const usedThisPeriod =
      current.backtestUsageMonth === oldPeriodKey ? current.backtestCountThisMonth : 0;
    const remaining = Math.max(0, oldPlan.monthlyBacktestLimit - usedThisPeriod);
    if (remaining > 0) {
      backtestCarry = {
        backtestUsageMonth: currentUsagePeriodKey(now, now),
        backtestCountThisMonth: -remaining,
      };
    }
  }

  await prisma.user.update({
    where: { id: input.userId },
    data: {
      planTier: input.planId,
      planStartDate: now,
      ...(backtestCarry ?? {}),
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
        // 청구가 확정된 플랜이 곧 등급이다 — 예약된 플랜 변경(revise)은 이 순간 전환된다
        planTier: input.planId,
        ...(input.nextBillingTime ? { nextBillingAt: new Date(input.nextBillingTime) } : {}),
        billingFailCount: 0,
      },
    }),
  ]);
  return true;
}

/**
 * 플랜 변경(revise) 승인 반영 — 다음 청구 플랜(subscriptionPlanId)만 바꾸고 등급(planTier)은
 * 건드리지 않는다. 남은 기간은 기존 플랜을 유지하고, 다음 결제가 들어올 때
 * recordPaypalSubscriptionPayment가 등급을 청구 플랜으로 전환한다.
 */
export async function schedulePaypalPlanChange(
  prisma: PrismaClient,
  input: { userId: number; planId: PlanId; nextBillingTime?: string }
): Promise<void> {
  await prisma.user.update({
    where: { id: input.userId },
    data: {
      subscriptionPlanId: input.planId,
      ...(input.nextBillingTime ? { nextBillingAt: new Date(input.nextBillingTime) } : {}),
    },
  });
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

/**
 * FREE 전환 + 구독 상태 비우기 — 잔존 구독 ID로 다시 청구가 반영되지 않게 한다.
 * carry는 이번 주기 백테스트 사용량 이월(lib/server/planDowngrade) — 호출자가 User 필드를
 * 이미 들고 있으면 계산해서 넘기고, 없으면 downgradePaypalSubscriberById를 쓴다.
 */
export async function downgradePaypalSubscriber(
  prisma: PrismaClient,
  userId: number,
  carry: UsageCarry
): Promise<void> {
  await prisma.user.update({
    where: { id: userId },
    data: {
      ...carry,
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

/** userId만 아는 호출자(웹훅)용 — 사용량 이월 필드를 읽어 강등한다. */
export async function downgradePaypalSubscriberById(
  prisma: PrismaClient,
  userId: number,
  now: Date = new Date()
): Promise<void> {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: USAGE_CARRY_SELECT,
  });
  await downgradePaypalSubscriber(prisma, userId, backtestUsageCarryOnDowngrade(user ?? {}, now));
}
