"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import BacktestDashboard from "@/components/strategy/backtest/BacktestDashboard";
import { BacktestHistoryItem } from "@/types/strategy";
import { ArrowLeft } from "phosphor-react";

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
      <DashboardLayout>
        <div className="flex items-center justify-center h-full text-gray-500 text-sm font-bold">
          불러오는 중...
        </div>
      </DashboardLayout>
    );
  }

  if (notFound || !item) {
    return (
      <DashboardLayout>
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
      <DashboardLayout>
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
    <DashboardLayout>
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-3 px-6 pt-5 pb-2">
          <button
            onClick={() => router.back()}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white text-xs font-bold rounded-lg border border-white/10 transition-all"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> 기록으로 돌아가기
          </button>
          <span className="text-white font-black text-base">{item.strategyName}</span>
          <span className="px-2 py-0.5 bg-main-blue/10 text-main-blue text-xs font-black rounded border border-main-blue/20">
            {item.universe}
          </span>
          <span className="text-xs text-gray-600 font-mono ml-auto">
            {new Date(item.timestamp).toLocaleString()}
          </span>
        </div>
        <BacktestDashboard
          result={item.result}
          onRestart={() => router.back()}
          disableHistorySave={true}
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
