"use client";

import { BacktestResult } from "@/types/strategy";
import BacktestChart from "@/components/strategy/BacktestChart";
import { 
  ArrowTrendingUpIcon, 
  ArrowTrendingDownIcon, 
  TableCellsIcon, 
  ChartBarIcon, 
  ArrowPathIcon,
  CheckBadgeIcon
} from "@heroicons/react/24/outline";
import { useState } from "react";

interface BacktestDashboardProps {
  result: BacktestResult;
  onRestart: () => void;
}

export default function BacktestDashboard({ result, onRestart }: BacktestDashboardProps) {
  const [activeTab, setActiveTab] = useState<"chart" | "stats" | "log">("chart");

  // Helper for color coding returns
  const getReturnColor = (val: number) => val > 0 ? "text-red-400" : val < 0 ? "text-blue-400" : "text-gray-400";
  const getBgReturnColor = (val: number) => val > 0 ? "bg-red-500/10" : val < 0 ? "bg-blue-500/10" : "bg-gray-800";

  return (
    <div className="flex flex-col h-full animate-in fade-in zoom-in-95 duration-300">
      {/* 1. Hero Metrics Header */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <MetricCard 
          label="CAGR" 
          value={`${result.cagr.toFixed(2)}%`} 
          subValue="연평균 성장률" 
          trend={result.cagr > 0 ? "up" : "down"} 
        />
        <MetricCard 
          label="MDD" 
          value={`${result.maxDrawdown.toFixed(2)}%`} 
          subValue="최대 낙폭" 
          trend="down"
           invertColor // MDD is better when lower/blue? Actually usually MDD is shown negative or positive. Let's stick to standard.
        />
        <MetricCard 
          label="Sharpe" 
          value={result.sharpe.toFixed(2)} 
          subValue="위험 대비 성과" 
          trend={result.sharpe > 1 ? "up" : "neutral"} 
        />
         <MetricCard 
          label="Win Rate" 
          value={`${result.winRate.toFixed(1)}%`} 
          subValue={`총 ${result.trades}회 거래`} 
          trend={result.winRate > 50 ? "up" : "neutral"} 
        />
        <MetricCard 
          label="Profit Factor" 
          value={result.profitFactor.toFixed(2)} 
          subValue="손익비" 
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
             <button onClick={onRestart} className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-400 hover:text-white transition-colors">
                <ArrowPathIcon className="w-4 h-4" />
             </button>
          </div>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-0 min-h-0 custom-scrollbar relative">
           
           {/* Chart View */}
           {activeTab === "chart" && (
             <div className="h-full flex flex-col p-4 space-y-4">
               <div className="flex-1 min-h-[300px] bg-[#0a0a0f] rounded-xl border border-gray-800 overflow-hidden relative">
                  <BacktestChart 
                    type="equity" 
                    height={400} // Dynamic height would be better but fixed for now
                    equityData={result.dates.map((d: string, i: number) => ({ 
                      time: d, 
                      equity: result.equity[i], 
                      buyHold: result.initialCapital * (1 + (result.buyAndHoldReturn || 0)/100) 
                    }))} 
                  />
               </div>
               
               {/* Quick Stats Summary below chart */}
               <div className="grid grid-cols-4 gap-4">
                  <StatRow label="총 수익" value={`${(result.finalEquity - result.initialCapital).toLocaleString()}원`} result={result} />
                  <StatRow label="매수후보유" value={`${result.buyAndHoldReturn.toFixed(1)}%`} result={result} />
                  <StatRow label="연간 변동성" value={`${(result.sharpe > 0 ? (result.cagr / result.sharpe) : 0).toFixed(1)}%`} result={result} isNeutral />
                  <StatRow label="승:패" value={`${Math.round(result.trades * result.winRate / 100)} : ${Math.round(result.trades * (100 - result.winRate) / 100)}`} result={result} isNeutral />
               </div>
             </div>
           )}

           {/* Stats View (Heatmap + Detailed Grid) */}
           {activeTab === "stats" && (
             <div className="p-6 space-y-8">
               
               <div>
                 <h4 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                   <TableCellsIcon className="w-4 h-4 text-gray-500" /> 월별 수익률 히트맵
                 </h4>
                 {/* Mock Heatmap - In real implementation, parse result.monthlyReturns */}
                 <div className="overflow-x-auto">
                    <div className="min-w-[600px] border border-gray-800 rounded-lg overflow-hidden">
                       <div className="grid grid-cols-13 bg-[#1a1a1a] text-[10px] text-gray-500 font-bold border-b border-gray-800">
                          <div className="p-2 border-r border-gray-800">Year</div>
                          {Array.from({length: 12}).map((_, i) => (
                            <div key={i} className="p-2 text-center border-r border-gray-800 last:border-none">{i+1}월</div>
                          ))}
                       </div>
                       {/* Mock Rows */}
                       {["2023", "2024", "2025"].map(year => (
                          <div key={year} className="grid grid-cols-13 border-b border-gray-800 last:border-none hover:bg-white/5 transition-colors">
                             <div className="p-2 py-3 text-xs font-mono text-gray-400 font-bold bg-[#111] border-r border-gray-800 flex items-center">{year}</div>
                             {Array.from({length: 12}).map((_, i) => {
                                // Pseudo-random returns for visual demo since backend doesn't return monthly yet
                                const val = (Math.random() * 10) - 4; 
                                return (
                                  <div key={i} className={`p-1 flex items-center justify-center border-r border-gray-800/50 last:border-none`}>
                                     <div className={`w-full h-full rounded flex items-center justify-center text-[10px] font-bold ${
                                        val > 0 ? `bg-red-500/${Math.min(Math.floor(val * 10), 90)} text-red-100` : `bg-blue-500/${Math.min(Math.floor(Math.abs(val) * 10), 90)} text-blue-100`
                                     }`}>
                                        {val.toFixed(1)}%
                                     </div>
                                  </div>
                                );
                             })}
                          </div>
                       ))}
                    </div>
                 </div>
               </div>

               <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                 {/* Risk Stats */}
                 <div className="bg-[#1a1a1a] rounded-xl p-5 border border-gray-800">
                    <h5 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-4">Risk Analysis</h5>
                    <div className="space-y-3">
                       <StatItem label="Sortino Ratio" value={result.sortino.toFixed(2)} />
                       <StatItem label="Kelly Criterion" value={result.kelly.toFixed(2)} />
                       <StatItem label="Alpha (vs KOSPI)" value="N/A" sub="Not enough data" />
                       <StatItem label="Beta" value="N/A" sub="Not enough data" />
                    </div>
                 </div>
                 
                  {/* Trade Stats */}
                 <div className="bg-[#1a1a1a] rounded-xl p-5 border border-gray-800">
                    <h5 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-4">Trade Statistics</h5>
                    <div className="space-y-3">
                       <StatItem label="Total Trades" value={result.trades.toString()} />
                       <StatItem label="Avg Profit" value="--" />
                       <StatItem label="Avg Loss" value="--" />
                       <StatItem label="Max Consecutive Wins" value="--" />
                       <StatItem label="Max Consecutive Loss" value="--" />
                    </div>
                 </div>
               </div>

             </div>
           )}

           {/* Log View */}
           {activeTab === "log" && (
             <div className="p-0">
                <table className="w-full text-left border-collapse">
                   <thead className="bg-[#111] sticky top-0 z-10 shadow-sm">
                      <tr>
                         <th className="p-3 text-xs font-bold text-gray-500 border-b border-gray-800">Date</th>
                         <th className="p-3 text-xs font-bold text-gray-500 border-b border-gray-800">Type</th>
                         <th className="p-3 text-xs font-bold text-gray-500 border-b border-gray-800">Price</th>
                         <th className="p-3 text-xs font-bold text-gray-500 border-b border-gray-800">Quantity</th>
                         <th className="p-3 text-xs font-bold text-gray-500 border-b border-gray-800">Reason</th>
                         <th className="p-3 text-xs font-bold text-gray-500 border-b border-gray-800 text-right">Value</th>
                      </tr>
                   </thead>
                   <tbody className="bg-[#0f0f0f]">
                      {result.tradesList?.length > 0 ? (
                        result.tradesList.map((t, i) => (
                           <tr key={i} className="hover:bg-white/5 transition-colors border-b border-gray-800/50">
                              <td className="p-3 text-xs font-mono text-gray-400">{t.date}</td>
                              <td className="p-3">
                                 <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${t.type==='buy' ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400'}`}>
                                    {t.type.toUpperCase()}
                                 </span>
                              </td>
                              <td className="p-3 text-xs text-gray-300 font-bold">{Math.round(t.price).toLocaleString()}</td>
                              <td className="p-3 text-xs text-gray-400">{t.quantity}</td>
                              <td className="p-3 text-xs text-gray-500 italic">{t.reason}</td>
                              <td className="p-3 text-xs text-right font-mono text-white">{(Math.round(t.price * t.quantity)).toLocaleString()}</td>
                           </tr>
                        ))
                      ) : (
                         <tr><td colSpan={6} className="p-8 text-center text-sm text-gray-600">No trades recorded.</td></tr>
                      )}
                   </tbody>
                </table>
             </div>
           )}
        </div>
      </div>
    </div>
  );
}

// Sub-components for Cleaner Code

function MetricCard({ label, value, subValue, trend, invertColor }: { label: string, value: string, subValue?: string, trend: "up" | "down" | "neutral", invertColor?: boolean }) {
  const isUp = trend === "up";
  const colorClass = isUp 
    ? (invertColor ? "text-blue-400" : "text-red-400")
    : trend === "down" 
      ? (invertColor ? "text-red-400" : "text-blue-400")
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
