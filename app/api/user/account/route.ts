import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { GUEST_DELETE_BLOCKED_MESSAGE, isGuestEmail } from "@/lib/server/guestAccounts";
import { releasedDeletedEmail } from "@/lib/server/deletedAccountEmail";

// DELETE: 본인 계정 삭제(soft delete, status=DELETED). 관리자 삭제와 달리 이메일을 해제해
// 같은 주소로 재가입할 수 있게 한다(관리자 삭제=제재는 이메일을 계속 점유한다).
// 자동갱신 구독이 활성 상태면 남은 빌링키로 청구가 계속되므로 먼저 구독 취소(해지 예약)를 요구한다.
// 삭제 시 빌링 상태를 모두 비워 이후 어떤 자동 청구도 일어나지 않게 한다.
export async function DELETE() {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // 게스트(특별 계정)는 운영자가 발급하고 운영자가 회수한다 — 본인 삭제를 막는다.
    // 게스트 아이디는 운영자만 발급하므로, 실수로 지우면 본인이 같은 아이디를 되살릴 수 없다.
    if (isGuestEmail(user.email)) {
      return NextResponse.json({ error: GUEST_DELETE_BLOCKED_MESSAGE }, { status: 403 });
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
        // 본인 삭제는 재가입을 허용한다 — 원래 이메일을 비워 같은 주소로 새 계정을 만들 수 있게 한다.
        email: releasedDeletedEmail(user.id, user.email),
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
