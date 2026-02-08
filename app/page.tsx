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
      <div className="p-4 md:p-6 lg:p-8 max-w-[1700px] mx-auto overflow-x-hidden w-full min-w-0">
        <div className="glass-card p-1 lg:p-2 bg-white/[0.01] border-white/5">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-1 lg:gap-2 items-start">
            {/* Left Column: Indices - Sticky - 3/12 */}
            <div className="lg:col-span-3 lg:sticky lg:top-[calc(var(--top-menu-bar-height)+48px)] space-y-2 lg:space-y-4 max-h-[calc(100vh-var(--top-menu-bar-height)-80px)] overflow-y-auto scrollbar-hide p-2 lg:p-4">
              <MarketIndices />
            </div>

            {/* Middle Column: Rankings (Main Scrollable) - 6/12 */}
            <div className="lg:col-span-6 space-y-2 lg:space-y-4 p-2 lg:p-4 border-x border-white/5">
              <div className="glass-card p-8 bg-gradient-to-br from-blue-600/10 to-transparent border-white/5 relative overflow-hidden group">
                 <div className="relative z-10 flex flex-col md:flex-row items-center justify-between gap-6">
                   <div className="flex flex-col">
                     <h2 className="text-3xl font-black text-white tracking-tighter font-outfit uppercase">
                       인공지능 시장 분석
                     </h2>
                     <p className="text-gray-500 font-medium mt-2 max-w-sm text-sm">
                       실시간 데이터와 퀀트 알고리즘을 결합하여 시장의 미세한 흐름을 포착합니다.
                     </p>
                     <div className="flex gap-6 mt-6">
                       <div className="flex flex-col">
                         <span className="text-[10px] text-gray-400 font-bold uppercase tracking-widest">Market Status</span>
                         <span className="text-green-500 font-black font-outfit flex items-center gap-2 text-lg">
                           <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                           BULLISH
                         </span>
                       </div>
                       <div className="w-px h-10 bg-white/5" />
                       <div className="flex flex-col">
                         <span className="text-[10px] text-gray-400 font-bold uppercase tracking-widest">Volatility</span>
                         <span className="text-white font-black font-outfit uppercase text-lg">Stable</span>
                       </div>
                     </div>
                   </div>
                   <button className="px-6 py-4 bg-white text-black font-black font-outfit rounded-xl hover:bg-gray-100 transition-all border border-white/20 whitespace-nowrap">
                     AI 시그널 탐색
                   </button>
                 </div>
                 
                 {/* Simplified Ambient Elements */}
                 <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/5 blur-[100px] rounded-full" />
              </div>
              <MarketRankings />
            </div>

            {/* Right Column: News - Sticky - 3/12 */}
            <div className="lg:col-span-3 lg:sticky lg:top-[calc(var(--top-menu-bar-height)+48px)] space-y-2 lg:space-y-4 max-h-[calc(100vh-var(--top-menu-bar-height)-80px)] overflow-y-auto scrollbar-hide p-2 lg:p-4">
              <TopNews />
              <AppPromotion />
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
