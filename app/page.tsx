import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/get-user";
import DashboardLayout from "@/components/layout/DashboardLayout";
import Link from "next/link";
import MarketIndices from "@/components/market/MarketIndices";
import MarketRankings from "@/components/market/MarketRankings";
import TopNews from "@/components/market/TopNews";
import AppPromotion from "@/components/ui/AppPromotion";

export default async function Home() {
  const user = await getCurrentUser();

  // Always show dashboard, regardless of login status
  return (
    <DashboardLayout userName={user?.name || "게스트"}>
      <div className="p-3 sm:p-4 md:p-5 space-y-3 sm:space-y-4 md:space-y-5 max-w-7xl mx-auto overflow-x-hidden w-full min-w-0">
        {/* Korean Market Indices */}
        <MarketIndices />

        {/* Market Rankings */}
        <MarketRankings />

        {/* Top News */}
        <TopNews />

        {/* App Promotion */}
        <AppPromotion />
      </div>
    </DashboardLayout>
  );
}
