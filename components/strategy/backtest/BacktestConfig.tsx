"use client";

import { useState, useEffect } from "react";
import { 
  PlayCircle,
  ArrowsClockwise,
  Globe,
  Code,
  Briefcase,
  ShieldCheck,
  WarningCircle
} from "phosphor-react";

const formatKoreanUnit = (num: number) => {
  if (num === 0) return "0원";
  const units = ["", "만", "억", "조", "경"];
  const result = [];
  let temp = num;
  let unitIdx = 0;

  while (temp > 0 && unitIdx < units.length) {
    const chunk = temp % 10000;
    if (chunk > 0) {
      const formattedChunk = chunk.toLocaleString();
      result.unshift(`${formattedChunk}${units[unitIdx]}`);
    }
    temp = Math.floor(temp / 10000);
    unitIdx++;
  }

  return result.join(" ") + "원";
};

export interface BacktestConfigOptions {
  period: string;
  startDate?: string;
  endDate?: string;
  initialCapital: number;
  commissionPct: number;
  slippagePct: number;
}

export interface StrategySummaryData {
  universeName: string;
  universeFiltersCount: number;
  blockNames: string[];
  riskSettings: {
    maxPositions: number;
    allocationType: string;
  };
  riskManagement: {
    stopLoss?: number;
    takeProfit?: number;
    trailingStop?: number;
    maxHoldingDays?: number;
  };
}

interface BacktestConfigProps {
  onRun: (options: BacktestConfigOptions) => void;
  isRunning: boolean;
  initialConfig?: Partial<BacktestConfigOptions>;
  summary: StrategySummaryData;
}

