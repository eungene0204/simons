import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";

// DELETE: 본인 계정 삭제(soft delete, status=DELETED — 관리자 콘솔의 삭제와 동일한 의미).
// 자동갱신 구독이 활성 상태면 남은 빌링키로 청구가 계속되므로 먼저 구독 취소(해지 예약)를 요구한다.
// 삭제 시 빌링 상태를 모두 비워 이후 어떤 자동 청구도 일어나지 않게 한다.
export async function DELETE() {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const record = await prisma.user.findUnique({
      where: { id: user.id },
      select: { subscriptionPlanId: true, subscriptionCanceledAt: true },
    });
    if (record?.subscriptionPlanId && !record.subscriptionCanceledAt) {
      return NextResponse.json(
        { error: "계정을 삭제하려면 먼저 요금제 구독을 취소해 주세요." },
        { status: 400 }
      );
    }

    await prisma.user.update({
      where: { id: user.id },
      data: {
        status: "DELETED",
        planTier: "FREE",
        planStartDate: null,
        tossBillingKey: null,
        subscriptionPlanId: null,
        nextBillingAt: null,
        subscriptionCanceledAt: null,
        billingFailCount: 0,
      },
    });

    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Failed to delete account:", error);
    return NextResponse.json(
      { error: "계정 삭제에 실패했습니다." },
      { status: 500 }
    );
  }
}
