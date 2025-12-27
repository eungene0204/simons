"use client";

import { useState, useEffect, useCallback, useRef, Fragment } from "react";
import {
  XMarkIcon,
  PlayCircleIcon,
  DocumentArrowDownIcon,
  CheckCircleIcon,
  ClockIcon,
  EyeIcon,
  ArrowRightIcon,
  ArrowLeftIcon,
  SparklesIcon,
  AdjustmentsHorizontalIcon,
  ShieldExclamationIcon,
  ChartBarIcon,
  CubeIcon,
  ArrowPathIcon,
  CpuChipIcon,
  ExclamationTriangleIcon,
  PlusIcon,
  MinusIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  InformationCircleIcon,
  BoltIcon,
  ArrowTrendingUpIcon,
  GlobeAltIcon,
  CheckIcon,
  ChartPieIcon,
  ShieldCheckIcon,
  Squares2X2Icon,
  TagIcon,
  MagnifyingGlassIcon,
  BanknotesIcon,
  EllipsisHorizontalIcon,
  CursorArrowRaysIcon,
} from "@heroicons/react/24/outline";
import { StrategyDSL, Condition, ConditionType, LogicOperator, BacktestResult, CanvasBlock } from "@/types/strategy";
import { signalBlocks } from "@/lib/strategy-blocks";
import { runBacktest } from "@/lib/backtest-engine";
import BacktestChart from "@/components/strategy/BacktestChart";
import RiskManagementEditor from "./RiskManagementEditor";
import Step1Universe from "./steps/Step1Universe";
import Step2Conditions from "./steps/Step2Conditions";

interface StrategyComposerV2Props {
  onSave: (strategy: StrategyDSL) => void;
  onCancel: () => void;
  onQuickPreview?: () => void;
  onQuickBacktest?: () => void;
  onFullBacktest?: () => void;
  initialStrategy?: StrategyDSL | null;
}

type StrategyStatus = "draft" | "saved" | "published";
type ComposerStep = 1 | 2 | 3 | 4 | 5;

type BlockCategory =
  | "price_signals"
  | "momentum"
  | "mean_reversion"
  | "factor_filters"
  | "risk_rules"
  | "position_sizing"
  | "portfolio_rules";


