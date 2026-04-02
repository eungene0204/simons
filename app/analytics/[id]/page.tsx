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
          // universe는 V2: { id: "kospi", filters: {...} } 또는 NL: 없음
          const universeId = s.universe?.id ?? s.universe;
          const UNIVERSE_NAMES: Record<string, string> = {
            kospi: "KOSPI", kosdaq: "KOSDAQ", kospi200: "KOSPI 200",
            KOR_KOSPI200: "KOSPI 200", KOR_KOSDAQ150: "KOSDAQ 150",
            US_TECH_TOP10: "미국 테크 Top 10", CRYPTO_TOP10: "크립토 Top 10",
          };
          const universeName = (typeof universeId === "string" && universeId)
            ? (UNIVERSE_NAMES[universeId] ?? universeId)
            : "";
          setStrategySummary({
            strategyName: data.name,
            universeName: universeName || "—",
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
          <Warning size={32} className="text-[var(--main-blue)]" weight="fill" />
          <p className="text-sm font-bold text-[var(--main-blue)]">{error ?? "결과를 불러올 수 없습니다."}</p>
          <button
            onClick={() => router.push("/analytics")}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/[0.05] hover:bg-white/10 text-gray-400 hover:text-white text-xs font-bold transition-all duration-200"
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
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.05]">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/analytics")}
              className="flex items-center gap-1.5 text-gray-500 hover:text-gray-300 transition-colors duration-200"
            >
              <ArrowLeft size={14} />
            </button>
            <ChartLineUp size={16} className="text-sky-400" weight="fill" />
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
            disableHistorySave={true}
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
