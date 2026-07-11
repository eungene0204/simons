import { NextResponse } from "next/server";
import {
  assertActiveUser,
  getSessionUserId,
  isUnauthorizedAccessError,
} from "@/lib/get-user";
import { prisma } from "@/lib/prisma";

// GET: 내 결제(청구) 내역 — 설정 모달 결제 탭의 청구서 목록.
// PENDING(승인 전 이탈 주문)은 실제 청구가 아니므로 제외한다.
// 원격 DB 왕복을 줄이기 위해 토큰은 DB 없이 해석하고 상태 검증과 조회를 병렬로 실행한다.
export async function GET() {
  try {
    const userId = await getSessionUserId();
    if (userId == null) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const [, orders] = await Promise.all([
      assertActiveUser(userId),
      prisma.paymentOrder.findMany({
        where: { userId, status: { in: ["DONE", "FAILED"] } },
        orderBy: { createdAt: "desc" },
        take: 24,
        select: {
          id: true,
          planId: true,
          amount: true,
          status: true,
          approvedAt: true,
          createdAt: true,
        },
      }),
    ]);

    return NextResponse.json({
      orders: orders.map((order) => ({
        id: order.id,
        planId: order.planId,
        amount: order.amount,
        status: order.status,
        date: (order.approvedAt ?? order.createdAt).toISOString(),
      })),
    });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch payment orders:", error);
    return NextResponse.json(
      { error: "결제 내역을 불러오지 못했습니다." },
      { status: 500 }
    );
  }
}
