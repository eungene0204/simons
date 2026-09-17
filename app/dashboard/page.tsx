import { redirect } from "next/navigation";
import { getSessionUserId } from "@/lib/get-user";
import { ACCOUNT_ACCESS_SELECT, isAccountUsable } from "@/lib/accountAccess";
import { getDashboardInitialData } from "@/lib/dashboard-data";
import { prisma } from "@/lib/prisma";
import DashboardLayout from "@/components/layout/DashboardLayout";
import PortfolioSummaryBar from "@/components/dashboard/PortfolioSummaryBar";
import BacktestActivityChart from "@/components/dashboard/BacktestActivityChart";
import AccountProfitChart from "@/components/dashboard/AccountProfitChart";
import MarketSnapshot from "@/components/dashboard/MarketSnapshot";
import VirtualAccountList from "@/components/dashboard/VirtualAccountList";
import VirtualTradingStatus from "@/components/dashboard/VirtualTradingStatus";
import RecentBacktestList from "@/components/dashboard/RecentBacktestList";
import WatchlistSnapshot from "@/components/dashboard/WatchlistSnapshot";
import { t } from "@/lib/i18n";
import { getRequestLanguage } from "@/lib/i18n/server";

export default async function DashboardPage() {
  // 세션 확인(DB 없음) → 계정 상태 검증과 대시보드 조회를 같은 왕복에 띄운다.
  // 원격 DB라 직렬로 기다리면 스켈레톤이 그만큼 오래 남는다.
  const userId = await getSessionUserId();
  if (userId == null) {
    redirect("/");
  }

  const [user, dashData] = await Promise.all([
    prisma.user.findUnique({ where: { id: userId }, select: { name: true, ...ACCOUNT_ACCESS_SELECT } }),
    getDashboardInitialData(userId),
  ]);
  // 정지(SUSPENDED)·삭제(DELETED)·이용 기한이 지난 계정은 유효한 토큰이 있어도 세션을 인정하지 않는다(getCurrentUser와 동일 기준).
  if (!user || !isAccountUsable(user)) {
    redirect("/");
  }

  const userName = user.name || t("게스트");

  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return (
    <DashboardLayout userName={userName}>
      <div className="w-full min-w-0 border border-white/[0.08]">
        <div className="divide-y divide-white/[0.08]">
          <PortfolioSummaryBar initialStats={dashData.portfolioStats} />

          <div className="grid grid-cols-1 divide-y divide-white/[0.08] lg:grid-cols-10 lg:divide-x lg:divide-y-0">
            <div className="lg:col-span-6">
              <AccountProfitChart initialData={dashData.accountMonthly} />
            </div>
            <div className="lg:col-span-4">
              <VirtualAccountList initialData={dashData.accountList} />
            </div>
          </div>

          <VirtualTradingStatus initialData={dashData.tradingStatus} />

          <div className="grid grid-cols-1 divide-y divide-white/[0.08] lg:grid-cols-10 lg:divide-x lg:divide-y-0">
            <div className="lg:col-span-3">
              <BacktestActivityChart initialRecords={dashData.backtestRecords} />
            </div>
            <div className="lg:col-span-7">
              <RecentBacktestList initialRecords={dashData.backtestRecords} />
            </div>
          </div>

          <MarketSnapshot />
          <WatchlistSnapshot />
        </div>
      </div>
    </DashboardLayout>
  );
}
