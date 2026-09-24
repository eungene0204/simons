import { getCurrentUser } from "@/lib/get-user";
import DashboardLayout from "@/components/layout/DashboardLayout";
import StrategyScreener from "@/components/screener/StrategyScreener";
import { t } from "@/lib/i18n";
import { getRequestLanguage } from "@/lib/i18n/server";

// 독립 스크리너(엔진 v16.33) — 저장한 전략의 조건을 오늘 데이터에 적용해 충족 종목을 본다.
export default async function ScreenerPage() {
  const user = await getCurrentUser();

  if (!user) {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center">
        <p className="text-gray-500">{t("로그인이 필요합니다.")}</p>
      </div>
    );
  }

  getRequestLanguage();
  return (
    <DashboardLayout userName={user.name}>
      <div className="p-3 sm:p-4 md:p-6 max-w-7xl mx-auto overflow-x-hidden w-full">
        <StrategyScreener />
      </div>
    </DashboardLayout>
  );
}
