import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { cancelUserSubscription } from "@/lib/server/subscriptionCancel";

// POST: 구독 해지. PayPal 쪽 구독을 취소해 다음 청구를 멈추고, 우리 쪽에는 해지 예약만
// 기록한다 — 남은 기간까지는 유료 플랜을 유지하고(약관 제12조 8항), 기간이 끝나면
// 만료 스윕(lib/server/paypalSubscriptionExpiry.ts)이 FREE로 내린다.
// 실제 분기는 cancelUserSubscription(결제 수단별)에 있다 — 토스 해지 라우트와 같은 헬퍼다.
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
    console.error("Failed to cancel PayPal subscription:", error);
    return NextResponse.json({ error: "구독 해지에 실패했습니다." }, { status: 500 });
  }
}
