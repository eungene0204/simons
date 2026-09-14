// 글로벌 서비스(/us) 요금제 페이지 — 영어·USD 전용.
//
// 한국 요금제 화면(PricingPlans + 토스 체크아웃)과 완전히 분리된 트리다. 토스페이먼츠
// 심사 영역(components/pricing/PricingPlans·PaymentCheckout 등)은 여기서 일절 쓰지 않는다.
// 카드 레이아웃은 한국 화면과 동일하게 맞추고(UsPricingPlans), 결제는 PayPal 정기구독
// (app/api/payment/paypal/*)으로 배선돼 있다. 자격증명·플랜이 주입되지 않은 환경에서는
// CTA가 열리지 않는다(준비 중 표시).

import Link from "next/link";
import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { getPlan } from "@/lib/plans";
import { getEffectivePlans } from "@/lib/server/effectivePlans";
import { isPaypalConfigured } from "@/lib/payment/PaypalProvider";
import { isPaypalSubscriptionConfigured } from "@/lib/payment/paypalPlans";
import UsPricingPlans from "@/components/pricing/us/UsPricingPlans";
import { isGuestEmail } from "@/lib/server/guestAccounts";

export default async function UsPricingPage() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/us");
  }

  const [record, plans] = await Promise.all([
    prisma.user.findUnique({
      where: { id: user.id },
      select: {
        planTier: true,
        paymentProvider: true,
        subscriptionPlanId: true,
        nextBillingAt: true,
        subscriptionCanceledAt: true,
      },
    }),
    getEffectivePlans(),
  ]);
  const currentPlanId = getPlan(record?.planTier).planId;
  // PayPal 구독 상태만 표시한다 — 토스 구독은 한국 화면의 소관이다
  const subscription =
    record?.paymentProvider === "paypal" && record.subscriptionPlanId
      ? {
          nextBillingAt: record.nextBillingAt?.toISOString() ?? null,
          canceled: record.subscriptionCanceledAt != null,
          // 청구 플랜(subscriptionPlanId)과 등급(planTier)이 다르면 플랜 변경이 예약된 상태다
          pendingPlanId:
            record.subscriptionPlanId !== currentPlanId
              ? (record.subscriptionPlanId as "PRO" | "PREMIUM")
              : null,
        }
      : null;
  const paypalEnabled = isPaypalConfigured() && isPaypalSubscriptionConfigured();

  return (
    <DashboardLayout userName={user.name || "Guest"}>
      <div className="min-h-[calc(100dvh-var(--top-menu-bar-height,76px))] bg-[var(--background)] px-5 py-6 text-white sm:px-8 lg:px-10">
        <div className="mx-auto flex min-h-[calc(100dvh-var(--top-menu-bar-height,76px)-3rem)] w-full max-w-7xl flex-col">
          <div className="text-center">
            <h1 className="text-4xl font-black tracking-[-0.04em] text-white md:text-6xl">
              Choose your plan
            </h1>
            <p className="mt-2 text-sm font-bold text-gray-500">
              Validate more strategies with more simulated capital and virtual accounts.
            </p>
          </div>

          <div className="mt-14">
            <UsPricingPlans
              currentPlanId={currentPlanId}
              subscription={subscription}
              paypalEnabled={paypalEnabled}
              plans={plans}
              isGuest={isGuestEmail(user.email)}
            />
          </div>

          <p className="mt-8 text-center text-xs font-bold text-[var(--text-label)]">
            {paypalEnabled
              ? "Prices are in USD. Subscriptions renew monthly via PayPal until canceled."
              : "Prices are in USD. Checkout via PayPal is being prepared."}
          </p>
          {/* 결제 전 고지 — 약관(환불 정책 Article 12 포함)에 대한 동의를 결제 지점에서 밝힌다 */}
          <p className="mt-2 text-center text-xs font-bold text-[var(--text-label)]">
            {"By subscribing you agree to the "}
            <Link
              href="/us/?legal=terms"
              className="underline underline-offset-2 hover:text-gray-400"
            >
              Terms of Service
            </Link>
            {", including the refund policy. You can cancel anytime; access continues until the end of the paid period."}
          </p>
        </div>
      </div>
    </DashboardLayout>
  );
}
