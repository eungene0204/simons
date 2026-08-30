import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { PaypalProvider, PaypalError } from "@/lib/payment/PaypalProvider";
import { planIdFromPaypalPlan } from "@/lib/payment/paypalPlans";
import { activatePaypalSubscription } from "@/lib/server/paypalSubscription";

// POST: 승인 복귀 화면이 호출하는 상태 동기화.
// 유료 전환의 정본은 웹훅이지만, 사용자가 돌아온 직후에도 결과가 보이도록 여기서 한 번 더
// PayPal에 상태를 물어 반영한다(웹훅과 같은 멱등 경로를 쓴다).
export async function POST(request: Request) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const record = await prisma.user.findUnique({
      where: { id: user.id },
      select: { paypalSubscriptionId: true, planTier: true },
    });
    const subscriptionId = record?.paypalSubscriptionId;
    if (!subscriptionId) {
      return NextResponse.json({ error: "구독 정보를 찾을 수 없습니다." }, { status: 404 });
    }

    const state = await new PaypalProvider().getSubscription(subscriptionId);
    // 남의 구독 ID를 밀어 넣어도 반영되지 않게, 구독에 박힌 참조값과 로그인 사용자를 대조한다
    if (state.userRef && state.userRef !== String(user.id)) {
      return NextResponse.json({ error: "구독 정보가 일치하지 않습니다." }, { status: 403 });
    }

    const planId = planIdFromPaypalPlan(state.providerPlanId);
    if (!state.active || !planId) {
      return NextResponse.json({ status: state.status, planId: record?.planTier ?? "FREE" });
    }

    await activatePaypalSubscription(prisma, {
      userId: user.id,
      planId,
      subscriptionId,
      payerId: state.payerId,
      nextBillingTime: state.nextBillingTime,
    });

    return NextResponse.json({ status: state.status, planId });
  } catch (error) {
    if (error instanceof PaypalError) {
      return NextResponse.json({ error: error.message }, { status: 502 });
    }
    console.error("Failed to sync PayPal subscription:", error);
    return NextResponse.json({ error: "구독 상태 확인에 실패했습니다." }, { status: 500 });
  }
}
