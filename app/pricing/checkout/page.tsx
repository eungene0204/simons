import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import { PLANS, isValidPlanId } from "@/lib/plans";
import PaymentCheckout from "@/components/pricing/PaymentCheckout";

// 유료 플랜(PRO/PREMIUM) 자동결제(빌링) 체크아웃 페이지. /pricing/checkout?plan=PRO
export default async function CheckoutPage({
  searchParams,
}: {
  searchParams: { plan?: string };
}) {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/");
  }

  const planId = (searchParams.plan ?? "").toUpperCase();
  if (!isValidPlanId(planId) || PLANS[planId].monthlyPrice <= 0) {
    redirect("/pricing");
  }

  return (
    <DashboardLayout userName={user.name || "게스트"}>
      <div className="min-h-[calc(100vh-var(--top-menu-bar-height,76px))] bg-[#050505] px-5 py-10 text-white sm:px-8 lg:px-10">
        <PaymentCheckout planId={planId} />
      </div>
    </DashboardLayout>
  );
}
