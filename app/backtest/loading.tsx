"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import { StrategyWaveBackground } from "@/components/strategy/StrategyWaveBackground";
import { Spinner } from "phosphor-react";

// 서버가 목록을 조회하는 동안 보여줄 화면.
export default function BacktestHistoryLoading() {
  return (
    <DashboardLayout userName="">
      <div className="min-h-[calc(100vh-var(--top-menu-bar-height,76px))]">
        <div className="relative flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] items-center justify-center overflow-hidden px-5 py-8 text-center">
          <StrategyWaveBackground />
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(15,15,15,0.18)_0%,rgba(15,15,15,0.72)_72%)]" />
          <div
            className="relative z-10 flex flex-col items-center gap-3"
            data-testid="backtest-history-loading"
          >
            <Spinner size={28} className="animate-spin text-white" aria-hidden="true" />
            <p className="text-sm font-bold text-gray-500">불러오는 중...</p>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
