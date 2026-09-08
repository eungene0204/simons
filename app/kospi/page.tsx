import { getCurrentUser } from "@/lib/get-user";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { t } from "@/lib/i18n";
import { getRequestLanguage } from "@/lib/i18n/server";

// 코스피 페이지 — 아직 지수 데이터가 붙지 않은 자리표시자다(내비게이션에 링크되지 않음).
// 표면만 디자인 시스템(flat 패널·다크 전용)에 맞췄다(2026-09-08). 내용을 채우거나 라우트를
// 정리하는 것은 별도 결정.
export default async function KospiPage() {
  const user = await getCurrentUser();

  if (!user) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center">
        <p className="text-sm font-bold text-[var(--text-label)]">{t("로그인이 필요합니다.")}</p>
      </div>
    );
  }

  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return (
    <DashboardLayout userName={user.name}>
      <div className="w-full min-w-0 border border-white/[0.08]">
        <div className="px-5 py-5">
          <h1 className="text-base font-black text-white font-outfit">{t("코스피 (KOSPI)")}</h1>
          <p className="mt-2 text-sm font-bold text-gray-400">
            {t("코스피 지수 정보를 확인할 수 있습니다.")}
          </p>
        </div>
      </div>
    </DashboardLayout>
  );
}
