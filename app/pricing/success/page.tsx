import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import PaymentSuccess from "@/components/pricing/PaymentSuccess";

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

  return (
    <DashboardLayout userName={user.name || "게스트"}>
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
