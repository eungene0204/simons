import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import PaymentSuccess from "@/components/pricing/PaymentSuccess";
import UsPaymentSuccess from "@/components/pricing/us/UsPaymentSuccess";
import { t } from "@/lib/i18n";
import { getRequestLanguage } from "@/lib/i18n/server";
import { getRequestRegion } from "@/lib/geo/server";

// 결제 승인 복귀 페이지. 지역마다 결제 수단이 달라 화면도 갈린다:
// - 한국: 토스페이먼츠 자동결제(빌링) successUrl — 쿼리의 customerKey/authKey로 승인을 확정한다
// - 글로벌(/us): PayPal 구독 승인 복귀 — 쿼리가 아니라 저장된 구독 ID로 상태를 확인한다
export default async function PaymentSuccessPage({
  searchParams,
}: {
  searchParams: { authKey?: string; customerKey?: string; orderId?: string };
}) {
  const region = getRequestRegion();
  const user = await getCurrentUser();
  if (!user) {
    redirect(region === "us" ? "/us" : "/");
  }

  if (region === "us") {
    return (
      <DashboardLayout userName={user.name || "Guest"}>
        <div className="flex min-h-[calc(100dvh-var(--top-menu-bar-height,76px))] items-center bg-[var(--background)] px-5 py-10 text-white sm:px-8 lg:px-10">
          <UsPaymentSuccess />
        </div>
      </DashboardLayout>
    );
  }

  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return (
    <DashboardLayout userName={user.name || t("게스트")}>
      <div className="flex min-h-[calc(100dvh-var(--top-menu-bar-height,76px))] items-center bg-[var(--background)] px-5 py-10 text-white sm:px-8 lg:px-10">
        <PaymentSuccess
          authKey={searchParams.authKey ?? ""}
          customerKey={searchParams.customerKey ?? ""}
          orderId={searchParams.orderId ?? ""}
        />
      </div>
    </DashboardLayout>
  );
}
