import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from "@/lib/get-user";

// POST: 전략 자동 실행 중지
export async function POST(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext();
    const account = await prisma.virtualAccount.findFirst({
      where: withOwnership({ id: params.id }, userId),
    });
    if (!account) {
      return NextResponse.json({ error: "Account not found" }, { status: 404 });
    }

    // 가상시장 상태 삭제
    await prisma.virtualMarketState.deleteMany({
      where: { accountId: params.id },
    });

    // tradingMode를 manual로 복원
    await prisma.virtualAccount.update({
      where: { id: params.id },
      data: { tradingMode: "manual" },
    });

    console.log(`[전략 자동 실행] 계좌=${params.id} 중지`);

    return NextResponse.json({ message: "전략 자동 실행이 중지되었습니다." });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Strategy stop error:", error);
    return NextResponse.json(
      { error: "전략 자동 실행 중지에 실패했습니다." },
      { status: 500 }
    );
  }
}
