"use client";

import { BacktestResult } from "@/types/strategy";
import BacktestConfig, { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";
import BacktestDashboard from "@/components/strategy/backtest/BacktestDashboard";
import { useState, useEffect } from "react";

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
      
       <div className="shrink-0 p-6 flex justify-between bg-[#0f0f0f] z-20">
         <button 
            onClick={onPrev} 
            className="px-6 py-3 bg-[#0a0a0a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 transition-all"
          >
            이전 단계
          </button>
          
          <button 
             onClick={onSave}
             className="px-8 py-3 bg-white text-black rounded-xl text-md font-black hover:bg-gray-100 transition-all shadow-xl shadow-white/5"
          >
            전략 저장
          </button>
       </div>
    </div>
  );
}
