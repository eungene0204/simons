"use client";

import { StrategyWaveBackground } from "@/components/strategy/StrategyWaveBackground";
import { Spinner } from "phosphor-react";
import { t } from "@/lib/i18n";

// 목록을 아직 그릴 수 없을 때의 화면.
// 라우트 전환 fallback(loading.tsx)과 캐시 없는 첫 조회(BacktestHistoryView)가 함께 쓴다.
export default function BacktestHistoryLoading() {
  return (
    <div className="min-h-[calc(100vh-var(--top-menu-bar-height,76px))]">
      <div className="relative flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] items-center justify-center overflow-hidden px-5 py-8 text-center">
        <StrategyWaveBackground />
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(15,15,15,0.18)_0%,rgba(15,15,15,0.72)_72%)]" />
        <div
          className="relative z-10 flex flex-col items-center gap-3"
          data-testid="backtest-history-loading"
        >
          <Spinner size={28} className="animate-spin text-white" aria-hidden="true" />
          <p className="text-sm font-bold text-gray-500">{t("불러오는 중...")}</p>
        </div>
      </div>
    </div>
  );
}
