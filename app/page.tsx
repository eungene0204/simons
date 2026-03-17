import { getCurrentUser } from "@/lib/get-user";
import DashboardLayout from "@/components/layout/DashboardLayout";
import WelcomeSection from "@/components/dashboard/WelcomeSection";
import StrategyOverview from "@/components/dashboard/StrategyOverview";
import BacktestHistory from "@/components/dashboard/BacktestHistory";
import VirtualAccountSummary from "@/components/dashboard/VirtualAccountSummary";
import MarketSnapshot from "@/components/dashboard/MarketSnapshot";

export default async function Home() {
  const user = await getCurrentUser();
  const userName = user?.name || "게스트";

  return (
    <DashboardLayout userName={userName}>
      <div className="p-4 md:p-5 lg:p-6 space-y-5 w-full min-w-0">
        <WelcomeSection userName={userName} />
        <StrategyOverview />
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-3">
            <BacktestHistory />
          </div>
          <div className="lg:col-span-2">
            <VirtualAccountSummary />
          </div>
        </div>
        <MarketSnapshot />
      </div>
    </DashboardLayout>
  );
}
