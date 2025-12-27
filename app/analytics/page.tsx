"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  XMarkIcon,
  ChartBarIcon,
  PlusIcon,
  TrashIcon,
  ArrowRightIcon,
  ArrowLeftIcon,
  ChevronDownIcon,
  InformationCircleIcon,
  BoltIcon,
  ArrowTrendingUpIcon,
  ArrowPathIcon,
  CpuChipIcon,
  SparklesIcon,
  MagnifyingGlassIcon,
} from "@heroicons/react/24/outline";
import StrategyComposer from "@/components/strategy/StrategyComposer";
import StrategyComposerV2 from "@/components/strategy/StrategyComposerV2";
import StrategyFusionModal from "@/components/strategy/StrategyFusionModal";
import { StrategyDSL } from "@/types/strategy";
import { getBasePrice, generateCandleData } from "@/lib/mock-stock-data";
import BacktestChart, {
  EquityDataPoint,
  DrawdownDataPoint,
} from "@/components/strategy/BacktestChart";
import {
  strategyGroups,
  getStrategyById,
  StrategyGroupId,
} from "@/lib/strategy-groups";
import { executeStrategy } from "@/lib/strategy-executor";

const formatPrice = (price: number) => {
  return new Intl.NumberFormat("ko-KR").format(price);
};

