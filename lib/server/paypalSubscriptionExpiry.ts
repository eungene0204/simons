// 해지 예약된 PayPal 구독의 기간 만료 스윕 — 스케줄러가 토스 갱신 잡과 함께 호출한다.
//
// 토스 구독은 우리가 청구하니 갱신 잡이 만료도 함께 처리하지만, PayPal 구독은 PayPal이
// 갱신하므로 그 잡의 대상이 아니다(lib/server/billingRenewal.ts는 toss만 조회). 해지 예약된
// 구독을 기간 끝에 FREE로 내리는 일은 여기서만 일어난다.
//
// 해지 예약된 것만 대상으로 한다 — 활성 구독은 PayPal이 청구하고 그 결과가 웹훅으로
// 들어오므로, 통지가 잠깐 늦었다고 유료 사용자를 내리면 안 된다.
import type { PrismaClient } from "@prisma/client";
import { downgradePaypalSubscriber } from "@/lib/server/paypalSubscription";
import { backtestUsageCarryOnDowngrade, USAGE_CARRY_SELECT } from "@/lib/server/planDowngrade";

export interface PaypalExpirySummary {
  downgraded: number;
}

export async function processDuePaypalExpirations(
  prisma: PrismaClient,
  now: Date = new Date()
): Promise<PaypalExpirySummary> {
  const summary: PaypalExpirySummary = { downgraded: 0 };

  const due = await prisma.user.findMany({
    where: {
      paymentProvider: "paypal",
      subscriptionPlanId: { not: null },
      subscriptionCanceledAt: { not: null },
      nextBillingAt: { lte: now },
    },
    select: { id: true, ...USAGE_CARRY_SELECT },
  });

  for (const user of due) {
    try {
      await downgradePaypalSubscriber(prisma, user.id, backtestUsageCarryOnDowngrade(user, now));
      summary.downgraded += 1;
    } catch (error) {
      // 한 명의 실패가 나머지를 막지 않도록 개별 격리
      console.error(`[PaypalExpiry] FREE 전환 실패 userId=${user.id}:`, error);
    }
  }

  return summary;
}
