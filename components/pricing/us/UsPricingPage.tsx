// 글로벌 서비스(/us) 요금제 페이지 — 영어·USD 전용.
//
// 한국 요금제 화면(PricingPlans + 토스 체크아웃)과 완전히 분리된 트리다. 토스페이먼츠
// 심사 영역(components/pricing/PricingPlans·PaymentCheckout 등)은 여기서 일절 쓰지 않는다.
// 카드 레이아웃은 한국 화면과 동일하게 맞추되(UsPricingPlans), 결제는 PayPal Checkout
// (lib/payment/PaypalProvider)으로 배선 예정이며 배선 전까지 CTA는 준비 중으로 표시한다.

import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { getPlan } from "@/lib/plans";
import UsPricingPlans from "@/components/pricing/us/UsPricingPlans";

export default async function UsPricingPage() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/us");
  }

  const record = await prisma.user.findUnique({
    where: { id: user.id },
    select: { planTier: true },
  });
  const currentPlanId = getPlan(record?.planTier).planId;

  return (
    <DashboardLayout userName={user.name || "Guest"}>
      <div className="min-h-[calc(100vh-var(--top-menu-bar-height,76px))] bg-[#050505] px-5 py-6 text-white sm:px-8 lg:px-10">
        <div className="mx-auto flex min-h-[calc(100vh-var(--top-menu-bar-height,76px)-3rem)] w-full max-w-7xl flex-col">
          <div className="text-center">
            <h1 className="text-4xl font-black tracking-[-0.04em] text-white md:text-6xl">
              Choose your plan
            </h1>
            <p className="mt-2 text-sm font-bold text-gray-500">
              Validate more strategies with more simulated capital and virtual accounts.
            </p>
          </div>

          <div className="mt-14">
            <UsPricingPlans currentPlanId={currentPlanId} />
          </div>

          <p className="mt-8 text-center text-xs font-bold text-gray-600">
            Prices are in USD. Checkout via PayPal is being prepared.
          </p>
        </div>
      </div>
    </DashboardLayout>
  );
}
