"use client";

import { useState, useEffect, Suspense } from "react";
import { useParams, useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import BacktestDashboard from "@/components/strategy/backtest/BacktestDashboard";
import { BacktestResult } from "@/types/strategy";
import { ChartLineUp, ArrowLeft, ArrowsClockwise, Warning } from "phosphor-react";

function StrategyResultContent() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [strategyName, setStrategyName] = useState("");
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [strategySummary, setStrategySummary] = useState<any>(null);
  const [aiSummary, setAiSummary] = useState<string | undefined>();
  const [aiScore, setAiScore] = useState<number | undefined>();

  useEffect(() => {
    fetch(`/api/strategy/${id}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) throw new Error(data.error);
        setStrategyName(data.name ?? "전략");
        if (!data.backtestResult) {
          setError("저장된 백테스트 결과가 없습니다.");
          return;
        }
        setResult(data.backtestResult);
        if (data.backtestResult.aiSummary) setAiSummary(data.backtestResult.aiSummary);
        if (data.backtestResult.aiScore != null) setAiScore(data.backtestResult.aiScore);

        // strategySummary 구성
        const s = data.settings;
        if (s) {
          const universe = Array.isArray(s.universe) ? s.universe : s.universe ? [s.universe] : [];
          setStrategySummary({
            strategyName: data.name,
            universeName: universe.join(", ") || "—",
            blockNames: [],
            positionText: s.max_positions ? `최대 ${s.max_positions}종목` : undefined,
            riskText: [
              s.stop_loss_pct ? `손절 ${s.stop_loss_pct}%` : "",
              s.take_profit_pct ? `익절 ${s.take_profit_pct}%` : "",
            ].filter(Boolean).join(", ") || undefined,
          });
        }
      })
      .catch((e) => setError(e.message ?? "불러오기 실패"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <DashboardLayout userName="">
        <div className="flex items-center justify-center h-full gap-2 text-gray-500">
          <ArrowsClockwise size={16} className="animate-spin" />
          <span className="text-sm font-bold">불러오는 중...</span>
        </div>
      </DashboardLayout>
    );
  }

  if (error || !result) {
    return (
      <DashboardLayout userName="">
        <div className="flex flex-col items-center justify-center h-full gap-4">
          <Warning size={36} className="text-red-400" weight="fill" />
          <p className="text-sm font-bold text-red-400">{error ?? "결과를 불러올 수 없습니다."}</p>
          <button
            onClick={() => router.push("/analytics")}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white text-xs font-bold transition-all"
          >
            <ArrowLeft size={13} />
            전략 목록으로
          </button>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout userName="">
      <div className="h-full flex flex-col">
        <div className="flex items-center justify-between px-6 py-3 border-b border-white/5">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/analytics")}
              className="flex items-center gap-1.5 text-gray-500 hover:text-white transition-colors"
            >
              <ArrowLeft size={14} />
            </button>
            <ChartLineUp size={18} className="text-blue-400" weight="fill" />
            <span className="text-sm font-black text-white">{strategyName}</span>
          </div>
        </div>
        <div className="flex-1 overflow-auto">
          <BacktestDashboard
            result={result}
            onRestart={() => router.push("/analytics")}
            strategySummary={strategySummary}
            aiSummary={aiSummary}
            aiScore={aiScore}
          />
        </div>
      </div>
    </DashboardLayout>
  );
}

export default function StrategyResultPage() {
  return (
    <Suspense>
      <StrategyResultContent />
    </Suspense>
  );
}
