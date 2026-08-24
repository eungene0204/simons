// 글로벌 서비스(/us) 요금제 페이지 — 영어·USD 전용.
//
// 한국 요금제 화면(PricingPlans + 토스 체크아웃)과 완전히 분리된 트리다. 토스페이먼츠
// 심사 영역(components/pricing/PricingPlans·PaymentCheckout 등)은 여기서 일절 쓰지 않는다.
// 결제는 PayPal Checkout(lib/payment/PaypalProvider)으로 배선 예정이며, 배선 전까지
// 유료 플랜 CTA는 준비 중으로 표시한다.

import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { getPlan, PLANS } from "@/lib/plans";
import { US_PRICING } from "@/lib/pricing/us";

function formatUsd(amount: number): string {
  return `$${amount.toLocaleString("en-US")}`;
}

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
              Validate more strategies with more virtual accounts and backtests.
            </p>
          </div>

          <div className="mt-14 grid gap-6 md:grid-cols-3">
            {US_PRICING.planOrder.map((planId) => {
              const plan = PLANS[planId];
              const price = US_PRICING.monthlyPrice[planId];
              const isCurrent = planId === currentPlanId;

              return (
                <div
                  key={planId}
                  className={`flex flex-col rounded-3xl border p-6 ${
                    isCurrent
                      ? "border-blue-500/40 bg-blue-500/[0.06]"
                      : "border-white/[0.08] bg-white/[0.02]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <h2 className="text-xl font-black tracking-tight">{plan.name}</h2>
                    {isCurrent && (
                      <span className="rounded-full bg-blue-500/15 px-2.5 py-1 text-[10px] font-black tracking-wide text-blue-300">
                        CURRENT PLAN
                      </span>
                    )}
                  </div>

                  <p className="mt-4 text-3xl font-black">
                    {price === 0 ? "Free" : `${formatUsd(price)}`}
                    {price > 0 && (
                      <span className="text-sm font-bold text-gray-500"> / month</span>
                    )}
                  </p>

                  <ul className="mt-6 flex-1 space-y-2 text-sm font-bold text-gray-400">
                    <li>{plan.monthlyBacktestLimit.toLocaleString("en-US")} backtests / month</li>
                    <li>
                      {plan.isUnlimitedStrategies
                        ? "Unlimited saved strategies"
                        : `${plan.maxStrategies} saved strategies`}
                    </li>
                    <li>
                      {plan.maxVirtualAccounts} virtual account
                      {plan.maxVirtualAccounts > 1 ? "s" : ""}
                    </li>
                  </ul>

                  {price === 0 ? (
                    <p className="mt-6 rounded-xl border border-white/[0.08] px-4 py-2.5 text-center text-sm font-black text-gray-400">
                      {isCurrent ? "Your current plan" : "Included at sign-up"}
                    </p>
                  ) : (
                    <p className="mt-6 rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-center text-sm font-black text-gray-500">
                      Paid plans launching soon
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          <p className="mt-8 text-center text-xs font-bold text-gray-600">
            Prices are in USD. Checkout via PayPal is being prepared.
          </p>
        </div>
      </div>
    </DashboardLayout>
  );
}
