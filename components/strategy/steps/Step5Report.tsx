"use client";

import { BacktestResult } from "@/types/strategy";
import BacktestDashboard from "@/components/strategy/backtest/BacktestDashboard";
import { ChartLineUp, FileText } from "phosphor-react";

interface Step5ReportProps {
  strategyName: string;
  backtestResult: BacktestResult | null;
  isBacktesting: boolean;
  onPrev: () => void;
  onSave: () => void;
  onRestart: () => void;
  onRunBacktest: (options: any) => void;
  configOptions: any;
  summaryData: any;
}

export default function Step5Report({
  strategyName,
  backtestResult,
  isBacktesting,
  onPrev,
  onSave,
  onRestart,
  onRunBacktest,
  configOptions,
  summaryData,
}: Step5ReportProps) {
  if (!backtestResult) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-[#0f0f0f] text-gray-500 relative overflow-hidden">
        {/* Premium Watermark Effect */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.03] select-none">
          <ChartLineUp size={480} weight="thin" />
        </div>
        
        <div className="relative z-10 flex flex-col items-center">
          <div className="w-20 h-20 mb-6 rounded-3xl bg-white/5 flex items-center justify-center border border-white/10 shadow-2xl">
            <FileText size={40} className="text-blue-500/50" />
          </div>
          <p className="text-lg font-medium text-white/70 mb-2">백테스트 결과가 없습니다</p>
          <p className="text-sm text-white/40 mb-8">백테스트 단계에서 테스트를 실행하여 결과를 확인해보세요.</p>
          <button 
            onClick={onPrev}
            className="group relative px-8 py-3 bg-blue-600/90 text-white rounded-xl font-bold hover:bg-blue-500 transition-all duration-300 shadow-[0_0_20px_rgba(59,130,246,0.3)] hover:shadow-[0_0_30px_rgba(59,130,246,0.5)] active:scale-95"
          >
            백테스트 단계로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden bg-[#0f0f0f] relative">
      <BacktestDashboard 
        result={backtestResult} 
        onRestart={onRestart}
        onRun={(options) => onRunBacktest(options)}
        onSave={onSave}
        currentOptions={configOptions}
        isRunning={isBacktesting}
        strategySummary={summaryData}
      />
    </div>
  );
}
