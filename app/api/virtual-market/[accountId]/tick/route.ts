import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

// POST: 프론트엔드 폴링용 — 경과시간 확인 후 step 위임
export async function POST(
  request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    const state = await prisma.virtualMarketState.findUnique({
      where: { accountId: params.accountId },
    });

    if (!state || state.status !== "running") {
      return NextResponse.json({ stepped: false, reason: "not running" });
    }

    // 경과시간 체크
    const elapsed =
      (Date.now() - new Date(state.updatedAt).getTime()) / 1000;

    if (elapsed < state.speed) {
      return NextResponse.json({
        stepped: false,
        reason: "waiting",
        nextStepIn: Math.ceil(state.speed - elapsed),
        currentDate: state.virtualDate,
      });
    }

    // step API 호출 (내부 위임)
    const origin = new URL(request.url).origin;
    const stepRes = await fetch(
      `${origin}/api/virtual-market/${params.accountId}/step`,
      { method: "POST" }
    );
    const stepData = await stepRes.json();

    return NextResponse.json(stepData);
  } catch (error) {
    console.error("Virtual market tick error:", error);
    return NextResponse.json(
      { error: "Tick failed" },
      { status: 500 }
    );
  }
}
