"use client";

import { useState, useEffect, useCallback, useRef, Fragment } from "react";
import {
  XMarkIcon,
  PlayCircleIcon,
  DocumentArrowDownIcon,
  CheckCircleIcon,
  ArrowRightIcon,
  ArrowLeftIcon,
  SparklesIcon,
  AdjustmentsHorizontalIcon,
  ChartBarIcon,
  CubeIcon,
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
  EllipsisHorizontalIcon,
  CursorArrowRaysIcon,
} from "@heroicons/react/24/outline";
import { StrategyDSL, Condition, ConditionType, LogicOperator, BacktestResult, CanvasBlock, RiskManagement } from "@/types/strategy";
import { signalBlocks } from "@/lib/strategy-blocks";
import { BacktestEngine } from "@/lib/strategy/BacktestEngine";
import BacktestChart from "@/components/strategy/BacktestChart";
import RiskManagementEditor from "./RiskManagementEditor";
import Step1Universe from "./steps/Step1Universe";
import Step2Conditions from "./steps/Step2Conditions";
import Step3Position from "./steps/Step3Position";
import Step4Risk from "./steps/Step4Risk";
import Step5Backtest from "./steps/Step5Backtest";

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
  const [rebalancingPeriod, setRebalancingPeriod] = useState<string>("none");

  const [positionRules, setPositionRules] = useState<any[]>([]);
  const [entryLogic, setEntryLogic] = useState<LogicOperator>("AND");
  const [exitLogic, setExitLogic] = useState<LogicOperator>("OR");
  const [riskManagement, setRiskManagement] = useState<RiskManagement>({
    position_size_pct: 5,
    max_positions: 10,
    stop_loss_pct: 10,
    take_profit_pct: 20,
    trailing_stop_pct: 0,
    max_holding_days: 0,
    max_daily_loss_pct: 5,
    max_total_exposure_pct: 50,
    max_sector_exposure_pct: 30,
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
      const engine = new BacktestEngine();
      const result = await engine.run(strategy, "1Y");
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
        stop_loss_pct: initialStrategy.risk.stop_loss_pct ?? 10,
        take_profit_pct: initialStrategy.risk.take_profit_pct ?? 20,
        trailing_stop_pct: initialStrategy.risk.trailing_stop_pct ?? 0,
        max_holding_days: initialStrategy.risk.max_holding_days ?? 0,
        max_daily_loss_pct: initialStrategy.risk.max_daily_loss_pct ?? 5,
        max_total_exposure_pct: initialStrategy.risk.max_total_exposure_pct ?? 50,
        max_sector_exposure_pct: initialStrategy.risk.max_sector_exposure_pct ?? 30,
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
      <div className="bg-[#0f0f0f] border-t border-gray-800 px-8 pt-10 pb-4 flex items-start justify-center gap-4">
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
                <span className="text-[10px] text-gray-400 font-bold uppercase tracking-tight">손절/익절</span>
                <span className="text-xs text-orange-400 font-bold">-{riskManagement.stop_loss_pct}% / +{riskManagement.take_profit_pct}%</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-gray-400 font-bold uppercase tracking-tight">최대 노출</span>
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
              <Step3Position
                initialCapital={initialCapital}
                setInitialCapital={setInitialCapital}
                maxPositions={maxPositions}
                setMaxPositions={setMaxPositions}
                allocationType={allocationType}
                setAllocationType={setAllocationType}
                allocationValue={allocationValue}
                setAllocationValue={setAllocationValue}
                executionTiming={executionTiming}
                setExecutionTiming={setExecutionTiming}
                rebalancingPeriod={rebalancingPeriod}
                setRebalancingPeriod={setRebalancingPeriod}
                onNext={() => setCurrentStep(4)}
                onPrev={() => setCurrentStep(2)}
              />
            )}

          {currentStep === 4 && (
            <Step4Risk
              riskManagement={riskManagement}
              setRiskManagement={setRiskManagement}
              onNext={() => setCurrentStep(5)}
              onPrev={() => setCurrentStep(3)}
            />
          )}

          {currentStep === 5 && (
            <Step5Backtest
              strategyName={strategyName}
              backtestResult={backtestResult}
              isBacktesting={isBacktesting}
              onPrev={() => setCurrentStep(4)}
              onSave={handleSave}
            />
          )}
        </div>
      )}
      </div>
      {/* Global Library Management Modal */}
    </div>
  );
}
