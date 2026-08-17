import Link from "next/link";
import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import { t } from "@/lib/i18n";
import { getRequestLanguage } from "@/lib/i18n/server";

// 토스페이먼츠 failUrl 리다이렉트 페이지 — 인증 실패/사용자 취소.
// 승인 API를 호출하지 않고 에러 코드에 따른 안내만 표시한다.
const FAIL_MESSAGES: Record<string, string> = {
  PAY_PROCESS_CANCELED: "결제가 취소되었습니다.",
  PAY_PROCESS_ABORTED: "결제가 중단되었습니다. 잠시 후 다시 시도해주세요.",
  REJECT_CARD_COMPANY: "카드사에서 결제를 거절했습니다. 카드 정보를 확인해주세요.",
};

export default async function PaymentFailPage({
  searchParams,
}: {
  searchParams: { code?: string; message?: string };
}) {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/");
  }

  const code = searchParams.code ?? "";
  const message =
    FAIL_MESSAGES[code] ?? searchParams.message ?? t("결제에 실패했습니다. 다시 시도해주세요.");

  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return (
    <DashboardLayout userName={user.name || t("게스트")}>
      <div className="flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] items-center bg-[#050505] px-5 py-10 text-white sm:px-8 lg:px-10">
        <div className="mx-auto w-full max-w-xl rounded-3xl border border-white/[0.08] bg-[#0a0a0a] px-8 py-12 text-center">
          <h1 className="text-2xl font-black tracking-tight text-[var(--main-red)]">
            {t("결제하지 못했습니다")}
          </h1>
          <p className="mt-3 text-sm font-bold text-gray-400">{message}</p>
          {code ? (
            <p className="mt-2 text-xs font-bold text-gray-600">{t("오류 코드: {0}", code)}</p>
          ) : null}
          <Link
            href="/pricing"
            className="mt-8 inline-block rounded-2xl border border-white/[0.12] px-6 py-3 text-sm font-black text-white hover:bg-white/[0.06]"
          >
            {t("요금제 페이지에서 다시 시도")}
          </Link>
        </div>
      </div>
    </DashboardLayout>
  );
}
