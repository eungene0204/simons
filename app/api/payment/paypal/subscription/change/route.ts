import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { isValidPlanId } from "@/lib/plans";
import { PaypalProvider, PaypalError, isPaypalConfigured } from "@/lib/payment/PaypalProvider";
import { isPaypalSubscriptionConfigured, paypalPlanIdFor } from "@/lib/payment/paypalPlans";
import { US_PRICING } from "@/lib/pricing/us";
import { publicOriginFrom } from "@/lib/server/publicOrigin";

// POST: 구독 중 플랜 변경. 방향에 따라 정책이 다르다(2026-08-31 확정):
//
// - 다운그레이드: PayPal revise로 빌링 플랜만 예약 교체 — 남은 기간은 현재 플랜 유지,
//   다음 결제일부터 새 가격·등급(그 결제가 확인될 때 planTier 전환).
// - 업그레이드: 즉시 전환 + 상위 플랜 월액 즉시 청구, **갱신일은 변경일로 고정**(+1개월).
//   남은 하위 플랜의 소모성 혜택(백테스트 잔여 횟수)은 버리지 않고 새 주기에 병합한다
//   (activatePaypalSubscription — 2026-08-31 정책 정정: 기간 연장 크레딧 방식 폐기).
//   이전 구독은 새 구독 활성화가 확인된 뒤 웹훅이 해지한다 — 먼저 해지하면 승인 이탈 시
//   구독을 잃는다.
// - 예약된 다운그레이드 취소(현 등급으로 되돌리기): revise로 원 플랜 복귀, 추가 청구 없음.
export async function POST(request: Request) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    if (!isPaypalConfigured() || !isPaypalSubscriptionConfigured()) {
      return NextResponse.json(
        { error: "PayPal 결제가 아직 설정되지 않았습니다." },
        { status: 503 }
      );
    }

    const { planId } = await request.json();
    if (!isValidPlanId(planId) || US_PRICING.monthlyPrice[planId] <= 0) {
      return NextResponse.json(
        { error: "결제가 필요한 플랜(PRO/PREMIUM)으로만 변경할 수 있습니다." },
        { status: 400 }
      );
    }

    const record = await prisma.user.findUnique({
      where: { id: user.id },
      select: {
        planTier: true,
        paymentProvider: true,
        paypalSubscriptionId: true,
        subscriptionPlanId: true,
        subscriptionCanceledAt: true,
        nextBillingAt: true,
      },
    });
    if (
      record?.paymentProvider !== "paypal" ||
      !record.paypalSubscriptionId ||
      !record.subscriptionPlanId
    ) {
      return NextResponse.json({ error: "변경할 구독이 없습니다." }, { status: 400 });
    }
    if (record.subscriptionCanceledAt) {
      return NextResponse.json(
        { error: "해지 예약된 구독은 플랜을 변경할 수 없습니다. 만료 후 다시 구독해주세요." },
        { status: 409 }
      );
    }
    if (record.subscriptionPlanId === planId) {
      return NextResponse.json({ error: "이미 해당 플랜으로 청구될 예정입니다." }, { status: 400 });
    }

    const origin = publicOriginFrom(request);
    const provider = new PaypalProvider();

    const targetPrice = US_PRICING.monthlyPrice[planId as "PRO" | "PREMIUM"];
    const billedPrice =
      US_PRICING.monthlyPrice[record.subscriptionPlanId as "PRO" | "PREMIUM"] ?? 0;
    // 예약된 다운그레이드를 되돌리는 경우(현 등급으로 복귀)는 추가 청구 없는 revise다
    const isRevertOfPendingChange = planId === record.planTier;

    if (targetPrice > billedPrice && !isRevertOfPendingChange) {
      // 업그레이드: 기본 상위 플랜으로 새 구독을 만든다 — 승인 즉시 청구되고,
      // 다음 갱신일은 자동으로 변경일 + 1개월이 된다(갱신일 고정 정책)
      const session = await provider.createSubscription({
        providerPlanId: paypalPlanIdFor(planId),
        userRef: String(user.id),
        returnUrl: `${origin}/us/pricing/success`,
        cancelUrl: `${origin}/us/pricing`,
        subscriberEmail: user.email,
        requestId: `upg-sub-${user.id}-${planId}-${Date.now()}`,
      });
      // 이전 구독은 보관만 한다 — 새 구독 활성화(웹훅) 확인 후에 해지한다.
      // subscriptionPlanId를 대상 플랜으로 미리 바꿔 둔다: 업그레이드 구독의 plan_id는
      // 1회성 플랜이라 env 매핑으로 알 수 없으므로, 웹훅·이력 기록은 이 값을 정본으로 쓴다
      // (2026-08-31 사고: 이 기록이 없어 활성화 웹훅이 "모르는 플랜"으로 무시 → 등급 미전환·
      //  이전 구독 미해지·이력 오기록 3중 결함).
      await prisma.user.update({
        where: { id: user.id },
        data: {
          paypalPriorSubscriptionId: record.paypalSubscriptionId,
          paypalSubscriptionId: session.subscriptionId,
          subscriptionPlanId: planId,
        },
      });
      return NextResponse.json({ approveUrl: session.approveUrl });
    }

    const session = await provider.reviseSubscriptionPlan({
      subscriptionId: record.paypalSubscriptionId,
      providerPlanId: paypalPlanIdFor(planId),
      // 변경은 성공 화면이 아니라 요금제 화면으로 돌아온다 — 성공 화면의 sync는 초기 구독
      // 승인용이고, 예약 전환의 반영은 UPDATED 웹훅이 담당한다
      returnUrl: `${origin}/us/pricing`,
      cancelUrl: `${origin}/us/pricing`,
    });

    return NextResponse.json({ approveUrl: session.approveUrl ?? null });
  } catch (error) {
    if (error instanceof PaypalError) {
      return NextResponse.json(
        { error: error.message },
        { status: error.httpStatus >= 500 ? 502 : 400 }
      );
    }
    console.error("Failed to revise PayPal subscription:", error);
    return NextResponse.json({ error: "플랜 변경에 실패했습니다." }, { status: 500 });
  }
}
