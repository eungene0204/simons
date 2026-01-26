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
  ListBulletIcon,
  CheckIcon
} from "@heroicons/react/24/outline";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";

interface BacktestDashboardProps {
  result: BacktestResult;
  onRestart: () => void;
  onRun?: (options: BacktestConfigOptions) => void;
  onSave?: () => void;
  currentOptions?: BacktestConfigOptions;
  isRunning?: boolean;
}

export default function BacktestDashboard({ 
  result, 
  onRestart, 
  onRun, 
  onSave,
  currentOptions,
  isRunning 
}: BacktestDashboardProps) {
  const [activeTab, setActiveTab] = useState<"chart" | "stats" | "log" | "assets">("chart");
  const [localOptions, setLocalOptions] = useState<BacktestConfigOptions | null>(currentOptions || null);
  const [stockMetadata, setStockMetadata] = useState<Record<string, { name: string, sector: string }>>({});

  useEffect(() => {
    const fetchStockMetadata = async () => {
      try {
        const response = await fetch("/api/stocks/names");
        if (response.ok) {
          const data = await response.json();
          setStockMetadata(data);
        }
      } catch (error) {
        console.error("Failed to fetch stock metadata:", error);
      }
    };
    fetchStockMetadata();
  }, []);
  
  const formatKRW = (val: number) => {
    const num = Number(val);
    if (isNaN(num) || num === 0) return "0원";
    return Math.round(num).toLocaleString() + "원";
  };

  const calculateMonthlyReturns = () => {
    if (!result.dates || !result.equity || result.dates.length === 0) return {};
    
    const monthlyData: { [year: string]: { [month: string]: number } } = {};
    const monthEndEquity: { [key: string]: number } = {};
    
    result.dates.forEach((dateStr, i) => {
      // dateStr is expected to be "YYYY-MM-DD"
      const parts = dateStr.split('-');
      if (parts.length < 2) return;
      const year = parts[0];
      const month = parseInt(parts[1], 10).toString();
      const key = `${year}-${month}`;
      monthEndEquity[key] = result.equity[i];
    });
    
    const keys = Object.keys(monthEndEquity).sort((a, b) => {
      const [ya, ma] = a.split('-').map(Number);
      const [yb, mb] = b.split('-').map(Number);
      return ya !== yb ? ya - yb : ma - mb;
    });

    let prevEquity = result.initialCapital;
    
    keys.forEach(key => {
      const [year, month] = key.split("-");
      const currentEquity = monthEndEquity[key];
      const monthlyReturn = ((currentEquity / prevEquity) - 1) * 100;
      
      if (!monthlyData[year]) monthlyData[year] = {};
      monthlyData[year][month] = monthlyReturn;
      
      prevEquity = currentEquity;
    });
    
    return monthlyData;
  };

  const monthlyReturns = calculateMonthlyReturns();
  const availableYears = Object.keys(monthlyReturns).sort((a, b) => b.localeCompare(a));

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
    <div className="flex-1 flex flex-col min-h-0 min-w-0 animate-in fade-in zoom-in-95 duration-300">
      {/* Missing Data Warnings */}
      {result.warnings && result.warnings.length > 0 && (
        <div className="mb-6 p-4 bg-main-red/10 border border-main-red/30 rounded-xl flex flex-col gap-2">
           <div className="flex items-center gap-2 text-main-red font-black text-base uppercase">
              <ExclamationTriangleIcon className="w-5 h-5" />
              주의: 백테스트 데이터 제한 사항
           </div>
           <ul className="list-disc list-inside space-y-1">
             {result.warnings.map((w, i) => (
               <li key={i} className="text-sm text-red-200/80 font-medium">
                 {w}
               </li>
             ))}
           </ul>
        </div>
      )}

      {/* 1. Hero Metrics Header */}
      <div className="flex-none grid grid-cols-2 lg:grid-cols-5 gap-2 mb-2">
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

      {/* 2. Main Content Area - Exact Mirror of Step 2 Pattern */}
      <div className="flex flex-col bg-[#111] rounded-2xl overflow-hidden mb-2 min-h-0 min-w-0">
        {/* Toolbar */}
        <div className="flex-none flex items-center justify-between px-3 py-2 bg-[#111]">
          <div className="flex bg-[#0a0a0a] rounded-lg p-1">
            {[
              { id: "chart", label: "차트 분석", icon: ChartBarIcon },
              { id: "assets", label: "종목 분석", icon: ListBulletIcon },
              { id: "stats", label: "통계 상세", icon: TableCellsIcon },
              { id: "log", label: "매매 기록", icon: CheckBadgeIcon },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`relative flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-bold transition-colors ${
                  activeTab === tab.id 
                    ? "text-white" 
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {activeTab === tab.id && (
                  <motion.div
                    layoutId="active-tab-backtest"
                    className="absolute inset-0 bg-tab_black rounded-md z-0"
                    transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                  />
                )}
                <span className="relative z-10 flex items-center gap-2">
                  <tab.icon className="w-4 h-4" />
                  {tab.label}
                </span>
              </button>
            ))}
          </div>
          
          <div className="flex items-center gap-3">
             <div className="text-sm font-mono text-gray-500">
                {result.dates[0]} ~ {result.dates[result.dates.length-1]}
             </div>
             
             <div className="h-4 w-[1px] bg-gray-800 mx-1" />

             <div className="flex items-center gap-2">
                 <button 
                   onClick={onRestart}
                   className="px-4 py-1.5 bg-[#161616] hover:bg-[#1f1f1f] border border-white/5 hover:border-white/10 text-white text-sm font-bold rounded-lg transition-all active:scale-95"
                 >
                   설정 변경
                 </button>
                  <button 
                    onClick={() => onRun && localOptions && onRun(localOptions)}
                    disabled={isRunning}
                    className={`px-4 py-1.5 bg-[#161616] hover:bg-[#1f1f1f] disabled:bg-gray-800 disabled:text-gray-600 text-white text-sm font-bold rounded-lg transition-all border border-white/5 hover:border-white/10 active:scale-95`}
                  >
                    {isRunning ? "실행 중..." : "재실행"}
                  </button>
                  {onSave && (
                    <button 
                      onClick={onSave}
                      className="px-4 py-1.5 bg-main-blue hover:bg-blue-600 text-white text-sm font-bold rounded-lg transition-all flex items-center gap-2 active:scale-95"
                    >
                      <CheckIcon className="w-4 h-4" />
                      전략 저장하기
                    </button>
                  )}
              </div>
          </div>
        </div>

        {/* Tab Content */}
        <div className="flex flex-col min-h-0 min-w-0 p-0 relative">
           
           {/* Chart View */}
            {activeTab === "chart" && (
              <div className="flex flex-col px-2 pt-2 pb-3 space-y-2 min-h-0">
                <div className="h-[280px] md:h-[380px] xl:h-[450px] bg-[#0a0a0f] rounded-xl overflow-hidden relative">
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
               <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-4">
                  <StatRow label="총 수익" value={formatKRW(result.finalEquity - result.initialCapital)} result={result} />
                   <StatRow label="매수후보유" value={`${(result.buyAndHoldReturn || 0).toFixed(1)}%`} result={result} />
                   <StatRow label="연간 변동성" value={`${(result.sharpe > 0 ? ((result.cagr || 0) / result.sharpe) : 0).toFixed(1)}%`} result={result} isNeutral />
                   <StatRow 
                     label="승:패" 
                     value={result.trades > 0 
                       ? `${Math.round((result.trades || 0) * (result.winRate || 0) / 100)} : ${Math.round((result.trades || 0) * (100 - (result.winRate || 0)) / 100)}` 
                       : "0 : 0"} 
                     result={result} 
                     isNeutral 
                   />
               </div>
             </div>
           )}

           {/* Assets View (Symbol Summary) */}
           {activeTab === "assets" && (
             <div className="h-full overflow-y-auto custom-scrollbar">
                <div className="bg-[#111] overflow-hidden">
                   <table className="w-full text-left border-collapse">
                      <thead className="bg-[#161616]">
                         <tr>
                            <th className="p-4 text-sm font-bold text-white">종목</th>
                            <th className="p-4 text-sm font-bold text-white">섹터</th>
                            <th className="p-4 text-sm font-bold text-white text-right">수익금</th>
                            <th className="p-4 text-sm font-bold text-white text-right">수익률</th>
                            <th className="p-4 text-sm font-bold text-white text-right">매매 횟수</th>
                         </tr>
                      </thead>
                       <tbody>
                          {result.symbols ? result.symbols.map(sym => {
                             const stats = result.perAssetStats?.[sym];
                             const meta = stockMetadata[sym];
                             
                             return (
                               <tr key={sym} className="border-b border-gray-800/50 hover:bg-white/5 transition-colors">
                                  <td className="p-4">
                                     <div className="flex flex-col">
                                        <span className="text-sm font-bold text-white">{meta?.name || sym}</span>
                                        <span className="text-xs text-gray-500 font-mono">{sym}</span>
                                     </div>
                                  </td>
                                  <td className="p-4 text-sm text-gray-400">{meta?.sector || "-"}</td>
                                  <td className={`p-4 text-sm font-bold text-right ${(stats?.profit || 0) > 0 ? 'text-main-red' : (stats?.profit || 0) < 0 ? 'text-main-blue' : 'text-white'}`}>
                                     {stats ? formatKRW(stats.profit) : "-"}
                                  </td>
                                  <td className={`p-4 text-sm font-bold text-right ${(stats?.totalReturn || 0) > 0 ? 'text-main-red' : (stats?.totalReturn || 0) < 0 ? 'text-main-blue' : 'text-white'}`}>
                                     {stats ? `${stats.totalReturn.toFixed(2)}%` : "-"}
                                  </td>
                                  <td className="p-4 text-sm text-white text-right font-mono">
                                     {stats ? `${stats.trades}회` : "-"}
                                  </td>
                               </tr>
                             );
                          }) : (
                            <tr className="border-b border-gray-800/50 hover:bg-white/5 transition-colors">
                                <td className="p-4">
                                   <div className="flex flex-col">
                                      <span className="text-sm font-bold text-white">삼성전자</span>
                                      <span className="text-xs text-gray-500 font-mono">{result.symbol}</span>
                                   </div>
                                </td>
                                <td className="p-4 text-sm text-gray-400">전기전자</td>
                                <td className={`p-4 text-sm font-bold text-right ${(result.finalEquity - result.initialCapital) >= 0 ? 'text-white' : 'text-gray-400'}`}>
                                   {formatKRW(result.finalEquity - result.initialCapital)}
                                </td>
                                <td className={`p-4 text-sm font-bold text-right ${(result.finalEquity - result.initialCapital) >= 0 ? 'text-white' : 'text-gray-400'}`}>
                                   {result.totalReturn.toFixed(2)}%
                                </td>
                                <td className="p-4 text-sm text-white text-right font-mono">
                                   {result.trades}회
                                </td>
                             </tr>
                          )}
                       </tbody>
                   </table>
                   <div className="p-6 bg-[#111]">
                      <p className="text-sm text-gray-500 leading-relaxed italic">
                        * 종목별 상세 수익 분석 기능은 준비 중입니다. 현재는 포트폴리오 전체 성과 중심으로 제공됩니다.
                      </p>
                   </div>
                </div>
             </div>
           )}

           {/* Stats View (Heatmap + Detailed Grid) */}
           {activeTab === "stats" && (
             <div className="h-full overflow-y-auto custom-scrollbar p-6 space-y-8">
               
                <div>
                  <h4 className="text-base font-bold text-white mb-4 flex items-center gap-2">
                    <TableCellsIcon className="w-4 h-4 text-gray-500" /> 월별 수익률 상세 (연도/월)
                  </h4>
                  <div className="overflow-x-auto custom-scrollbar rounded-xl overflow-hidden">
                    <table className="w-full border-collapse text-sm">
                      <thead className="bg-[#1a1a1a] text-white font-bold">
                        <tr>
                          <th className="p-2 text-center min-w-[60px] text-sm">연도</th>
                          {Array.from({length: 12}).map((_, i) => (
                            <th key={i} className="p-2 text-center min-w-[50px] text-sm font-mono">{i+1}월</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="bg-[#111]">
                        {availableYears.map(year => (
                          <tr key={year} className="hover:bg-white/5 transition-colors">
                            <td className="p-2 py-3 font-mono text-gray-400 font-bold bg-[#161616] text-center">{year}</td>
                            {Array.from({length: 12}).map((_, i) => {
                              const month = (i + 1).toString();
                              const val = monthlyReturns[year][month];
                              return (
                                <td key={i} className="p-1">
                                  <div className={`w-full py-1.5 flex items-center justify-center text-sm font-black font-mono ${
                                    val > 0 
                                      ? `text-[#ef4444]` 
                                      : val < 0 
                                        ? `text-[#377af4]`
                                        : `text-gray-500`
                                  }`}>
                                    {val !== undefined ? `${val > 0 ? '+' : ''}${val.toFixed(1)}%` : '-'}
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
                 <div className="bg-[#1a1a1a] rounded-xl p-5">
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
                 <div className="bg-[#1a1a1a] rounded-xl p-5">
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
              <div className="h-full overflow-y-auto custom-scrollbar">
                 {result.tradesList?.length > 0 ? (
                    <table className="w-full text-left border-collapse">
                      <thead className="bg-[#161616] sticky top-0 z-10">
                         <tr>
                            <th className="p-3 text-sm font-bold text-white">날짜</th>
                            <th className="p-3 text-sm font-bold text-white">종목</th>
                            <th className="p-3 text-sm font-bold text-white">구분</th>
                            <th className="p-3 text-sm font-bold text-white">체결가</th>
                            <th className="p-3 text-sm font-bold text-white">수량</th>
                            <th className="p-3 text-sm font-bold text-white">매매사유</th>
                            <th className="p-3 text-sm font-bold text-white text-right">거래금액</th>
                         </tr>
                      </thead>
                      <tbody className="bg-[#0f0f0f]">
                          {result.tradesList.map((t, i) => {
                             const tradeAmount = t.amount || 0;
                             
                             return (
                              <tr key={i} className="hover:bg-white/5 transition-colors">
                                 <td className="p-3 text-sm font-mono text-gray-400">{t.date}</td>
                                 <td className="p-3 text-sm font-bold text-white">
                                    <div className="flex flex-col">
                                       <span>{stockMetadata[t.symbol]?.name || t.symbol}</span>
                                       <span className="text-[10px] text-gray-500 font-mono">{t.symbol}</span>
                                    </div>
                                 </td>
                                  <td className="p-3">
                                    <span className={`px-2 py-0.5 rounded text-sm font-bold ${t.type==='buy' ? 'text-[#ef4444]' : 'text-[#377af4]'}`}>
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
                    <div className="h-full flex flex-col items-center justify-center text-gray-600 space-y-2 pb-20">
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

function MetricCard({ label, value, subValue, trend, colorClass }: { label: string, value: string, subValue?: string, trend?: "up"|"down"|"neutral", colorClass?: string }) {
  const dynamicColor = trend === "up" ? "text-main-red" : trend === "down" ? "text-main-blue" : (colorClass || "text-white");
      
  return (
    <div className="bg-[#111] border border-gray-800 p-2 md:p-3 rounded-xl flex flex-col justify-between hover:border-gray-700 transition-colors">
      <div className="text-[10px] md:text-xs font-bold text-gray-500 uppercase tracking-widest mb-0.5">{label}</div>
      <div className={`text-xl md:text-2xl xl:text-3xl font-black ${dynamicColor} tracking-tight`}>{value}</div>
      {subValue && <div className="text-[10px] md:text-[11px] text-gray-600 font-medium mt-0.5 truncate">{subValue}</div>}
    </div>
  );
}

function StatRow({ label, value, result, isNeutral }: { label: string, value: string, result: any, isNeutral?: boolean }) {
  const dynamicColor = isNeutral 
    ? "text-white" 
    : (value.includes("-") ? "text-main-blue" : (parseFloat(value) === 0 ? "text-white" : "text-main-red"));

  return (
    <div className="bg-[#111] rounded-lg px-3 pt-2 pb-0.5 flex flex-col justify-center">
       <div className="text-xs text-gray-400 mb-0.5 font-bold">{label}</div>
       <div className={`text-xl md:text-2xl font-black ${dynamicColor}`}>{value}</div>
    </div>
  );
}

function StatItem({ label, value, sub }: { label: string, value: string, sub?: string }) {
   return (
      <div className="flex justify-between items-center py-1 border-b border-gray-800/50 last:border-none">
         <span className="text-base text-gray-400 font-medium">{label}</span>
         <div className="text-right">
            <div className="text-base font-bold text-white font-mono">{value}</div>
            {sub && <div className="text-xs text-gray-600">{sub}</div>}
         </div>
      </div>
   );
}
