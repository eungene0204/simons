import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import PaymentSuccess from "@/components/pricing/PaymentSuccess";
import { t } from "@/lib/i18n";
import { getRequestLanguage } from "@/lib/i18n/server";

// 토스페이먼츠 자동결제(빌링) successUrl 리다이렉트 페이지.
// 토스가 쿼리로 customerKey/authKey를 붙여주고, orderId는 체크아웃에서 successUrl에 직접 실어 보낸다.
export default async function PaymentSuccessPage({
  searchParams,
}: {
  searchParams: { authKey?: string; customerKey?: string; orderId?: string };
}) {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/");
  }

  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return (
    <DashboardLayout userName={user.name || t("게스트")}>
      <div className="flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] items-center bg-[#050505] px-5 py-10 text-white sm:px-8 lg:px-10">
        <PaymentSuccess
          authKey={searchParams.authKey ?? ""}
          customerKey={searchParams.customerKey ?? ""}
          orderId={searchParams.orderId ?? ""}
        />
      </div>
    </DashboardLayout>
  );
}
