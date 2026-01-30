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
  onViewChange?: (view: "config" | "dashboard") => void;
  summaryData: any; // Using any for now to avoid circular deps or complex imports, ideally stick to StrategySummaryData
}

export default function Step5Backtest({
  strategyName,
  backtestResult,
  isBacktesting,
  onPrev,
  onSave,
  onRunBacktest,
  onViewChange,
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

  const [lastResultId, setLastResultId] = useState<any>(null);

  useEffect(() => {
    // Only auto-switch to dashboard if we get a NEW result 
    if (backtestResult && !isBacktesting) {
      if (backtestResult !== lastResultId) {
        setView("dashboard");
        onViewChange?.("dashboard");
        setLastResultId(backtestResult);
      }
    }
  }, [backtestResult, isBacktesting, lastResultId, onViewChange]);

  const handleRun = (options: BacktestConfigOptions) => {
    console.log("[DEBUG] Step5Backtest: handleRun called with", options);
    setConfigOptions(options);
    onRunBacktest(options);
  };

  const handleRestart = () => {
    setView("config");
    onViewChange?.("config");
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden bg-[#0f0f0f] relative px-0 pb-0">
      <div className="flex-none px-4 pt-4 pb-2">
        <h3 className="text-xl font-black text-[#dfdfdf] tracking-tight">백테스트 & 성과 분석</h3>
        <p className="text-sm text-[#a0a0a0] mt-1 font-medium">
          설정한 전략을 과거 데이터를 바탕으로 시뮬레이션하고 성과를 검증합니다.
        </p>
      </div>
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        {backtestResult && view === "dashboard" ? (
          <BacktestDashboard 
            key={`${backtestResult === (lastResultId as any) ? "same" : "new"}-${JSON.stringify({
              summary: summaryData,
              // Explicitly include canvasBlocks if not already in summary
            })}`}
            result={backtestResult} 
            onRestart={handleRestart}
            onRun={handleRun}
            onSave={onSave}
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
    </div>
  );
}
