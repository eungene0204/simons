import { getCurrentUser } from "@/lib/get-user";
import DashboardLayout from "@/components/layout/DashboardLayout";
import StockDetail from "@/components/stock/StockDetail";
import { t } from "@/lib/i18n";
import { getRequestLanguage } from "@/lib/i18n/server";

export default async function StockDetailPage({
  params,
}: {
  params: Promise<{ symbol: string }> | { symbol: string };
}) {
  const resolvedParams = await Promise.resolve(params);
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
        <StockDetail symbol={resolvedParams.symbol} />
      </div>
    </DashboardLayout>
  );
}

