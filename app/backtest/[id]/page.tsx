"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "phosphor-react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import BacktestDashboard from "@/components/strategy/backtest/BacktestDashboard";
import { BacktestHistoryItem } from "@/types/strategy";

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
        <div className="flex flex-col items-center justify-center h-full text-gray-500 gap-4">
          <p className="text-base font-bold">기록을 찾을 수 없습니다.</p>
          <button
            onClick={() => router.back()}
            className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 text-white text-sm font-bold rounded-xl border border-white/10 transition-all"
          >
            <ArrowLeft className="w-4 h-4" /> 돌아가기
          </button>
        </div>
      </DashboardLayout>
    );
  }

  if (!item.result) {
    return (
      <DashboardLayout userName="">
        <div className="flex flex-col items-center text-gray-500 gap-4 pt-48 pb-32">
          <p className="text-base font-bold">이 기록에는 상세 결과가 저장되어 있지 않습니다.</p>
          <p className="text-sm text-gray-600">새로 실행된 백테스트부터 상세 결과가 저장됩니다.</p>
          <button
            onClick={() => router.back()}
            className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 text-white text-sm font-bold rounded-xl border border-white/10 transition-all"
          >
            <ArrowLeft className="w-4 h-4" /> 돌아가기
          </button>
        </div>
      </DashboardLayout>
    );
  }

  const conds = item.conditions as any;

  return (
    <DashboardLayout userName="">
      <div className="w-full min-w-0">
        <BacktestDashboard
          result={item.result}
          onRestart={() => router.push("/analytics/new")}
          disableHistorySave={true}
          promptText={item.strategyName}
          aiSummary={item.metrics.aiSummary}
          aiScore={item.metrics.aiScore}
          aiStrengths={item.metrics.aiStrengths}
          aiWeaknesses={item.metrics.aiWeaknesses}
          aiImprovements={item.metrics.aiImprovements}
          strategySummary={{
            universeName: item.universe,
            blockNames: conds?.entry?.names || conds?.names || [],
            strategyName: item.strategyName,
            entryLogic: conds?.entry?.logic,
            exitLogic: conds?.exit?.logic,
            entryBlocks: conds?.entry?.names || conds?.names || [],
            exitBlocks: conds?.exit?.names || [],
            positionText: conds?.position,
            riskText: conds?.risk,
          }}
        />
      </div>
    </DashboardLayout>
  );
}