export default function BacktestConfig({ onRun, isRunning, initialConfig, summary }: BacktestConfigProps) {
  const [period, setPeriod] = useState(initialConfig?.period || "1Y");
  const [initialCapital, setInitialCapital] = useState(initialConfig?.initialCapital || 10000000);
  const [commissionPct, setCommissionPct] = useState(initialConfig?.commissionPct || 0.015);
  const [slippagePct, setSlippagePct] = useState(initialConfig?.slippagePct || 0.05);
  
  // Custom Date Range State
  const [startDate, setStartDate] = useState(initialConfig?.startDate || new Date(new Date().setFullYear(new Date().getFullYear() - 1)).toISOString().split('T')[0]);
  const [endDate, setEndDate] = useState(initialConfig?.endDate || new Date().toISOString().split('T')[0]);

  // Sync with initialConfig if it changes (e.g. returning from dashboard)
  useEffect(() => {
    if (initialConfig) {
      if (initialConfig.period) setPeriod(initialConfig.period);
      if (initialConfig.initialCapital) setInitialCapital(initialConfig.initialCapital);
      if (initialConfig.commissionPct !== undefined) setCommissionPct(initialConfig.commissionPct);
      if (initialConfig.slippagePct !== undefined) setSlippagePct(initialConfig.slippagePct);
      if (initialConfig.startDate) setStartDate(initialConfig.startDate);
      if (initialConfig.endDate) setEndDate(initialConfig.endDate);
    }
  }, [initialConfig]);

  const periods = [
    { id: "6M", label: "6개월" },
    { id: "1Y", label: "1년" },
    { id: "5Y", label: "5년" },
    { id: "10Y", label: "10년" },
    { id: "20Y", label: "20년" },
    { id: "custom", label: "직접 입력" },
  ];
  const handlePeriodChange = (id: string) => {
    setPeriod(id);
    if (id !== "custom") {
      const end = new Date();
      const start = new Date();
      
      switch (id) {
        case "6M": start.setMonth(end.getMonth() - 6); break;
        case "1Y": start.setFullYear(end.getFullYear() - 1); break;
        case "5Y": start.setFullYear(end.getFullYear() - 5); break;
        case "10Y": start.setFullYear(end.getFullYear() - 10); break;
        case "20Y": start.setFullYear(end.getFullYear() - 20); break;
      }
      setStartDate(start.toISOString().split('T')[0]);
      setEndDate(end.toISOString().split('T')[0]);
    }
  };

  const handleRun = () => {
    onRun({
      period,
      startDate: period === "custom" ? startDate : undefined,
      endDate: period === "custom" ? endDate : undefined,
      initialCapital,
      commissionPct,
      slippagePct,
    });
  };

  return (
    <div className="w-full h-full flex flex-col lg:flex-row bg-[#0a0a0a] animate-in fade-in duration-500">
      
      {/* =========================================================
          Left Column: Functional Inputs (Simulation Parameters)
          ========================================================= */}
      <div className="flex-1 flex flex-col border-r border-white/5 overflow-y-auto">
        
        {/* Step 1: Period */}
        <div className="flex-1 p-6 lg:p-10 border-b border-white/5 flex flex-col justify-center">
          <div className="flex flex-col mb-8">
            <span className="text-xs font-bold text-main-blue uppercase tracking-widest mb-2">Step 1</span>
            <h2 className="text-xl font-black text-[#dfdfdf] tracking-tight">테스트 기간 설정</h2>
          </div>
          
          <div className="space-y-4 max-w-2xl">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {periods.map((p) => (
                <button
                  key={p.id}
                  onClick={() => handlePeriodChange(p.id)}
                  className={`py-3.5 rounded-lg text-sm font-bold transition-all border ${
                    period === p.id 
                      ? "bg-main-blue border-main-blue text-white shadow-[0_0_15px_rgba(59,134,247,0.3)]" 
                      : "bg-[#111] border-white/5 text-[#a0a0a0] hover:bg-white/5 hover:text-white"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {period === "custom" && (
              <div className="flex gap-4 mt-6 animate-in fade-in slide-in-from-top-2 duration-200 bg-[#111] p-5 rounded-xl border border-white/5">
                 <div className="flex-1 space-y-2">
                   <label className="text-[11px] font-black text-[#606060] uppercase tracking-widest pl-1">시작일</label>
                   <input 
                     type="date" 
                     value={startDate}
                     onChange={(e) => setStartDate(e.target.value)}
                     className="bg-[#0a0a0a] border border-white/10 rounded-lg px-4 py-3 text-sm text-white font-bold w-full outline-none focus:border-main-blue transition-all" 
                   />
                 </div>
                 <div className="flex-1 space-y-2">
                   <label className="text-[11px] font-black text-[#606060] uppercase tracking-widest pl-1">종료일</label>
                   <input 
                     type="date" 
                     value={endDate}
                     onChange={(e) => setEndDate(e.target.value)}
                     className="bg-[#0a0a0a] border border-white/10 rounded-lg px-4 py-3 text-sm text-white font-bold w-full outline-none focus:border-main-blue transition-all" 
                   />
                 </div>
              </div>
            )}
          </div>
        </div>

        {/* Step 2: Capital & Costs */}
        <div className="flex-1 p-6 lg:p-10 flex flex-col justify-center">
          <div className="flex flex-col mb-8">
            <span className="text-xs font-bold text-main-blue uppercase tracking-widest mb-2">Step 2</span>
            <h2 className="text-xl font-black text-[#dfdfdf] tracking-tight">초기 자본 및 거래 비용</h2>
          </div>

          <div className="space-y-6 max-w-2xl">
             <div className="space-y-2">
                <label className="text-[11px] font-black text-[#a0a0a0] uppercase tracking-widest pl-1">초기 자본금</label>
                <div className="bg-[#111] border border-white/5 rounded-xl px-5 py-4 group hover:border-white/10 focus-within:border-main-blue transition-all relative overflow-hidden">
                   <div className="absolute inset-y-0 left-0 w-1 bg-main-blue opacity-0 group-focus-within:opacity-100 transition-opacity" />
                   <div className="flex items-center justify-between">
                      <input 
                        type="text"
                        value={initialCapital.toLocaleString()}
                        onChange={(e) => {
                          const val = Number(e.target.value.replace(/,/g, ''));
                          if (!isNaN(val)) setInitialCapital(val);
                        }}
                        className="w-full bg-transparent border-none p-0 text-white font-black text-2xl outline-none"
                      />
                      <span className="text-[#606060] font-black text-lg ml-3 tracking-widest">KRW</span>
                   </div>
                   <p className="text-xs font-bold text-main-blue mt-2 text-right">{formatKoreanUnit(initialCapital)}</p>
                </div>
             </div>

             <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[11px] font-black text-[#a0a0a0] uppercase tracking-widest pl-1">수수료</label>
                  <div className="flex items-center bg-[#111] border border-white/5 rounded-xl px-4 py-3 group hover:border-white/10 focus-within:border-white transition-all">
                    <input 
                      type="number" 
                      step="0.001"
                      value={commissionPct}
                      onChange={(e) => setCommissionPct(Number(e.target.value))}
                      className="w-full bg-transparent border-none p-0 text-lg text-white font-black outline-none font-mono"
                    />
                    <span className="text-sm text-[#606060] font-black ml-2">%</span>
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-[11px] font-black text-[#a0a0a0] uppercase tracking-widest pl-1">슬리피지</label>
                  <div className="flex items-center bg-[#111] border border-white/5 rounded-xl px-4 py-3 group hover:border-white/10 focus-within:border-white transition-all">
                    <input 
                      type="number" 
                      step="0.01"
                      value={slippagePct}
                      onChange={(e) => setSlippagePct(Number(e.target.value))}
                      className="w-full bg-transparent border-none p-0 text-lg text-white font-black outline-none font-mono"
                    />
                    <span className="text-sm text-[#606060] font-black ml-2">%</span>
                  </div>
                </div>
             </div>
          </div>
        </div>

        {/* Bottom Action Bar (Left Pane) */}
        <div className="mt-auto border-t border-white/5 bg-[#050505] p-6 lg:px-10 py-5 flex items-center justify-between shrink-0">
          <div className="hidden sm:block text-[11px] text-[#606060] font-medium leading-relaxed max-w-sm">
            시뮬레이션은 과거 데이터 기반 연산으로 미래 수익을 보장하지 않으며, 보수적 평가를 위해 수수료와 슬리피지가 자동 차감됩니다.
          </div>
          <button
            onClick={handleRun}
            disabled={isRunning}
            className="w-full sm:w-auto relative overflow-hidden group py-4 px-10 bg-main-blue hover:bg-blue-500 text-white rounded-lg text-base font-black transition-all flex items-center justify-center gap-3 shadow-[0_0_20px_rgba(59,134,247,0.3)] hover:shadow-[0_0_30px_rgba(59,134,247,0.4)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 disabled:hover:shadow-none min-w-[200px]"
          >
            {isRunning ? (
              <>
                <ArrowsClockwise className="w-5 h-5 animate-spin" />
                <span>분석 중...</span>
              </>
            ) : (
              <>
                <PlayCircle className="w-5 h-5" />
                <span>백테스트 시작</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* =========================================================
          Right Column: Strategy Snapshot (Bento Grid)
          ========================================================= */}
      <div className="w-full lg:w-[480px] xl:w-[540px] bg-[#141414] flex flex-col overflow-y-auto shrink-0 border-l border-white/5">
        <div className="p-6 lg:p-10 flex-1 flex flex-col relative">
          <div className="absolute top-0 right-0 w-64 h-64 bg-main-blue/5 rounded-full blur-[80px] pointer-events-none" />
          
          <div className="flex items-center gap-3 mb-8 relative z-10">
            <h2 className="text-lg font-black text-white/80 tracking-widest uppercase">전략 스냅샷</h2>
            <div className="flex-1 h-px bg-white/5" />
            <span className="px-2 py-1 bg-white/5 rounded text-[9px] font-black text-white/40 tracking-widest border border-white/5">
              SUMMARY
            </span>
          </div>

          {/* Bento Grid Container */}
          <div className="flex-1 grid grid-cols-2 gap-3 auto-rows-max relative z-10">
            
            {/* CELL 1: Universe (Full width) */}
            <div className="col-span-2 bg-[#1a1a1a]/80 rounded-xl p-5 border border-white/5 hover:border-white/10 transition-colors group flex flex-col sm:flex-row gap-4 items-start sm:items-center">
               <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0 group-hover:bg-blue-500/20 transition-colors">
                 <Globe className="w-5 h-5 text-blue-500" />
               </div>
               <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-black text-blue-500 uppercase tracking-widest mb-1">유니버스 설정</div>
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="text-lg font-black text-white truncate">{summary.universeName}</span>
                    {summary.universeFiltersCount > 0 ? (
                      <span className="text-[10px] font-bold text-[#a0a0a0] bg-[#222] px-2 py-0.5 rounded border border-[#333]">
                        {summary.universeFiltersCount} 필터
                      </span>
                    ) : (
                      <span className="text-[10px] font-medium text-[#606060] italic">전체 종목</span>
                    )}
                  </div>
               </div>
            </div>

            {/* CELL 2: Trading Logic (Full width) */}
            <div className="col-span-2 bg-[#1a1a1a]/80 rounded-xl p-5 border border-white/5 hover:border-white/10 transition-colors group flex flex-col gap-3">
               <div className="flex items-center gap-3">
                 <div className="w-10 h-10 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center shrink-0 group-hover:bg-purple-500/20 transition-colors">
                   <Code className="w-5 h-5 text-purple-500" />
                 </div>
                 <div className="flex-1">
                    <div className="text-[10px] font-black text-purple-500 uppercase tracking-widest mb-0.5">매매 로직 블록</div>
                    <div className="text-xs text-[#606060] font-bold">{summary.blockNames.length} 조건 설정됨</div>
                 </div>
               </div>
               
               <div className="bg-[#111] rounded-lg border border-white/5 p-3 max-h-[160px] overflow-y-auto custom-scrollbar">
                  {summary.blockNames.length > 0 ? (
                    <ul className="space-y-1.5">
                      {summary.blockNames.map((name, idx) => (
                        <li key={idx} className="flex items-start gap-2 text-xs text-[#dfdfdf] font-medium leading-relaxed">
                           <span className="text-purple-500/50 text-[8px] mt-1.5">●</span>
                           <span className="break-words">{name}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-4 text-center opacity-50">
                      <WarningCircle className="w-5 h-5 text-[#a0a0a0] mb-1" />
                      <span className="text-xs font-bold text-[#a0a0a0]">설정된 조건이 없습니다</span>
                    </div>
                  )}
               </div>
            </div>

            {/* CELL 3: Position Sizing (Left Half) */}
            <div className="col-span-2 sm:col-span-1 bg-[#1a1a1a]/80 rounded-xl p-5 border border-white/5 hover:border-white/10 transition-colors group flex flex-col justify-between">
               <div>
                 <div className="w-8 h-8 rounded-md bg-orange-500/10 border border-orange-500/20 flex items-center justify-center mb-3 group-hover:bg-orange-500/20 transition-colors">
                   <Briefcase className="w-4 h-4 text-orange-500" />
                 </div>
                 <div className="text-[10px] font-black text-orange-500 uppercase tracking-widest mb-4">포지션/비중</div>
               </div>
               
               <div className="space-y-2.5">
                  <div className="flex flex-col">
                     <span className="text-[9px] text-[#606060] font-bold uppercase mb-0.5">최대 보유 종목</span>
                     <span className="text-base font-black text-white">{summary.riskSettings.maxPositions}<span className="text-[10px] text-[#a0a0a0] ml-1">개</span></span>
                  </div>
                  <div className="h-px w-full bg-white/5" />
                  <div className="flex flex-col">
                     <span className="text-[9px] text-[#606060] font-bold uppercase mb-0.5">배분 방식</span>
                     <span className="text-xs font-black text-white">
                        {summary.riskSettings.allocationType === 'equal' ? '동일 비중' : '고정 비율'}
                     </span>
                  </div>
               </div>
            </div>

            {/* CELL 4: Risk Management (Right Half) */}
            <div className="col-span-2 sm:col-span-1 bg-[#1a1a1a]/80 rounded-xl p-5 border border-white/5 hover:border-white/10 transition-colors group flex flex-col justify-between">
               <div>
                 <div className="w-8 h-8 rounded-md bg-green-500/10 border border-green-500/20 flex items-center justify-center mb-3 group-hover:bg-green-500/20 transition-colors">
                   <ShieldCheck className="w-4 h-4 text-green-500" />
                 </div>
                 <div className="text-[10px] font-black text-green-500 uppercase tracking-widest mb-4">청산 방어선</div>
               </div>
               
               <div className="space-y-2.5">
                  <div className="flex items-center justify-between">
                     <span className="text-[10px] text-[#a0a0a0] font-bold">손절매</span>
                     <span className={`text-sm font-black ${summary.riskManagement.stopLoss ? 'text-red-500' : 'text-[#606060]'}`}>
                       {summary.riskManagement.stopLoss ? `-${summary.riskManagement.stopLoss}%` : 'OFF'}
                     </span>
                  </div>
                  <div className="h-px w-full bg-white/5" />
                  <div className="flex items-center justify-between">
                     <span className="text-[10px] text-[#a0a0a0] font-bold">익절매</span>
                     <span className={`text-sm font-black ${summary.riskManagement.takeProfit ? 'text-green-500' : 'text-[#606060]'}`}>
                       {summary.riskManagement.takeProfit ? `+${summary.riskManagement.takeProfit}%` : 'OFF'}
                     </span>
                  </div>
                   <div className="h-px w-full bg-white/5" />
                  <div className="flex items-center justify-between">
                     <span className="text-[10px] text-[#a0a0a0] font-bold">MDD 제어</span>
                     <span className={`text-sm font-black ${summary.riskManagement.trailingStop ? 'text-orange-500' : 'text-[#606060]'}`}>
                       {summary.riskManagement.trailingStop ? 'ON' : 'OFF'}
                     </span>
                  </div>
               </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
