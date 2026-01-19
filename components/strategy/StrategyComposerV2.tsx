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
import { BacktestService } from "@/lib/strategy/BacktestService";
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
    min_cash_reserve_pct: 10,
    max_daily_buy_pct: 20,
    stop_loss_pct: 10,
    take_profit_pct: 20,
    trailing_stop_pct: 0,
    max_holding_days: 0,
    max_daily_loss_pct: 5,
    max_total_exposure_pct: 50,
    max_sector_exposure_pct: 30,
    max_mdd_limit_pct: 15,
  });
  // Canvas state
  const [canvasBlocks, setCanvasBlocks] = useState<CanvasBlock[]>([]);
  const [selectedBlock, setSelectedBlock] = useState<CanvasBlock | null>(null);
  const [activeParamTab, setActiveParamTab] = useState<'block' | 'global'>('block');
  const [editingBlock, setEditingBlock] = useState<CanvasBlock | null>(null);
  const [draggedOver, setDraggedOver] = useState(false);
  
  // Backtest Preview State
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [isBacktesting, setIsBacktesting] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);
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
  const [reorderDragItem, setReorderDragItem] = useState<{ type: 'category' | 'block', id: string, index: number, categoryId?: string } | null>(null);
  const [isBacktestDashboard, setIsBacktestDashboard] = useState(false);

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

  // Reset backtest dashboard state when leaving step 5
  useEffect(() => {
    if (currentStep !== 5) {
      setIsBacktestDashboard(false);
    }
  }, [currentStep]);

  // Reset scroll to top when changing steps
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
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

    setActiveParamTab('block');
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

  const runSimulation = useCallback(async (options: any) => {
    console.error("[DEBUG] StrategyComposerV2: runSimulation CALLED with options:", options);
    try {
      setIsBacktesting(true);
      setBacktestError(null);
      
      console.error("[DEBUG] StrategyComposerV2: Preparing strategy payload...");

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
        universe: {
          id: universe,
          filters: universeFilters
        },
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

      const engine = new BacktestService();
      const result = await engine.run(strategy, options);
      setBacktestResult(result);
    } catch (e: any) {
      console.error("Backtest Error:", e);
      setBacktestError(e.message || "백테스트 중 알 수 없는 오류가 발생했습니다.");
    } finally {
      setIsBacktesting(false);
    }
  }, [strategyName, universe, canvasBlocks, riskManagement, entryLogic, exitLogic, universeFilters]);

  // Trigger simulation when entering step 5




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
        min_cash_reserve_pct: initialStrategy.risk.min_cash_reserve_pct ?? 10,
        max_daily_buy_pct: initialStrategy.risk.max_daily_buy_pct ?? 20,
        stop_loss_pct: initialStrategy.risk.stop_loss_pct ?? 10,
        take_profit_pct: initialStrategy.risk.take_profit_pct ?? 20,
        trailing_stop_pct: initialStrategy.risk.trailing_stop_pct ?? 0,
        max_holding_days: initialStrategy.risk.max_holding_days ?? 0,
        max_daily_loss_pct: initialStrategy.risk.max_daily_loss_pct ?? 5,
        max_total_exposure_pct: initialStrategy.risk.max_total_exposure_pct ?? 50,
        max_sector_exposure_pct: initialStrategy.risk.max_sector_exposure_pct ?? 30,
        max_mdd_limit_pct: initialStrategy.risk.max_mdd_limit_pct ?? 15,
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
      universe: {
        id: universe,
        filters: universeFilters,
      },
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
    { num: 5, label: "백테스트" },
  ];


  return (
    <div className={`flex flex-col bg-[#050505] transition-all duration-500 relative min-h-screen`}>
      <div className="flex-1 flex flex-col relative z-10">
      {/* Top Header Bar */}
      <div className="bg-[#0f0f0f] px-8 py-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6 flex-1">
            <div className="flex items-center gap-4">
              <span className="text-3xl font-black text-white tracking-tight">
                {strategyName || (currentStep === 1 ? "새로운 전략 개요" : "이름 없는 전략")}
              </span>
              <span className="px-3 py-1 rounded-lg bg-white/10 text-gray-300 text-xs font-bold uppercase tracking-[0.15em] border border-white/5">
                {stepLabels.find(s => s.num === currentStep)?.label}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={onCancel}
              className="px-4 py-2 text-sm font-bold text-gray-400 hover:text-white hover:bg-white/5 rounded-xl transition-all border border-white/10"
            >
              초기화
            </button>
          </div>
        </div>
      </div>

      {/* Horizontal Timeline Context Bar with spacing from header */}
      {!(currentStep === 5 && isBacktestDashboard) && (
        <div className="bg-[#0f0f0f] px-8 pt-6 pb-6">
        <div className="max-w-full mx-auto flex items-center justify-between gap-0">
          {/* Step 1: Universe */}
          <div 
            onClick={() => setCurrentStep(1)}
            className={`relative flex flex-col items-center gap-2 group cursor-pointer px-6 py-3 rounded-[24px] transition-all duration-300 border backdrop-blur-md min-w-[160px] ${
              currentStep === 1 
                ? "bg-white/10 border-white/20 shadow-lg" 
                : "bg-white/[0.03] border-white/5 hover:border-white/10 hover:bg-white/5"
            }`}
          >
            <span className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Step 01</span>
            <div className="flex items-center gap-3">
              <div className={`flex items-center justify-center w-8 h-8 rounded-full border transition-all ${
                universe ? "border-white/40 bg-white/10" : "border-gray-800 bg-gray-900"
              }`}>
                <GlobeAltIcon className={`w-4 h-4 ${universe ? "text-white" : "text-gray-600"}`} />
              </div>
              <span className={`text-sm font-black tracking-tight ${universe ? "text-white" : "text-gray-600"}`}>
                {universe ? universe.toUpperCase() : "유니버스"}
              </span>
            </div>
          </div>

          {/* Connector 1-2 */}
          <div className="flex-1 px-4">
            <div className="h-[1px] w-full bg-white/10" />
          </div>

          {/* Step 2: Signal Blocks */}
          <div 
            onClick={() => setCurrentStep(2)}
            className={`relative flex flex-col items-center gap-2 group cursor-pointer px-6 py-3 rounded-[24px] transition-all duration-300 border backdrop-blur-md min-w-[160px] ${
              currentStep === 2 
                ? "bg-white/10 border-white/20 shadow-lg" 
                : "bg-white/[0.03] border-white/5 hover:border-white/10 hover:bg-white/5"
            }`}
          >
            <span className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Step 02</span>
            <div className="flex items-center gap-3">
              <div className={`flex items-center justify-center w-8 h-8 rounded-full border transition-all ${
                canvasBlocks.length > 0 ? "border-white/40 bg-white/10" : "border-gray-800 bg-gray-900"
              }`}>
                <CubeIcon className={`w-4 h-4 ${canvasBlocks.length > 0 ? "text-white" : "text-gray-600"}`} />
              </div>
              <span className={`text-sm font-black tracking-tight ${canvasBlocks.length > 0 ? "text-white" : "text-gray-600"}`}>
                매매 조건
              </span>
            </div>
          </div>

          {/* Connector 2-3 */}
          <div className="flex-1 px-4">
            <div className="h-[1px] w-full bg-white/10" />
          </div>

          {/* Step 3: Position */}
          <div 
            onClick={() => setCurrentStep(3)}
            className={`relative flex flex-col items-center gap-2 group cursor-pointer px-6 py-3 rounded-[24px] transition-all duration-300 border backdrop-blur-md min-w-[160px] ${
              currentStep === 3 
                ? "bg-white/10 border-white/20 shadow-lg" 
                : "bg-white/[0.03] border-white/5 hover:border-white/10 hover:bg-white/5"
            }`}
          >
            <span className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Step 03</span>
            <div className="flex items-center gap-3">
              <div className={`flex items-center justify-center w-8 h-8 rounded-full border transition-all ${
                currentStep >= 3 ? "border-white/40 bg-white/10" : "border-gray-800 bg-gray-900"
              }`}>
                <ChartPieIcon className={`w-4 h-4 ${currentStep >= 3 ? "text-white" : "text-gray-600"}`} />
              </div>
              <span className={`text-sm font-black tracking-tight ${currentStep >= 3 ? "text-white" : "text-gray-600"}`}>
                포지션/비중
              </span>
            </div>
          </div>

          {/* Connector 3-4 */}
          <div className="flex-1 px-4">
            <div className="h-[1px] w-full bg-white/10" />
          </div>

          {/* Step 4: Risk */}
          <div 
            onClick={() => setCurrentStep(4)}
            className={`relative flex flex-col items-center gap-2 group cursor-pointer px-6 py-3 rounded-[24px] transition-all duration-300 border backdrop-blur-md min-w-[160px] ${
              currentStep === 4 
                ? "bg-white/10 border-white/20 shadow-lg" 
                : "bg-white/[0.03] border-white/5 hover:border-white/10 hover:bg-white/5"
            }`}
          >
            <span className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Step 04</span>
            <div className="flex items-center gap-3">
              <div className={`flex items-center justify-center w-8 h-8 rounded-full border transition-all ${
                currentStep >= 4 ? "border-white/40 bg-white/10" : "border-gray-800 bg-gray-900"
              }`}>
                <ShieldCheckIcon className={`w-4 h-4 ${currentStep >= 4 ? "text-white" : "text-gray-600"}`} />
              </div>
              <span className={`text-sm font-black tracking-tight ${currentStep >= 4 ? "text-white" : "text-gray-600"}`}>
                리스크 관리
              </span>
            </div>
          </div>

          {/* Connector 4-5 */}
          <div className="flex-1 px-4">
            <div className="h-[1px] w-full bg-white/10" />
          </div>

          {/* Step 5: Backtest */}
          <div 
            onClick={() => setCurrentStep(5)}
            className={`relative flex flex-col items-center gap-2 group cursor-pointer px-6 py-3 rounded-[24px] transition-all duration-300 border backdrop-blur-md min-w-[160px] ${
              currentStep === 5 
                ? "bg-white/10 border-white/20 shadow-lg" 
                : "bg-white/[0.03] border-white/5 hover:border-white/10 hover:bg-white/5"
            }`}
          >
            <span className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Step 05</span>
            <div className="flex items-center gap-3">
              <div className={`flex items-center justify-center w-8 h-8 rounded-full border transition-all ${
                currentStep >= 5 ? "border-white/40 bg-white/10" : "border-gray-800 bg-gray-900"
              }`}>
                <PlayCircleIcon className={`w-4 h-4 ${currentStep >= 5 ? "text-white" : "text-gray-600"}`} />
              </div>
              <span className={`text-sm font-black tracking-tight ${currentStep >= 5 ? "text-white" : "text-gray-600"}`}>
                백테스트
              </span>
            </div>
          </div>
        </div>
      </div>
      )}

      <div className="flex-1 flex min-h-0 min-w-0">
        {currentStep === 2 ? (
          <div className="flex-1 flex flex-col min-w-0">
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
              reorderDragItem={reorderDragItem}
              setReorderDragItem={setReorderDragItem}
              canvasRef={canvasRef}
              canvasWidth={canvasWidth}
              onNext={() => setCurrentStep(3)}
              onPrev={() => setCurrentStep(1)}
              handleAddBlock={handleAddBlock}
              handleRemoveBlockFromBin={handleRemoveBlockFromBin}
            />
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0 min-w-0 bg-[#0f0f0f] relative">
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
              onRunBacktest={runSimulation}
              onViewChange={(view) => setIsBacktestDashboard(view === "dashboard")}
              summaryData={{
                universeName: universe === "US_TECH_TOP10" ? "미국 테크 Top 10" : 
                              universe === "KOR_KOSPI200" ? "KOSPI 200" :
                              universe === "KOR_KOSDAQ150" ? "KOSDAQ 150" : 
                              universe === "CRYPTO_TOP10" ? "크립토 Top 10" : 
                              universe === "kospi" ? "KOSPI" :
                              universe === "kosdaq" ? "KOSDAQ" : universe,
                universeFiltersCount: Object.keys(universeFilters).length,
                blockNames: canvasBlocks.map(b => {
                  const blockDef = signalBlocks[b.blockId];
                  return blockDef ? blockDef.name : b.blockId;
                }),
                riskSettings: {
                  maxPositions,
                  allocationType,
                },
                riskManagement: {
                  stopLoss: riskManagement.stop_loss_pct,
                  takeProfit: riskManagement.take_profit_pct,
                  trailingStop: riskManagement.trailing_stop_pct,
                  maxHoldingDays: riskManagement.max_holding_days,
                }
              }}
            />
          )}

          {backtestError && (
             <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-50 animate-in fade-in slide-in-from-bottom-4">
                <div className="bg-red-500/10 border border-red-500/50 backdrop-blur-md px-6 py-4 rounded-2xl flex items-center gap-4 shadow-2xl">
                   <ExclamationTriangleIcon className="w-6 h-6 text-red-500 shrink-0" />
                   <div className="flex flex-col">
                      <span className="text-sm font-bold text-white">시뮬레이션 오류</span>
                      <span className="text-xs text-red-400">{backtestError}</span>
                   </div>
                   <button 
                      onClick={() => setBacktestError(null)}
                      className="ml-4 p-1 hover:bg-white/10 rounded-full transition-colors"
                   >
                     <XMarkIcon className="w-4 h-4 text-gray-400" />
                   </button>
                </div>
             </div>
          )}
        </div>
      )}
      </div>
      </div>
    </div>
  );
}
