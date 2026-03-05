"use client";

import BacktestConfig, { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";
import { useState, useEffect } from "react";

interface Step4BacktestProps {
  strategyName: string;
  isBacktesting: boolean;
  onPrev: () => void;
  onRunBacktest: (options: BacktestConfigOptions) => void;
  configOptions: BacktestConfigOptions;
  summaryData: any;
}

export default function Step4Backtest({
  strategyName,
  isBacktesting,
  onPrev,
  onRunBacktest,
  configOptions: initialOptions,
  summaryData,
}: Step4BacktestProps) {
  useEffect(() => {
    console.error("[DEBUG] Step4Backtest: MOUNTED");
  }, []);

  const [configOptions, setConfigOptions] = useState<BacktestConfigOptions>(initialOptions);

  const handleRun = (options: BacktestConfigOptions) => {
    console.error("[DEBUG-TRACE] Step4Backtest: handleRun CALLED with", options);
    setConfigOptions(options);
    onRunBacktest(options);
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden bg-[#0f0f0f] relative px-0 pb-0">
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        <div className="h-full overflow-y-auto custom-scrollbar">
           <BacktestConfig 
             onRun={handleRun} 
             isRunning={isBacktesting}
             initialConfig={configOptions}
             summary={summaryData}
           />
        </div>
      </div>
    </div>
  );
}