export default function AnalyticsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const symbol = searchParams.get("symbol") || "";
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);
  const [strategy, setStrategy] = useState<StrategyDSL | null>(null);
  const [savedStrategies, setSavedStrategies] = useState<StrategyDSL[]>([]);
  const [showComposer, setShowComposer] = useState(false);

  // Backtesting state
  const [selectedGroupId, setSelectedGroupId] =
    useState<StrategyGroupId | null>("trend_following");
  const [selectedStrategyIds, setSelectedStrategyIds] = useState<string[]>([
    "sma_crossover",
  ]);
  const [backtestParamsByStrategy, setBacktestParamsByStrategy] = useState<
    Record<string, Record<string, number>>
  >({});
  const [strategyPriorities, setStrategyPriorities] = useState<
    Record<string, number>
  >({});
  const [strategyDiagnostics, setStrategyDiagnostics] = useState<{
    conflicts: string[];
    deduped: number;
  }>({ conflicts: [], deduped: 0 });
  const [expandedGroups, setExpandedGroups] = useState<Set<StrategyGroupId>>(
    new Set<StrategyGroupId>(["trend_following"])
  );
  const [backtestResults, setBacktestResults] = useState<any>(null);
  const [backtestStatus, setBacktestStatus] = useState<
    "idle" | "running" | "completed" | "error"
  >("idle");
  const [backtestProgress, setBacktestProgress] = useState<{
    step: number;
    stepName: string;
    progress: number;
    details?: string;
  }>({
    step: 0,
    stepName: "",
    progress: 0,
  });
  const [executionLogs, setExecutionLogs] = useState<string[]>([]);
  const [backtestPeriod, setBacktestPeriod] = useState<
    "1Y" | "3Y" | "5Y" | "Max"
  >("1Y");
  const [resultTab, setResultTab] = useState<"summary" | "chart" | "report">(
    "summary"
  );
  const [chartType, setChartType] = useState<
    "equity" | "drawdown" | "heatmap" | "distribution"
  >("equity");
  const [savedScenarios, setSavedScenarios] = useState<any[]>([]);
  const [showCompare, setShowCompare] = useState(false);
  const [activeTab, setActiveTab] = useState<"strategies" | "backtest">(
    "strategies"
  );
  const [showFusionModal, setShowFusionModal] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedForFusion, setSelectedForFusion] = useState<Set<string>>(new Set());
  const [useV2Composer, setUseV2Composer] = useState(true); // Toggle for new UI

  // Load saved strategies from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("savedStrategies");
    if (saved) {
      try {
        setSavedStrategies(JSON.parse(saved));
      } catch (e) {
        console.error("Failed to load saved strategies", e);
      }
    }
  }, []);

  // Save strategy
  const handleSaveStrategy = (strategyData: StrategyDSL) => {
    const updated = [...savedStrategies, strategyData];
    setSavedStrategies(updated);
    localStorage.setItem("savedStrategies", JSON.stringify(updated));
    setStrategy(strategyData);
    setShowComposer(false);
    setCurrentStep(1);
  };

  // Load strategy
  const handleLoadStrategy = (strategyId: string) => {
    const loaded = savedStrategies.find((s) => s.id === strategyId);
    if (loaded) {
      setStrategy(loaded);
      setShowComposer(false);
    }
  };

  // Delete strategy
  const handleDeleteStrategy = (strategyId: string) => {
    const updated = savedStrategies.filter((s) => s.id !== strategyId);
    setSavedStrategies(updated);
    localStorage.setItem("savedStrategies", JSON.stringify(updated));
    setSelectedStrategyIds((prev) => prev.filter((id) => id !== strategyId));
  };

  const openComposer = () => {
    console.log("openComposer called");
    setActiveTab("strategies");
    setShowComposer(true);
    setCurrentStep(1);
    setStrategy(null);
    setSelectedStrategyIds([]);
    setSelectionMode(false); // Reset selection mode
    // Ensure V2 is used
    setUseV2Composer(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Initialize params when strategy changes
  useEffect(() => {
    // Ensure priorities are contiguous and cover all selected strategies
    setStrategyPriorities(() => {
      const next: Record<string, number> = {};
      selectedStrategyIds.forEach((id, idx) => {
        next[id] = idx + 1;
      });
      return next;
    });

    // Seed default params per selected strategy
    setBacktestParamsByStrategy((prev) => {
      const next = { ...prev };
      selectedStrategyIds.forEach((id) => {
        if (!next[id]) {
          const strategyDef = getStrategyById(id);
          const defaults: Record<string, number> = {};
          strategyDef?.params.forEach((param) => {
            defaults[param.key] = param.default;
          });
          next[id] = defaults;
        }
      });

      // Drop params for unselected strategies
      Object.keys(next).forEach((id) => {
        if (!selectedStrategyIds.includes(id)) {
          delete next[id];
        }
      });

      return next;
    });
  }, [selectedStrategyIds]);

  // Get current strategy
  const selectedStrategiesDef = selectedStrategyIds
    .map((id) => getStrategyById(id))
    .filter(
      (
        s
      ): s is NonNullable<
        ReturnType<typeof getStrategyById>
      > => Boolean(s)
    );

  // Toggle group expansion
  const toggleGroup = (groupId: StrategyGroupId) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
  };

  const toggleStrategySelection = (
    strategyId: string,
    groupId: StrategyGroupId
  ) => {
    setSelectedGroupId(groupId);
    setStrategyDiagnostics({ conflicts: [], deduped: 0 });
    setBacktestStatus("idle");
    setBacktestResults(null);
    setSelectedStrategyIds((prev) =>
      prev.includes(strategyId)
        ? prev.filter((id) => id !== strategyId)
        : [...prev, strategyId]
    );
  };

  const adjustPriority = (strategyId: string, direction: "up" | "down") => {
    setStrategyDiagnostics({ conflicts: [], deduped: 0 });
    setBacktestStatus("idle");
    setBacktestResults(null);
    setSelectedStrategyIds((prev) => {
      const idx = prev.indexOf(strategyId);
      if (idx === -1) return prev;
      if (direction === "up" && idx === 0) return prev;
      if (direction === "down" && idx === prev.length - 1) return prev;
      const next = [...prev];
      const swapIdx = direction === "up" ? idx - 1 : idx + 1;
      [next[idx], next[swapIdx]] = [next[swapIdx], next[idx]];
      return next;
    });
  };

  // Calculate moving average
  const calculateMA = (prices: number[], period: number): number[] => {
    const ma: number[] = [];
    for (let i = 0; i < prices.length; i++) {
      if (i < period - 1) {
        ma.push(NaN);
      } else {
        const sum = prices
          .slice(i - period + 1, i + 1)
          .reduce((a, b) => a + b, 0);
        ma.push(sum / period);
      }
    }
    return ma;
  };

  // Calculate RSI
  const calculateRSI = (prices: number[], period: number): number[] => {
    const rsi: number[] = [];
    const gains: number[] = [];
    const losses: number[] = [];

    for (let i = 1; i < prices.length; i++) {
      const change = prices[i] - prices[i - 1];
      gains.push(change > 0 ? change : 0);
      losses.push(change < 0 ? -change : 0);
    }

    for (let i = 0; i < prices.length; i++) {
      if (i < period) {
        rsi.push(NaN);
      } else {
        const avgGain =
          gains.slice(i - period, i).reduce((a, b) => a + b, 0) / period;
        const avgLoss =
          losses.slice(i - period, i).reduce((a, b) => a + b, 0) / period;
        if (avgLoss === 0) {
          rsi.push(100);
        } else {
          const rs = avgGain / avgLoss;
          rsi.push(100 - 100 / (1 + rs));
        }
      }
    }
    return rsi;
  };

  // Save scenario
  const saveScenario = () => {
    if (!backtestResults) return;
    const scenario = {
      id: Date.now().toString(),
      strategies: [...selectedStrategyIds],
      paramsByStrategy: { ...backtestParamsByStrategy },
      priorities: { ...strategyPriorities },
      results: { ...backtestResults },
      timestamp: new Date().toISOString(),
      symbol,
      period: backtestPeriod,
    };
    setSavedScenarios([...savedScenarios, scenario]);
    alert("시나리오가 저장되었습니다.");
  };

  // Load scenario
  const loadScenario = (scenario: any) => {
    if (scenario.strategies?.length) {
      const ordered =
        scenario.priorities && Object.keys(scenario.priorities).length > 0
          ? [...scenario.strategies].sort(
              (a, b) =>
                (scenario.priorities?.[a] ?? 999) -
                (scenario.priorities?.[b] ?? 999)
            )
          : scenario.strategies;
      setSelectedStrategyIds(ordered);
    }
    if (scenario.paramsByStrategy) {
      setBacktestParamsByStrategy(scenario.paramsByStrategy);
    }
    if (scenario.priorities) {
      setStrategyPriorities(scenario.priorities);
    }
    if (scenario.results?.strategyDiagnostics) {
      setStrategyDiagnostics({
        conflicts: scenario.results.strategyDiagnostics.conflicts ?? [],
        deduped: scenario.results.strategyDiagnostics.deduped ?? 0,
      });
    } else {
      setStrategyDiagnostics({ conflicts: [], deduped: 0 });
    }
    setBacktestResults(scenario.results);
    setBacktestPeriod(scenario.period);
    setBacktestStatus("completed");
  };

  // Run backtest with step-by-step progress
  const runBacktest = async () => {
    if (!symbol) {
      alert("종목을 선택해주세요.");
      return;
    }
    if (selectedStrategiesDef.length === 0) {
      alert("최소 한 개 이상의 전략을 선택해주세요.");
      return;
    }

    setBacktestStatus("running");
    setBacktestResults(null);
    setStrategyDiagnostics({ conflicts: [], deduped: 0 });
    setExecutionLogs([]);

    const simulationDays =
      backtestPeriod === "1Y"
        ? 365
        : backtestPeriod === "3Y"
        ? 1095
        : backtestPeriod === "5Y"
        ? 1825
        : 3650;

    // Step 1: Initialization and Validation
    setBacktestProgress({
      step: 1,
      stepName: "초기화 및 검증",
      progress: 10,
      details: "종목 정보 확인 중...",
    });
    setExecutionLogs((prev) => [...prev, "[정보] 백테스트 초기화 중..."]);
    await new Promise((resolve) => setTimeout(resolve, 200));

    // Step 2: Data Preparation
    setBacktestProgress({
      step: 2,
      stepName: "데이터 준비",
      progress: 25,
      details: "과거 데이터 생성 중...",
    });
    setExecutionLogs((prev) => [...prev, "[정보] 과거 데이터 로딩 중..."]);
    const basePrice = getBasePrice(symbol);
    const historicalData = generateCandleData(symbol, basePrice, simulationDays);
    const prices = historicalData.map((d) => d.close);
    const dates = historicalData.map((d) => d.date);
    setExecutionLogs((prev) => [
      ...prev,
      `[완료] ${dates.length}일 데이터 로드 완료`,
    ]);
    await new Promise((resolve) => setTimeout(resolve, 300));

    // Step 3: Strategy Calculation
    setBacktestProgress({
      step: 3,
      stepName: "전략 지표 계산",
      progress: 40,
      details: selectedStrategiesDef
        .map((s) => s.name)
        .join(", ")
        .concat(" 계산 중..."),
    });
    setExecutionLogs((prev) => [
      ...prev,
      `[정보] ${selectedStrategiesDef.length}개 전략 지표 계산 중...`,
    ]);

    // Execute strategies and merge based on priority/duplicates/conflicts
    const strategyResults = selectedStrategiesDef.map((strategyDef) => {
      const params = backtestParamsByStrategy[strategyDef.id] || {};
      const result = executeStrategy(
        strategyDef,
        params,
        symbol,
        simulationDays,
        historicalData
      );
      return { strategyDef, params, result };
    });

    const prioritySorted = [...strategyResults].sort(
      (a, b) =>
        (strategyPriorities[a.strategyDef.id] ?? 999) -
        (strategyPriorities[b.strategyDef.id] ?? 999)
    );

    const tradeMap = new Map<
      string,
      { date: string; type: "buy" | "sell"; price: number; source: string }
    >();
    const conflicts: string[] = [];
    let deduped = 0;

    prioritySorted.forEach(({ strategyDef, result }) => {
      result.trades.forEach((trade) => {
        const key = `${trade.date}-${trade.type}`;
        const oppositeKey = `${trade.date}-${
          trade.type === "buy" ? "sell" : "buy"
        }`;

        if (tradeMap.has(oppositeKey)) {
          conflicts.push(
            `충돌: ${trade.date} ${trade.type.toUpperCase()} vs ${
              tradeMap.get(oppositeKey)?.type.toUpperCase() || ""
            } (${strategyDef.name})`
          );
          return;
        }

        if (tradeMap.has(key)) {
          deduped += 1;
          return;
        }

        tradeMap.set(key, { ...trade, source: strategyDef.name });
      });
    });

    const trades = Array.from(tradeMap.values()).sort(
      (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
    );

    const initialCapital = 10000000;
    const maxLength = Math.max(
      ...strategyResults.map(({ result }) => result.equity.length)
    );
    const equity: number[] = [];
    for (let i = 0; i < maxLength; i++) {
      const values = strategyResults
        .map(({ result }) => result.equity[i])
        .filter((v) => typeof v === "number" && !isNaN(v));
      equity.push(
        values.length > 0
          ? values.reduce((a, b) => a + b, 0) / values.length
          : initialCapital
      );
    }

    const finalEquity = equity[equity.length - 1] || initialCapital;
    setStrategyDiagnostics({ conflicts, deduped });
    if (conflicts.length > 0) {
      setExecutionLogs((prev) => [
        ...prev,
        `[경고] ${conflicts.length}개 충돌 감지`,
      ]);
    }
    setExecutionLogs((prev) => [
      ...prev,
      `[정보] 우선순위: ${prioritySorted
        .map(({ strategyDef }) => strategyDef.name)
        .join(" > ")}`,
      `[정보] 중복 신호 제거 ${deduped}건`,
    ]);

    // Calculate metrics from execution result

    // Step 5: Calculate Metrics
    setBacktestProgress({
      step: 5,
      stepName: "성과 지표 계산",
      progress: 85,
      details: "수익률, 리스크 지표 계산 중...",
    });
    setExecutionLogs((prev) => [
      ...prev,
      `[정보] 거래 완료: 총 ${Math.floor(trades.length / 2)}회`,
    ]);
    setExecutionLogs((prev) => [...prev, "[정보] 성과 지표 계산 중..."]);
    await new Promise((resolve) => setTimeout(resolve, 200));

    // Calculate metrics
    const totalReturn = ((finalEquity - initialCapital) / initialCapital) * 100;
    const buyAndHoldReturn =
      equity.length > 0 && prices.length > 0
        ? ((prices[prices.length - 1] - prices[0]) / prices[0]) * 100
        : 0;

    // Calculate buy and hold equity curve
    const buyAndHoldEquity = prices.map((price) => {
      const shares = initialCapital / prices[0];
      return shares * price;
    });

    // Calculate win rate
    let wins = 0;
    let losses = 0;
    for (let i = 0; i < trades.length - 1; i += 2) {
      if (i + 1 < trades.length) {
        const buyPrice = trades[i].price;
        const sellPrice = trades[i + 1].price;
        if (sellPrice > buyPrice) wins++;
        else losses++;
      }
    }
    const winRate = trades.length > 0 ? (wins / (wins + losses)) * 100 : 0;

    // Calculate max drawdown
    let maxDrawdown = 0;
    let peak = equity[0];
    for (let i = 1; i < equity.length; i++) {
      if (equity[i] > peak) peak = equity[i];
      const drawdown = ((peak - equity[i]) / peak) * 100;
      if (drawdown > maxDrawdown) maxDrawdown = drawdown;
    }

    // Calculate additional metrics
    const totalDays = dates.length;
    const cagr =
      totalDays > 0
        ? (Math.pow(finalEquity / initialCapital, 365 / totalDays) - 1) * 100
        : 0;

    // Calculate Sharpe Ratio (simplified)
    const returns = equity
      .slice(1)
      .map((val, i) => (val - equity[i]) / equity[i]);
    const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
    const stdDev = Math.sqrt(
      returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) /
        returns.length
    );
    const sharpe = stdDev > 0 ? (avgReturn / stdDev) * Math.sqrt(252) : 0;

    // Calculate Sortino Ratio
    const negativeReturns = returns.filter((r) => r < 0);
    const downsideStdDev = Math.sqrt(
      negativeReturns.reduce((sum, r) => sum + Math.pow(r, 2), 0) /
        negativeReturns.length
    );
    const sortino =
      downsideStdDev > 0 ? (avgReturn / downsideStdDev) * Math.sqrt(252) : 0;

    // Calculate Profit Factor
    let totalProfit = 0;
    let totalLoss = 0;
    for (let i = 0; i < trades.length - 1; i += 2) {
      if (i + 1 < trades.length) {
        const profit = trades[i + 1].price - trades[i].price;
        if (profit > 0) totalProfit += profit;
        else totalLoss += Math.abs(profit);
      }
    }
    const profitFactor = totalLoss > 0 ? totalProfit / totalLoss : 0;

    // Calculate monthly/yearly returns for heatmap
    const monthlyReturns: Record<string, number> = {};
    const yearlyReturns: Record<string, number> = {};
    let lastEquity = initialCapital;
    dates.forEach((date, i) => {
      if (i > 0 && equity[i] > 0) {
        const dateObj = new Date(date);
        const month = String(dateObj.getMonth() + 1).padStart(2, "0");
        const monthKey = `${dateObj.getFullYear()}-${month}`;
        const yearKey = String(dateObj.getFullYear());
        const returnPct = ((equity[i] - lastEquity) / lastEquity) * 100;
        monthlyReturns[monthKey] = (monthlyReturns[monthKey] || 0) + returnPct;
        yearlyReturns[yearKey] = (yearlyReturns[yearKey] || 0) + returnPct;
        lastEquity = equity[i];
      }
    });

    // Step 6: Finalize Results
    setBacktestProgress({
      step: 6,
      stepName: "결과 정리",
      progress: 95,
      details: "결과 데이터 저장 중...",
    });
    setExecutionLogs((prev) => [...prev, "[완료] 백테스트 결과 정리 중..."]);
    await new Promise((resolve) => setTimeout(resolve, 100));

    setBacktestResults({
      totalReturn,
      cagr,
      buyAndHoldReturn,
      finalEquity,
      initialCapital,
      trades: Math.floor(trades.length / 2),
      winRate,
      maxDrawdown,
      sharpe,
      sortino,
      profitFactor,
      equity,
      buyAndHoldEquity,
      dates,
      tradesList: trades,
      monthlyReturns,
      yearlyReturns,
      strategyDiagnostics: {
        conflicts,
        deduped,
        priorities: prioritySorted.map(({ strategyDef }) => strategyDef.id),
      },
      strategySelection: [...selectedStrategyIds],
    });

    setBacktestProgress({
      step: 6,
      stepName: "완료",
      progress: 100,
      details: "백테스트 완료",
    });
    setExecutionLogs((prev) => [
      ...prev,
      `[완료] 백테스트 완료! 총 수익률: ${
        totalReturn >= 0 ? "+" : ""
      }${totalReturn.toFixed(2)}%`,
    ]);
    await new Promise((resolve) => setTimeout(resolve, 300));

    setBacktestStatus("completed");
    setBacktestProgress({
      step: 0,
      stepName: "",
      progress: 0,
    });
  };

  // Stop backtest
  const stopBacktest = () => {
    setBacktestStatus("idle");
  };

  // Prepare chart data for TradingView Lightweight Charts
  const equityChartDataForLWC = useMemo((): EquityDataPoint[] => {
    if (!backtestResults?.equity || !backtestResults?.dates) return [];
    const step = Math.max(1, Math.floor(backtestResults.equity.length / 250));
    return backtestResults.equity
      .map((equity: number, i: number) => {
        if (i % step !== 0) return null;
        const date = backtestResults.dates?.[i] || `${i}`;
        const buyHoldValue =
          backtestResults.buyAndHoldEquity?.[i] ||
          backtestResults.initialCapital;
        // Convert date to YYYY-MM-DD format
        const dateObj = new Date(date);
        const formattedDate = dateObj.toISOString().split("T")[0];
        return {
          time: formattedDate,
          equity: Math.round(equity),
          buyHold: Math.round(buyHoldValue),
        };
      })
      .filter((d: any) => d !== null) as EquityDataPoint[];
  }, [backtestResults]);

  const drawdownChartDataForLWC = useMemo((): DrawdownDataPoint[] => {
    if (!backtestResults?.equity || !backtestResults?.dates) return [];
    const step = Math.max(1, Math.floor(backtestResults.equity.length / 250));
    let peak = backtestResults.initialCapital;
    return backtestResults.equity
      .map((equity: number, i: number) => {
        if (i % step !== 0) return null;
        if (equity > peak) peak = equity;
        const drawdown = ((peak - equity) / peak) * 100;
        const date = backtestResults.dates?.[i] || `${i}`;
        // Convert date to YYYY-MM-DD format
        const dateObj = new Date(date);
        const formattedDate = dateObj.toISOString().split("T")[0];
        return {
          time: formattedDate,
          drawdown: Math.max(0, drawdown),
        };
      })
      .filter((d: any) => d !== null) as DrawdownDataPoint[];
  }, [backtestResults]);

  return (
    <DashboardLayout userName={"User"}>
      <div className="p-3 sm:p-4 md:p-5 space-y-3 sm:space-y-4 md:space-y-5 max-w-7xl mx-auto overflow-x-hidden w-full min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white mb-2">전략연구소</h1>
            <p className="text-sm text-gray-400">
              나만의 매매전략을 만들고 백테스트해보세요
            </p>
          </div>
          {activeTab === "strategies" && (
            <div className="flex items-center gap-3">
              {savedStrategies.length >= 2 && (
                <>
                  {!selectionMode ? (
                    <button
                      onClick={() => {
                        setSelectionMode(true);
                        setSelectedForFusion(new Set());
                      }}
                      className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm font-medium hover:bg-gray-600 flex items-center gap-2"
                    >
                      <SparklesIcon className="w-5 h-5" />
                      전략 선택하기
                    </button>
                  ) : (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          setSelectionMode(false);
                          setSelectedForFusion(new Set());
                        }}
                        className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm font-medium hover:bg-gray-600"
                      >
                        취소
                      </button>
                      <button
                        onClick={() => {
                          if (selectedForFusion.size >= 2) {
                            setShowFusionModal(true);
                          } else {
                            alert("최소 2개 이상의 전략을 선택해주세요.");
                          }
                        }}
                        disabled={selectedForFusion.size < 2}
                        className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      >
                        <SparklesIcon className="w-5 h-5" />
                        전략 조합하기 ({selectedForFusion.size}개 선택됨)
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* Tab Navigation */}
        <div className="mb-6 flex items-center gap-2 overflow-x-auto">
          <button
            onClick={() => {
              setActiveTab("strategies");
              setShowComposer(false);
            }}
            className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === "strategies"
                ? "bg-[#252525] text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            전략 만들기
          </button>
          <button
            onClick={() => setActiveTab("backtest")}
            className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === "backtest"
                ? "bg-[#252525] text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            백테스트
          </button>
        </div>

        {/* Strategy Composer or Backtest Panel */}
        {showComposer && (
          <>
            {useV2Composer ? (
              <StrategyComposerV2
                key={strategy ? strategy.id : "new-strategy"} // Force re-mount on strategy change
                onSave={handleSaveStrategy}
                onCancel={() => {
                  setShowComposer(false);
                  setCurrentStep(1);
                  setStrategy(null);
                }}
                onQuickPreview={() => {
                  // Quick preview logic
                  console.log("Quick preview");
                }}
                onQuickBacktest={() => {
                  setActiveTab("backtest");
                  setShowComposer(false);
                }}
                onFullBacktest={() => {
                  setActiveTab("backtest");
                  setShowComposer(false);
                }}
                initialStrategy={strategy}
              />
            ) : (
              <StrategyComposer
                currentStep={currentStep}
                onStepChange={setCurrentStep}
                onSave={handleSaveStrategy}
                onCancel={() => {
                  setShowComposer(false);
                  setCurrentStep(1);
                  setStrategy(null);
                }}
                initialStrategy={strategy}
              />
            )}
          </>
        )}
        {!showComposer &&
          (activeTab === "strategies" ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {savedStrategies.length === 0 ? (
                <div className="col-span-full">
                  <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-12 text-center">
                    <ChartBarIcon className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                    <h3 className="text-lg font-semibold text-white mb-2">
                      저장된 전략이 없습니다
                    </h3>
                    <p className="text-sm text-gray-400 mb-4">
                      새 전략을 만들어보세요
                    </p>
                    <button
                      onClick={openComposer}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-600 flex items-center gap-2 mx-auto"
                    >
                      <PlusIcon className="w-5 h-5" />새 전략 만들기
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div
                    className="bg-[#1a1a1a] rounded-lg border border-dashed border-gray-700 p-6 hover:border-blue-500 transition-all cursor-pointer flex flex-col justify-center items-center text-center"
                    onClick={openComposer}
                  >
                    <div className="w-12 h-12 rounded-full bg-blue-600/20 border border-blue-600/40 flex items-center justify-center mb-3">
                      <PlusIcon className="w-6 h-6 text-blue-400" />
                    </div>
                    <h3 className="text-base font-semibold text-white mb-1">
                      새 전략 만들기
                    </h3>
                    <p className="text-sm text-gray-400">
                      템플릿을 선택하거나 직접 조립해보세요.
                    </p>
                  </div>
                  {savedStrategies.map((s) => {
                    const isSelected = selectedForFusion.has(s.id);
                    return (
                      <div
                        key={s.id}
                        className={`bg-[#1a1a1a] rounded-lg border p-6 transition-all group ${
                          selectionMode
                            ? isSelected
                              ? "border-purple-500 bg-purple-500/10 cursor-pointer"
                              : "border-gray-800 hover:border-gray-700 cursor-pointer"
                            : "border-gray-800 hover:border-gray-700 cursor-pointer"
                        }`}
                        onClick={() => {
                          if (selectionMode) {
                            const newSet = new Set(selectedForFusion);
                            if (newSet.has(s.id)) {
                              newSet.delete(s.id);
                            } else {
                              newSet.add(s.id);
                            }
                            setSelectedForFusion(newSet);
                          } else {
                            handleLoadStrategy(s.id);
                          }
                        }}
                      >
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex items-center gap-3 flex-1">
                            {selectionMode && (
                              <div
                                className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 ${
                                  isSelected
                                    ? "bg-purple-600 border-purple-600"
                                    : "border-gray-600"
                                }`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const newSet = new Set(selectedForFusion);
                                  if (newSet.has(s.id)) {
                                    newSet.delete(s.id);
                                  } else {
                                    newSet.add(s.id);
                                  }
                                  setSelectedForFusion(newSet);
                                }}
                              >
                                {isSelected && (
                                  <CheckCircleIcon className="w-4 h-4 text-white" />
                                )}
                              </div>
                            )}
                            <h3 className="text-base font-semibold text-white group-hover:text-blue-400 transition-colors">
                              {s.name || "이름 없는 전략"}
                            </h3>
                          </div>
                          {!selectionMode && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteStrategy(s.id);
                              }}
                              className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-red-600/20 rounded"
                            >
                              <TrashIcon className="w-4 h-4 text-red-400" />
                            </button>
                          )}
                        </div>
                        <p className="text-sm text-gray-400 mb-4 line-clamp-2">
                          {s.description || "설명이 없습니다"}
                        </p>
                        <div className="flex items-center justify-between text-xs text-gray-500">
                          <span>
                            {s.entry?.conditions?.length || 0}개 진입 조건
                          </span>
                          <span>
                            {new Date(
                              s.created_at || Date.now()
                            ).toLocaleDateString("ko-KR")}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          ) : activeTab === "backtest" ? (
            <div className="space-y-6">
              {/* Control Center */}
              <div className="rounded-2xl border border-gray-800/60 bg-gradient-to-r from-[#0c0c12] to-[#09090e] p-5 shadow-xl flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.2em] text-gray-500">
                    Strategy Lab
                  </p>
                  <h2 className="text-2xl font-bold text-white mt-1">
                    백테스트 제어판
                  </h2>
                  <p className="text-sm text-gray-500 mt-1">
                    종목과 기간을 선택하고 바로 실행해보세요.
                  </p>
                </div>
                <div className="w-full md:w-auto flex items-center gap-3 flex-wrap">
                  <div className="relative group">
                    <div className="flex items-center gap-2 bg-gradient-to-br from-[#0e0e15] to-[#0a0a10] border border-gray-700/50 rounded-xl px-4 py-2.5 shadow-lg hover:border-blue-500/50 transition-all duration-300 hover:shadow-blue-600/10">
                      <MagnifyingGlassIcon className="w-4 h-4 text-gray-400 group-hover:text-blue-400 transition-colors flex-shrink-0" />
                      {!symbol ? (
                        <input
                          type="text"
                          placeholder="종목 코드 입력 (예: 005930)"
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              const newSymbol = (e.target as HTMLInputElement)
                                .value;
                              if (newSymbol)
                                router.push(`/analytics?symbol=${newSymbol}`);
                            }
                          }}
                          className="w-40 bg-transparent text-white text-sm placeholder:text-gray-500 focus:outline-none focus:placeholder:text-gray-600 transition-all"
                        />
                      ) : (
                        <>
                          <span className="text-sm text-blue-400 font-mono font-semibold">
                            {symbol}
                          </span>
                          <button
                            onClick={() => router.push("/analytics")}
                            className="p-1 hover:bg-gray-700/30 rounded-md transition-colors flex-shrink-0"
                            title="종목 변경"
                          >
                            <XMarkIcon className="w-3.5 h-3.5 text-gray-400 hover:text-white" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 bg-[#0e0e15] border border-gray-800 rounded-xl px-2 py-1">
                    {(["1Y", "3Y", "5Y", "Max"] as const).map((period) => (
                      <button
                        key={period}
                        onClick={() => setBacktestPeriod(period)}
                        className={`px-3 py-1 text-xs font-medium rounded-lg transition ${
                          backtestPeriod === period
                            ? "bg-blue-600 text-white shadow-lg shadow-blue-600/30"
                            : "text-gray-400 hover:text-white hover:bg-gray-800/70"
                        }`}
                      >
                        {period}
                      </button>
                    ))}
                  </div>
                  {backtestStatus === "running" && (
                    <button
                      onClick={stopBacktest}
                      className="px-4 py-2 bg-red-600/80 text-white rounded-xl text-xs font-semibold hover:bg-red-600 transition shadow-lg shadow-red-600/30 flex items-center gap-2"
                    >
                      <XMarkIcon className="w-4 h-4" />
                      중지
                    </button>
                  )}
                  <button
                    onClick={runBacktest}
                    disabled={backtestStatus === "running" || !symbol}
                    className={`px-6 py-2 rounded-xl text-sm font-semibold transition-all flex items-center justify-center gap-2 ${
                      backtestStatus === "running"
                        ? "bg-yellow-600/80 text-white cursor-not-allowed"
                        : "bg-gradient-to-r from-blue-600 to-indigo-600 text-white hover:shadow-lg hover:shadow-blue-600/30"
                    } disabled:opacity-50 disabled:cursor-not-allowed`}
                  >
                    {backtestStatus === "running" ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        실행 중...
                      </>
                    ) : (
                      <>
                        <BoltIcon className="w-4 h-4" />
                        백테스트 실행
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Core layout */}
              <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
                {/* Left column */}
                <div className="xl:col-span-3 space-y-4">
                  <div className="rounded-2xl border border-gray-800/60 bg-[#0b0b11] p-4 shadow-lg">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-white">
                        전략 선택
                      </h3>
                      <SparklesIcon className="w-4 h-4 text-blue-400" />
                    </div>
                    <p className="text-[11px] text-gray-500 mb-2">
                      여러 전략을 복수 선택해 조합하고, 충돌은 자동으로 탐지합니다.
                    </p>
                    <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
                      {strategyGroups.map((group) => {
                        const isExpanded = expandedGroups.has(group.id);
                        const isGroupSelected = selectedGroupId === group.id;

                        return (
                          <div
                            key={group.id}
                            className="border-b border-gray-800/50 last:border-b-0 pb-2 last:pb-0"
                          >
                            <button
                              onClick={() => {
                                setSelectedGroupId(group.id);
                                toggleGroup(group.id);
                              }}
                              className={`w-full text-left px-2 py-2 rounded-lg text-xs flex items-center gap-2 transition-colors ${
                                isGroupSelected
                                  ? "bg-blue-600/20 text-white"
                                  : "text-gray-400 hover:text-white hover:bg-gray-800/50"
                              }`}
                            >
                              <span className="text-base">{group.icon}</span>
                              <span className="flex-1 font-semibold">
                                {group.name}
                              </span>
                              <ChevronDownIcon
                                className={`w-3 h-3 transition-transform ${
                                  isExpanded ? "rotate-180" : ""
                                }`}
                              />
                            </button>

                            {isExpanded && (
                              <div className="mt-1 space-y-0.5 pl-6">
                                {group.strategies.map((strategy) => {
                                  const isSelected =
                                    selectedStrategyIds.includes(strategy.id);
                                  const priority =
                                    strategyPriorities[strategy.id];
                                  return (
                                    <button
                                      key={strategy.id}
                                      onClick={() =>
                                        toggleStrategySelection(
                                          strategy.id,
                                          group.id
                                        )
                                      }
                                      className={`w-full text-left px-2 py-1.5 rounded text-[11px] flex items-center gap-2 transition-colors ${
                                        isSelected
                                          ? "bg-blue-600/30 text-white border border-blue-500/50"
                                          : "text-gray-400 hover:text-white hover:bg-gray-800/50"
                                      }`}
                                    >
                                      <span className="flex-1 truncate">
                                        {strategy.name}
                                      </span>
                                      {isSelected && (
                                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-900/50 border border-blue-700 text-blue-200">
                                          우선 {priority ?? "-"}
                                        </span>
                                      )}
                                      {isSelected && (
                                        <CheckCircleIcon className="w-3 h-3 text-blue-400 flex-shrink-0" />
                                      )}
                                    </button>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-gray-800/60 bg-[#0b0b11] p-4 shadow-lg">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-white">
                        파라미터 & 우선순위
                      </h3>
                      <div className="text-[11px] text-gray-500">
                        중복 제거 {strategyDiagnostics.deduped}건 · 충돌{" "}
                        {strategyDiagnostics.conflicts.length}건
                      </div>
                    </div>
                    <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
                      {selectedStrategiesDef.length > 0 ? (
                        selectedStrategiesDef.map((strategyDef) => {
                          const params =
                            backtestParamsByStrategy[strategyDef.id] || {};
                          const priority = strategyPriorities[strategyDef.id];

                          // Parse label to separate Korean and English
                          const parseLabel = (label: string) => {
                            const match = label.match(/^(.+?)\s*\((.+?)\)$/);
                            if (match) {
                              return {
                                korean: match[1].trim(),
                                english: match[2].trim(),
                              };
                            }
                            return { korean: label, english: "" };
                          };

                          return (
                            <div
                              key={strategyDef.id}
                              className="border border-gray-800 rounded-lg p-3 bg-[#0f0f16] shadow-inner"
                            >
                              <div className="flex items-center justify-between mb-2">
                                <div>
                                  <p className="text-[11px] text-gray-500">
                                    우선순위 {priority ?? "-"}
                                  </p>
                                  <p className="text-sm font-semibold text-white">
                                    {strategyDef.name}
                                  </p>
                                </div>
                                <div className="flex items-center gap-1">
                                  <button
                                    onClick={() =>
                                      adjustPriority(strategyDef.id, "up")
                                    }
                                    className="p-1 rounded border border-gray-800 text-gray-400 hover:text-white hover:border-blue-500"
                                    title="우선순위 올리기"
                                  >
                                    ↑
                                  </button>
                                  <button
                                    onClick={() =>
                                      adjustPriority(strategyDef.id, "down")
                                    }
                                    className="p-1 rounded border border-gray-800 text-gray-400 hover:text-white hover:border-blue-500"
                                    title="우선순위 내리기"
                                  >
                                    ↓
                                  </button>
                                  <button
                                    onClick={() =>
                                      setSelectedStrategyIds((prev) =>
                                        prev.filter(
                                          (id) => id !== strategyDef.id
                                        )
                                      )
                                    }
                                    className="p-1 rounded border border-gray-800 text-gray-400 hover:text-red-300 hover:border-red-500"
                                    title="전략 제거"
                                  >
                                    <XMarkIcon className="w-3 h-3" />
                                  </button>
                                </div>
                              </div>

                              <div className="space-y-3">
                                {strategyDef.params.map((param) => {
                                  const { korean, english } = parseLabel(
                                    param.label
                                  );
                                  const currentValue =
                                    params[param.key] ?? param.default;
                                  const step =
                                    param.max - param.min > 50
                                      ? 1
                                      : param.max - param.min > 10
                                      ? 0.5
                                      : 0.1;

                                  return (
                                    <div
                                      key={param.key}
                                      className="flex items-center justify-between gap-2"
                                    >
                                      <label className="flex flex-col text-xs font-medium text-gray-300 text-left">
                                        <span className="whitespace-nowrap">
                                          {korean}
                                        </span>
                                        {english && (
                                          <span className="text-[10px] text-gray-500 font-normal whitespace-nowrap">
                                            {english}
                                          </span>
                                        )}
                                      </label>
                                      <div className="flex items-center gap-3 justify-end flex-1 max-w-[150px]">
                                        <div className="flex-1 space-y-1">
                                          <div className="flex items-center justify-between text-[10px] text-gray-500">
                                            <span className="tabular-nums">
                                              {param.min}
                                            </span>
                                            <span className="text-white font-medium tabular-nums">
                                              {currentValue}
                                            </span>
                                            <span className="tabular-nums">
                                              {param.max}
                                            </span>
                                          </div>
                                          <input
                                            type="range"
                                            min={param.min}
                                            max={param.max}
                                            step={step}
                                            value={currentValue}
                                            onChange={(e) =>
                                              setBacktestParamsByStrategy(
                                                (prev) => ({
                                                  ...prev,
                                                  [strategyDef.id]: {
                                                    ...(prev[
                                                      strategyDef.id
                                                    ] || {}),
                                                    [param.key]: parseFloat(
                                                      e.target.value
                                                    ),
                                                  },
                                                })
                                              )
                                            }
                                            className="w-full h-1 bg-gray-800 rounded-lg appearance-none cursor-pointer slider"
                                          />
                                        </div>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          );
                        })
                      ) : (
                        <div className="text-xs text-gray-500 text-center py-4">
                          전략을 선택해주세요
                        </div>
                      )}
                    </div>
                    {strategyDiagnostics.conflicts.length > 0 && (
                      <div className="mt-3 rounded-lg border border-red-800/60 bg-red-900/20 p-2 text-[11px] text-red-200 space-y-1">
                        {strategyDiagnostics.conflicts
                          .slice(0, 3)
                          .map((conflict, idx) => (
                            <div key={idx} className="flex items-start gap-1">
                              <ExclamationTriangleIcon className="w-3 h-3 mt-[2px]" />
                              <span>{conflict}</span>
                            </div>
                          ))}
                        {strategyDiagnostics.conflicts.length > 3 && (
                          <div className="text-gray-300">
                            +{" "}
                            {strategyDiagnostics.conflicts.length - 3}
                            건 더 있음
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Center column */}
                <div className="xl:col-span-7">
                  <div className="rounded-2xl border border-gray-800/60 bg-[#07070c] h-full flex flex-col shadow-xl">
                    {backtestStatus === "running" ? (
                      <>
                        {/* Chart Header Skeleton with Shimmer */}
                        <div className="px-5 py-3 border-b border-gray-800/60 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            {[1, 2, 3].map((i) => (
                              <div
                                key={i}
                                className="h-7 w-20 bg-gray-800/50 rounded-lg relative overflow-hidden"
                              >
                                {backtestStatus === "running" && (
                                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent animate-shimmer" />
                                )}
                              </div>
                            ))}
                          </div>
                          <div className="h-4 w-24 bg-gray-800/50 rounded relative overflow-hidden">
                            {backtestStatus === "running" && (
                              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent animate-shimmer" />
                            )}
                          </div>
                        </div>
                        {/* Chart Area Skeleton with Shimmer */}
                        <div className="flex-1 p-5">
                          <div className="h-full space-y-4">
                            <div className="h-72 bg-[#0a0a0f] rounded-lg border border-gray-800/40 relative overflow-hidden">
                              {backtestStatus === "running" && (
                                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent animate-shimmer" />
                              )}
                              <div className="absolute inset-0 flex items-center justify-center">
                                <div className="text-center">
                                  <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                                  <div className="text-sm text-gray-400">
                                    {backtestProgress.stepName}
                                  </div>
                                  <div className="text-xs text-gray-500 mt-1">
                                    {backtestProgress.details}
                                  </div>
                                </div>
                              </div>
                            </div>
                            <div className="grid grid-cols-4 gap-3">
                              {[1, 2, 3, 4].map((i) => (
                                <div
                                  key={i}
                                  className="bg-[#0a0a0f] rounded-lg p-3 border border-gray-800/40 relative overflow-hidden"
                                >
                                  {backtestStatus === "running" && (
                                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent animate-shimmer" />
                                  )}
                                  <div className="h-3 w-16 bg-gray-800/50 rounded mb-2" />
                                  <div className="h-5 w-24 bg-gray-800/50 rounded" />
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </>
                    ) : backtestStatus === "completed" && backtestResults ? (
                      <>
                        <div className="px-5 py-3 border-b border-gray-800/60 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            {["equity", "drawdown", "heatmap"].map((type) => (
                              <button
                                key={type}
                                onClick={() => setChartType(type as any)}
                                className={`px-3 py-1.5 text-xs rounded-lg ${
                                  chartType === type
                                    ? "bg-blue-600 text-white shadow-blue-600/40 shadow-sm"
                                    : "text-gray-400 hover:text-white hover:bg-gray-800/70"
                                }`}
                              >
                                {type === "equity"
                                  ? "수익곡선"
                                  : type === "drawdown"
                                  ? "낙폭"
                                  : "히트맵"}
                              </button>
                            ))}
                          </div>
                          <div className="text-xs text-gray-500">
                            총 수익률{" "}
                            <span
                              className={`font-semibold ${
                                backtestResults.totalReturn >= 0
                                  ? "text-red-400"
                                  : "text-blue-400"
                              }`}
                            >
                              {backtestResults.totalReturn >= 0 ? "+" : ""}
                              {backtestResults.totalReturn.toFixed(2)}%
                            </span>
                          </div>
                        </div>

                        <div className="flex-1 p-5 overflow-auto">
                          {chartType === "equity" && (
                            <div className="h-full space-y-4">
                              {/* Enhanced Equity Chart with Recharts */}
                              <div className="relative">
                                <div className="absolute top-0 left-0 flex items-center gap-4 mb-2 text-xs z-10 pl-4 pt-4">
                                  <div className="flex items-center gap-2">
                                    <div className="w-3 h-3 rounded bg-blue-600" />
                                    <span className="text-gray-400">전략</span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <div className="w-3 h-3 rounded bg-gray-600" />
                                    <span className="text-gray-400">
                                      Buy & Hold
                                    </span>
                                  </div>
                                </div>
                                <div className="h-72 bg-[#0a0a0f] rounded-lg p-4 border border-gray-800/40">
                                  <BacktestChart
                                    type="equity"
                                    equityData={equityChartDataForLWC}
                                    height={280}
                                  />
                                </div>
                              </div>

                              {/* Key Metrics Grid */}
                              <div className="grid grid-cols-4 gap-3">
                                <div className="bg-[#0a0a0f] rounded-lg p-3 border border-gray-800/40">
                                  <div className="text-[10px] text-gray-500 mb-1">
                                    초기 자본
                                  </div>
                                  <div className="text-sm font-bold text-white">
                                    {formatPrice(
                                      backtestResults.initialCapital
                                    )}
                                    원
                                  </div>
                                </div>
                                <div className="bg-[#0a0a0f] rounded-lg p-3 border border-gray-800/40">
                                  <div className="text-[10px] text-gray-500 mb-1">
                                    최종 자산
                                  </div>
                                  <div className="text-sm font-bold text-white">
                                    {formatPrice(backtestResults.finalEquity)}원
                                  </div>
                                </div>
                                <div className="bg-[#0a0a0f] rounded-lg p-3 border border-gray-800/40">
                                  <div className="text-[10px] text-gray-500 mb-1">
                                    순이익
                                  </div>
                                  <div
                                    className={`text-sm font-bold ${
                                      backtestResults.finalEquity -
                                        backtestResults.initialCapital >=
                                      0
                                        ? "text-red-400"
                                        : "text-blue-400"
                                    }`}
                                  >
                                    {backtestResults.finalEquity -
                                      backtestResults.initialCapital >=
                                    0
                                      ? "+"
                                      : ""}
                                    {formatPrice(
                                      backtestResults.finalEquity -
                                        backtestResults.initialCapital
                                    )}
                                    원
                                  </div>
                                </div>
                                <div className="bg-[#0a0a0f] rounded-lg p-3 border border-gray-800/40">
                                  <div className="text-[10px] text-gray-500 mb-1">
                                    거래 횟수
                                  </div>
                                  <div className="text-sm font-bold text-white">
                                    {backtestResults.trades}회
                                  </div>
                                </div>
                              </div>
                            </div>
                          )}

                          {chartType === "drawdown" && (
                            <div className="h-full space-y-4">
                              <div className="relative">
                                <div className="absolute top-0 left-0 right-0 flex items-center justify-between mb-2 text-xs z-10">
                                  <div className="text-gray-400">
                                    Drawdown 분석
                                  </div>
                                  <div className="text-yellow-400">
                                    최대 낙폭:{" "}
                                    {backtestResults.maxDrawdown.toFixed(2)}%
                                  </div>
                                </div>
                                <div className="h-72 bg-[#0a0a0f] rounded-lg p-4 border border-gray-800/40 mt-8">
                                  <BacktestChart
                                    type="drawdown"
                                    drawdownData={drawdownChartDataForLWC}
                                    height={280}
                                  />
                                </div>
                              </div>
                            </div>
                          )}

                          {chartType === "heatmap" && (
                            <div className="h-full space-y-4">
                              <div className="text-xs text-gray-400 mb-2">
                                월별 수익률 히트맵
                              </div>
                              <div className="grid grid-cols-12 gap-2">
                                {Object.entries(
                                  backtestResults.monthlyReturns || {}
                                ).map(([month, returnPct]: [string, any]) => (
                                  <div
                                    key={month}
                                    className={`p-3 rounded-lg text-center border transition-all ${
                                      returnPct >= 5
                                        ? "bg-red-600/30 border-red-500/50 text-red-400"
                                        : returnPct >= 0
                                        ? "bg-red-600/10 border-red-500/30 text-red-300"
                                        : returnPct >= -5
                                        ? "bg-blue-600/10 border-blue-500/30 text-blue-400"
                                        : "bg-blue-600/30 border-blue-500/50 text-blue-400"
                                    }`}
                                  >
                                    <div className="text-xs font-bold">
                                      {returnPct >= 0 ? "+" : ""}
                                      {returnPct.toFixed(1)}%
                                    </div>
                                    <div className="text-[10px] text-gray-500 mt-1">
                                      {month.split("-")[1]}월
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </>
                    ) : (
                      <>
                        {/* Chart Header Skeleton (no shimmer) */}
                        <div className="px-5 py-3 border-b border-gray-800/60 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            {[1, 2, 3].map((i) => (
                              <div
                                key={i}
                                className="h-7 w-20 bg-gray-800/50 rounded-lg"
                              />
                            ))}
                          </div>
                          <div className="h-4 w-24 bg-gray-800/50 rounded" />
                        </div>
                        {/* Chart Area Skeleton (no shimmer) */}
                        <div className="flex-1 p-5">
                          <div className="h-full space-y-4">
                            <div className="h-72 bg-[#0a0a0f] rounded-lg border border-gray-800/40 flex items-center justify-center">
                              <div className="text-center text-gray-500 text-sm">
                                종목을 선택하고 백테스트를 실행하세요
                              </div>
                            </div>
                            <div className="grid grid-cols-4 gap-3">
                              {[1, 2, 3, 4].map((i) => (
                                <div
                                  key={i}
                                  className="bg-[#0a0a0f] rounded-lg p-3 border border-gray-800/40"
                                >
                                  <div className="h-3 w-16 bg-gray-800/50 rounded mb-2" />
                                  <div className="h-5 w-24 bg-gray-800/50 rounded" />
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                </div>

                {/* Right column */}
                <div className="xl:col-span-2">
                  <div className="rounded-2xl border border-gray-800/60 bg-[#0b0b11] h-full shadow-lg">
                    {backtestStatus === "running" ? (
                      <div className="p-5 space-y-4 h-full flex flex-col">
                        {/* Metrics Skeleton with Shimmer */}
                        <div className="h-5 w-24 bg-gray-800/50 rounded relative overflow-hidden">
                          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent animate-shimmer" />
                        </div>
                        <div className="space-y-3">
                          {[1, 2, 3, 4, 5, 6].map((i) => (
                            <div
                              key={i}
                              className="space-y-1 relative overflow-hidden"
                            >
                              <div className="h-3 w-20 bg-gray-800/50 rounded" />
                              <div className="h-7 w-32 bg-gray-800/50 rounded relative overflow-hidden">
                                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent animate-shimmer" />
                              </div>
                            </div>
                          ))}
                        </div>
                        {/* Execution Log */}
                        <div className="mt-auto pt-4 border-t border-gray-800/50">
                          <h3 className="text-sm font-semibold text-white mb-2">
                            실행 로그
                          </h3>
                          <div className="flex-1 overflow-y-auto space-y-1.5 text-xs font-mono max-h-32">
                            {executionLogs.map((log, idx) => {
                              const isInfo = log.includes("[정보]");
                              const isRunning = log.includes("[실행중]");
                              const isProgress = log.includes("[진행]");
                              const isComplete = log.includes("[완료]");

                              return (
                                <div
                                  key={idx}
                                  className={`${
                                    isComplete
                                      ? "text-blue-400"
                                      : isRunning || isProgress
                                      ? "text-yellow-400"
                                      : isInfo
                                      ? "text-blue-400"
                                      : "text-gray-300"
                                  } animate-fade-in`}
                                >
                                  {log}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    ) : backtestStatus === "completed" && backtestResults ? (
                      <div className="p-5 space-y-4">
                        <h3 className="text-sm font-semibold text-white">
                          성과 지표
                        </h3>
                        <div className="space-y-3 text-sm">
                          <div>
                            <div className="text-xs text-gray-500 mb-1">
                              총 수익률
                            </div>
                            <div
                              className={`text-xl font-bold ${
                                backtestResults.totalReturn >= 0
                                  ? "text-red-400"
                                  : "text-blue-400"
                              }`}
                            >
                              {backtestResults.totalReturn >= 0 ? "+" : ""}
                              {backtestResults.totalReturn.toFixed(2)}%
                            </div>
                          </div>
                          <div>
                            <div className="text-xs text-gray-500 mb-1">
                              CAGR
                            </div>
                            <div
                              className={`text-xl font-bold ${
                                backtestResults.cagr >= 0
                                  ? "text-red-400"
                                  : "text-blue-400"
                              }`}
                            >
                              {backtestResults.cagr >= 0 ? "+" : ""}
                              {backtestResults.cagr.toFixed(2)}%
                            </div>
                          </div>
                          <div>
                            <div className="text-xs text-gray-500 mb-1">
                              최대 낙폭
                            </div>
                            <div className="text-xl font-bold text-yellow-400">
                              {backtestResults.maxDrawdown.toFixed(2)}%
                            </div>
                          </div>
                          <div>
                            <div className="text-xs text-gray-500 mb-1">
                              Sharpe 비율
                            </div>
                            <div
                              className={`text-xl font-bold ${
                                backtestResults.sharpe >= 0
                                  ? "text-red-400"
                                  : "text-blue-400"
                              }`}
                            >
                              {backtestResults.sharpe.toFixed(2)}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs text-gray-500 mb-1">
                              승률
                            </div>
                            <div className="text-xl font-bold text-white">
                              {backtestResults.winRate.toFixed(1)}%
                            </div>
                          </div>
                          <div>
                            <div className="text-xs text-gray-500 mb-1">
                              총 거래 수
                            </div>
                            <div className="text-xl font-bold text-white">
                              {backtestResults.trades}
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="p-5 space-y-4">
                        {/* Metrics Skeleton (no shimmer) */}
                        <div className="h-5 w-24 bg-gray-800/50 rounded" />
                        <div className="space-y-3">
                          {[1, 2, 3, 4, 5, 6].map((i) => (
                            <div key={i} className="space-y-1">
                              <div className="h-3 w-20 bg-gray-800/50 rounded" />
                              <div className="h-7 w-32 bg-gray-800/50 rounded" />
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Trade history */}
              {backtestStatus === "completed" && backtestResults && (
                <div className="rounded-2xl border border-gray-800/60 bg-[#09090f] shadow-xl">
                  <div className="p-4 md:p-5 flex items-center justify-between">
                    <div>
                      <p className="text-[11px] uppercase tracking-widest text-gray-500">
                        Trade History
                      </p>
                      <h3 className="text-lg font-semibold text-white mt-1">
                        거래 내역
                      </h3>
                    </div>
                    <div className="text-xs text-gray-500">최근 20개 거래</div>
                  </div>
                  <div className="max-h-[200px] overflow-auto border-t border-gray-800/60">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-gray-800 text-gray-400">
                          <th className="text-left py-2 pl-4">날짜</th>
                          <th className="text-left py-2">유형</th>
                          <th className="text-right py-2">가격</th>
                          <th className="text-right py-2">수량</th>
                          <th className="text-right py-2 pr-4">금액</th>
                        </tr>
                      </thead>
                      <tbody>
                        {backtestResults.tradesList
                          ?.slice(-20)
                          .reverse()
                          .map((trade: any, i: number) => (
                            <tr
                              key={i}
                              className="border-b border-gray-800/40 hover:bg-gray-800/30"
                            >
                              <td className="py-2 pl-4 text-gray-300">
                                {trade.date}
                              </td>
                              <td
                                className={`py-2 font-medium ${
                                  trade.type === "buy"
                                    ? "text-red-400"
                                    : "text-blue-400"
                                }`}
                              >
                                {trade.type === "buy" ? "매수" : "매도"}
                              </td>
                              <td className="py-2 text-right text-white">
                                {formatPrice(trade.price)}
                              </td>
                              <td className="py-2 text-right text-gray-300">
                                -
                              </td>
                              <td className="py-2 pr-4 text-right text-white">
                                {formatPrice(trade.price)}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          ) : null        )}
      </div>

      {/* Strategy Fusion Modal */}
      <StrategyFusionModal
        isOpen={showFusionModal}
        onClose={() => {
          setShowFusionModal(false);
          setSelectionMode(false);
          setSelectedForFusion(new Set());
        }}
        savedStrategies={savedStrategies}
        onSave={(strategy) => {
          handleSaveStrategy(strategy);
          setSelectionMode(false);
          setSelectedForFusion(new Set());
        }}
        initialSelectedIds={Array.from(selectedForFusion)}
      />
    </DashboardLayout>
  );
}
