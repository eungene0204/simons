import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { getPlan } from "@/lib/plans";
import PricingPlans from "@/components/pricing/PricingPlans";

export default async function PricingPage() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/");
  }

  const record = await prisma.user.findUnique({
    where: { id: user.id },
    select: { planTier: true },
  });
  const currentPlan = getPlan(record?.planTier);

  return (
    <DashboardLayout userName={user.name || "게스트"}>
      <div className="min-h-[calc(100vh-var(--top-menu-bar-height,76px))] bg-[#050505] px-5 py-6 text-white sm:px-8 lg:px-10">
        <div className="mx-auto flex min-h-[calc(100vh-var(--top-menu-bar-height,76px)-3rem)] w-full max-w-7xl flex-col">
          <div className="text-center">
            <h1 className="text-4xl font-black tracking-[-0.04em] text-white md:text-6xl">
              플랜을 선택하세요
            </h1>
            <p className="mt-2 text-sm font-bold text-gray-500">
              초기 모의 투자금과 가상계좌 수에 따라 더 많은 전략을 검증할 수 있습니다.
            </p>
          </div>

          <div className="mt-14">
            <PricingPlans currentPlanId={currentPlan.planId} />
          </div>

          <footer className="mt-auto border-t border-white/[0.08] pt-6 text-center">
            <p className="text-xs font-bold leading-relaxed text-gray-600">
              초기 모의 투자금은 실제 돈이 아니라 가상계좌 시뮬레이션을 위한 금액입니다. 플랜을 변경해도
              이미 생성된 계좌의 초기 모의 투자금과 잔고는 변경되지 않습니다.
            </p>
          </footer>
        </div>
      </div>
    </DashboardLayout>
  );
}
