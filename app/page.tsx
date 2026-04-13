import { getCurrentUser } from "@/lib/get-user";
import { getDashboardInitialData } from "@/lib/dashboard-data";
import DashboardLayout from "@/components/layout/DashboardLayout";
import PortfolioSummaryBar from "@/components/dashboard/PortfolioSummaryBar";
import BacktestActivityChart from "@/components/dashboard/BacktestActivityChart";
import AccountProfitChart from "@/components/dashboard/AccountProfitChart";
import MarketSnapshot from "@/components/dashboard/MarketSnapshot";
import StrategyList from "@/components/dashboard/StrategyList";
import VirtualTradingStatus from "@/components/dashboard/VirtualTradingStatus";
import RecentBacktestList from "@/components/dashboard/RecentBacktestList";
import WatchlistSnapshot from "@/components/dashboard/WatchlistSnapshot";

export default async function Home() {
  const [user, dashData] = await Promise.all([
    getCurrentUser(),
    getDashboardInitialData(),
  ]);
  const userName = user?.name || "게스트";

  return (
    <DashboardLayout userName={userName}>
      <div className="w-full min-w-0 border border-white/[0.08]">
        <div className="divide-y divide-white/[0.08]">
          {/* Row 1: 포트폴리오 요약 */}
          <PortfolioSummaryBar initialStats={dashData.portfolioStats} />

          {/* Row 2: 계좌별 수익률 차트 + 전략 목록 */}
          <div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
            <div className="lg:col-span-6">
              <AccountProfitChart initialData={dashData.accountMonthly} />
            </div>
            <div className="lg:col-span-4">
              <StrategyList initialData={dashData.strategyList} />
            </div>
          </div>

          {/* Row 3: 가상매매 실시간 현황 */}
          <VirtualTradingStatus initialData={dashData.tradingStatus} />

          {/* Row 4: 백테스트 활동 + 최근 백테스트 결과 */}
          <div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
            <div className="lg:col-span-3">
              <BacktestActivityChart initialRecords={dashData.backtestRecords} />
            </div>
            <div className="lg:col-span-7">
              <RecentBacktestList initialRecords={dashData.backtestRecords} />
            </div>
          </div>

          {/* Row 5: 시장 지표 */}
          <MarketSnapshot />

          {/* Row 6: 관심 종목 */}
          <WatchlistSnapshot />
        </div>
      </div>
    </DashboardLayout>
  );
}