export default function StrategyComposerV2({
  onSave,
  onCancel,
  onQuickPreview,
  onQuickBacktest,
  onFullBacktest,
  initialStrategy,
}: StrategyComposerV2Props) {
  // Header state
  const [strategyName, setStrategyName] = useState("");
  const [strategyStatus, setStrategyStatus] = useState<StrategyStatus>("draft");
  const [currentStep, setCurrentStep] = useState<ComposerStep>(1);

  // Strategy state
  const [universe, setUniverse] = useState<string>("kospi");
  const [universeFilters, setUniverseFilters] = useState({
    marketCapRange: [0, 100], // [min_percentile, max_percentile]
    minTradingVolume: 0, // in Billions (KRW)
    excludeLossMaking: false,
    excludeCapitalImpaired: false,
    selectedSectors: [] as string[],
    excludeAdministrative: false,
    excludePreferred: false,
    excludeETF_ETN: false,
    excludeSPAC: false,
    excludeREITs: false,
    excludeInvestmentWarning: false,
    excludeDelistingPending: false,
    excludeForeignStock: false,
    excludePennyStocks: false,
    excludeNewListings: false,
    excludeHighVolatility: false,
  });
  const [initialCapital, setInitialCapital] = useState(10000000); // 1,000만원
  const [maxPositions, setMaxPositions] = useState(10);
  const [allocationType, setAllocationType] = useState<"equal" | "fixed_pct">("equal");
  const [allocationValue, setAllocationValue] = useState(5); // 5%
  const [executionTiming, setExecutionTiming] = useState<"next_open" | "current_close">("next_open");
  const [rebalancingPeriod, setRebalancingPeriod] = useState<"none" | "daily" | "weekly" | "monthly">("none");

  const [positionRules, setPositionRules] = useState<any[]>([]);
  const [entryLogic, setEntryLogic] = useState<LogicOperator>("AND");
  const [exitLogic, setExitLogic] = useState<LogicOperator>("OR");
  const [riskManagement, setRiskManagement] = useState({
    position_size_pct: 5,
    max_positions: 10,
    max_daily_loss_pct: 5,
    max_total_exposure_pct: 50,
  });
  // Canvas state
  const [canvasBlocks, setCanvasBlocks] = useState<CanvasBlock[]>([]);
  const [selectedBlock, setSelectedBlock] = useState<CanvasBlock | null>(null);
  const [activeParamTab, setActiveParamTab] = useState<'block' | 'global'>('global');
  const [editingBlock, setEditingBlock] = useState<CanvasBlock | null>(null);
  const [draggedOver, setDraggedOver] = useState(false);
  
  // Backtest Preview State
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [isBacktesting, setIsBacktesting] = useState(false);
  const [hoveredInfo, setHoveredInfo] = useState<{ id: string, rect: DOMRect } | null>(null);
  const [hoveredParam, setHoveredParam] = useState<{ label: string, tooltip: string, rect: DOMRect } | null>(null);
  const [savedFeedback, setSavedFeedback] = useState<string | null>(null);
  const feedbackTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [isSearchMenuOpen, setIsSearchMenuOpen] = useState(false);
  const [unlockedBlockIds, setUnlockedBlockIds] = useState<string[]>([]);
  const [manuallyHiddenBlockIds, setManuallyHiddenBlockIds] = useState<string[]>([]);
  const [editingCategoryKey, setEditingCategoryKey] = useState<string | null>(null);
  const [isLibraryManagementOpen, setIsLibraryManagementOpen] = useState(false);
  const [activeMgmtCategory, setActiveMgmtCategory] = useState<string>("indicator");
  const [hoveredEditIcon, setHoveredEditIcon] = useState<{ label: string, rect: DOMRect } | null>(null);
  const [customBlockOrder, setCustomBlockOrder] = useState<Record<string, string[]>>({});
  const [draggedModalItemIndex, setDraggedModalItemIndex] = useState<number | null>(null);
  const [customCategoryOrder, setCustomCategoryOrder] = useState<string[]>(['filter', 'indicator', 'risk', 'ml']);
  const [draggedCategoryIndex, setDraggedCategoryIndex] = useState<number | null>(null);
  const [openSignalGroups, setOpenSignalGroups] = useState<string[]>([]);
  const [sectorSearchTerm, setSectorSearchTerm] = useState("");

  // Responsive Canvas State
  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasWidth, setCanvasWidth] = useState(1000);

  useEffect(() => {
    if (!canvasRef.current) return;
    
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setCanvasWidth(entry.contentRect.width);
      }
    });
    
    observer.observe(canvasRef.current);
    return () => observer.disconnect();
  }, [currentStep]);

  // Prevent background scroll when modals are open
  useEffect(() => {
    if (isLibraryManagementOpen || isSearchMenuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isLibraryManagementOpen, isSearchMenuOpen]);

  const handleAddBlock = useCallback((blockId: string, blockType?: string) => {
    if (canvasBlocks.some(b => b.blockId === blockId)) {
      alert("이미 추가된 블록입니다");
      return;
    }

    const type = blockType || signalBlocks[blockId]?.category || "entry";
    
    const newBlock: CanvasBlock = {
      id: Math.random().toString(36).substr(2, 9),
      type: type.includes("risk") ? "exit" : type.includes("filter") ? "filter" : "entry",
      blockId: blockId,
      position: { x: 0, y: 0 },
      params: signalBlocks[blockId]?.defaultParams ? { ...signalBlocks[blockId].defaultParams } : {},
    };

    const updated = [...canvasBlocks, newBlock];
    
    const sorted = [
      ...updated.filter(b => b.type === "filter"),
      ...updated.filter(b => b.type === "entry"),
      ...updated.filter(b => b.type === "exit")
    ];
    
    setCanvasBlocks(sorted);
    setSelectedBlock(newBlock);
  }, [canvasBlocks]);

  const handleRemoveBlockFromBin = useCallback((blockId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (unlockedBlockIds.includes(blockId)) {
      setUnlockedBlockIds(prev => prev.filter(id => id !== blockId));
    } else {
      setManuallyHiddenBlockIds(prev => [...prev, blockId]);
    }
    setSavedFeedback("보관함에서 삭제되었습니다.");
    if (feedbackTimeoutRef.current) clearTimeout(feedbackTimeoutRef.current);
    feedbackTimeoutRef.current = setTimeout(() => setSavedFeedback(null), 2000);
  }, [unlockedBlockIds]);





  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  const runSimulation = useCallback(async () => {
    setIsBacktesting(true);

    // Map canvas blocks to backtest conditions
    const entryConditionsMap = canvasBlocks
      .filter(b => b.type === "entry" || b.type === "filter")
      .map(b => ({
        type: (b.type === "filter" ? "filter" : "indicator") as ConditionType,
        id: b.blockId,
        params: b.params,
      }));

    const exitConditionsMap = canvasBlocks
      .filter(b => b.type === "exit")
      .map(b => ({
        type: "indicator" as ConditionType,
        id: b.blockId,
        params: b.params,
      }));

    // Construct StrategyDSL from current state
    const strategy: StrategyDSL = {
      id: "temp_preview",
      name: strategyName,
      description: "Preview Strategy",
      version: "1.0",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      entry: {
        logic: entryLogic,
        conditions: entryConditionsMap
      },
      exit: {
        logic: exitLogic,
        conditions: exitConditionsMap
      },
      risk: riskManagement || {
        position_size_pct: 10,
        max_positions: 10,
        max_daily_loss_pct: 5,
        max_total_exposure_pct: 100
      }
    };

    try {
      const result = await runBacktest(strategy, "1Y");
      setBacktestResult(result);
    } catch (e) {
      console.error(e);
    } finally {
      setIsBacktesting(false);
    }
  }, [strategyName, universe, canvasBlocks, riskManagement, entryLogic, exitLogic]);

  // Trigger simulation when entering step 5
  useEffect(() => {
    if (currentStep === 5) {
      runSimulation();
    }
  }, [currentStep, runSimulation]);



  // Initialize from existing strategy
  useEffect(() => {
    if (initialStrategy) {
      setStrategyName(initialStrategy.name);
      
      // Populate canvas blocks from existing conditions
      const blocks: CanvasBlock[] = [
        ...initialStrategy.entry.conditions.map((c, i) => ({
          id: `entry-${i}-${Math.random().toString(36).substr(2, 5)}`,
          type: c.type === "filter" ? ("filter" as const) : ("entry" as const),
          blockId: c.id,
          position: { x: 0, y: 0 },
          params: c.params,
        })),
        ...initialStrategy.exit.conditions.map((c, i) => ({
          id: `exit-${i}-${Math.random().toString(36).substr(2, 5)}`,
          type: "exit" as const,
          blockId: c.id,
          position: { x: 0, y: 0 },
          params: c.params,
        })),
      ];
      
      const sortedBlocks = [
        ...blocks.filter(b => b.type === "filter"),
        ...blocks.filter(b => b.type === "entry"),
        ...blocks.filter(b => b.type === "exit")
      ];
      
      setCanvasBlocks(sortedBlocks);
      
      if (initialStrategy.entry.logic) setEntryLogic(initialStrategy.entry.logic);
      if (initialStrategy.exit.logic) setExitLogic(initialStrategy.exit.logic);
      
      setRiskManagement({
        position_size_pct: initialStrategy.risk.position_size_pct,
        max_positions: initialStrategy.risk.max_positions,
        max_daily_loss_pct: initialStrategy.risk.max_daily_loss_pct ?? 5,
        max_total_exposure_pct: initialStrategy.risk.max_total_exposure_pct ?? 50,
      });
    }
  }, [initialStrategy]);


  const handleSave = () => {
    if (!strategyName.trim()) {
      alert("전략 이름을 입력하세요");
      return;
    }

    const entryConditionsMap = canvasBlocks
      .filter(b => b.type === "entry" || b.type === "filter")
      .map(b => ({
        type: (b.type === "filter" ? "filter" : "indicator") as ConditionType,
        id: b.blockId,
        params: b.params,
      }));

    const exitConditionsMap = canvasBlocks
      .filter(b => b.type === "exit")
      .map(b => ({
        type: "indicator" as ConditionType,
        id: b.blockId,
        params: b.params,
      }));

    const strategy: StrategyDSL = {
      id: initialStrategy?.id || `strategy_${Date.now()}`,
      name: strategyName.trim(),
      description: "",
      version: "1.0.0",
      entry: {
        logic: entryLogic,
        conditions: entryConditionsMap,
      },
      exit: {
        logic: exitLogic,
        conditions: exitConditionsMap,
      },
      risk: riskManagement,
      created_at: initialStrategy?.created_at || new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    onSave(strategy);
    setStrategyStatus("saved");
  };

  const stepLabels = [
    { num: 1, label: "유니버스 선택" },
    { num: 2, label: "매매 조건" },
    { num: 3, label: "포지션/비중" },
    { num: 4, label: "리스크 관리" },
    { num: 5, label: "미리보기" },
  ];


  return (
    <div className="flex flex-col bg-[#0f0f0f] relative">
      {/* Top Header Bar */}
      <div className="bg-[#0f0f0f] border-b border-gray-800 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4 flex-1">
            <div className="flex items-center gap-3">
              <span className="text-xl font-bold text-white tracking-tight">
                {strategyName || (currentStep === 1 ? "새로운 전략 개요" : "이름 없는 전략")}
              </span>
              <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 text-[10px] font-bold uppercase tracking-wider border border-blue-500/20">
                {stepLabels.find(s => s.num === currentStep)?.label}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onCancel}
              className="px-3 py-1.5 text-xs font-bold text-gray-500 hover:text-white hover:bg-gray-800 rounded-md transition-all border border-gray-800"
            >
              초기화
            </button>
          </div>
        </div>
      </div>

      {/* Horizontal Timeline Context Bar with spacing from header */}
      <div className="bg-[#0f0f0f] border-t border-gray-800 px-8 pt-10 pb-4 flex items-start justify-center gap-4 overflow-x-auto custom-scrollbar">
        {/* Step 1: Universe */}
        <div 
          onClick={() => setCurrentStep(1)}
          className="relative flex flex-col items-center gap-3 shrink-0 group cursor-pointer hover:bg-white/10 p-2 rounded-xl transition-all duration-200 active:scale-95"
        >
          <span className="absolute -top-6 text-xs text-gray-500 font-semibold tracking-wider">유니버스</span>
          <div className={`relative flex items-center justify-center w-10 h-10 rounded-full border-2 transition-all ${
            universe ? "border-blue-500 bg-blue-500/10" : "border-gray-700 bg-gray-800"
          }`}>
            <GlobeAltIcon className={`w-5 h-5 ${universe ? "text-blue-400" : "text-gray-500"}`} />
            {universe && (
              <div className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-blue-500 border border-[#0f0f0f] flex items-center justify-center">
                <CheckIcon className="w-2.5 h-2.5 text-white" />
              </div>
            )}
          </div>
          <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-3 min-w-[180px] min-h-[64px] flex flex-col items-center justify-center">
            <span className={`text-sm font-bold ${universe ? "text-white" : "text-gray-600"}`}>
              {universe ? universe.toUpperCase() : "미선택"}
            </span>
            {universe && (
              <div className="flex flex-wrap justify-center gap-x-1 mt-1 leading-tight">
                <span className="text-[10px] text-gray-500 whitespace-nowrap">시총 {universeFilters.marketCapRange[0]}~{universeFilters.marketCapRange[1]}%</span>
                {universeFilters.minTradingVolume > 0 && (
                   <span className="text-[10px] text-gray-500 whitespace-nowrap">· {universeFilters.minTradingVolume}억↑</span>
                )}
                {universeFilters.selectedSectors.length > 0 && (
                   <span className="text-[10px] text-gray-500 whitespace-nowrap">· 섹터({universeFilters.selectedSectors.length})</span>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Connector Line */}
        <div className="h-10 flex items-center shrink-0">
          <div className="w-8 h-0.5 bg-gray-800" />
        </div>

        {/* Step 2: Signal Blocks */}
        <div 
          onClick={() => setCurrentStep(2)}
          className="relative flex flex-col items-center gap-3 shrink-0 group cursor-pointer hover:bg-white/10 p-2 rounded-xl transition-all duration-200 active:scale-95"
        >
          <span className="absolute -top-6 text-xs text-gray-500 font-semibold tracking-wider">매매 조건</span>
          <div className={`relative flex items-center justify-center w-10 h-10 rounded-full border-2 transition-all ${
            canvasBlocks.length > 0 ? "border-red-500 bg-red-500/10" : "border-gray-700 bg-gray-800"
          }`}>
            <CubeIcon className={`w-5 h-5 ${canvasBlocks.length > 0 ? "text-red-400" : "text-gray-500"}`} />
            {canvasBlocks.length > 0 && (
              <div className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-red-500 border border-[#0f0f0f] flex items-center justify-center">
                <span className="text-[9px] font-bold text-white">{canvasBlocks.length}</span>
              </div>
            )}
          </div>
          <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-3 min-w-[180px] min-h-[64px] flex flex-col justify-start">
            {canvasBlocks.length > 0 ? (
              <div className="flex flex-col gap-2">
                {/* Entry Blocks */}
                {canvasBlocks.filter(b => b.type === "entry" || b.type === "filter").length > 0 && (
                  <div className="flex items-start gap-2">
                    <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 font-medium h-fit mt-0.5">
                      매수
                    </span>
                    <div className="flex flex-col">
                      <span className="text-xs text-gray-300 truncate w-[100px]">
                        {canvasBlocks.filter(b => b.type === "entry" || b.type === "filter").map(b => signalBlocks[b.blockId]?.name || b.blockId).join(", ")}
                      </span>
                    </div>
                  </div>
                )}
                {/* Exit Blocks */}
                {canvasBlocks.filter(b => b.type === "exit").length > 0 && (
                  <div className="flex items-start gap-2">
                    <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 font-medium h-fit mt-0.5">
                      매도
                    </span>
                    <div className="flex flex-col">
                      <span className="text-xs text-gray-300 truncate w-[100px]">
                        {canvasBlocks.filter(b => b.type === "exit").map(b => signalBlocks[b.blockId]?.name || b.blockId).join(", ")}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            ) : (
               <div className="flex justify-center items-center h-full">
                 <span className="text-sm text-gray-600 font-medium">설정 안됨</span>
               </div>
            )}
          </div>
        </div>

        {/* Connector Line */}
        <div className="h-10 flex items-center shrink-0">
          <div className="w-8 h-0.5 bg-gray-800" />
        </div>

        {/* Step 3: Position */}
        <div 
          onClick={() => setCurrentStep(3)}
          className={`relative flex flex-col items-center gap-3 shrink-0 transition-all cursor-pointer hover:bg-white/10 p-2 rounded-xl active:scale-95 ${currentStep >= 3 ? "opacity-100" : "opacity-40"}`}
        >
          <span className="absolute -top-6 text-xs text-gray-500 font-semibold tracking-wider">포지션</span>
          <div className={`relative flex items-center justify-center w-10 h-10 rounded-full border-2 transition-all ${
            currentStep >= 3 ? "border-emerald-500 bg-emerald-500/10" : "border-gray-700 bg-gray-800"
          }`}>
            <ChartPieIcon className={`w-5 h-5 ${currentStep >= 3 ? "text-emerald-400" : "text-gray-500"}`} />
          </div>
          <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-3 min-w-[180px] min-h-[64px] flex flex-col justify-start">
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-gray-400 font-bold uppercase tracking-tight">수량</span>
                <span className="text-xs text-white font-bold">{maxPositions}개</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-gray-400 font-bold uppercase tracking-tight">배분</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 font-medium">
                  {allocationType === "equal" ? "동일" : `${allocationValue}%`}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Connector Line */}
        <div className="h-10 flex items-center shrink-0">
          <div className="w-8 h-0.5 bg-gray-800" />
        </div>

        {/* Step 4: Risk */}
        <div 
          onClick={() => setCurrentStep(4)}
          className={`relative flex flex-col items-center gap-3 shrink-0 transition-all cursor-pointer hover:bg-white/10 p-2 rounded-xl active:scale-95 ${currentStep >= 4 ? "opacity-100" : "opacity-40"}`}
        >
          <span className="absolute -top-6 text-xs text-gray-500 font-semibold tracking-wider">리스크</span>
          <div className={`relative flex items-center justify-center w-10 h-10 rounded-full border-2 transition-all ${
            currentStep >= 4 ? "border-orange-500 bg-orange-500/10" : "border-gray-700 bg-gray-800"
          }`}>
            <ShieldCheckIcon className={`w-5 h-5 ${currentStep >= 4 ? "text-orange-400" : "text-gray-500"}`} />
          </div>
          <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-3 min-w-[180px] min-h-[64px] flex flex-col justify-start">
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-gray-400 font-bold uppercase tracking-tight">손절</span>
                <span className="text-xs text-red-400 font-bold">{riskManagement.max_daily_loss_pct}%</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-gray-400 font-bold uppercase tracking-tight">노출</span>
                <span className="text-xs text-blue-400 font-bold">{riskManagement.max_total_exposure_pct}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* Connector Line */}
        <div className="h-10 flex items-center shrink-0">
          <div className="w-8 h-0.5 bg-gray-800" />
        </div>

        {/* Step 5: Backtest */}
        <div 
          onClick={() => setCurrentStep(5)}
          className={`relative flex flex-col items-center gap-3 shrink-0 transition-all cursor-pointer hover:bg-white/10 p-2 rounded-xl active:scale-95 ${currentStep >= 5 ? "opacity-100" : "opacity-40"}`}
        >
          <span className="absolute -top-6 text-xs text-gray-500 font-semibold tracking-wider">백테스트</span>
          <div className={`relative flex items-center justify-center w-10 h-10 rounded-full border-2 transition-all ${
            currentStep >= 5 ? "border-blue-500 bg-blue-500/10" : "border-gray-700 bg-gray-800"
          }`}>
            <PlayCircleIcon className={`w-5 h-5 ${currentStep >= 5 ? "text-blue-400" : "text-gray-500"}`} />
          </div>
          <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-3 min-w-[180px] min-h-[64px] flex flex-col items-center justify-center">
             <div className="flex flex-col items-center">
               <span className="text-[10px] text-gray-400 font-bold uppercase tracking-tight">성과 요약</span>
               <span className={`text-xs font-bold mt-1 ${backtestResult ? (backtestResult.totalReturn >= 0 ? "text-red-400" : "text-blue-400") : "text-gray-600"}`}>
                 {backtestResult ? `${backtestResult.totalReturn.toFixed(1)}%` : "대기 중"}
               </span>
             </div>
          </div>
        </div>
      </div>

      <div className="flex-1 flex min-h-0 overflow-hidden">
        {currentStep === 2 ? (
          <Step2Conditions
            canvasBlocks={canvasBlocks}
            setCanvasBlocks={setCanvasBlocks}
            selectedBlock={selectedBlock}
            setSelectedBlock={setSelectedBlock}
            activeParamTab={activeParamTab}
            setActiveParamTab={setActiveParamTab}
            entryLogic={entryLogic}
            setEntryLogic={setEntryLogic}
            exitLogic={exitLogic}
            setExitLogic={setExitLogic}
            unlockedBlockIds={unlockedBlockIds}
            setUnlockedBlockIds={setUnlockedBlockIds}
            manuallyHiddenBlockIds={manuallyHiddenBlockIds}
            setManuallyHiddenBlockIds={setManuallyHiddenBlockIds}
            customBlockOrder={customBlockOrder}
            setCustomBlockOrder={setCustomBlockOrder}
            customCategoryOrder={customCategoryOrder}
            setCustomCategoryOrder={setCustomCategoryOrder}
            hoveredInfo={hoveredInfo}
            setHoveredInfo={setHoveredInfo}
            hoveredParam={hoveredParam}
            setHoveredParam={setHoveredParam}
            hoveredEditIcon={hoveredEditIcon}
            setHoveredEditIcon={setHoveredEditIcon}
            isSearchMenuOpen={isSearchMenuOpen}
            setIsSearchMenuOpen={setIsSearchMenuOpen}
            isLibraryManagementOpen={isLibraryManagementOpen}
            setIsLibraryManagementOpen={setIsLibraryManagementOpen}
            activeMgmtCategory={activeMgmtCategory}
            setActiveMgmtCategory={setActiveMgmtCategory}
            draggedModalItemIndex={draggedModalItemIndex}
            setDraggedModalItemIndex={setDraggedModalItemIndex}
            draggedCategoryIndex={draggedCategoryIndex}
            setDraggedCategoryIndex={setDraggedCategoryIndex}
            openSignalGroups={openSignalGroups}
            setOpenSignalGroups={setOpenSignalGroups}
            savedFeedback={savedFeedback}
            setSavedFeedback={setSavedFeedback}
            canvasRef={canvasRef}
            canvasWidth={canvasWidth}
            onNext={() => setCurrentStep(3)}
            onPrev={() => setCurrentStep(1)}
            handleAddBlock={handleAddBlock}
            handleRemoveBlockFromBin={handleRemoveBlockFromBin}
          />
        ) : (
          <div className="flex-1 bg-[#0f0f0f] relative overflow-y-auto">
            {currentStep === 1 && (
              <Step1Universe
                strategyName={strategyName}
                setStrategyName={setStrategyName}
                universe={universe}
                setUniverse={setUniverse}
                universeFilters={universeFilters}
                setUniverseFilters={setUniverseFilters}
                sectorSearchTerm={sectorSearchTerm}
                setSectorSearchTerm={setSectorSearchTerm}
                onNext={() => setCurrentStep(2)}
              />
            )}

            {currentStep === 3 && (
            <div className="flex flex-col min-h-full">
              <div className="space-y-6 p-8">
               <div className="flex items-center justify-between mb-6">
                 <div>
                   <h3 className="text-xl font-black text-white tracking-tight">포지션 & 비중 설정</h3>
                   <p className="text-sm text-gray-500 mt-1 font-medium">
                     자산 배분 방식과 매매 체결 시점, 리밸런싱 주기를 구성합니다.
                   </p>
                 </div>
               </div>

                <div className="bg-[#0f0f0f] rounded-2xl border border-gray-800/50 p-8 min-h-[580px] max-w-5xl mx-auto shadow-2xl">
                 <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                   {/* Section 1: Capital & Max Positions */}
                   <div className="space-y-6">
                     <div className="flex items-center gap-3.5 mb-2">
                       <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center border border-blue-500/20 shadow-inner">
                         <BanknotesIcon className="w-5 h-5 text-blue-400" />
                       </div>
                       <div>
                         <h4 className="text-md font-black text-white">자산 및 포트폴리오</h4>
                         <p className="text-[11px] text-gray-500">운용 규모와 분산 투자 범위를 설정합니다.</p>
                       </div>
                     </div>
                     
                     <div className="space-y-6 bg-[#0a0a0a]/40 p-6 rounded-2xl border border-gray-800/40 backdrop-blur-sm">
                       <div>
                         <label className="text-[10px] text-gray-500 font-black mb-2.5 block uppercase tracking-widest">초기 자본금</label>
                         <div className="relative group">
                           <input 
                             type="number" 
                             value={initialCapital}
                             onChange={(e) => setInitialCapital(Number(e.target.value))}
                             className="w-full bg-[#0a0a0a] border border-gray-800 rounded-xl px-5 py-3.5 text-white font-black text-lg focus:border-blue-500/50 focus:ring-4 focus:ring-blue-500/5 outline-none transition-all group-hover:border-gray-700"
                           />
                           <span className="absolute right-5 top-1/2 -translate-y-1/2 text-gray-600 font-bold text-sm">KRW</span>
                         </div>
                       </div>
                       
                       <div>
                         <div className="flex justify-between items-end mb-3">
                           <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest">최대 보유 종목 수</label>
                           <span className="text-lg font-black text-blue-400">{maxPositions}<span className="text-xs ml-0.5 text-gray-500">개</span></span>
                         </div>
                         <div className="flex items-center gap-4">
                           <input 
                             type="range" 
                             min="1" 
                             max="100" 
                             value={maxPositions}
                             onChange={(e) => setMaxPositions(Number(e.target.value))}
                             className="flex-1 h-2 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
                           />
                         </div>
                         <p className="text-[10px] text-gray-500 mt-3 font-medium">동시에 최대 {maxPositions}개의 종목까지 매수합니다.</p>
                       </div>
                     </div>
                   </div>

                   {/* Section 2: Allocation Strategy */}
                   <div className="space-y-6">
                     <div className="flex items-center gap-3.5 mb-2">
                       <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center border border-red-500/20 shadow-inner">
                         <ChartPieIcon className="w-5 h-5 text-red-400" />
                       </div>
                       <div>
                         <h4 className="text-md font-black text-white">비중 배분 정책</h4>
                         <p className="text-[11px] text-gray-500">개별 종목당 자산 투입 비중을 결정합니다.</p>
                       </div>
                     </div>

                     <div className="space-y-6 bg-[#0a0a0a]/40 p-6 rounded-2xl border border-gray-800/40 backdrop-blur-sm">
                       <div className="flex p-1 bg-[#0a0a0a] rounded-xl border border-gray-800">
                         <button 
                           onClick={() => setAllocationType("equal")}
                           className={`flex-1 py-2.5 rounded-lg text-xs font-black transition-all ${
                             allocationType === "equal" 
                               ? "bg-red-500 text-white shadow-lg shadow-red-900/40" 
                               : "text-gray-500 hover:text-gray-300"
                           }`}
                         >
                           동일 비중
                         </button>
                         <button 
                           onClick={() => setAllocationType("fixed_pct")}
                           className={`flex-1 py-2.5 rounded-lg text-xs font-black transition-all ${
                             allocationType === "fixed_pct" 
                               ? "bg-red-500 text-white shadow-lg shadow-red-900/40" 
                               : "text-gray-500 hover:text-gray-300"
                           }`}
                         >
                           고정 비중 (%)
                         </button>
                       </div>

                       <div className="min-h-[80px]">
                         {allocationType === "fixed_pct" ? (
                           <div className="animate-in fade-in slide-in-from-top-2 duration-300">
                             <div className="flex justify-between items-end mb-3">
                               <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest">종목당 투입 비중</label>
                               <span className="text-lg font-black text-red-400">{allocationValue}<span className="text-xs ml-0.5 text-gray-500">%</span></span>
                             </div>
                             <div className="flex items-center gap-4">
                               <input 
                                 type="range" 
                                 min="1" 
                                 max="100" 
                                 value={allocationValue}
                                 onChange={(e) => setAllocationValue(Number(e.target.value))}
                                 className="flex-1 h-2 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-red-500"
                               />
                             </div>
                             <p className="text-[10px] text-gray-500 mt-3 font-medium">거래 건마다 가용 자산의 {allocationValue}%를 고정적으로 투자합니다.</p>
                           </div>
                         ) : (
                           <div className="animate-in fade-in duration-300">
                             <div className="p-4 bg-red-500/5 border border-red-500/10 rounded-xl">
                               <p className="text-[11px] text-red-400/80 leading-relaxed font-bold italic">
                                 "최대 보유 종목 수({maxPositions}개)에 맞춰 모든 자산을 균등하게 배분합니다. 종목당 배정 목표는 약 {Number(100/maxPositions).toFixed(1)}% 입니다."
                               </p>
                             </div>
                           </div>
                         )}
                       </div>
                     </div>
                   </div>

                   {/* Section 3: Execution Timing */}
                   <div className="space-y-6">
                     <div className="flex items-center gap-3.5 mb-2">
                       <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center border border-orange-500/20 shadow-inner">
                         <ClockIcon className="w-5 h-5 text-orange-400" />
                       </div>
                       <div>
                         <h4 className="text-md font-black text-white">체결 시점 선택</h4>
                         <p className="text-[11px] text-gray-500">조건 충족 시 실제 주문이 나가는 타이밍입니다.</p>
                       </div>
                     </div>

                     <div className="grid grid-cols-1 gap-3 bg-[#1a1a1a]/40 p-6 rounded-2xl border border-gray-800/40 backdrop-blur-sm">
                       <button 
                         onClick={() => setExecutionTiming("next_open")}
                         className={`px-5 py-4 rounded-xl border transition-all text-left flex items-start gap-4 ${
                           executionTiming === "next_open"
                             ? "bg-orange-500/10 border-orange-500/30 ring-1 ring-orange-500/20"
                             : "bg-[#0a0a0a] border-gray-800 hover:border-gray-700"
                         }`}
                       >
                         <div className={`w-2 h-2 rounded-full mt-1.5 ${executionTiming === "next_open" ? "bg-orange-400 animate-pulse" : "bg-gray-700"}`} />
                         <div>
                           <div className={`text-sm font-black mb-1 ${executionTiming === "next_open" ? "text-orange-400" : "text-gray-400"}`}>익일 시가 (Next Open)</div>
                           <div className="text-[11px] text-gray-500 leading-tight">신호가 발생한 다음 영업일 아침 시가에 즉시 체결합니다. 가장 일반적인 방식입니다.</div>
                         </div>
                       </button>
                       <button 
                         onClick={() => setExecutionTiming("current_close")}
                         className={`px-5 py-4 rounded-xl border transition-all text-left flex items-start gap-4 ${
                           executionTiming === "current_close"
                             ? "bg-orange-500/10 border-orange-500/30 ring-1 ring-orange-500/20"
                             : "bg-[#0a0a0a] border-gray-800 hover:border-gray-700"
                         }`}
                       >
                         <div className={`w-2 h-2 rounded-full mt-1.5 ${executionTiming === "current_close" ? "bg-orange-400 animate-pulse" : "bg-gray-700"}`} />
                         <div>
                           <div className={`text-sm font-black mb-1 ${executionTiming === "current_close" ? "text-orange-400" : "text-gray-400"}`}>당일 종가 (Direct Close)</div>
                           <div className="text-[11px] text-gray-500 leading-tight">신호가 발생한 당일 장 마감 직전 종가로 체결합니다. 빠른 대응이 가능합니다.</div>
                         </div>
                       </button>
                     </div>
                   </div>

                   {/* Section 4: Rebalancing */}
                   <div className="space-y-6">
                     <div className="flex items-center gap-3.5 mb-2">
                       <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20 shadow-inner">
                         <ArrowPathIcon className="w-5 h-5 text-emerald-400" />
                       </div>
                       <div>
                         <h4 className="text-md font-black text-white">리밸런싱 설정</h4>
                         <p className="text-[11px] text-gray-500">보유 종목의 비중을 정기적으로 재조정합니다.</p>
                       </div>
                     </div>

                     <div className="bg-[#1a1a1a]/40 p-6 rounded-2xl border border-gray-800/40 backdrop-blur-sm">
                       <div className="flex p-1 bg-[#0a0a0a] rounded-xl border border-gray-800 mb-5">
                         {[
                           { id: "none", label: "안함" },
                           { id: "daily", label: "매일" },
                           { id: "weekly", label: "매주" },
                           { id: "monthly", label: "매월" }
                         ].map((period) => (
                           <button
                             key={period.id}
                             onClick={() => setRebalancingPeriod(period.id as any)}
                             className={`flex-1 py-2.5 rounded-lg text-xs font-black transition-all ${
                               rebalancingPeriod === period.id
                                 ? "bg-emerald-500 text-white shadow-lg shadow-emerald-900/40"
                                 : "text-gray-500 hover:text-gray-300"
                             }`}
                           >
                             {period.label}
                           </button>
                         ))}
                       </div>
                       <div className="p-4 bg-emerald-500/5 border border-emerald-500/10 rounded-xl">
                         <p className="text-[11px] text-emerald-400/80 leading-relaxed font-medium">
                           {rebalancingPeriod === "none" 
                             ? "💡 포지션 진입 시점의 비중을 그대로 유지하며 별도의 도중 조정을 하지 않습니다."
                             : `💡 정해진 주기(${rebalancingPeriod === "daily" ? "매일" : rebalancingPeriod === "weekly" ? "매주" : "매월"})마다 포트폴리오 비중을 배분 정책에 맞춰 다시 계산합니다.`}
                         </p>
                       </div>
                     </div>
                   </div>
                 </div>
               </div>

                <div className="sticky bottom-0 bg-[#0f0f0f]/90 backdrop-blur-xl border-t border-gray-800/50 p-6 flex justify-end gap-3 z-50 mt-auto">
                 <button
                   onClick={() => setCurrentStep(2)}
                   className="px-6 py-3 bg-[#0a0a0a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 hover:text-white transition-all flex items-center gap-2 shadow-xl"
                 >
                   <ArrowLeftIcon className="w-5 h-5" />
                   이전 단계
                 </button>
                 <button
                   onClick={() => setCurrentStep(4)}
                   className="px-8 py-3 bg-blue-600 text-white rounded-xl text-md font-black hover:bg-blue-500 transition-all flex items-center gap-3 shadow-xl shadow-blue-900/40 hover:scale-[1.02]"
                 >
                   다음 단계 <ArrowRightIcon className="w-5 h-5" />
                 </button>
               </div>
              </div>
            </div>
          )}

          {currentStep === 4 && (
            <div className="flex flex-col min-h-full">
              <div className="space-y-6 p-8">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h3 className="text-xl font-black text-white tracking-tight">리스크 관리</h3>
                    <p className="text-sm text-gray-500 mt-1 font-medium">
                      손절매, 익절매 등 자산 보호를 위한 규칙을 설정합니다.
                    </p>
                  </div>
                </div>
              <div className="bg-[#0f0f0f] rounded-2xl border border-gray-800/50 p-8 min-h-[580px] max-w-5xl mx-auto flex items-center justify-center shadow-2xl">
                 <div className="text-center">
                   <div className="w-16 h-16 rounded-2xl bg-orange-500/10 flex items-center justify-center border border-orange-500/20 mx-auto mb-4">
                     <ShieldCheckIcon className="w-8 h-8 text-orange-400" />
                   </div>
                   <h4 className="text-lg font-bold text-white mb-2">리스크 규칙 구성</h4>
                    <p className="text-sm text-gray-500 max-w-sm">여기에 리스크 관리 블록들이 배치될 예정입니다.</p>
                  </div>
               </div>
             </div>

              {/* Sticky Navigation Footer */}
              <div className="sticky bottom-0 bg-[#0a0a0a]/90 backdrop-blur-xl border-t border-gray-800/50 p-6 flex justify-end gap-3 z-50 mt-auto">
                <button
                  onClick={() => setCurrentStep(3)}
                  className="px-6 py-3 bg-[#0a0a0a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 hover:text-white transition-all flex items-center gap-2"
                >
                  <ArrowLeftIcon className="w-5 h-5" />
                  이전 단계
                </button>
                <button
                  onClick={() => setCurrentStep(5)}
                  className="px-8 py-3 bg-blue-600 text-white rounded-xl text-md font-black hover:bg-blue-500 transition-all flex items-center gap-3 shadow-xl shadow-blue-900/40 hover:scale-[1.02]"
                >
                  다음: 미리보기
                  <ArrowRightIcon className="w-5 h-5" />
                </button>
              </div>
            </div>
          )}

          {currentStep === 5 && (
            <div className="flex flex-col p-8 gap-6">
              <div className="flex items-center justify-between shrink-0 mb-4"><div><h3 className="text-xl font-black text-white">전략 검증</h3><p className="text-sm text-gray-500 mt-1 font-medium">결과를 확인하고 전략을 최종 점검하세요.</p></div></div>
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 flex-1 min-h-0">
                <div className="xl:col-span-2 space-y-4">
                  <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4">
                    <div className="h-72 bg-[#0a0a0f] rounded border border-gray-800 overflow-hidden relative">
                      {backtestResult ? (
                        <BacktestChart type="equity" height={288} equityData={backtestResult.dates.map((d: string, i: number) => ({ time: d, equity: backtestResult.equity[i], buyHold: backtestResult.initialCapital * (1 + (backtestResult.buyAndHoldReturn || 0)/100) }))} />
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center text-gray-500 text-sm">{isBacktesting ? "시뮬레이션 중..." : "결과 없음"}</div>
                      )}
                    </div>
                  </div>
                  <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4"><h4 className="text-sm font-semibold text-white mb-3">로그</h4><div className="space-y-2 pr-2 custom-scrollbar">{/* Logs... */}</div></div>
                </div>
                <div className="space-y-4">
                  <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4">
                    <h4 className="text-sm font-semibold text-white mb-3">성과</h4>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div className="p-3 rounded bg-[#0a0a0a] border border-gray-800"><div className="text-xs text-gray-400 mb-1">수익률</div><div className={`text-lg font-bold ${(backtestResult?.totalReturn || 0) >= 0 ? "text-red-400" : "text-blue-400"}`}>{backtestResult?.totalReturn.toFixed(1)}%</div></div>
                      <div className="p-3 rounded bg-[#0a0a0a] border border-gray-800"><div className="text-xs text-gray-400 mb-1">MDD</div><div className="text-lg font-bold text-blue-400">{backtestResult?.maxDrawdown.toFixed(1)}%</div></div>
                    </div>
                  </div>
                  <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4 space-y-4">
                    <div className="flex items-center gap-2 text-green-400 mb-1"><CheckCircleIcon className="w-5 h-5" /><span className="text-sm font-bold uppercase tracking-wider">검증 종료</span></div>
                    <p className="text-xs text-gray-500 leading-relaxed">전략을 저장하고 테스트를 시작할 수 있습니다.</p>
                  </div>
                </div>
              </div>
              <div className="p-8 flex justify-end gap-3 mt-auto sticky bottom-0 bg-[#0f0f0f]/90 backdrop-blur-md z-20">
                <button onClick={() => setCurrentStep(4)} className="px-6 py-3 bg-[#0a0a0a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 transition-all flex items-center gap-2">
                  <ArrowLeftIcon className="w-5 h-5" /> 이전 단계
                </button>
                <button onClick={handleSave} className="px-8 py-3 bg-red-600 text-white rounded-xl text-md font-black hover:bg-red-500 transition-all flex items-center gap-3 shadow-xl shadow-red-900/40">
                  전략 저장 <ArrowRightIcon className="w-5 h-5" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
      </div>
      {/* Global Library Management Modal */}
    </div>
  );
}
