"use client";

import { useState, useEffect } from "react";
import { 
  PlayCircleIcon,
  ArrowPathIcon
} from "@heroicons/react/24/outline";

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

  useEffect(() => {
    console.error("[DEBUG] BacktestConfig component MOUNTED (v2)");
  }, []);

  const handleRun = () => {
    console.error("[DEBUG] BacktestConfig: handleRun initiated");
    
    console.error("[DEBUG] Options to be passed:", {
      period,
      initialCapital,
      commissionPct,
      slippagePct
    });

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
    <div className="w-full max-w-6xl mx-auto p-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_1.8fr] gap-6 mb-8">
        
        {/* Left Column: Period & Capital */}
        <div className="space-y-6 flex flex-col">
           <div className="bg-[#111] border border-gray-800 rounded-3xl p-6 flex-1 flex flex-col">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xl font-black text-[#dfdfdf] uppercase tracking-tight">테스트 기간</span>
            </div>
            
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2">
                {periods.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => handlePeriodChange(p.id)}
                    className={`py-2.5 rounded-lg text-sm font-bold transition-all border ${
                      period === p.id 
                        ? "bg-main-blue border-main-blue text-white shadow-lg shadow-main-blue/20" 
                        : "bg-[#1a1a1a] border-gray-800 text-[#a0a0a0] hover:bg-gray-800 hover:text-gray-300"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              {period === "custom" && (
                <div className="flex gap-2 mt-2 animate-in fade-in slide-in-from-top-2 duration-200">
                   <div className="flex-1 space-y-1">
                     <label className="text-xs text-[#a0a0a0]">시작일</label>
                     <input 
                       type="date" 
                       value={startDate}
                       onChange={(e) => setStartDate(e.target.value)}
                       className="bg-[#1a1a1a] border border-gray-800 rounded-xl px-3 py-2 text-sm text-white font-bold w-full outline-none focus:border-white uppercase" 
                     />
                   </div>
                   <div className="flex-1 space-y-1">
                     <label className="text-xs text-[#a0a0a0]">종료일</label>
                     <input 
                       type="date" 
                       value={endDate}
                       onChange={(e) => setEndDate(e.target.value)}
                       className="bg-[#1a1a1a] border border-gray-800 rounded-xl px-3 py-2 text-sm text-white font-bold w-full outline-none focus:border-white uppercase" 
                     />
                   </div>
                </div>
              )}
            </div>
          </div>

          <div className="bg-[#111] border border-gray-800 rounded-2xl p-6 flex-1 flex flex-col">
            <div className="flex items-center gap-2 mb-6">
              <span className="text-xl font-black text-[#dfdfdf] uppercase tracking-tight">투자금 및 비용</span>
            </div>

            <div className="space-y-6">
               <div className="space-y-2">
                  <label className="text-sm text-gray-500 font-bold">초기 자본금</label>
                  <div className="bg-[#1a1a1a] border border-gray-800 rounded-2xl px-5 py-4 group hover:border-gray-700 focus-within:border-white transition-all">
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
                        <span className="text-[#a0a0a0] font-bold text-lg ml-2">원</span>
                     </div>
                     <p className="text-sm font-bold text-white/40 mt-1 text-right">{formatKoreanUnit(initialCapital)}</p>
                  </div>
               </div>

               <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-sm text-gray-500 font-bold">수수료 (%)</label>
                    <div className="flex items-center bg-[#1a1a1a] border border-gray-800 rounded-2xl px-4 py-3">
                      <input 
                        type="number" 
                        step="0.001"
                        value={commissionPct}
                        onChange={(e) => setCommissionPct(Number(e.target.value))}
                        className="w-full bg-transparent border-none p-0 text-base text-white font-bold outline-none font-mono"
                      />
                      <span className="text-sm text-gray-500 ml-1">%</span>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm text-gray-500 font-bold">슬리피지 (%)</label>
                    <div className="flex items-center bg-[#1a1a1a] border border-gray-800 rounded-2xl px-4 py-3">
                      <input 
                        type="number" 
                        step="0.01"
                        value={slippagePct}
                        onChange={(e) => setSlippagePct(Number(e.target.value))}
                        className="w-full bg-transparent border-none p-0 text-base text-white font-bold outline-none font-mono"
                      />
                      <span className="text-sm text-gray-500 ml-1">%</span>
                    </div>
                  </div>
               </div>

            </div>
          </div>
        </div>

        {/* Right Column: Strategy Summary */}
        <div className="bg-[#111] border border-gray-800 rounded-3xl p-6 flex flex-col">
          <div className="flex items-center gap-2 mb-6">
            <span className="text-xl font-black text-[#dfdfdf] uppercase tracking-tight">전략 요약</span>
          </div>

          <div className="flex-1 space-y-6">
             {/* Universe Summary */}
             <div className="space-y-2">
                <div className="flex justify-between items-center text-sm">
                   <span className="text-[#a0a0a0] font-bold">유니버스</span>
                </div>
                <div className="bg-[#1a1a1a] p-4 rounded-2xl border border-gray-800">
                   <div className="text-base font-bold text-[#dfdfdf] mb-1">{summary.universeName}</div>
                   {summary.universeFiltersCount > 0 && (
                     <div className="text-sm text-gray-500">
                        {summary.universeFiltersCount}개의 필터 적용됨
                     </div>
                   )}
                </div>
             </div>

             {/* Logic Summary */}
             <div className="space-y-2">
                <div className="flex justify-between items-center text-sm">
                   <span className="text-[#a0a0a0] font-bold">매매 조건</span>
                </div>
                 <div className="bg-[#1a1a1a] p-4 rounded-2xl border border-gray-800">
                    <div className="space-y-1.5 max-h-[120px] overflow-y-auto custom-scrollbar pr-2">
                       {summary.blockNames.length > 0 ? (
                         summary.blockNames.map((name, idx) => (
                           <div key={idx} className="flex items-center gap-2 text-sm text-gray-300">
                              <div className="w-1.5 h-1.5 rounded-full bg-white/50 shrink-0" />
                              <span className="truncate">{name}</span>
                           </div>
                         ))
                       ) : (
                         <div className="text-sm text-gray-500 italic">설정된 조건 없음</div>
                       )}
                    </div>
                 </div>
             </div>

              {/* Position & Risk Summary */}
               <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                   <div className="flex justify-between items-center text-sm">
                      <span className="text-[#a0a0a0] font-bold">포지션 설정</span>
                   </div>
                   <div className="bg-[#1a1a1a] p-3 rounded-2xl border border-gray-800 space-y-1.5">
                      <div className="flex justify-between">
                         <span className="text-xs text-[#a0a0a0]">최대 종목</span>
                         <span className="text-sm text-white font-bold">{summary.riskSettings.maxPositions}개</span>
                      </div>
                      <div className="flex justify-between">
                         <span className="text-xs text-[#a0a0a0]">비중 방식</span>
                         <span className="text-sm text-white font-bold uppercase">
                            {summary.riskSettings.allocationType === 'equal' ? '동일' : '고정'}
                         </span>
                      </div>
                   </div>
                </div>

                <div className="space-y-2">
                   <div className="flex justify-between items-center text-sm">
                      <span className="text-[#a0a0a0] font-bold">리스크 관리</span>
                   </div>
                   <div className="bg-[#1a1a1a] p-3 rounded-2xl border border-gray-800 space-y-1.5">
                      <div className="flex justify-between">
                         <span className="text-xs text-[#a0a0a0]">손절</span>
                         <span className="text-sm text-white font-bold">-{summary.riskManagement.stopLoss || 0}%</span>
                      </div>
                      <div className="flex justify-between">
                         <span className="text-xs text-[#a0a0a0]">익절</span>
                         <span className="text-sm text-white font-bold">{summary.riskManagement.takeProfit || 0}%</span>
                      </div>
                   </div>
                </div>
              </div>
          </div>
        </div>
      </div>

      <button
        onClick={handleRun}
        disabled={isRunning}
        className="w-full py-4 bg-[#161616] hover:bg-[#1f1f1f] text-white rounded-2xl text-lg font-black transition-all flex items-center justify-center gap-3 shadow-xl border border-white/5 hover:border-white/10 active:scale-[0.99] disabled:opacity-70 disabled:cursor-not-allowed"
      >
        {isRunning ? (
          <>
            <ArrowPathIcon className="w-6 h-6 animate-spin" />
            시뮬레이션 실행 중...
          </>
        ) : (
          <>
            <PlayCircleIcon className="w-6 h-6" />
            백테스트 시작하기
          </>
        )}
      </button>

      <div className="mt-6 text-center">
        <p className="text-xs text-gray-600">
          * 시뮬레이션은 과거 데이터를 기반으로 하며 미래의 수익을 보장하지 않습니다. <br/>
          * 설정된 슬리피지와 수수료는 매 거래마다 차감되어 최종 수익률에 반영됩니다.
        </p>
      </div>
    </div>
  );
}
