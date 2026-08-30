import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { PaypalProvider, PaypalError } from "@/lib/payment/PaypalProvider";
import { markPaypalSubscriptionCanceled } from "@/lib/server/paypalSubscription";

// POST: 구독 해지. PayPal 쪽 구독을 취소해 다음 청구를 멈추고, 우리 쪽에는 해지 예약만
// 기록한다 — 남은 기간까지는 유료 플랜을 유지하고(약관 제12조 8항), 기간이 끝나면
// 만료 스윕(lib/server/paypalSubscriptionExpiry.ts)이 FREE로 내린다.
export async function POST() {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const record = await prisma.user.findUnique({
      where: { id: user.id },
      select: {
        paypalSubscriptionId: true,
        subscriptionPlanId: true,
        subscriptionCanceledAt: true,
        nextBillingAt: true,
      },
    });
    if (!record?.paypalSubscriptionId || !record.subscriptionPlanId) {
      return NextResponse.json({ error: "해지할 구독이 없습니다." }, { status: 400 });
    }
    if (record.subscriptionCanceledAt) {
      // 이미 해지 예약됨 — 멱등 처리
      return NextResponse.json({
        ok: true,
        expiresAt: record.nextBillingAt?.toISOString() ?? null,
      });
    }

    try {
      await new PaypalProvider().cancelSubscription(record.paypalSubscriptionId);
    } catch (error) {
      // 이미 PayPal 쪽에서 취소된 구독이면 우리 기록만 맞추면 된다
      if (!(error instanceof PaypalError) || error.httpStatus >= 500) {
        throw error;
      }
    }

    await markPaypalSubscriptionCanceled(prisma, user.id);

    return NextResponse.json({
      ok: true,
      expiresAt: record.nextBillingAt?.toISOString() ?? null,
    });
  } catch (error) {
    console.error("Failed to cancel PayPal subscription:", error);
    return NextResponse.json({ error: "구독 해지에 실패했습니다." }, { status: 500 });
  }
}
