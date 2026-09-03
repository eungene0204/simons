import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { cancelUserSubscription } from "@/lib/server/subscriptionCancel";

// POST: 자동갱신 해지 예약. 즉시 FREE로 내리지 않고 다음 결제일까지 유료 플랜을 유지하며,
// 기간이 끝나면 갱신 잡(billingRenewal)·만료 스윕(paypalSubscriptionExpiry)이 FREE로 전환한다
// — 약관 제12조 8항. 결제 수단(토스/PayPal) 분기는 cancelUserSubscription이 맡는다 —
// 설정 모달이 /us에서도 이 라우트를 쓰므로 PayPal 구독도 여기서 실제로 취소돼야 한다.
export async function POST() {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const outcome = await cancelUserSubscription(prisma, user.id);
    if (outcome.status === "none") {
      return NextResponse.json({ error: "해지할 구독이 없습니다." }, { status: 400 });
    }
    return NextResponse.json({ ok: true, expiresAt: outcome.expiresAt });
  } catch (error) {
    console.error("Failed to cancel subscription:", error);
    return NextResponse.json({ error: "구독 해지에 실패했습니다." }, { status: 500 });
  }
}
