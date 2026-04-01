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
      <div className="p-4 md:p-5 lg:p-6 space-y-5 w-full min-w-0">
        {/* Row 1: 포트폴리오 요약 (총 투자금 / 전체 수익률 / 총 수익금 / 일간 손익) */}
        <PortfolioSummaryBar initialStats={dashData.portfolioStats} />

        {/* Row 2: 계좌별 수익률 차트 + 전략 목록 */}
        <div className="grid grid-cols-1 lg:grid-cols-10 gap-6 items-stretch">
          <div className="lg:col-span-6 h-full">
            <AccountProfitChart initialData={dashData.accountMonthly} />
          </div>
          <div className="lg:col-span-4 h-full">
            <StrategyList initialData={dashData.strategyList} />
          </div>
        </div>

        {/* Row 3: 가상매매 실시간 현황 (실행 중 계좌 / 보유 종목 / 오늘 체결 / 일간 손익) */}
        <VirtualTradingStatus initialData={dashData.tradingStatus} />

        {/* Row 4: 백테스트 활동 + 최근 백테스트 결과 */}
        <div className="grid grid-cols-1 lg:grid-cols-10 gap-6">
          <div className="lg:col-span-3">
            <BacktestActivityChart initialRecords={dashData.backtestRecords} />
          </div>
          <div className="lg:col-span-7">
            <RecentBacktestList initialRecords={dashData.backtestRecords} />
          </div>
        </div>

        {/* Row 5: 시장 지표 */}
        <MarketSnapshot />

        {/* Row 6: 관심 종목 (데이터 있을 때만 표시) */}
        <WatchlistSnapshot />
      </div>
    </DashboardLayout>
  );
}
