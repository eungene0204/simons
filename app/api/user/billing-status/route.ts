import { NextResponse } from "next/server";
import { getSessionUserId } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { getPlan } from "@/lib/plans";
import { BILLING_MAX_FAIL_COUNT } from "@/lib/server/billingRenewal";

export const dynamic = "force-dynamic";

// 자동결제 실패 배너용 상태(2026-11-26) — 메일 발송 계정이 없어 사이트 안에서 알린다.
// 상단 메뉴가 페이지 진입마다 부르므로 한 번의 조회로 끝낸다. 실패 상태가 아니면 failure=null.
// 대상은 토스 자동결제뿐이다(PayPal은 PayPal이 갱신·안내하고 이 실패 횟수를 쓰지 않는다).
export async function GET() {
  const userId = await getSessionUserId();
  if (userId == null) return NextResponse.json({ failure: null });

  try {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: {
        billingFailCount: true,
        nextBillingAt: true,
        subscriptionPlanId: true,
        subscriptionCanceledAt: true,
        paymentProvider: true,
      },
    });
    const failing =
      user != null &&
      user.billingFailCount > 0 &&
      user.subscriptionPlanId != null &&
      user.subscriptionCanceledAt == null &&
      user.paymentProvider === "toss";
    if (!failing) return NextResponse.json({ failure: null });

    return NextResponse.json({
      failure: {
        planName: getPlan(user.subscriptionPlanId).name,
        failCount: user.billingFailCount,
        maxFailCount: BILLING_MAX_FAIL_COUNT,
        nextRetryAt: user.nextBillingAt?.toISOString() ?? null,
      },
    });
  } catch (error) {
    // 배너는 부가 안내다 — 조회 실패로 화면을 깨뜨리지 않는다.
    console.error("Failed to read billing status:", error);
    return NextResponse.json({ failure: null });
  }
}
