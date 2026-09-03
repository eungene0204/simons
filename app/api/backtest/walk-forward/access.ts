import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { getUserPlan } from "@/lib/server/planLimits";

// 워크포워드 검증은 요금제 페이지가 프리미엄 전용으로 안내하는 기능이다. 화면 잠금
// (OptimizationPage)만으로는 API 직접 호출을 막지 못하므로 두 프록시 라우트(단발·SSE)가
// 백엔드로 넘기기 전에 여기서 로그인·플랜을 재검증한다.
export const WALK_FORWARD_ALLOWED_PLANS = new Set(["PREMIUM"]);
export const WALK_FORWARD_PLAN_MESSAGE =
  "워크포워드 검증은 프리미엄 플랜에서 사용할 수 있습니다.";

/** 허용되면 null, 아니면 클라이언트가 detail로 읽는 401/403 응답을 돌려준다. */
export async function rejectWalkForwardIfNotAllowed(): Promise<NextResponse | null> {
  const user = await getCurrentUser();
  if (!user) {
    return NextResponse.json({ detail: "로그인이 필요합니다." }, { status: 401 });
  }
  const plan = await getUserPlan(prisma, user.id);
  if (!WALK_FORWARD_ALLOWED_PLANS.has(plan.planId)) {
    return NextResponse.json({ detail: WALK_FORWARD_PLAN_MESSAGE }, { status: 403 });
  }
  return null;
}
