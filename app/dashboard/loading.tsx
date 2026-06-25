// 대시보드 서버 컴포넌트(page.tsx)는 getCurrentUser + getDashboardInitialData를
// await 하므로, 첫 진입(캐시 미스) 시 데이터가 준비될 때까지 화면이 멈춰 보인다.
// loading.tsx를 두면 Next.js가 클릭 즉시 이 스켈레톤을 스트리밍해 체감 렌더링이 빨라진다.
export default function DashboardLoading() {
  return (
    <div className="w-full min-w-0 border border-white/[0.08] animate-pulse">
      <div className="divide-y divide-white/[0.08]">
        {/* PortfolioSummaryBar */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="border-r border-b border-white/[0.08] p-4">
              <div className="h-2 w-2/3 rounded bg-white/5 mb-3" />
              <div className="h-5 w-3/4 rounded bg-white/5 mb-2" />
              <div className="h-3 w-1/2 rounded bg-white/5" />
            </div>
          ))}
        </div>

        {/* AccountProfitChart + VirtualAccountList */}
        <div className="grid grid-cols-1 lg:grid-cols-10 lg:divide-x lg:divide-white/[0.08]">
          <div className="lg:col-span-6 p-5">
            <div className="h-3 w-32 rounded bg-white/5 mb-4" />
            <div className="h-56 w-full rounded bg-white/5" />
          </div>
          <div className="lg:col-span-4 p-5">
            <div className="h-3 w-24 rounded bg-white/5 mb-4" />
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-12 w-full rounded bg-white/5 mb-2" />
            ))}
          </div>
        </div>

        {/* VirtualTradingStatus */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="border-r border-b border-white/[0.08] p-4">
              <div className="h-2 w-2/3 rounded bg-white/5 mb-3" />
              <div className="h-5 w-1/2 rounded bg-white/5" />
            </div>
          ))}
        </div>

        {/* BacktestActivityChart + RecentBacktestList */}
        <div className="grid grid-cols-1 lg:grid-cols-10 lg:divide-x lg:divide-white/[0.08]">
          <div className="lg:col-span-3 p-5">
            <div className="h-3 w-24 rounded bg-white/5 mb-4" />
            <div className="h-40 w-full rounded bg-white/5" />
          </div>
          <div className="lg:col-span-7 p-5">
            <div className="h-3 w-28 rounded bg-white/5 mb-4" />
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-10 w-full rounded bg-white/5 mb-2" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
