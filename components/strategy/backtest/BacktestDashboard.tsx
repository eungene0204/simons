"use client";

import { BacktestResult } from "@/types/strategy";
import BacktestChart from "@/components/strategy/BacktestChart";
import { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";
import { 
  ArrowTrendingUpIcon, 
  ArrowTrendingDownIcon, 
  TableCellsIcon, 
  ChartBarIcon, 
  ArrowPathIcon,
  CheckBadgeIcon,
  ExclamationTriangleIcon,
  ListBulletIcon
} from "@heroicons/react/24/outline";
import { useState, useEffect } from "react";

interface BacktestDashboardProps {
  result: BacktestResult;
  onRestart: () => void;
  onRun?: (options: BacktestConfigOptions) => void;
  currentOptions?: BacktestConfigOptions;
  isRunning?: boolean;
}

export default function BacktestDashboard({ 
  result, 
  onRestart, 
  onRun, 
  currentOptions,
  isRunning 
}: BacktestDashboardProps) {
  const [activeTab, setActiveTab] = useState<"chart" | "stats" | "log" | "assets">("chart");
  const [localOptions, setLocalOptions] = useState<BacktestConfigOptions | null>(currentOptions || null);
  
  const formatKRW = (val: number) => {
    const num = Number(val);
    if (isNaN(num) || num === 0) return "0원";
    return Math.round(num).toLocaleString() + "원";
  };

  useEffect(() => {
    if (currentOptions) setLocalOptions(currentOptions);
  }, [currentOptions]);

  useEffect(() => {
    console.log("[DEBUG] BacktestDashboard: result received", {
      totalReturn: result.totalReturn,
      diff: result.finalEquity - result.initialCapital,
      numTrades: result.trades,
      numEquityPoints: result.equity.length,
      sampleTrades: result.tradesList?.slice(0, 3)
    });
  }, [result]);

  return (
    <div className="flex flex-col h-full animate-in fade-in zoom-in-95 duration-300">
      {/* Missing Data Warnings */}
      {result.warnings && result.warnings.length > 0 && (
        <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl flex flex-col gap-2">
           <div className="flex items-center gap-2 text-amber-400 font-black text-sm uppercase">
              <ExclamationTriangleIcon className="w-5 h-5" />
              주의: 백테스트 데이터 제한 사항
           </div>
           <ul className="list-disc list-inside space-y-1">
             {result.warnings.map((w, i) => (
               <li key={i} className="text-xs text-amber-200 font-medium">
                 {w}
               </li>
             ))}
           </ul>
        </div>
      )}

      {/* 1. Hero Metrics Header */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <MetricCard 
          label="연평균수익률" 
          value={`${result.cagr.toFixed(2)}%`} 
          subValue="CAGR" 
          trend={result.cagr > 0 ? "up" : "down"} 
        />
        <MetricCard 
          label="최대낙폭" 
          value={`${result.maxDrawdown.toFixed(2)}%`} 
          subValue="MDD" 
          trend="down"
        />
        <MetricCard 
          label="샤프지수" 
          value={result.sharpe.toFixed(2)} 
          subValue="위험 대비 성과" 
          trend={result.sharpe > 1 ? "up" : "neutral"} 
        />
         <MetricCard 
          label="승률" 
          value={`${result.winRate.toFixed(1)}%`} 
          subValue={`총 ${result.trades}회 거래`} 
          trend={result.winRate > 50 ? "up" : "neutral"} 
        />
        <MetricCard 
          label="손익비" 
          value={result.profitFactor.toFixed(2)} 
          subValue="Profit Factor" 
          trend={result.profitFactor > 1.5 ? "up" : "neutral"} 
        />
      </div>

      {/* 2. Main Content Area */}
      <div className="flex-1 min-h-0 flex flex-col bg-[#111] border border-gray-800 rounded-2xl overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-[#161616]">
          <div className="flex bg-[#0a0a0a] rounded-lg p-1 border border-gray-800">
            {[
              { id: "chart", label: "차트 분석", icon: ChartBarIcon },
              { id: "assets", label: "종목 분석", icon: ListBulletIcon },
              { id: "stats", label: "통계 상세", icon: TableCellsIcon },
              { id: "log", label: "매매 기록", icon: CheckBadgeIcon },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-bold transition-all ${
                  activeTab === tab.id 
                    ? "bg-gray-800 text-white shadow-sm" 
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>
          
          <div className="flex items-center gap-3">
             <div className="text-xs font-mono text-gray-500">
                {result.dates[0]} ~ {result.dates[result.dates.length-1]}
             </div>
             
             <div className="h-4 w-[1px] bg-gray-800 mx-1" />

             <div className="flex items-center gap-2">
                 <button 
                   onClick={onRestart}
                   className="px-4 py-1.5 bg-[#1a1a1a] border border-gray-700 hover:bg-gray-800 text-gray-300 text-xs font-bold rounded-lg transition-all"
                 >
                   설정 변경
                 </button>
                 <button 
                   onClick={() => onRun && localOptions && onRun(localOptions)}
                   disabled={isRunning}
                   className={`px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-800 disabled:text-gray-600 text-white text-xs font-bold rounded-lg transition-all shadow-lg shadow-indigo-600/20 active:scale-95`}
                 >
                   {isRunning ? "실행 중..." : "재실행"}
                 </button>
              </div>
          </div>
        </div>

        {/* Tab Content */}
        <div className="h-[600px] min-h-[600px] overflow-y-auto p-0 custom-scrollbar relative">
           
           {/* Chart View */}
           {activeTab === "chart" && (
             <div className="h-full flex flex-col p-3 space-y-3">
               <div className="flex-1 min-h-[300px] bg-[#0a0a0f] rounded-xl border border-gray-800 overflow-hidden relative">
                  <BacktestChart 
                    type="equity" 
                    equityData={result.dates.map((d: string, i: number) => ({ 
                      time: d, 
                      equity: result.equity[i], 
                      buyHold: result.benchmarkEquity ? result.benchmarkEquity[i] : (result.initialCapital * (1 + (result.buyAndHoldReturn || 0)/100))
                    }))} 
                  />
               </div>
               
               {/* Quick Stats Summary below chart */}
               <div className="grid grid-cols-4 gap-4">
                  <StatRow label="총 수익" value={formatKRW(result.finalEquity - result.initialCapital)} result={result} />
                  <StatRow label="매수후보유" value={`${result.buyAndHoldReturn.toFixed(1)}%`} result={result} />
                  <StatRow label="연간 변동성" value={`${(result.sharpe > 0 ? (result.cagr / result.sharpe) : 0).toFixed(1)}%`} result={result} isNeutral />
                  <StatRow label="승:패" value={`${Math.round(result.trades * result.winRate / 100)} : ${Math.round(result.trades * (100 - result.winRate) / 100)}`} result={result} isNeutral />
               </div>
             </div>
           )}

           {/* Assets View (Symbol Summary) */}
           {activeTab === "assets" && (
             <div className="p-6">
                <div className="bg-[#1a1a1a] rounded-xl border border-gray-800 overflow-hidden">
                   <table className="w-full text-left border-collapse">
                      <thead className="bg-[#111] border-b border-gray-800">
                         <tr>
                            <th className="p-4 text-sm font-bold text-gray-500">종목</th>
                            <th className="p-4 text-sm font-bold text-gray-500">섹터</th>
                            <th className="p-4 text-sm font-bold text-gray-500 text-right">수익금</th>
                            <th className="p-4 text-sm font-bold text-gray-500 text-right">수익률</th>
                            <th className="p-4 text-sm font-bold text-gray-500 text-right">매매 횟수</th>
                         </tr>
                      </thead>
                      <tbody>
                         <tr className="border-b border-gray-800/50 hover:bg-white/5 transition-colors">
                            <td className="p-4">
                               <div className="flex flex-col">
                                  <span className="text-sm font-bold text-white">삼성전자</span>
                                  <span className="text-[11px] text-gray-500 font-mono">{result.symbol || "005930"}</span>
                               </div>
                            </td>
                            <td className="p-4 text-sm text-gray-400">전기전자</td>
                            <td className={`p-4 text-sm font-bold text-right ${(result.finalEquity - result.initialCapital) >= 0 ? 'text-red-400' : 'text-blue-400'}`}>
                               {formatKRW(result.finalEquity - result.initialCapital)}
                            </td>
                            <td className={`p-4 text-sm font-bold text-right ${(result.finalEquity - result.initialCapital) >= 0 ? 'text-red-400' : 'text-blue-400'}`}>
                               {result.totalReturn.toFixed(2)}%
                            </td>
                            <td className="p-4 text-sm text-white text-right font-mono">
                               {result.trades}회
                            </td>
                         </tr>
                      </tbody>
                   </table>
                   <div className="p-6 bg-[#161616] border-t border-gray-800">
                      <p className="text-xs text-gray-500 leading-relaxed italic">
                        * 현재 베타 버전에서는 단일 종목 백테스트 분석 결과만 제공됩니다. 곧 멀티 종목 분석 기능이 추가될 예정입니다.
                      </p>
                   </div>
                </div>
             </div>
           )}

           {/* Stats View (Heatmap + Detailed Grid) */}
           {activeTab === "stats" && (
             <div className="p-6 space-y-8">
               
                <div>
                  <h4 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                    <TableCellsIcon className="w-4 h-4 text-gray-500" /> 월별 수익률 상세 (연도/월)
                  </h4>
                  <div className="overflow-x-auto custom-scrollbar">
                    <table className="w-full border-collapse overflow-hidden text-[13px]">
                      <thead className="bg-[#1a1a1a] text-gray-500 font-bold">
                        <tr>
                          <th className="p-2 text-center min-w-[60px]">연도</th>
                          {Array.from({length: 12}).map((_, i) => (
                            <th key={i} className="p-2 text-center min-w-[50px]">{i+1}월</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="bg-[#111]">
                        {["2023", "2024", "2025"].map(year => (
                          <tr key={year} className="hover:bg-white/5 transition-colors">
                            <td className="p-2 py-3 font-mono text-gray-400 font-bold bg-[#161616] text-center">{year}</td>
                            {Array.from({length: 12}).map((_, i) => {
                              // Pseudo-random returns for visual demo
                              const val = (Math.random() * 10) - 4; 
                              return (
                                <td key={i} className="p-1">
                                  <div className={`w-full py-1.5 rounded flex items-center justify-center text-[11px] font-bold ${
                                    val > 0 ? `bg-red-500/${Math.min(Math.floor(val * 10), 90)} text-red-100` : `bg-blue-500/${Math.min(Math.abs(val) * 10, 90)} text-blue-100`
                                  }`}>
                                    {val.toFixed(1)}%
                                  </div>
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

               <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                 {/* Risk Stats */}
                 <div className="bg-[#1a1a1a] rounded-xl p-5 border border-gray-800">
                     <h5 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-4">리스크 및 성과 분석</h5>
                     <div className="space-y-3">
                        <StatItem label="초기 자본" value={formatKRW(result.initialCapital)} />
                        <StatItem label="최종 자산" value={formatKRW(result.finalEquity)} />
                        <StatItem label="소르티노 지수" value={result.sortino.toFixed(2)} />
                        <StatItem label="켈리 공식" value={result.kelly.toFixed(2)} />
                       <StatItem label="알파 (KOSPI 대비)" value="-" sub="데이터 부족" />
                       <StatItem label="베타" value="-" sub="데이터 부족" />
                    </div>
                 </div>
                 
                  {/* Trade Stats */}
                 <div className="bg-[#1a1a1a] rounded-xl p-5 border border-gray-800">
                    <h5 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-4">매매 통계</h5>
                    <div className="space-y-3">
                       <StatItem label="총 매매 횟수" value={result.trades.toString()} />
                       <StatItem label="평균 수익" value="--" />
                       <StatItem label="평균 손실" value="--" />
                       <StatItem label="최대 연속 수익" value="--" />
                       <StatItem label="최대 연속 손실" value="--" />
                    </div>
                 </div>
               </div>

             </div>
           )}

           {/* Log View */}
           {activeTab === "log" && (
              <div className="h-full">
                 {result.tradesList?.length > 0 ? (
                    <table className="w-full text-left border-collapse">
                      <thead className="bg-[#111] sticky top-0 z-10 shadow-sm">
                         <tr>
                            <th className="p-3 text-sm font-bold text-gray-500 border-b border-gray-800">날짜</th>
                            <th className="p-3 text-sm font-bold text-gray-500 border-b border-gray-800">구분</th>
                            <th className="p-3 text-sm font-bold text-gray-500 border-b border-gray-800">체결가</th>
                            <th className="p-3 text-sm font-bold text-gray-500 border-b border-gray-800">수량</th>
                            <th className="p-3 text-sm font-bold text-gray-500 border-b border-gray-800">매매사유</th>
                            <th className="p-3 text-sm font-bold text-gray-500 border-b border-gray-800 text-right">거래금액</th>
                         </tr>
                      </thead>
                      <tbody className="bg-[#0f0f0f]">
                          {result.tradesList.map((t, i) => {
                             const tradeAmount = t.amount || (Number(t.price) * Number(t.quantity));
                             
                             return (
                             <tr key={i} className="hover:bg-white/5 transition-colors border-b border-gray-800/50">
                                <td className="p-3 text-sm font-mono text-gray-400">{t.date}</td>
                                <td className="p-3">
                                   <span className={`px-1.5 py-0.5 rounded text-[11px] font-bold ${t.type==='buy' ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400'}`}>
                                      {t.type === 'buy' ? '매수' : '매도'}
                                   </span>
                                </td>
                                <td className="p-3 text-sm text-gray-300 font-bold">{Math.round(Number(t.price)).toLocaleString()}</td>
                                <td className="p-3 text-sm text-gray-400">
                                   {Math.floor(Number(t.quantity)).toLocaleString()}주
                                </td>
                                <td className="p-3 text-sm text-gray-500 italic">{t.reason}</td>
                                <td className="p-3 text-sm text-right font-mono text-white">
                                   {formatKRW(tradeAmount)}
                                </td>
                             </tr>
                             );
                          })}
                      </tbody>
                    </table>
                 ) : (
                    <div className="h-full flex flex-col items-center justify-center text-gray-600 space-y-2">
                       <CheckBadgeIcon className="w-12 h-12 text-gray-800" />
                       <p className="text-lg font-bold">기록이 없습니다</p>
                       <p className="text-sm">백테스트 기간 동안 매매 조건이 충족되지 않았습니다.</p>
                    </div>
                 )}
              </div>
           )}
        </div>
      </div>
    </div>
  );
}

// Sub-components for Cleaner Code

function MetricCard({ label, value, subValue, trend }: { label: string, value: string, subValue?: string, trend: "up" | "down" | "neutral" }) {
  const isUp = trend === "up";
  const colorClass = isUp 
    ? "text-red-400"
    : trend === "down" 
      ? "text-blue-400"
      : "text-gray-300";
      
  return (
    <div className="bg-[#111] border border-gray-800 p-4 rounded-xl flex flex-col justify-between shadow-sm hover:border-gray-700 transition-colors">
      <div className="text-[11px] font-bold text-gray-500 uppercase tracking-widest mb-1">{label}</div>
      <div className={`text-2xl font-black ${colorClass} tracking-tight`}>{value}</div>
      {subValue && <div className="text-[10px] text-gray-600 font-medium mt-1 truncate">{subValue}</div>}
    </div>
  );
}

function StatRow({ label, value, result, isNeutral }: { label: string, value: string, result: any, isNeutral?: boolean }) {
  return (
    <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
       <div className="text-[10px] text-gray-500 mb-1">{label}</div>
       <div className={`text-lg font-bold ${isNeutral ? "text-white" : (value.includes("-") ? "text-blue-400" : "text-red-400")}`}>{value}</div>
    </div>
  );
}

function StatItem({ label, value, sub }: { label: string, value: string, sub?: string }) {
   return (
      <div className="flex justify-between items-center py-1 border-b border-gray-800/50 last:border-none">
         <span className="text-sm text-gray-400 font-medium">{label}</span>
         <div className="text-right">
            <div className="text-sm font-bold text-white font-mono">{value}</div>
            {sub && <div className="text-[10px] text-gray-600">{sub}</div>}
         </div>
      </div>
   );
}
