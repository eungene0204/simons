import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";

// POST: 자동갱신 해지 예약. 즉시 FREE로 내리지 않고 다음 결제일까지 유료 플랜을 유지하며,
// 다음 결제일에 갱신 잡(billingRenewal)이 청구 없이 FREE로 전환한다 — 약관 제12조 8항.
export async function POST() {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const record = await prisma.user.findUnique({
      where: { id: user.id },
      select: { subscriptionPlanId: true, nextBillingAt: true, subscriptionCanceledAt: true },
    });
    if (!record?.subscriptionPlanId) {
      return NextResponse.json({ error: "해지할 구독이 없습니다." }, { status: 400 });
    }
    if (record.subscriptionCanceledAt) {
      // 이미 해지 예약됨 — 멱등 처리
      return NextResponse.json({
        ok: true,
        expiresAt: record.nextBillingAt?.toISOString() ?? null,
      });
    }

    await prisma.user.update({
      where: { id: user.id },
      data: { subscriptionCanceledAt: new Date() },
    });

    return NextResponse.json({
      ok: true,
      expiresAt: record.nextBillingAt?.toISOString() ?? null,
    });
  } catch (error) {
    console.error("Failed to cancel subscription:", error);
    return NextResponse.json({ error: "구독 해지에 실패했습니다." }, { status: 500 });
  }
}
