import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { getPlan } from "@/lib/plans";
import PricingPlans from "@/components/pricing/PricingPlans";
import { t } from "@/lib/i18n";
import { getRequestLanguage } from "@/lib/i18n/server";

export default async function PricingPage() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/");
  }

  const record = await prisma.user.findUnique({
    where: { id: user.id },
    select: {
      planTier: true,
      subscriptionPlanId: true,
      nextBillingAt: true,
      subscriptionCanceledAt: true,
    },
  });
  const currentPlan = getPlan(record?.planTier);
  // 자동결제(빌링) 구독 상태 — 다음 결제일/해지 여부를 플랜 카드에 표시한다
  const subscription = record?.subscriptionPlanId
    ? {
        nextBillingAt: record.nextBillingAt?.toISOString() ?? null,
        canceled: record.subscriptionCanceledAt != null,
      }
    : null;

  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return (
    <DashboardLayout userName={user.name || t("게스트")}>
      <div className="min-h-[calc(100vh-var(--top-menu-bar-height,76px))] bg-[#050505] px-5 py-6 text-white sm:px-8 lg:px-10">
        <div className="mx-auto flex min-h-[calc(100vh-var(--top-menu-bar-height,76px)-3rem)] w-full max-w-7xl flex-col">
          <div className="text-center">
            <h1 className="text-4xl font-black tracking-[-0.04em] text-white md:text-6xl">
              {t("플랜을 선택하세요")}
            </h1>
            <p className="mt-2 text-sm font-bold text-gray-500">
              {t("초기 모의 투자금과 가상계좌 수에 따라 더 많은 전략을 검증할 수 있습니다.")}
            </p>
          </div>

          <div className="mt-14">
            <PricingPlans currentPlanId={currentPlan.planId} subscription={subscription} />
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
