"use client";

import { BacktestResult } from "@/types/strategy";
import BacktestConfig, { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";
import BacktestDashboard from "@/components/strategy/backtest/BacktestDashboard";
import { useState, useEffect } from "react";
import { ChartBarIcon, ArrowLeftIcon, CheckIcon } from "@heroicons/react/24/outline";

interface Step5BacktestProps {
  strategyName: string;
  backtestResult: BacktestResult | null;
  isBacktesting: boolean;
  onPrev: () => void;
  onSave: () => void;
  onRunBacktest: (options: BacktestConfigOptions) => void;
  summaryData: any; // Using any for now to avoid circular deps or complex imports, ideally stick to StrategySummaryData
}

export default function Step5Backtest({
  strategyName,
  backtestResult,
  isBacktesting,
  onPrev,
  onSave,
  onRunBacktest,
  summaryData,
}: Step5BacktestProps) {
  useEffect(() => {
    console.error("[DEBUG] Step5Backtest: MOUNTED");
  }, []);

  const [view, setView] = useState<"config" | "dashboard">("config");
  const [configOptions, setConfigOptions] = useState<BacktestConfigOptions>({
    period: "1Y",
    initialCapital: 10000000,
    commissionPct: 0.015,
    slippagePct: 0.05
  });

  const [lastResultId, setLastResultId] = useState<string | null>(null);

  useEffect(() => {
    // Only auto-switch to dashboard if we get a NEW result 
    // (comparing some identifying field like a timestamp or just the object reference)
    if (backtestResult && !isBacktesting) {
      // If result object changed, it's a new run
      if (backtestResult !== (lastResultId as any)) {
        setView("dashboard");
        setLastResultId(backtestResult as any);
      }
    }
  }, [backtestResult, isBacktesting]);

  const handleRun = (options: BacktestConfigOptions) => {
    setConfigOptions(options);
    onRunBacktest(options);
  };

  const handleRestart = () => {
    setView("config");
  };

  return (
    <div className="flex flex-col h-full bg-[#0f0f0f] relative overflow-hidden">
      <div className="px-8 pt-8 pb-4">
        <h3 className="text-xl font-black text-[#dfdfdf] tracking-tight">백테스트 & 성과 분석</h3>
        <p className="text-sm text-[#a0a0a0] mt-1 font-medium">
          설정한 전략을 과거 데이터를 바탕으로 시뮬레이션하고 성과를 검증합니다.
        </p>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        {backtestResult && view === "dashboard" ? (
          <BacktestDashboard 
            result={backtestResult} 
            onRestart={handleRestart}
            onRun={handleRun}
            currentOptions={configOptions}
            isRunning={isBacktesting}
          />
        ) : (
          <div className="h-full overflow-y-auto custom-scrollbar">
             <BacktestConfig 
               onRun={handleRun} 
               isRunning={isBacktesting}
               initialConfig={configOptions}
               summary={summaryData}
             />
          </div>
        )}
      </div>
      <div className="h-8" />

      {/* macOS-style Bottom Toolbar / Status View */}
      <div className="sticky bottom-0 left-0 right-0 bg-[#0f0f0f] backdrop-blur-3xl px-8 py-5 z-50 border-t border-white/5">
        <div className="max-w-full mx-auto flex items-center justify-between">
          <div className="flex items-center gap-12">
            <div className="flex items-center gap-6">
              <div className="w-16 h-16 bg-[rgb(59, 134, 247)] rounded-2xl flex items-center justify-center shadow-[0_0_40px_rgba(0,122,255,0.4)]">
                <ChartBarIcon className="w-8 h-8 text-white" />
              </div>
              <div className="space-y-1">
                <h4 className="text-xl font-black text-[#dfdfdf] tracking-tight uppercase">백테스트 요약</h4>
              </div>
            </div>
            
            <div className="h-12 w-px bg-white/10" />
            
            <div className="flex gap-12">
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">초기 자본</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">{(configOptions.initialCapital / 10000).toLocaleString()}만원</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">수수료</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">
                  {configOptions.commissionPct}%
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">테스트 기간</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">
                  {configOptions.period}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button 
              onClick={onPrev} 
              className="px-8 py-5 bg-white/5 text-white/40 rounded-2xl text-lg font-black hover:bg-white/10 hover:text-white transition-all flex items-center gap-4 active:scale-95"
            >
              <ArrowLeftIcon className="w-6 h-6" /> 이전
            </button>
            <button 
              onClick={onSave} 
              className="group px-12 py-5 bg-white text-black rounded-2xl text-lg font-black hover:bg-gray-100 transition-all flex items-center gap-4 shadow-[0_20px_40px_rgba(255,255,255,0.1)] hover:scale-105 active:scale-95"
            >
              전략 저장하기 <CheckIcon className="w-6 h-6 group-hover:scale-110 transition-transform duration-500" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
