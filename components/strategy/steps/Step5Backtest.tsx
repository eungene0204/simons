"use client";

import { BacktestResult } from "@/types/strategy";
import BacktestConfig, { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";
import BacktestDashboard from "@/components/strategy/backtest/BacktestDashboard";
import { useState } from "react";

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
  const [view, setView] = useState<"config" | "dashboard">("config");

  if (backtestResult && view !== "dashboard") {
    setView("dashboard");
  }

  const handleRun = (options: BacktestConfigOptions) => {
    onRunBacktest(options);
    // Don't switch view yet, wait for result or show loading in config
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
          />
        ) : (
          <div className="h-full overflow-y-auto custom-scrollbar">
             <BacktestConfig 
               onRun={handleRun} 
               isRunning={isBacktesting}
               summary={summaryData}
             />
          </div>
        )}
      </div>
      
       <div className="shrink-0 p-6 flex justify-between bg-[#0f0f0f] border-t border-gray-800 z-20">
         <button 
            onClick={onPrev} 
            className="px-6 py-3 bg-[#0a0a0a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 transition-all"
          >
            이전 단계
          </button>
          
          <button 
             onClick={onSave}
             className="px-8 py-3 bg-red-600 text-white rounded-xl text-md font-black hover:bg-red-500 transition-all shadow-xl shadow-red-900/40"
          >
            전략 저장
          </button>
       </div>
    </div>
  );
}
