import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/get-user";
import { getDashboardInitialData } from "@/lib/dashboard-data";
import DashboardLayout from "@/components/layout/DashboardLayout";
import PortfolioSummaryBar from "@/components/dashboard/PortfolioSummaryBar";
import BacktestActivityChart from "@/components/dashboard/BacktestActivityChart";
import AccountProfitChart from "@/components/dashboard/AccountProfitChart";
import MarketSnapshot from "@/components/dashboard/MarketSnapshot";
import VirtualAccountList from "@/components/dashboard/VirtualAccountList";
import VirtualTradingStatus from "@/components/dashboard/VirtualTradingStatus";
import RecentBacktestList from "@/components/dashboard/RecentBacktestList";
import WatchlistSnapshot from "@/components/dashboard/WatchlistSnapshot";

export default async function DashboardPage() {
  const user = await getCurrentUser();

  if (!user) {
    redirect("/");
  }

  const dashData = await getDashboardInitialData(user.id);

  const userName = user.name || "게스트";

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
