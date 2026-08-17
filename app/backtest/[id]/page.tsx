"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "phosphor-react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import BacktestDashboard from "@/components/strategy/backtest/BacktestDashboard";
import { buildHistorySummary } from "@/lib/backtest-history";
import { BacktestHistoryItem } from "@/types/strategy";
import { normalizeLegacyBreakoutStrategy } from "@/components/strategy/legacyBreakout";
import {
  buildWalkForwardParameterRanges,
  buildWalkForwardRequest,
  hasWalkForwardParameterRanges,
  type AdvisorWalkForwardSettings,
} from "../../analytics/new/parsedStrategyMerge";
import { runWalkForwardStream, type WalkForwardProgressHandler } from "../../analytics/new/walkForwardStream";
import { t } from "@/lib/i18n";

const backtestEmptyStateClassName =
  "flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] flex-col items-center justify-center gap-4 px-4 text-center text-gray-500";

export default function BacktestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [item, setItem] = useState<BacktestHistoryItem | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    fetch(`/api/backtest/history/${id}`)
      .then((r) => {
        if (!r.ok) { setNotFound(true); setIsLoading(false); return null; }
        return r.json();
      })
      .then((data) => {
        if (data) setItem(data);
        setIsLoading(false);
      })
      .catch(() => { setNotFound(true); setIsLoading(false); });
  }, [id]);

  if (isLoading) {
    return (
      <DashboardLayout userName="">
        <div className="p-4 md:p-5 lg:p-6 space-y-5">
          <div className="animate-pulse space-y-3">
            <div className="h-6 bg-white/[0.04] rounded-xl w-48" />
            <div className="h-4 bg-white/[0.04] rounded-xl w-32" />
          </div>
          <div className="animate-pulse grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-24 bg-white/[0.04] rounded-2xl" />
            ))}
          </div>
          <div className="animate-pulse h-64 bg-white/[0.04] rounded-2xl" />
        </div>
      </DashboardLayout>
    );
  }

  if (notFound || !item) {
    return (
      <DashboardLayout userName="">
        <div className={backtestEmptyStateClassName}>
          <p className="text-base font-bold">{t("기록을 찾을 수 없습니다.")}</p>
          <button
            onClick={() => router.back()}
            className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 text-white text-sm font-bold rounded-xl border border-white/10 transition-all"
          >
            <ArrowLeft className="w-4 h-4" />{t(" 돌아가기")}
          </button>
        </div>
      </DashboardLayout>
    );
  }

  if (!item.result) {
    return (
      <DashboardLayout userName="">
        <div className={backtestEmptyStateClassName}>
          <p className="text-base font-bold">{t("이 기록에는 상세 결과가 저장되어 있지 않습니다.")}</p>
          <p className="text-sm text-gray-600">{t("새로 실행된 백테스트부터 상세 결과가 저장됩니다.")}</p>
          <button
            onClick={() => router.back()}
            className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 text-white text-sm font-bold rounded-xl border border-white/10 transition-all"
          >
            <ArrowLeft className="w-4 h-4" />{t(" 돌아가기")}
          </button>
        </div>
      </DashboardLayout>
    );
  }

  const strategySummary = buildHistorySummary({
    conditions: item.conditions,
    universeName: item.universe,
    strategyName: item.strategyName,
  });

  const normalizedBacktestDsl = item.settings ? normalizeLegacyBreakoutStrategy(item.settings as any) : null;

  // BacktestHistory.result는 백엔드 응답을 그대로 저장한 것이라 signals만 있고
  // BacktestDashboard가 매매 기록 탭에 쓰는 tradesList는 없다(app/analytics/[id]와 달리
  // 여기서는 별도 매핑을 거치지 않았음). signals에서 재구성해 보완한다.
  const result = {
    ...item.result,
    tradesList: item.result.tradesList?.length
      ? item.result.tradesList
      : (item.result.signals ?? []).map((signal: any) => ({
          date: signal.date,
          symbol: signal.symbol,
          type: signal.type as "buy" | "sell",
          price: signal.price,
          quantity: signal.quantity ?? 0,
          amount: signal.amount ?? 0,
          reason: signal.condition,
        })),
  };

  const handleWalkForward = async (
    settings: AdvisorWalkForwardSettings,
    signal?: AbortSignal,
    onProgress?: WalkForwardProgressHandler
  ) => {
    if (!normalizedBacktestDsl) {
      throw new Error(t("이 기록에는 워크포워드 분석에 필요한 전략 설정이 저장되어 있지 않습니다."));
    }

    const ranges = buildWalkForwardParameterRanges(normalizedBacktestDsl);
    if (!hasWalkForwardParameterRanges(ranges)) {
      throw new Error(
        t("워크포워드 최적화에 사용할 숫자 파라미터가 없습니다. 손절/익절, 지표 기간, 임계값처럼 조정 가능한 조건이 포함된 전략에서 실행해 주세요.")
      );
    }

    return runWalkForwardStream(buildWalkForwardRequest(normalizedBacktestDsl, settings, ranges), {
      signal,
      onProgress,
    });
  };

  return (
    <DashboardLayout userName="">
      <div className="w-full min-w-0">
        <BacktestDashboard
          result={result}
          onRestart={() => router.back()}
          disableHistorySave={true}
          promptText={item.prompt || item.strategyName}
          backtestDsl={normalizedBacktestDsl ?? undefined}
          onWalkForward={normalizedBacktestDsl ? handleWalkForward : undefined}
          aiSummary={item.metrics.aiSummary}
          aiScore={item.metrics.aiScore}
          aiStrengths={item.metrics.aiStrengths}
          aiWeaknesses={item.metrics.aiWeaknesses}
          aiImprovements={item.metrics.aiImprovements}
          advisorScore={item.metrics.advisorScore}
          riskScore={item.metrics.riskScore}
          overfitRisk={item.metrics.overfitRisk}
          strategySummary={{ ...strategySummary, universeName: strategySummary.universeName ?? "", strategyName: strategySummary.strategyName ?? "" }}
        />
      </div>
    </DashboardLayout>
  );
}
