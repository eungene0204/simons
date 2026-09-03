// 자동갱신 구독 해지(예약) — 결제 수단(PSP)에 따라 갈라지는 유일한 지점.
//
// 토스 구독은 우리가 청구하므로 해지 예약(subscriptionCanceledAt)만 적으면 갱신 잡이
// 다음 결제일에 청구 없이 FREE로 내린다. PayPal 구독은 PayPal이 청구하므로 PayPal 쪽 구독을
// 먼저 취소해야 한다 — 우리 기록만 바꾸면 청구는 계속되고 다음 결제 웹훅이 등급을 다시 올린다
// (2026-09-03 감사: KR 요금제 페이지·설정 모달이 PayPal 구독자에게도 토스 경로만 탔다).
// 어느 경로든 남은 결제 기간까지는 유료 플랜을 유지한다(약관 제12조 8항).
import type { PrismaClient } from "@prisma/client";
import { PaypalProvider, PaypalError } from "@/lib/payment/PaypalProvider";
import { markPaypalSubscriptionCanceled } from "@/lib/server/paypalSubscription";

export type CancelSubscriptionOutcome =
  | { status: "none" }
  | { status: "already" | "scheduled"; expiresAt: string | null };

export async function cancelUserSubscription(
  prisma: PrismaClient,
  userId: number
): Promise<CancelSubscriptionOutcome> {
  const record = await prisma.user.findUnique({
    where: { id: userId },
    select: {
      paymentProvider: true,
      paypalSubscriptionId: true,
      subscriptionPlanId: true,
      subscriptionCanceledAt: true,
      nextBillingAt: true,
    },
  });
  if (!record?.subscriptionPlanId) {
    return { status: "none" };
  }
  const expiresAt = record.nextBillingAt?.toISOString() ?? null;
  if (record.subscriptionCanceledAt) {
    return { status: "already", expiresAt };
  }

  if (record.paymentProvider === "paypal" && record.paypalSubscriptionId) {
    try {
      await new PaypalProvider().cancelSubscription(record.paypalSubscriptionId);
    } catch (error) {
      // 이미 PayPal 쪽에서 취소된 구독이면 우리 기록만 맞추면 된다
      if (!(error instanceof PaypalError) || error.httpStatus >= 500) {
        throw error;
      }
    }
    await markPaypalSubscriptionCanceled(prisma, userId);
    return { status: "scheduled", expiresAt };
  }

  await prisma.user.update({
    where: { id: userId },
    data: { subscriptionCanceledAt: new Date() },
  });
  return { status: "scheduled", expiresAt };
}
