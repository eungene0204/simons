import { getCurrentUser } from "@/lib/get-user";
import DashboardLayout from "@/components/layout/DashboardLayout";
import ResearchTestConsole from "@/components/research/ResearchTestConsole";
import { t } from "@/lib/i18n";
import { getRequestLanguage } from "@/lib/i18n/server";
import type { Metadata } from "next";

// 내부 시험 콘솔이라 검색 결과에 내지 않는다.
export const metadata: Metadata = { title: "전략 연구 에이전트", robots: { index: false, follow: true } };

export default async function ResearchPage() {
  const user = await getCurrentUser();
  const userName = user?.name || t("게스트");

  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return (
    <DashboardLayout userName={userName}>
      <ResearchTestConsole />
    </DashboardLayout>
  );
}
