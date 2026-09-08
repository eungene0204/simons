"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";

// 요금제 서버 컴포넌트(page.tsx)는 원격 DB 조회를 await 하므로, loading.tsx가 없으면
// 클릭 후 데이터가 올 때까지 이전 화면에 멈춘 듯 보인다. 스켈레톤을 두어 클릭 즉시 전환한다.
export default function PricingLoading() {
  return (
    <DashboardLayout userName="">
      <div className="min-h-[calc(100dvh-var(--top-menu-bar-height,76px))] bg-[var(--background)] px-5 py-6 text-white sm:px-8 lg:px-10">
        <div className="mx-auto w-full max-w-7xl animate-pulse motion-reduce:animate-none">
          <div className="flex flex-col items-center">
            <div className="h-10 w-72 rounded bg-white/5 md:h-14 md:w-96" />
            <div className="mt-4 h-3 w-80 rounded bg-white/5" />
          </div>
          <div className="mt-14 grid grid-cols-1 items-stretch gap-6 lg:grid-cols-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="rounded-2xl border border-white/[0.08] p-6">
                <div className="h-3 w-16 rounded bg-white/5" />
                <div className="mt-4 h-8 w-32 rounded bg-white/5" />
                <div className="mt-6 space-y-3">
                  {[...Array(5)].map((_, j) => (
                    <div key={j} className="h-3 w-full rounded bg-white/5" />
                  ))}
                </div>
                <div className="mt-8 h-11 w-full rounded-xl bg-white/5" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
