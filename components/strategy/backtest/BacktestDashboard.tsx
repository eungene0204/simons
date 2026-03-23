"use client";

import { BacktestResult, BacktestHistoryItem } from "@/types/strategy";
import BacktestChart from "@/components/strategy/BacktestChart";
import { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";
import { 
  TrendUp, 
  TrendDown, 
  Table, 
  ChartBar, 
  ArrowsClockwise,
  ShieldCheck,
  Warning,
  Info,
  List,
  Check,
  CaretUp,
  CaretDown,
  Clock,
  Trash,
  X
} from "phosphor-react";


import { useState, useEffect, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import XAIModal from "./XAIModal";
import WalkForwardModal, { WalkForwardSettings } from "./WalkForwardModal";
import MonteCarloPanel from "./MonteCarloPanel";
import BacktestSummaryCard from "./BacktestSummaryCard";

const processedExecutionIds = new Set<string>();

interface BacktestDashboardProps {
  result: BacktestResult;
  onRestart: () => void;
  onRun?: (options: BacktestConfigOptions) => void;
  onSave?: () => void;
  onWalkForward?: (settings: WalkForwardSettings) => Promise<any>;
  currentOptions?: BacktestConfigOptions;
  isRunning?: boolean;
  strategySummary?: {
    universeName: string;
    blockNames: string[];
    strategyName: string;
    entryLogic?: string;
    exitLogic?: string;
    entryBlocks?: string[];
    exitBlocks?: string[];
    positionText?: string;
    riskText?: string;
  };
}

const METRIC_DESCRIPTIONS: Record<string, string> = {
  cagr: "연평균수익률(Compound Annual Growth Rate). 전체 수익률을 연간 단위로 환산하여 복리 성장을 나타낸 지표입니다.\n\n[ 가이드라인 ]\n🟢 우수: 20% 이상\n🟡 보통: 10% ~ 20%\n🔴 미흡: 10% 미만",
  mdd: "최대 낙폭(Maximum Drawdown). 특정 기간 동안 발생한 전고점 대비 최대 하락 비율로, 전략의 리스크를 측정합니다.\n\n[ 가이드라인 ]\n🟢 안정: 10% 미만\n🟡 보통: 10% ~ 20%\n🔴 위험: 20% 초과",
  sharpe: "샤프 지수. 위험 1단위당 얻은 초과 수익을 나타내며, 수치가 높을수록 위험 대비 수익 효율이 좋습니다.\n\n[ 가이드라인 ]\n🟢 우수: 1.5 이상\n🟡 보통: 1.0 ~ 1.5\n🔴 미흡: 1.0 미만",
  profitFactor: "손익비. 총 이익을 총 손실로 나눈 값으로, 1원 손실당 기대할 수 있는 수익금을 의미합니다.\n\n[ 가이드라인 ]\n🟢 우수: 2.0 이상\n🟡 보통: 1.5 ~ 2.0\n🔴 미흡: 1.5 미만",
  totalReturn: "백테스트 시작 시점부터 종료 시점까지의 전체 자산 변동 비율입니다.",
  buyHold: "전략을 사용하지 않고 단순히 종목을 매수하여 보유했을 때의 수익률(벤치마크)입니다.\n\n이 수치보다 전략의 수익률(Total Return)이 높아야 전략을 사용하는 의미가 있습니다.",
  volatility: "연간 변동성. 수익률의 표준편차를 연간 단위로 환산한 값으로, 변동폭이 클수록 위험이 높음을 의미합니다.\n\n[ 가이드라인 ]\n🟢 우수: 15% 미만\n🟡 보통: 15% ~ 25%\n🔴 미흡: 25% 초과",
  sortino: "소르티노 지수. 하락 변동성(손실 위험)만을 고려한 위험 대비 수익 효율 지표입니다.\n\n[ 가이드라인 ]\n🟢 우수: 2.0 이상\n🟡 보통: 1.0 ~ 2.0\n🔴 미흡: 1.0 미만",
  kelly: "켈리 공식. 자산 대비 최적의 배팅 비율을 계산하는 모델로, 가산 비중 조절에 참고할 수 있습니다.\n\n[ 가이드라인 ]\n🟢 최적: 10% ~ 20%\n🟡 공격적: 20% 이상 (리스크 증가)\n🔴 보수적: 10% 미만"
};

export default function BacktestDashboard({
  result,
  onRestart,
  onRun,
  onSave,
  onWalkForward,
  currentOptions,
  isRunning,
  strategySummary
}: BacktestDashboardProps) {
  const [activeTab, setActiveTab] = useState<"chart" | "stats" | "log" | "assets" | "history" | "monte-carlo">("chart");
  const [history, setHistory] = useState<BacktestHistoryItem[]>([]);
  const [isWFAOpen, setIsWFAOpen] = useState(false);


  const [localOptions, setLocalOptions] = useState<BacktestConfigOptions | null>(currentOptions || null);
  const [stockMetadata, setStockMetadata] = useState<Record<string, { name: string, sector: string }>>({});
  const [sortConfig, setSortConfig] = useState<{ key: 'profit' | 'totalReturn' | 'trades' | null, direction: 'asc' | 'desc' }>({ key: null, direction: 'desc' });
  const [hoveredMetric, setHoveredMetric] = useState<{ label: string, description: string, rect: DOMRect } | null>(null);
  const [isWarningsOpen, setIsWarningsOpen] = useState(false);
  const [xaiTarget, setXaiTarget] = useState<{ symbol: string; date: string } | null>(null);
  const lastProcessedResultRef = useRef<string | null>(null);
  const isSavingRef = useRef(false);

  // Load history on mount
  useEffect(() => {
    fetch("/api/backtest/history")
      .then(r => r.ok ? r.json() : [])
      .then(data => setHistory(data))
      .catch(() => {});
  }, []);

  // Save history when a new backtest result arrives
  useEffect(() => {
    // isRunning 이 deps에 포함되어야 batching이 안 될 때도 재실행됨
    if (isRunning || !result) return;

    // Idempotency: skip if this execution was already saved
    if (result.executionId && processedExecutionIds.has(result.executionId)) return;
    if (isSavingRef.current) return;

    const saveHistory = async () => {
      isSavingRef.current = true;
      if (result.executionId) {
        processedExecutionIds.add(result.executionId);
      }

      try {
        if (strategySummary) {
          const newItemData = {
            strategyName: strategySummary.strategyName || "이름 없는 전략",
            universe: strategySummary.universeName,
            conditions: {
              entry: {
                logic: strategySummary.entryLogic || "AND",
                names: strategySummary.entryBlocks || []
              },
              exit: {
                logic: strategySummary.exitLogic || "AND",
                names: strategySummary.exitBlocks || []
              },
              position: strategySummary.positionText,
              risk: strategySummary.riskText
            },
            metrics: {
              totalReturn: result.totalReturn || 0,
              cagr: result.cagr || 0,
              mdd: result.maxDrawdown || 0,
              winRate: result.winRate || 0,
              profitFactor: result.profitFactor || 0,
              buyHold: result.buyAndHoldReturn || 0,
              trades: result.trades || 0,
              executionTime: result.executionTime ?? 0,
            },
          };

          const saveResponse = await fetch("/api/backtest/history", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(newItemData),
          });

          if (saveResponse.ok) {
            const savedData = await saveResponse.json();
            setHistory(prev => [savedData, ...prev]);
            lastProcessedResultRef.current = result.executionId;
          }
        }
      } catch (error) {
        console.error("Failed to save backtest history:", error);
      } finally {
        isSavingRef.current = false;
      }
    };

    saveHistory();
  }, [result, isRunning, strategySummary]);

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

  const sortedSymbols = useMemo(() => {
    if (!result.symbols) return [];
    
    // 1. Filter out symbols with 0 trades
    let symbols = result.symbols.filter(sym => {
      const stats = result.perAssetStats?.[sym];
      return stats && stats.trades > 0;
    });

    if (!sortConfig.key) return symbols;

    // 2. Sort remaining symbols
    return symbols.sort((a, b) => {
      const key = sortConfig.key;
      if (!key) return 0;
      
      const statsA = result.perAssetStats?.[a];
      const statsB = result.perAssetStats?.[b];
      
      const valA = statsA ? (statsA[key as keyof typeof statsA] as number || 0) : 0;
      const valB = statsB ? (statsB[key as keyof typeof statsB] as number || 0) : 0;

      if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
      if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [result.symbols, result.perAssetStats, sortConfig]);

  const handleSort = (key: 'profit' | 'totalReturn' | 'trades') => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  const SortIcon = ({ column }: { column: 'profit' | 'totalReturn' | 'trades' }) => {
    const isActive = sortConfig.key === column;
    const Icon = sortConfig.direction === 'asc' ? CaretUp : CaretDown;
    
    return (
      <div className={`w-3 h-3 transition-opacity ${isActive ? 'opacity-100 text-white' : 'opacity-0 group-hover:opacity-40 text-gray-400'}`}>
        <Icon className="w-3 h-3" />
      </div>
    );
  };
  const availableYears = Object.keys(monthlyReturns).sort((a, b) => b.localeCompare(a));

  useEffect(() => {
    if (currentOptions) setLocalOptions(currentOptions);
  }, [currentOptions]);

  const handleDeleteHistoryItem = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm("이 테스트 기록을 삭제하시겠습니까?")) {
      try {
        const response = await fetch(`/api/backtest/history?id=${id}`, {
          method: "DELETE",
        });
        if (response.ok) {
          setHistory(prev => prev.filter(item => item.id !== id));
        }
      } catch (error) {
        console.error("Failed to delete history item:", error);
      }
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 min-w-0 animate-in fade-in zoom-in-95 duration-300 px-6">
      <div className="pt-8 px-2 mb-4 flex flex-col gap-1">
        <h2 className="text-3xl font-black text-white tracking-tight">
          백테스트 결과
        </h2>
        <span className="text-sm font-mono text-gray-500 font-normal mb-2">
          {result.dates[0] && result.dates[result.dates.length-1] && `${result.dates[0]} ~ ${result.dates[result.dates.length-1]}`}
        </span>

        <div className="flex items-center justify-between w-full">
          <div className="flex bg-[#0a0a0a] rounded-lg p-1 w-fit">
            {[
              { id: "chart", label: "차트 분석", icon: ChartBar },
              { id: "assets", label: "종목 분석", icon: List },
              { id: "stats", label: "통계 상세", icon: Table },
              { id: "log", label: "매매 기록", icon: ShieldCheck },
              { id: "history", label: "테스트 기록", icon: Clock },
              { id: "monte-carlo", label: "몬테카를로", icon: ChartBar },
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
          
          <div className="flex items-center gap-2">
            {onWalkForward && (
              <button
                onClick={() => setIsWFAOpen(true)}
                className="px-4 py-1.5 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 text-sm font-bold rounded-lg transition-all border border-purple-500/30 hover:border-purple-500/50 active:scale-95 flex items-center gap-1.5"
              >
                <ChartBar className="w-4 h-4" />
                워크포워드
              </button>
            )}
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
                <Check className="w-4 h-4" />
                전략 저장하기
              </button>
            )}
          </div>
        </div>
      </div>

      {/* AI Summary */}
      <BacktestSummaryCard result={result} strategySummary={strategySummary} />

      {/* Missing Data Warnings */}
      {result.warnings && result.warnings.length > 0 && (
        <div className="mb-6 bg-main-red/5 border border-main-red/20 rounded-2xl overflow-hidden transition-all duration-300">
          <button 
            onClick={() => setIsWarningsOpen(!isWarningsOpen)}
            className="w-full px-5 py-4 flex items-center justify-between hover:bg-main-red/10 transition-colors"
          >
            <div className="flex items-center gap-3 text-main-red font-black text-sm uppercase tracking-tight">
              <Warning className="w-5 h-5" />
              <span>주의: {result.warnings.length}개의 데이터 제한 사항</span>
            </div>
            <motion.div
              animate={{ rotate: isWarningsOpen ? 180 : 0 }}
              transition={{ duration: 0.3, ease: "circOut" }}
            >
              <CaretDown className="w-5 h-5 text-main-red/60" />
            </motion.div>
          </button>

          <AnimatePresence>
            {isWarningsOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.4, ease: [0.23, 1, 0.32, 1] }}
              >
                <div className="px-5 pb-5 pt-1 border-t border-main-red/10">
                  <ul className="space-y-2">
                    {result.warnings.map((w, i) => {
                      let displayWarning = w;
                      const symMatch = w.match(/^([0-9A-Z]{6}):/);
                      if (symMatch) {
                        const sym = symMatch[1];
                        const name = stockMetadata[sym]?.name;
                        if (name) {
                          displayWarning = w.replace(sym, `${name} (${sym})`);
                        }
                      }
                      return (
                        <li key={i} className="flex gap-2 text-xs text-red-100/60 leading-relaxed font-medium">
                          <span className="text-main-red/40 mt-1">•</span>
                          {displayWarning}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* 1. Hero Metrics Header */}
      <div className="flex-none grid grid-cols-2 lg:grid-cols-5 gap-2 px-2 mb-2">
        <MetricCard 
          label="연평균수익률" 
          value={`${result.cagr.toFixed(2)}%`} 
          subValue="CAGR" 
          trend={result.cagr > 0 ? "up" : "down"} 
          description={METRIC_DESCRIPTIONS.cagr}
          onHover={(rect) => setHoveredMetric(rect ? { label: "연평균수익률", description: METRIC_DESCRIPTIONS.cagr, rect } : null)}
        />
        <MetricCard 
          label="최대낙폭" 
          value={`${result.maxDrawdown.toFixed(2)}%`} 
          subValue="MDD" 
          trend="down"
          description={METRIC_DESCRIPTIONS.mdd}
          onHover={(rect) => setHoveredMetric(rect ? { label: "최대낙폭", description: METRIC_DESCRIPTIONS.mdd, rect } : null)}
        />
        <MetricCard 
          label="샤프지수" 
          value={result.sharpe.toFixed(2)} 
          subValue="위험 대비 성과" 
          trend={result.sharpe > 1 ? "up" : "neutral"} 
          description={METRIC_DESCRIPTIONS.sharpe}
          onHover={(rect) => setHoveredMetric(rect ? { label: "샤프지수", description: METRIC_DESCRIPTIONS.sharpe, rect } : null)}
        />

        <MetricCard 
          label="손익비" 
          value={result.profitFactor.toFixed(2)} 
          subValue="Profit Factor" 
          trend={result.profitFactor > 1.5 ? "up" : "neutral"} 
          description={METRIC_DESCRIPTIONS.profitFactor}
          onHover={(rect) => setHoveredMetric(rect ? { label: "손익비", description: METRIC_DESCRIPTIONS.profitFactor, rect } : null)}
        />
      </div>

      {/* 2. Main Content Area - Exact Mirror of Step 2 Pattern */}
      <div className="flex flex-col bg-[#111] rounded-2xl overflow-hidden mb-2 min-h-0 min-w-0">

        {/* Tab Content */}
        <div className="flex flex-col min-h-0 min-w-0 p-0 relative">
           
           {/* Chart View */}
            {activeTab === "chart" && (
              <div className="flex flex-col px-2 pt-2 pb-3 space-y-2 min-h-0">
                <div className="h-[280px] md:h-[380px] xl:h-[450px] bg-[#0a0a0f] rounded-xl overflow-hidden relative">
                  <BacktestChart 
                    type="equity" 
                    trades={result.tradesList}
                    equityData={result.dates.map((d: string, i: number) => ({ 
                      time: d, 
                      equity: result.equity[i], 
                      buyHold: result.benchmarkEquity ? result.benchmarkEquity[i] : (result.initialCapital * (1 + (result.buyAndHoldReturn || 0)/100))
                    }))} 
                  />
               </div>
               
               {/* Quick Stats Summary below chart */}
               <div className="grid grid-cols-2 md:grid-cols-5 gap-2 md:gap-4">
                  <StatRow 
                    label="총 수익" 
                    value={formatKRW(result.finalEquity - result.initialCapital)} 
                    result={result} 
                  />
                  <StatRow 
                    label="총수익률" 
                    value={`${(result.totalReturn || 0).toFixed(1)}%`} 
                    result={result} 
                    description={METRIC_DESCRIPTIONS.totalReturn}
                    onHover={(rect) => setHoveredMetric(rect ? { label: "총수익률", description: METRIC_DESCRIPTIONS.totalReturn, rect } : null)}
                  />
                   <StatRow 
                     label="매수후보유" 
                     value={`${(result.buyAndHoldReturn || 0).toFixed(1)}%`} 
                     result={result} 
                     colorOverride="text-main-green" 
                     description={METRIC_DESCRIPTIONS.buyHold}
                     onHover={(rect) => setHoveredMetric(rect ? { label: "매수후보유", description: METRIC_DESCRIPTIONS.buyHold, rect } : null)}
                   />
                   <StatRow 
                     label="연간 변동성" 
                     value={`${(result.sharpe > 0 ? ((result.cagr || 0) / result.sharpe) : 0).toFixed(1)}%`} 
                     result={result} 
                     isNeutral 
                     description={METRIC_DESCRIPTIONS.volatility}
                     onHover={(rect) => setHoveredMetric(rect ? { label: "연간 변동성", description: METRIC_DESCRIPTIONS.volatility, rect } : null)}
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
                             <th className="p-4 text-sm font-bold text-white text-right">
                                <div 
                                  className="inline-flex items-center justify-end gap-1 cursor-pointer transition-colors group"
                                  onClick={() => handleSort('profit')}
                                >
                                   수익금 <SortIcon column="profit" />
                                </div>
                             </th>
                             <th className="p-4 text-sm font-bold text-white text-right">
                                <div 
                                  className="inline-flex items-center justify-end gap-1 cursor-pointer transition-colors group"
                                  onClick={() => handleSort('totalReturn')}
                                >
                                   수익률 <SortIcon column="totalReturn" />
                                </div>
                             </th>
                             <th className="p-4 text-sm font-bold text-white text-right">
                                <div 
                                  className="inline-flex items-center justify-end gap-1 cursor-pointer transition-colors group"
                                  onClick={() => handleSort('trades')}
                                >
                                   매매 횟수 <SortIcon column="trades" />
                                </div>
                             </th>
                         </tr>
                      </thead>
                       <tbody>
                          {sortedSymbols.length > 0 ? sortedSymbols.map(sym => {
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
                             <tr>
                                <td colSpan={5} className="p-12 text-center text-gray-500">
                                   <div className="flex flex-col items-center gap-2">
                                      <List className="w-8 h-8 opacity-20" />
                                      <span className="text-sm font-medium">매매 결과가 있는 종목이 부재합니다.</span>
                                   </div>
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
                     <ChartBar className="w-4 h-4 text-gray-500" /> 월별 수익률 추이 (Monthly Returns)
                     {(() => {
                       const allYears = Object.keys(monthlyReturns).sort();
                       if (allYears.length > 0) return (
                         <span className="text-xs text-gray-500 font-normal ml-1">
                           {allYears[0]} ~ {allYears[allYears.length - 1]}
                         </span>
                       );
                     })()}
                   </h4>
                   <div className="h-[350px] md:h-[500px] xl:h-[600px] bg-[#0a0a0f] rounded-xl overflow-hidden relative border border-gray-800/50">
                      <BacktestChart
                        type="seasonal_returns"
                        seasonalData={(() => {
                           // 최대 10년만 표시 (최근 연도 기준)
                           const MAX_YEARS = 10;
                           const years = Object.keys(monthlyReturns).sort().slice(-MAX_YEARS);
                           return years.map(year => ({
                              year,
                              data: Object.keys(monthlyReturns[year]).sort((a,b) => Number(a)-Number(b)).map(month => ({
                                 time: `${year}-${month.padStart(2, '0')}-01`,
                                 value: monthlyReturns[year][month]
                              }))
                           }));
                        })()}
                      />
                   </div>
                 </div>

               <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                 {/* Risk Stats */}
                 <div className="bg-[#1a1a1a] rounded-xl p-5">
                     <h5 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-4">리스크 및 성과 분석</h5>
                     <div className="space-y-3">
                        <StatItem label="초기 자본" value={formatKRW(result.initialCapital)} />
                        <StatItem label="최종 자산" value={formatKRW(result.finalEquity)} />
                        <StatItem 
                          label="소르티노 지수" 
                          value={result.sortino.toFixed(2)} 
                          description={METRIC_DESCRIPTIONS.sortino}
                          onHover={(rect) => setHoveredMetric(rect ? { label: "소르티노 지수", description: METRIC_DESCRIPTIONS.sortino, rect } : null)}
                        />
                        <StatItem 
                          label="켈리 공식" 
                          value={result.kelly.toFixed(2)} 
                          description={METRIC_DESCRIPTIONS.kelly}
                          onHover={(rect) => setHoveredMetric(rect ? { label: "켈리 공식", description: METRIC_DESCRIPTIONS.kelly, rect } : null)}
                        />
                    </div>
                 </div>
                 
                  {/* Trade Stats */}
                 <div className="bg-[#1a1a1a] rounded-xl p-5">
                    <h5 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-4">매매 통계</h5>
                    <div className="space-y-3">
                       <StatItem label="총 매매 횟수" value={result.trades.toString()} />
                       <StatItem label="평균 수익" value={formatKRW(result.avgProfit || 0)} />
                       <StatItem label="평균 손실" value={formatKRW(result.avgLoss || 0)} />
                       <StatItem label="최대 연속 수익" value={`${result.maxConsecutiveWins || 0}회`} />
                       <StatItem label="최대 연속 손실" value={`${result.maxConsecutiveLosses || 0}회`} />
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
                             <th className="p-3 text-sm font-bold text-white text-center">AI 분석</th>
                             <th className="p-3 text-sm font-bold text-white">매매사유</th>
                             <th className="p-3 text-sm font-bold text-white text-right">거래금액</th>
                         </tr>
                      </thead>
                      <tbody className="bg-[#0f0f0f]">
                          {result.tradesList.map((t, i) => {
                             const tradeAmount = t.amount || 0;
                             return (
                              <tr key={`${t.symbol}-${t.date}-${t.type}-${i}`} className="hover:bg-white/5 transition-colors">
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
                                  <td className="p-3 text-center">
                                     <button 
                                       onClick={() => setXaiTarget({ symbol: t.symbol, date: t.date })}
                                       className="px-2 py-1 bg-main-blue/10 hover:bg-main-blue/20 text-main-blue text-[10px] font-black rounded border border-main-blue/20 transition-all"
                                     >
                                       분석
                                     </button>
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
                       <ShieldCheck className="w-12 h-12 text-gray-800" />
                       <p className="text-lg font-bold">기록이 없습니다</p>
                       <p className="text-sm">백테스트 기간 동안 매매 조건이 충족되지 않았습니다.</p>
                    </div>
                 )}
              </div>
           )}

            {/* Monte Carlo View */}
            {activeTab === "monte-carlo" && (
              <MonteCarloPanel
                equity={result.equity}
                dates={result.dates}
                initialCapital={result.initialCapital}
              />
            )}

            {/* History View */}
            {activeTab === "history" && (
              <div className="h-full overflow-y-auto custom-scrollbar p-6">
                 <div className="flex items-center justify-between mb-6">
                    <h4 className="text-xl font-black text-white flex items-center gap-2">
                       <Clock className="w-6 h-6 text-main-blue" />
                       테스트 기록 (최근 50개)
                    </h4>
                    <button 
                      onClick={async () => {
                        if (confirm("모든 테스트 기록을 삭제하시겠습니까?")) {
                          try {
                            const response = await fetch("/api/backtest/history", {
                              method: "DELETE",
                            });
                            if (response.ok) {
                              setHistory([]);
                            }
                          } catch (error) {
                            console.error("Failed to clear history:", error);
                          }
                        }
                      }}
                      className="flex items-center gap-2 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-500 text-xs font-bold rounded-lg border border-red-500/20 transition-all"
                    >
                       <Trash className="w-4 h-4" />
                       기록 전체 삭제
                    </button>
                 </div>

                 {history.length > 0 ? (
                   <div className="space-y-4">
                      {history.map((item) => (
                        <div key={item.id} className="bg-[#161616] border border-white/5 rounded-2xl p-5 hover:border-white/10 transition-all group">
                           <div className="flex items-start justify-between mb-4">
                              <div>
                                 <div className="flex items-center gap-3 mb-1.5">
                                    <span className="text-base font-black text-white">{item.strategyName}</span>
                                    <span className="px-2.5 py-1 bg-main-blue/10 text-main-blue text-xs font-black rounded uppercase tracking-wider border border-main-blue/20">
                                       {item.universe}
                                    </span>
                                 </div>
                                  <div className="flex flex-wrap items-center gap-y-2 gap-x-4">
                                     {/* 1. Entry Blocks Rendering (Red Theme) */}
                                     {(() => {
                                         const conds = item.conditions as any;
                                         const entry = conds?.entry || (Array.isArray(item.conditions) ? { logic: "AND", names: item.conditions } : { logic: conds.logic || "AND", names: conds.names || [] });
                                         const isEntryAnd = String(entry.logic).trim().toUpperCase() === "AND";
                                         const names = entry.names || [];
                                         if (names.length === 0) return null;

                                         return (
                                           <div className="flex items-center">
                                             {names.map((name: string, idx: number) => (
                                               <div key={`entry-${idx}`} className="flex items-center">
                                                  {/* PHYSICAL LINE: ONLY DRAW IF 'AND' AND NOT FIRST */}
                                                  {idx > 0 && isEntryAnd && <div className="w-5 h-[1.5px] bg-red-500/40" />}
                                                  {/* GAP: ONLY IF 'OR' AND NOT FIRST */}
                                                  {idx > 0 && !isEntryAnd && <div className="w-4" />}
                                                  
                                                  <span className={`px-2.5 py-1 ${!isEntryAnd ? 'bg-red-500/5 text-red-400/80 border-red-500/20' : 'bg-red-500/10 text-red-500 border-red-500/10'} text-[10px] font-bold rounded-md border whitespace-nowrap`}>
                                                    {name}
                                                  </span>
                                               </div>
                                             ))}
                                           </div>
                                         );
                                     })()}

                                     {/* Divider if both exist (Simple Spacer) */}
                                     {((item.conditions as any).entry?.names?.length > 0 && (item.conditions as any).exit?.names?.length > 0) && (
                                       <div className="w-6" /> 
                                     )}

                                     {/* 2. Exit Blocks Rendering (Blue Theme) */}
                                     {(() => {
                                         const conds = item.conditions as any;
                                         if (!conds?.exit || (conds.exit.names || []).length === 0) return null;
                                         const exit = conds.exit;
                                         const isExitAnd = String(exit.logic).trim().toUpperCase() === "AND";
                                         const names = exit.names || [];

                                         return (
                                           <div className="flex items-center">
                                             {names.map((name: string, idx: number) => (
                                               <div key={`exit-${idx}`} className="flex items-center">
                                                  {/* PHYSICAL LINE: ONLY DRAW IF 'AND' AND NOT FIRST */}
                                                  {idx > 0 && isExitAnd && <div className="w-5 h-[1.5px] bg-blue-500/40" />}
                                                  {/* GAP: ONLY IF 'OR' AND NOT FIRST */}
                                                  {idx > 0 && !isExitAnd && <div className="w-4" />}

                                                  <span className={`px-2.5 py-1 ${!isExitAnd ? 'bg-blue-500/5 text-blue-400/80 border-blue-500/20' : 'bg-blue-500/10 text-blue-500 border-blue-500/10'} text-[10px] font-bold rounded-md border whitespace-nowrap`}>
                                                    {name}
                                                  </span>
                                               </div>
                                             ))}
                                           </div>
                                         );
                                     })()}

                                     {/* 3. Position and Risk Settings */}
                                     {(() => {
                                         const conds = item.conditions as any;
                                         if (!conds?.position && !conds?.risk) return null;
                                         return (
                                           <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 mt-1 sm:mt-0">
                                              {conds.position && (
                                                <div className="flex items-center gap-1.5 bg-gray-800/30 px-2 py-1 rounded text-[10px] border border-gray-700/50">
                                                   <span className="text-gray-500 font-bold">포지션/비중</span>
                                                   <span className="text-gray-300">{conds.position}</span>
                                                </div>
                                              )}
                                              {conds.risk && (
                                                <div className="flex items-center gap-1.5 bg-gray-800/30 px-2 py-1 rounded text-[10px] border border-gray-700/50">
                                                   <span className="text-gray-500 font-bold">리스크 관리</span>
                                                   <span className="text-gray-300">{conds.risk}</span>
                                                </div>
                                              )}
                                           </div>
                                         )
                                     })()}
                                  </div>
                              </div>
                              <div className="flex flex-col items-end gap-2">
                                 <button
                                    onClick={(e) => handleDeleteHistoryItem(item.id, e)}
                                    className="p-1.5 text-gray-600 hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                                    title="기록 삭제"
                                 >
                                    <X className="w-4 h-4" />
                                 </button>
                                 <div className="text-xs text-gray-500 font-mono">
                                    {new Date(item.timestamp).toLocaleString()}
                                 </div>
                              </div>
                           </div>
                           
                           <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
                              <HistoryMetric label="총 수익률" value={`${item.metrics.totalReturn.toFixed(1)}%`} trend={item.metrics.totalReturn > 0 ? "up" : "down"} />
                              <HistoryMetric label="CAGR" value={`${item.metrics.cagr.toFixed(1)}%`} trend={item.metrics.cagr > 0 ? "up" : "down"} />
                              <HistoryMetric label="MDD" value={`${item.metrics.mdd.toFixed(1)}%`} trend="down" />
                              <HistoryMetric label="손익비" value={item.metrics.profitFactor.toFixed(2)} />
                              <HistoryMetric label="매수후보유" value={`${item.metrics.buyHold.toFixed(1)}%`} colorOverride="text-main-green" />
                              <HistoryMetric label="매매횟수" value={`${item.metrics.trades}회`} />
                              <HistoryMetric label="소요시간" value={item.metrics.executionTime !== undefined ? `${item.metrics.executionTime.toFixed(2)}초` : "-"} />
                           </div>
                        </div>
                      ))}
                   </div>
                 ) : (
                   <div className="h-[300px] flex flex-col items-center justify-center text-gray-600 space-y-3">
                      <div className="p-4 bg-white/5 rounded-full border border-white/5">
                        <Clock className="w-10 h-10 opacity-20" />
                      </div>
                      <p className="text-base font-bold">기록된 테스트가 없습니다</p>
                      <p className="text-sm text-gray-500">백테스트를 실행하면 이곳에 자동으로 기록됩니다.</p>
                   </div>
                 )}
              </div>
            )}
        </div>
      </div>

      {hoveredMetric && (
        <div 
          className="fixed z-[1000] pointer-events-none" 
          style={(() => {
            const rect = hoveredMetric.rect;
            const tooltipWidth = 256; // w-64 is 256px
            let left = rect.left + rect.width / 2;
            const padding = 16;

            if (typeof window !== 'undefined') {
              if (left - tooltipWidth / 2 < padding) {
                left = tooltipWidth / 2 + padding;
              } else if (left + tooltipWidth / 2 > window.innerWidth - padding) {
                left = window.innerWidth - tooltipWidth / 2 - padding;
              }
            }

            return { 
              left: `${left}px`, 
              top: `${rect.top - 8}px`,
              transform: 'translate(-50%, -100%)'
            };
          })()}
        >
          <div className="w-64 p-4 bg-[#161616] rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 slide-in-from-bottom-2 duration-200 backdrop-blur-2xl border border-white/10">
            <div className="text-[10px] text-main-blue font-bold uppercase tracking-widest mb-1.5 opacity-80">{hoveredMetric.label}</div>
            <p className="text-xs text-white/75 font-bold leading-relaxed whitespace-pre-wrap">{hoveredMetric.description}</p>
          </div>
        </div>
      )}

      <XAIModal
        isOpen={!!xaiTarget}
        onClose={() => setXaiTarget(null)}
        symbol={xaiTarget?.symbol || ""}
        date={xaiTarget?.date || ""}
      />

      {onWalkForward && (
        <WalkForwardModal
          open={isWFAOpen}
          onOpenChange={setIsWFAOpen}
          onRun={onWalkForward}
        />
      )}
    </div>
  );
}

// Sub-components for Cleaner Code

function MetricCard({ 
  label, 
  value, 
  subValue, 
  trend, 
  colorClass,
  description,
  onHover
}: { 
  label: string, 
  value: string, 
  subValue?: string, 
  trend?: "up"|"down"|"neutral", 
  colorClass?: string,
  description?: string,
  onHover?: (rect: DOMRect | null) => void
}) {
  const dynamicColor = trend === "up" ? "text-main-red" : trend === "down" ? "text-main-blue" : (colorClass || "text-white");
      
  return (
    <div className="bg-[#111] border border-gray-800 p-2 md:p-3 rounded-xl flex flex-col justify-between hover:border-gray-700 transition-colors">
      <div className="flex items-center justify-between mb-0.5">
        <div className="text-[10px] md:text-xs font-bold text-gray-500 uppercase tracking-widest">{label}</div>
        {description && onHover && (
           <Info 
             className="w-3.5 h-3.5 text-gray-600 hover:text-gray-400 cursor-help transition-colors"
             onMouseEnter={(e) => onHover(e.currentTarget.getBoundingClientRect())}
             onMouseLeave={() => onHover(null)}
           />
        )}
      </div>
      <div className={`text-xl md:text-2xl xl:text-3xl font-black ${dynamicColor} tracking-tight`}>{value}</div>
      {subValue && <div className="text-[10px] md:text-[11px] text-gray-600 font-medium mt-0.5 truncate">{subValue}</div>}
    </div>
  );
}

function StatRow({ 
  label, 
  value, 
  result, 
  isNeutral, 
  colorOverride,
  description,
  onHover
}: { 
  label: string, 
  value: string, 
  result: any, 
  isNeutral?: boolean, 
  colorOverride?: string,
  description?: string,
  onHover?: (rect: DOMRect | null) => void
}) {
  const dynamicColor = colorOverride 
    ? colorOverride
    : (isNeutral 
        ? "text-white" 
        : (value.includes("-") ? "text-main-blue" : (parseFloat(value) === 0 ? "text-white" : "text-main-red")));

  return (
    <div className="bg-[#111] rounded-lg px-3 pt-2 pb-0.5 flex flex-col justify-center">
       <div className="flex items-center justify-between mb-0.5">
          <div className="text-xs text-gray-400 font-bold">{label}</div>
          {description && onHover && (
             <Info 
               className="w-3 h-3 text-gray-700 hover:text-gray-500 cursor-help transition-colors"
               onMouseEnter={(e) => onHover(e.currentTarget.getBoundingClientRect())}
               onMouseLeave={() => onHover(null)}
             />
          )}
       </div>
       <div className={`text-xl md:text-2xl font-black ${dynamicColor}`}>{value}</div>
    </div>
  );
}

function StatItem({ 
  label, 
  value, 
  sub,
  description,
  onHover
}: { 
  label: string, 
  value: string, 
  sub?: string,
  description?: string,
  onHover?: (rect: DOMRect | null) => void
}) {
   return (
      <div className="flex justify-between items-center py-1">
         <div className="flex items-center gap-1.5">
            <span className="text-base text-gray-400 font-medium">{label}</span>
            {description && onHover && (
               <Info 
                 className="w-4 h-4 text-gray-700 hover:text-gray-500 cursor-help transition-colors"
                 onMouseEnter={(e) => onHover(e.currentTarget.getBoundingClientRect())}
                 onMouseLeave={() => onHover(null)}
               />
            )}
         </div>
         <div className="text-right">
            <div className="text-base font-bold text-white font-mono">{value}</div>
            {sub && <div className="text-xs text-gray-600">{sub}</div>}
         </div>
      </div>
   );
}

function HistoryMetric({ 
  label, 
  value, 
  trend, 
  colorOverride 
}: { 
  label: string, 
  value: string, 
  trend?: "up" | "down", 
  colorOverride?: string 
}) {
  const dynamicColor = colorOverride 
    ? colorOverride 
    : (trend === "up" ? "text-main-red" : trend === "down" ? "text-main-blue" : "text-white");

  return (
    <div className="flex flex-col">
       <span className="text-xs text-gray-500 font-bold uppercase tracking-wider mb-1">{label}</span>
       <span className={`text-base font-black ${dynamicColor}`}>{value}</span>
    </div>
  );
}
