import { getCurrentUser } from "@/lib/get-user";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { t } from "@/lib/i18n";
import { getRequestLanguage } from "@/lib/i18n/server";

export default async function KospiPage() {
  const user = await getCurrentUser();

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">{t("로그인이 필요합니다.")}</p>
      </div>
    );
  }

  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return (
    <DashboardLayout userName={user.name}>
      <div className="p-3 sm:p-4 md:p-6 max-w-7xl mx-auto overflow-x-hidden w-full">
        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
            {t("코스피 (KOSPI)")}
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            {t("코스피 지수 정보를 확인할 수 있습니다.")}
          </p>
        </div>
      </div>
    </DashboardLayout>
  );
}

