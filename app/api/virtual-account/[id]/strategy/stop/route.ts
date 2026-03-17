import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

// POST: 전략 자동 실행 중지
export async function POST(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const account = await prisma.virtualAccount.findUnique({
      where: { id: params.id },
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
    console.error("Strategy stop error:", error);
    return NextResponse.json(
      { error: "전략 자동 실행 중지에 실패했습니다." },
      { status: 500 }
    );
  }
}
