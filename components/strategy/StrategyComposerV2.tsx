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
import { StrategyDSL, Condition, ConditionType, LogicOperator, BacktestResult } from "@/types/strategy";
import { signalBlocks } from "@/lib/strategy-blocks";
import { runBacktest } from "@/lib/backtest-engine";
import BacktestChart from "@/components/strategy/BacktestChart";
import ConditionBlockEditor from "./ConditionBlockEditor";
import RiskManagementEditor from "./RiskManagementEditor";
import StrategyBlockSearchMenu from "./StrategyBlockSearchMenu";

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

interface CanvasBlock {
  id: string;
  type: "filter" | "entry" | "exit";
  blockId: string;
  position: { x: number; y: number };
  params: Record<string, any>;
  connections?: string[]; // IDs of connected blocks
}

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
  const [sectorSearchTerm, setSectorSearchTerm] = useState("");

  const ALL_SECTORS = [
    "에너지", "화학", "소재", "철강", "비철금속", "건설", "조선", "기계", "항공", "운송", 
    "상업서비스", "자동차", "자동차부품", "섬유/의류", "생활용품", "호텔/레저", "화장품", "유통", 
    "식품", "음료", "담배", "제약", "바이오", "의료기기", "건강관리", "은행", "증권", "보험", 
    "다각화금융", "IT서비스", "소프트웨어", "반도체", "디스플레이", "하드웨어", "통신장비", 
    "통신서비스", "유틸리티", "미디어/엔터", "게임"
  ];

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

  // Calculate blocks per row targetting 4 by default
  const blocksPerRow = canvasWidth > 720 ? 4 : Math.max(1, Math.floor((canvasWidth - 30) / 185));
  const totalGridWidth = blocksPerRow * 185 - 65; // (Width * N) + (Gap * (N-1))
  const sidePadding = Math.max(15, (canvasWidth - totalGridWidth) / 2);

  const numRows = Math.ceil(canvasBlocks.length / blocksPerRow);
  const canvasMinHeight = Math.max(600, 100 + numRows * 135 + 100); // Higher rows + padding

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

  const blockCategories: Record<BlockCategory, { name: string; icon: any; blocks: any[] }> = {
    price_signals: {
      name: "Price Signals",
      icon: ChartBarIcon,
      blocks: [
        { id: "ma_crossover", name: "이동평균 교차", category: "price_signals" },
        { id: "breakout", name: "돌파", category: "price_signals" },
        { id: "candle_pattern", name: "캔들 패턴", category: "price_signals" },
      ],
    },
    momentum: {
      name: "Momentum",
      icon: ArrowRightIcon,
      blocks: [
        { id: "absolute_momentum", name: "절대 모멘텀", category: "momentum" },
        { id: "relative_momentum", name: "상대 모멘텀", category: "momentum" },
        { id: "dual_momentum", name: "듀얼 모멘텀", category: "momentum" },
      ],
    },
    mean_reversion: {
      name: "Mean Reversion",
      icon: ArrowPathIcon,
      blocks: [
        { id: "rsi", name: "RSI", category: "mean_reversion" },
        { id: "bollinger_bands", name: "Bollinger Bands", category: "mean_reversion" },
        { id: "stochastic", name: "Stochastic", category: "mean_reversion" },
      ],
    },
    factor_filters: {
      name: "Factor Filters",
      icon: SparklesIcon,
      blocks: [
        { id: "value_factor", name: "Value", category: "factor_filters" },
        { id: "quality_factor", name: "Quality", category: "factor_filters" },
        { id: "low_vol_factor", name: "Low Volatility", category: "factor_filters" },
      ],
    },
    risk_rules: {
      name: "Risk Rules",
      icon: ShieldExclamationIcon,
      blocks: [
        { id: "price_limit_exit", name: "손절/익절", category: "risk_rules" },
        { id: "mdd_cut", name: "MDD Cut", category: "risk_rules" },
      ],
    },
    position_sizing: {
      name: "Position Sizing",
      icon: AdjustmentsHorizontalIcon,
      blocks: [
        { id: "equal_weight", name: "Equal Weight", category: "position_sizing" },
        { id: "vol_target", name: "Vol Target", category: "position_sizing" },
        { id: "risk_parity", name: "Risk Parity", category: "position_sizing" },
      ],
    },
    portfolio_rules: {
      name: "Portfolio Rules",
      icon: CubeIcon,
      blocks: [
        { id: "rebalance_monthly", name: "월간 리밸런싱", category: "portfolio_rules" },
        { id: "max_holdings", name: "최대 종목 수", category: "portfolio_rules" },
        { id: "leverage", name: "레버리지", category: "portfolio_rules" },
      ],
    },
  };

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
    
    // Custom sort order: filter -> entry -> exit
    const sorted = [
      ...updated.filter(b => b.type === "filter"),
      ...updated.filter(b => b.type === "entry"),
      ...updated.filter(b => b.type === "exit")
    ];
    
    setCanvasBlocks(sorted);
    setSelectedBlock(newBlock);
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

  const handleModalItemDragStart = (index: number) => {
    setDraggedModalItemIndex(index);
  };

  const handleModalItemDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleModalItemDrop = (categoryKey: string, targetIndex: number, currentBlocks: any[]) => {
    if (draggedModalItemIndex === null) return;
    
    const newBlocks = [...currentBlocks];
    const [draggedItem] = newBlocks.splice(draggedModalItemIndex, 1);
    newBlocks.splice(targetIndex, 0, draggedItem);
    
    const newOrder = newBlocks.map(b => b.id);
    setCustomBlockOrder(prev => ({
      ...prev,
      [categoryKey]: newOrder
    }));
    
    setDraggedModalItemIndex(null);
  };

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

  // Grouped Library for Step 2 (Signal / Filter / Risk / Model)
  const groupedSignalLibrary = {
    filter: {
      key: "filter",
      label: "종목 필터 블록",
      icon: AdjustmentsHorizontalIcon,
      blocks: Object.values(signalBlocks).filter(
        (b) => b.category === "filter" && 
               (!b.hidden || unlockedBlockIds.includes(b.id)) && 
               !manuallyHiddenBlockIds.includes(b.id)
      ).sort((a, b) => {
        const order = customBlockOrder["filter"] || [];
        const indexA = order.indexOf(a.id);
        const indexB = order.indexOf(b.id);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return 0;
      }).map((b) => ({
        id: b.id,
        name: b.name,
        description: b.description,
        blockType: "factor_filters" as const,
      })),
    },
    indicator: {
      key: "indicator",
      label: "매매 시그널 블록",
      icon: SparklesIcon,
      blocks: Object.values(signalBlocks).filter(
        (b) => (b.category === "indicator" || b.category === "flow") && 
               (!b.hidden || unlockedBlockIds.includes(b.id)) && 
               !manuallyHiddenBlockIds.includes(b.id)
      ).sort((a, b) => {
        const order = customBlockOrder["indicator"] || [];
        const indexA = order.indexOf(a.id);
        const indexB = order.indexOf(b.id);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return 0;
      }).map((b) => ({
        id: b.id,
        name: b.name,
        description: b.description,
        blockType: b.category,
      })),
    },
    risk: {
      key: "risk",
      label: "리스크 블록",
      icon: ShieldExclamationIcon,
      blocks: Object.values(signalBlocks).filter(
        (b) => b.category === "risk" && 
               (!b.hidden || unlockedBlockIds.includes(b.id)) && 
               !manuallyHiddenBlockIds.includes(b.id)
      ).sort((a, b) => {
        const order = customBlockOrder["risk"] || [];
        const indexA = order.indexOf(a.id);
        const indexB = order.indexOf(b.id);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return 0;
      }).map((b) => ({
        id: b.id,
        name: b.name,
        description: b.description,
        blockType: "risk_rules" as const,
      })),
    },
    ml: {
      key: "ml",
      label: "AI 블록",
      icon: CpuChipIcon,
      blocks: Object.values(signalBlocks).filter(
        (b) => b.category === "ml" && 
               (!b.hidden || unlockedBlockIds.includes(b.id)) && 
               !manuallyHiddenBlockIds.includes(b.id)
      ).sort((a, b) => {
        const order = customBlockOrder["ml"] || [];
        const indexA = order.indexOf(a.id);
        const indexB = order.indexOf(b.id);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return 0;
      }).map((b) => ({
        id: b.id,
        name: b.name,
        description: b.description,
        blockType: "ml" as const,
      })),
    },
  } as const;


  const [openSignalGroups, setOpenSignalGroups] = useState<(keyof typeof groupedSignalLibrary)[]>([]);

  const filteredLibraryEntries = () => {
    if (currentStep === 3) {
      return { position_sizing: blockCategories.position_sizing };
    }
    if (currentStep === 4) {
      return { risk_rules: blockCategories.risk_rules };
    }
    return blockCategories;
  };

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

      {/* Main Content Area */}
      <div className="flex-1 flex min-h-0">
        {/* Left Panel: Block Library - Only show for Step 2 */}
        {currentStep === 2 && (
          <>
            <div className="w-48 bg-[#0f0f0f] relative z-50 flex flex-col shrink-0">
              <div className="flex-1 px-4 py-3 space-y-3">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-black text-white uppercase tracking-wider">조건 블록함</h3>
                  <button
                    type="button"
                    onClick={() => setIsLibraryManagementOpen(true)}
                    className="p-1 px-1.5 bg-[#1a1a1a] border border-gray-800 rounded-md text-gray-400 hover:text-white hover:border-gray-600 transition-all flex items-center gap-1 group/mgmt"
                  >
                    <EllipsisHorizontalIcon className="w-4 h-4" />
                  </button>
                </div>

                <div className="space-y-3">
                  {customCategoryOrder.map((key) => {
                    const group = (groupedSignalLibrary as any)[key];
                    if (!group) return null;
                    const filteredBlocks = group.blocks;
                    
                    return (
                      <Fragment key={group.key}>
                        <div className="rounded-lg bg-[#151515] border border-gray-800/20">
                          <button
                            type="button"
                            onClick={() => setOpenSignalGroups((prev) => 
                              prev.includes(group.key) 
                                ? prev.filter(k => k !== group.key) 
                                : [...prev, group.key]
                            )}
                            className="w-full flex items-center justify-between px-3 py-2.5 text-xs font-black text-gray-400 hover:text-white hover:bg-[#181818] transition-all group/header"
                          >
                            <span className="flex items-center gap-2">
                              <group.icon className="w-4 h-4" />
                              <span>{group.label}</span>
                            </span>
                            <div className="flex items-center gap-1">
                              <ChevronDownIcon className={`w-3.5 h-3.5 transition-transform ${openSignalGroups.includes(group.key) ? "rotate-180" : ""}`} />
                            </div>
                          </button>
                          {openSignalGroups.includes(group.key) && (
                            <div className="px-2 pt-1 pb-3 space-y-1 bg-[#151515]">
                              {filteredBlocks.length === 0 && <div className="text-[10px] text-gray-600 px-3 py-2 italic text-center">결과 없음</div>}
                              {filteredBlocks.map((block) => {
                                const blockDef = signalBlocks[block.id];
                                return (
                                  <div
                                    key={block.id}
                                    draggable
                                    onDragStart={(e) => {
                                      e.dataTransfer.setData("blockId", block.id);
                                      e.dataTransfer.setData("blockType", blockDef?.category || "");
                                    }}
                                    className="group p-2.5 bg-[#1a1a1a] border border-gray-800/50 rounded-lg text-xs font-bold text-gray-400 hover:text-white hover:border-blue-500/30 hover:bg-blue-500/5 cursor-move transition-all flex items-center justify-between"
                                  >
                                    <span className="truncate pr-2">{block.name}</span>
                                    <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                      <div 
                                        className="relative p-1"
                                        onMouseEnter={(e) => setHoveredInfo({ id: block.id, rect: e.currentTarget.getBoundingClientRect() })}
                                        onMouseLeave={() => setHoveredInfo(null)}
                                      >
                                        <InformationCircleIcon className={`w-4 h-4 transition-colors cursor-help ${hoveredInfo?.id === block.id ? "text-blue-400" : "text-gray-400 hover:text-blue-400"}`} />
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </Fragment>
                    );
                  })}
                </div>

                {/* Fixed Block Search Button */}
                <div className="py-3 border-t border-gray-800/30">
                  <button
                    type="button"
                    onClick={() => setIsSearchMenuOpen(!isSearchMenuOpen)}
                    className={`w-full flex items-center justify-center gap-2.5 py-3.5 rounded-xl transition-all group ${
                      isSearchMenuOpen
                        ? "bg-blue-600 text-white shadow-[0_8px_20px_rgba(37,99,235,0.3)]"
                        : "bg-[#161616] border border-gray-800/50 text-gray-500 hover:text-white hover:border-blue-500/30 hover:bg-blue-500/5"
                    }`}
                  >
                    <MagnifyingGlassIcon className={`w-5 h-5 transition-transform duration-300 ${isSearchMenuOpen ? "rotate-90 text-white" : "text-gray-500 group-hover:text-blue-400"}`} />
                    <span className="text-sm font-black uppercase tracking-widest">블록 검색</span>
                  </button>
                </div>
              </div>

              <div className="border-t border-gray-800/30 bg-[#0f0f0f] px-3 pt-3 pb-6 flex items-center justify-center">
                <p className="text-[10px] text-gray-600 text-center leading-relaxed font-medium">
                  찾고 계신 지표가 없나요? <br />
                  <span className="text-blue-500/70 hover:text-blue-400 cursor-pointer underline decoration-dotted underline-offset-4 transition-colors">기능 요청하기</span>
                </p>
              </div>
          </div>

            {/* Header Tooltip for "블록 편집" */}
            {hoveredEditIcon && (
              <div 
                className="fixed z-[9999] pointer-events-none transition-all duration-200"
                style={{ 
                  left: hoveredEditIcon.rect.left + (hoveredEditIcon.rect.width / 2), 
                  top: hoveredEditIcon.rect.bottom + 8,
                  transform: 'translateX(-50%)'
                }}
              >
                <div className="px-3 py-1.5 bg-[#0a0a0a] border border-gray-800 rounded-lg shadow-xl animate-in fade-in zoom-in-95 slide-in-from-top-2 duration-200">
                  <p className="text-[11px] text-gray-300 font-bold whitespace-nowrap">
                    {hoveredEditIcon.label}
                  </p>
                  <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-[#0a0a0a] border-l border-t border-gray-800 rotate-45" />
                </div>
              </div>
            )}

            {/* Global Tooltip Portal-like implementation */}
            {hoveredInfo && (
              <div 
                className="fixed z-[9999] pointer-events-none transition-all duration-200"
                style={{ 
                  left: hoveredInfo.rect.right + 12, 
                  top: hoveredInfo.rect.top + (hoveredInfo.rect.height / 2),
                  transform: 'translateY(-50%)'
                }}
              >
                <div className="w-80 p-5 bg-[#161616] border border-gray-800 rounded-3xl shadow-[0_30px_60px_rgba(0,0,0,0.6)] animate-in fade-in zoom-in-95 slide-in-from-left-2 duration-200">
                  <p className="text-[13px] text-gray-300 font-bold leading-[1.7] whitespace-pre-wrap">
                    {signalBlocks[hoveredInfo.id]?.description || "이 블록에 대한 설명이 아직 없습니다."}
                  </p>
                  
                  {/* Arrow */}
                  <div className="absolute top-1/2 -left-1.5 -translate-y-1/2 w-3 h-3 bg-[#161616] border-l border-b border-gray-800 rotate-45" />
                </div>
              </div>
            )}
          </>
        )}

        {/* Center Canvas */}
        <div className="flex-1 bg-[#0f0f0f] relative">
          {currentStep === 1 && (
            <div className="flex flex-col min-h-full">
              <div className="p-8 max-w-[1440px] mx-auto w-full space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="flex flex-col gap-2 border-b border-gray-800/50 pb-8">
                  <div className="flex items-center gap-3">
                    <input
                      type="text"
                      value={strategyName}
                      onChange={(e) => setStrategyName(e.target.value)}
                      placeholder="새로운 전략의 이름을 입력하세요"
                      className="text-4xl font-black text-white bg-transparent border-none outline-none placeholder:text-gray-800 tracking-tighter flex-1"
                    />
                    <div className="px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center gap-2">
                       <SparklesIcon className="w-4 h-4 text-blue-400" />
                       <span className="text-[10px] font-black text-blue-400 uppercase tracking-widest">Hi-Fi 전략</span>
                    </div>
                  </div>
                  <p className="text-gray-500 text-sm mt-1 font-medium">탐색할 시장의 범위와 기본적인 필터링 조건을 설정하여 나만의 유니버스를 구축하세요.</p>
                </div>

                <div className="space-y-8 max-w-5xl mx-auto w-full">
                  {/* Market Selection Section */}
                  <div className="space-y-8">
                    <div className="space-y-6 bg-[#0a0a0a] rounded-2xl border border-gray-800/50 p-6 shadow-xl">
                      <div className="flex items-center gap-2 mb-2">
                        <GlobeAltIcon className="w-6 h-6 text-blue-400" />
                        <h3 className="text-lg font-black text-white uppercase tracking-wider">시장 및 규모 선택</h3>
                      </div>
                      
                      <div className="grid grid-cols-3 gap-3">
                        {[
                          { id: "kospi", name: "KOSPI", desc: "대형주 중심" },
                          { id: "kosdaq", name: "KOSDAQ", desc: "기술주 중심" },
                          { id: "kospi200", name: "KOSPI 200", desc: "우량주 200" },
                        ].map((m) => (
                          <div
                            key={m.id}
                            onClick={() => setUniverse(m.id)}
                            className={`p-4 rounded-xl cursor-pointer transition-all border-2 flex flex-col justify-center text-center group ${
                              universe === m.id
                                ? "bg-blue-600/10 border-blue-500/50 shadow-[0_0_20px_rgba(37,99,235,0.1)]"
                                : "bg-[#151515] border-gray-800/50 hover:border-gray-700"
                            }`}
                          >
                            <div className={`text-base font-black transition-colors ${universe === m.id ? "text-white" : "text-gray-500 group-hover:text-gray-300"}`}>{m.name}</div>
                            <div className="text-xs text-gray-600 mt-1 font-bold">{m.desc}</div>
                          </div>
                        ))}
                      </div>

                      <div className="space-y-8 pt-4 border-t border-gray-800/50">
                        <div className="space-y-4">
                          <div className="flex justify-between items-center px-1">
                            <label className="text-sm font-black text-gray-400 uppercase tracking-tight">시가총액 범위</label>
                            <span className="text-sm font-black text-blue-400 tabular-nums">
                              상위 {universeFilters.marketCapRange[0]}% ~ {universeFilters.marketCapRange[1]}%
                            </span>
                          </div>
                          <div className="px-2">
                            <input
                              type="range"
                              min="0"
                              max="100"
                              value={universeFilters.marketCapRange[1]}
                              onChange={(e) => setUniverseFilters({...universeFilters, marketCapRange: [universeFilters.marketCapRange[0], parseInt(e.target.value)]})}
                              className="w-full h-1.5 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
                            />
                            <div className="flex justify-between text-xs text-gray-600 mt-2 font-black uppercase tracking-tighter">
                              <span>순위 높음</span>
                              <span>전체 범위</span>
                              <span>순위 낮음</span>
                            </div>
                          </div>
                        </div>

                        <div className="space-y-4">
                          <div className="flex justify-between items-center px-1">
                            <label className="text-sm font-black text-gray-400 uppercase tracking-tight">최소 거래대금 (20일 평균)</label>
                            <span className="text-sm font-black text-emerald-400 tabular-nums">
                              {universeFilters.minTradingVolume === 0 ? "제한 없음" : `${universeFilters.minTradingVolume}억원 이상`}
                            </span>
                          </div>
                          <div className="px-2">
                             <input
                              type="range"
                              min="0"
                              max="100"
                              step="5"
                              value={universeFilters.minTradingVolume}
                              onChange={(e) => setUniverseFilters({...universeFilters, minTradingVolume: parseInt(e.target.value)})}
                              className="w-full h-1.5 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-6 bg-[#0a0a0a] rounded-2xl border border-gray-800/50 p-6 shadow-xl">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <TagIcon className="w-6 h-6 text-emerald-400" />
                          <h3 className="text-lg font-black text-white uppercase tracking-wider">섹터 선택</h3>
                        </div>
                        <div className="relative">
                          <MagnifyingGlassIcon className="w-4 h-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
                          <input 
                            type="text"
                            placeholder="섹터 검색..."
                            value={sectorSearchTerm}
                            onChange={(e) => setSectorSearchTerm(e.target.value)}
                            className="pl-9 pr-4 py-2 bg-[#151515] border border-gray-800 rounded-lg text-sm font-bold text-white focus:outline-none focus:border-blue-500 transition-all w-48"
                          />
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-2 pr-2 custom-scrollbar p-1">
                         {ALL_SECTORS.filter(s => s.toLowerCase().includes(sectorSearchTerm.toLowerCase())).map(sector => (
                          <button
                            key={sector}
                            onClick={() => {
                              const next = universeFilters.selectedSectors.includes(sector)
                                ? universeFilters.selectedSectors.filter(s => s !== sector)
                                : [...universeFilters.selectedSectors, sector];
                              setUniverseFilters({...universeFilters, selectedSectors: next});
                            }}
                            className={`px-3 py-1.5 rounded-lg text-xs font-black transition-all border ${
                              universeFilters.selectedSectors.includes(sector)
                                ? "bg-emerald-600 border-emerald-500 text-white shadow-lg shadow-emerald-900/40"
                                : "bg-[#151515] border-gray-800 text-gray-500 hover:text-gray-300 hover:border-gray-700"
                            }`}
                          >
                            {sector}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Exclusion Filters Section */}
                  <div className="space-y-8">
                    <div className="space-y-6 bg-[#0a0a0a] rounded-2xl border border-gray-800/50 p-6 shadow-xl">
                      <div className="flex items-center gap-2 mb-2">
                        <ShieldExclamationIcon className="w-6 h-6 text-red-500" />
                        <h3 className="text-lg font-black text-white uppercase tracking-wider">제외 필터 설정</h3>
                      </div>

                      <div className="space-y-6">
                        <div className="grid grid-cols-2 gap-3">
                          <button
                            onClick={() => setUniverseFilters({...universeFilters, excludeLossMaking: !universeFilters.excludeLossMaking})}
                            className={`p-3 rounded-xl border transition-all flex items-center gap-3 text-left ${
                              universeFilters.excludeLossMaking 
                                ? "bg-red-500/10 border-red-500/50" 
                                : "bg-[#151515] border-gray-800 hover:border-gray-700"
                            }`}
                          >
                            <ShieldExclamationIcon className={`w-5 h-5 ${universeFilters.excludeLossMaking ? "text-red-400" : "text-gray-600"}`} />
                            <div className="min-w-0">
                              <p className="text-sm font-black text-white truncate">적자 기업 제외</p>
                              <p className="text-xs text-gray-600 font-bold">영업이익 기준</p>
                            </div>
                          </button>

                          <button
                            onClick={() => setUniverseFilters({...universeFilters, excludeCapitalImpaired: !universeFilters.excludeCapitalImpaired})}
                            className={`p-3 rounded-xl border transition-all flex items-center gap-3 text-left ${
                              universeFilters.excludeCapitalImpaired 
                                ? "bg-red-500/10 border-red-500/50" 
                                : "bg-[#151515] border-gray-800 hover:border-gray-700"
                            }`}
                          >
                             <ExclamationTriangleIcon className={`w-5 h-5 ${universeFilters.excludeCapitalImpaired ? "text-red-400" : "text-gray-600"}`} />
                            <div className="min-w-0">
                              <p className="text-sm font-black text-white truncate">자본잠식 제외</p>
                              <p className="text-xs text-gray-600 font-bold">재무 건전성 미달</p>
                            </div>
                          </button>
                        </div>

                        <div className="bg-[#151515]/50 rounded-xl border border-gray-800/50 p-4">
                          <div className="grid grid-cols-1 gap-y-3.5">
                            {[
                              { id: 'excludePennyStocks', label: '동전주 제외 (1,000원 미만)' },
                              { id: 'excludeNewListings', label: '신규 상장주 제외 (1년 이내)' },
                              { id: 'excludeHighVolatility', label: '急등락주 제외 (변동성 상위)' },
                              { id: 'excludeAdministrative', label: '관리종목 및 거래정지 제외' },
                              { id: 'excludeInvestmentWarning', label: '투자주의 / 경고 / 위험 제외' },
                              { id: 'excludeDelistingPending', label: '정리매매 종목 제외' },
                              { id: 'excludeETF_ETN', label: 'ETF / ETN 제외' },
                              { id: 'excludeSPAC', label: 'SPAC (기업인수목적) 제외' },
                              { id: 'excludeREITs', label: '리츠 (부동산투자) 제외' },
                              { id: 'excludePreferred', label: '우선주 제외' },
                              { id: 'excludeForeignStock', label: '해외 본사 기업 제외' }
                            ].map((item) => (
                              <label key={item.id} className="flex items-center gap-3 cursor-pointer group">
                                <div className="relative flex items-center">
                                  <input 
                                    type="checkbox" 
                                    checked={(universeFilters as any)[item.id]}
                                    onChange={(e) => setUniverseFilters({...universeFilters, [item.id]: e.target.checked})}
                                    className="peer h-5 w-5 appearance-none rounded border border-gray-700 bg-[#0a0a0a] checked:bg-red-500 checked:border-red-500 transition-all cursor-pointer" 
                                  />
                                  <CheckIcon className="absolute h-4 w-4 text-white left-0.5 opacity-0 peer-checked:opacity-100 transition-opacity pointer-events-none" />
                                </div>
                                <span className="text-sm font-bold text-gray-500 group-hover:text-gray-300 transition-colors">{item.label}</span>
                              </label>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="bg-blue-600/5 border border-blue-500/20 rounded-2xl p-6 space-y-4">
                        <div className="flex items-center gap-2">
                           <InformationCircleIcon className="w-5 h-5 text-blue-400" />
                           <span className="text-sm font-black text-white uppercase tracking-wider">유니버스 요약</span>
                        </div>
                        <div className="space-y-3">
                           <div className="flex justify-between items-center text-sm">
                              <span className="text-gray-500 font-bold">대상 시장</span>
                              <span className="text-blue-400 font-black">{universe.toUpperCase()}</span>
                           </div>
                           <div className="flex justify-between items-center text-sm">
                              <span className="text-gray-500 font-bold">섹터 제한</span>
                              <span className="text-white font-black">{universeFilters.selectedSectors.length > 0 ? `${universeFilters.selectedSectors.length}개 선택됨` : "전체 섹터"}</span>
                           </div>
                           <div className="flex justify-between items-center text-sm">
                              <span className="text-gray-500 font-bold">제외 조건</span>
                              <span className="text-red-400 font-black">{Object.values(universeFilters).filter(v => v === true).length}개 활성</span>
                           </div>
                        </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="sticky bottom-0 bg-[#0f0f0f] z-50 mt-auto">
                <div className="max-w-5xl mx-auto w-full p-6 flex justify-end">
                  <button
                    onClick={() => setCurrentStep(2)}
                    className="px-10 py-4 bg-blue-600 text-white rounded-xl font-black hover:bg-blue-500 flex items-center gap-3 transition-all hover:scale-[1.02] shadow-xl shadow-blue-900/40"
                  >
                    다음 단계: 매매 조건 설정
                    <ArrowRightIcon className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {currentStep === 2 && (
            <div className="flex flex-col min-h-full">
              <div 
                ref={canvasRef}
                className="flex-1 relative border border-gray-800 rounded-3xl overflow-hidden mx-3 mb-6 bg-[#0a0a0a]/30"
                style={{ minHeight: canvasMinHeight }}
                onDragOver={(e) => { e.preventDefault(); setDraggedOver(true); }}
                onDragLeave={() => setDraggedOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDraggedOver(false);
                  const blockId = e.dataTransfer.getData("blockId");
                  const blockType = e.dataTransfer.getData("blockType");
                  if (blockId) {
                    handleAddBlock(blockId, blockType);
                  }
                }}
              >
                <div className="absolute inset-0 pointer-events-none opacity-20" style={{ backgroundImage: "radial-gradient(#4b5563 1px, transparent 1px)", backgroundSize: "20px 20px" }} />
                
                {canvasBlocks.length === 0 && (
                  <div className="absolute inset-0 flex items-center justify-center p-12 text-center pointer-events-none">
                    <div className="max-w-md space-y-4 animate-in fade-in zoom-in duration-700">
                      <div className="w-20 h-20 bg-gray-800/20 rounded-full flex items-center justify-center mx-auto border border-gray-700/30 mb-6">
                        <PlusIcon className="w-10 h-10 text-gray-600" />
                      </div>
                      <h4 className="text-xl font-black text-gray-400">전략 구성을 시작해보세요</h4>
                      <p className="text-sm text-gray-500 font-medium leading-relaxed">
                        왼쪽 도구함에서 원하는 지표나 조건을 드래그하여<br />
                        이곳에 놓아주세요. 나만의 매매 전략을 만들 수 있습니다.
                      </p>
                    </div>
                  </div>
                )}

                <div className="absolute inset-0">
                  <svg className="absolute inset-0 w-full h-full pointer-events-none z-0">
                    <defs>
                      <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                        <feGaussianBlur stdDeviation="2" result="blur" />
                        <feComposite in="SourceGraphic" in2="blur" operator="over" />
                      </filter>
                      <marker id="arrowhead-red" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                        <polygon points="0 0, 10 3.5, 0 7" fill="#EF4444" />
                      </marker>
                      <marker id="arrowhead-blue" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                        <polygon points="0 0, 10 3.5, 0 7" fill="#3B82F6" />
                      </marker>
                      <marker id="arrowhead-gray" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                        <polygon points="0 0, 10 3.5, 0 7" fill="#4B5563" />
                      </marker>
                    </defs>
                    {canvasBlocks.map((block, index) => {
                      if (index === canvasBlocks.length - 1) return null;
                      const nextBlock = canvasBlocks[index + 1];
                      const isEntryOrFilter = (b: CanvasBlock) => b.type === "entry" || b.type === "filter";
                      const isExit = (b: CanvasBlock) => b.type === "exit";
                      
                      let shouldConnect = false;
                      let color = "#4B5563";
                      let markerId = "arrowhead-gray";

                      if (isEntryOrFilter(block) && isEntryOrFilter(nextBlock)) {
                        shouldConnect = entryLogic === "AND";
                        color = "#EF4444";
                        markerId = "arrowhead-red";
                      } else if (isExit(block) && isExit(nextBlock)) {
                        shouldConnect = exitLogic === "AND";
                        color = "#3B82F6";
                        markerId = "arrowhead-blue";
                      }

                      if (!shouldConnect) return null;

                      const col = index % blocksPerRow;
                      const row = Math.floor(index / blocksPerRow);
                      const nextCol = (index + 1) % blocksPerRow;
                      const nextRow = Math.floor((index + 1) / blocksPerRow);

                      const startX = sidePadding + col * 185 + 120; // Right side of block
                      const startY = 60 + row * 135 + 32; // Center of block height
                      
                      let endX, endY;
                      const isNewRow = nextRow > row;

                      if (isNewRow) {
                        endX = sidePadding + nextCol * 185 + 60; // Center of next block
                        endY = 60 + nextRow * 135; // Top of next block
                      } else {
                        endX = sidePadding + nextCol * 185; // Left side of next block
                        endY = 60 + nextRow * 135 + 32; // Center of next block height
                      }

                      const dx = endX - startX;
                      const dy = endY - startY;
                      
                      let pathD;
                      if (isNewRow) {
                        const gutterY = startY + (endY - startY) / 2;
                        // Start at right, curve into gutter, travel horizontally, curve into top
                        pathD = `M ${startX} ${startY} 
                                 C ${startX + 30} ${startY}, ${startX + 30} ${gutterY}, ${startX} ${gutterY}
                                 L ${endX + 30} ${gutterY}
                                 C ${endX} ${gutterY}, ${endX} ${gutterY}, ${endX} ${endY}`;
                      } else {
                        const offset = Math.min(Math.max(dx * 0.4, 20), 40);
                        const cp1x = startX + offset;
                        const cp1y = startY;
                        const cp2x = endX - offset;
                        const cp2y = endY;
                        pathD = `M ${startX} ${startY} C ${cp1x} ${cp1y} ${cp2x} ${cp2y} ${endX} ${endY}`;
                      }

                      return (
                        <g key={`flow-${block.id}-${nextBlock.id}`}>
                          {/* Background Glow */}
                          <path
                            d={pathD}
                            stroke={color}
                            strokeWidth="4"
                            fill="none"
                            className="opacity-10"
                            filter="url(#glow)"
                          />
                          {/* Main Line */}
                          <path
                            d={pathD}
                            stroke={color}
                            strokeWidth="1.5"
                            fill="none"
                            className="opacity-40"
                          />
                          {/* Animated flow */}
                          <path
                            d={pathD}
                            stroke={color}
                            strokeWidth="1.5"
                            fill="none"
                            strokeDasharray="4,12"
                            className="opacity-60 animate-dash"
                          />
                        </g>
                      );
                    })}
                  </svg>
                  {canvasBlocks.map((block, index) => {
                    const colIdx = index % blocksPerRow;
                    const rowIdx = Math.floor(index / blocksPerRow);
                    const xOffset = sidePadding + colIdx * 185;
                    const yOffset = 60 + rowIdx * 135;

                    const typeStyles = 
                      block.type === "entry" 
                        ? "border-red-500/30 bg-red-950/20 hover:bg-red-900/30 shadow-red-900/5" 
                        : block.type === "exit" 
                        ? "border-blue-500/30 bg-blue-950/20 hover:bg-blue-900/30 shadow-blue-900/5" 
                        : "border-[rgba(100,155,107,0.3)] bg-[rgba(100,155,107,0.1)] hover:bg-[rgba(100,155,107,0.2)] shadow-[rgba(100,155,107,0.05)]";

                    const isSelected = selectedBlock?.id === block.id;

                    return (
                      <div
                        key={block.id}
                        onClick={() => {
                          setSelectedBlock(block);
                          setActiveParamTab('block');
                        }}
                        className={`absolute p-4 rounded-xl transition-all duration-300 border backdrop-blur-md group cursor-pointer ${typeStyles} ${
                          isSelected 
                            ? "ring-2 ring-blue-500/50 scale-105 z-10 shadow-2xl" 
                            : "hover:scale-105 z-1 shadow-lg"
                        }`}
                        style={{ left: `${xOffset}px`, top: `${yOffset}px`, width: "120px" }}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-1.5">
                            <span className={`w-2 h-2 rounded-full ${
                               block.type === "entry" ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.6)]" : 
                               block.type === "exit" ? "bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)]" : 
                               "bg-[rgb(100,155,107)] shadow-[0_0_8px_rgba(100,155,107,0.6)]"
                            }`} />
                            <span className={`text-[9px] font-bold px-1 rounded-sm ${
                              block.type === "entry" ? "bg-red-500/20 text-red-400" :
                              block.type === "exit" ? "bg-blue-500/20 text-blue-400" :
                              "bg-[rgba(100,155,107,0.2)] text-[rgb(100,155,107)]"
                            }`}>
                              {block.type === "entry" ? "매수" : block.type === "exit" ? "매도" : "필터"}
                            </span>
                          </div>
                          <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <span className="w-1 h-1 rounded-full bg-white/20" />
                            <span className="w-1 h-1 rounded-full bg-white/20" />
                          </div>
                        </div>
                        <div className="text-[12px] font-black text-white leading-tight tracking-tight">
                          {signalBlocks[block.blockId]?.name || block.blockId}
                        </div>
                        <button 
                          onClick={(e) => { 
                            e.stopPropagation(); 
                            setCanvasBlocks(canvasBlocks.filter(b => b.id !== block.id)); 
                            if (selectedBlock?.id === block.id) setSelectedBlock(null); 
                          }} 
                          className="absolute -top-2 -right-2 w-6 h-6 bg-[#1a1a1a] border border-gray-800 text-gray-500 rounded-lg opacity-0 group-hover:opacity-100 transition-all hover:text-white hover:bg-red-900/50 hover:border-red-500/50 flex items-center justify-center shadow-xl"
                        >
                          <XMarkIcon className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="p-8 flex justify-end gap-3 mt-auto sticky bottom-0 bg-[#0f0f0f]/90 backdrop-blur-md z-20">
                <button onClick={() => setCurrentStep(1)} className="px-6 py-3 bg-[#1a1a1a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 transition-all flex items-center gap-2">
                  <ArrowLeftIcon className="w-5 h-5" /> 이전 단계
                </button>
                <button onClick={() => setCurrentStep(3)} className="px-8 py-3 bg-blue-600 text-white rounded-xl text-md font-black hover:bg-blue-500 transition-all flex items-center gap-3 shadow-xl shadow-blue-900/40">
                  다음 단계 <ArrowRightIcon className="w-5 h-5" />
                </button>
              </div>
            </div>
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

        {/* Right Panel: Parameter Editor (Only for Step 2) */}
        {currentStep === 2 && (
          <div className="bg-[#0f0f0f] w-60 flex flex-col relative z-30">
            {/* Tabs */}
            <div className="flex p-1 gap-1">
              <button
                onClick={() => setActiveParamTab('block')}
                className={`flex-1 py-2 text-sm font-black uppercase tracking-widest transition-all rounded-lg ${
                  activeParamTab === 'block'
                    ? "text-white bg-white/5"
                    : "text-gray-600 hover:text-gray-400 hover:bg-gray-800/20"
                }`}
              >
                블록 설정
              </button>
              <button
                onClick={() => setActiveParamTab('global')}
                className={`flex-1 py-2 text-sm font-black uppercase tracking-widest transition-all rounded-lg ${
                  activeParamTab === 'global'
                    ? "text-white bg-white/5"
                    : "text-gray-600 hover:text-gray-400 hover:bg-gray-800/20"
                }`}
              >
                전역 논리 설정
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-2 py-4 custom-scrollbar">
              {activeParamTab === 'block' ? (
                selectedBlock ? (
                  <div className="space-y-4">
                    <div className="p-3 bg-[#1a1a1a] rounded-lg border border-gray-800">
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-sm text-white font-bold">{signalBlocks[selectedBlock.blockId]?.name || selectedBlock.blockId}</div>
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold uppercase tracking-tight ${selectedBlock.type === "entry" ? "bg-red-500/20 text-red-400" : selectedBlock.type === "exit" ? "bg-blue-500/20 text-blue-400" : "bg-purple-500/20 text-purple-400"}`}>
                            {selectedBlock.type === "entry" ? "매수" : selectedBlock.type === "exit" ? "매도" : "필터"}
                          </span>
                        </div>
                      </div>
                      <p className="text-[12px] text-gray-400 leading-relaxed tabular-nums">{signalBlocks[selectedBlock.blockId]?.description || "시그널을 발생시킵니다."}</p>
                    </div>
                    <div className="space-y-3">
                      {(() => {
                        const blockDef = signalBlocks[selectedBlock.blockId];
                        if (!blockDef || !blockDef.paramSchema) return <div className="text-xs text-gray-500">파라미터가 없습니다.</div>;

                        const getVal = (k: string) => selectedBlock.params[k] ?? blockDef.defaultParams[k];

                        // Custom Input-based UI for Investor block (as requested)
                        if (selectedBlock.blockId === "investor_net_buy") {
                          const renderInput = (key: string) => {
                            const param = blockDef.paramSchema[key];
                            const val = getVal(key);
                            return (
                              <div key={key} className="space-y-1.5 flex-1">
                                <label className="text-xs text-gray-500 font-black uppercase tracking-tight">{param.label}</label>
                                <div className="flex items-center gap-2 bg-[#1a1a1a] border border-gray-800/50 rounded-lg px-3 py-2.5 hover:border-gray-700 focus-within:border-blue-500/40 transition-all">
                                  <input 
                                    type="text"
                                    value={val === 0 ? "" : val}
                                    placeholder="0"
                                    onChange={(e) => {
                                      const raw = e.target.value;
                                      const v = raw === "" ? 0 : isNaN(parseFloat(raw)) ? 0 : parseFloat(raw);
                                      const newParams = { ...selectedBlock.params, [key]: v };
                                      setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams } : b));
                                      setSelectedBlock({ ...selectedBlock, params: newParams });
                                    }}
                                    className="bg-transparent text-xs font-black text-white w-full outline-none tabular-nums"
                                  />
                                  {param.suffix && <span className="text-[10px] font-black text-gray-600 uppercase">{param.suffix}</span>}
                                </div>
                              </div>
                            );
                          };

                          const renderSelect = (key: string) => {
                            const param = blockDef.paramSchema[key];
                            const val = getVal(key);
                            return (
                              <div key={key} className="space-y-1.5 flex-1">
                                <label className="text-xs text-gray-500 font-black uppercase tracking-tight">{param.label}</label>
                                <div className="relative group/select">
                                  <select 
                                    value={val} 
                                    onChange={(e) => { 
                                      const rawVal = e.target.value;
                                      const v = isNaN(parseFloat(rawVal)) ? rawVal : parseFloat(rawVal);
                                      let newParams = { ...selectedBlock.params, [key]: v };
                                      let newType = selectedBlock.type;

                                      if (key === "investorType") {
                                        const newInvType = v as string;
                                        const memory = { ...(selectedBlock.params._investorMemory || {}) };
                                        if (memory[newInvType]) {
                                          newParams = { ...newParams, period: memory[newInvType].period, minAmount: memory[newInvType].minAmount, _investorMemory: memory };
                                        }
                                      }
                                      if (key === "signalType") newType = v === "buy" ? "entry" : "exit";

                                      setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams, type: newType } : b)); 
                                      setSelectedBlock({ ...selectedBlock, params: newParams, type: newType }); 
                                    }} 
                                    className="w-full appearance-none pl-3 pr-10 py-2.5 bg-[#1a1a1a] border border-gray-800/50 rounded-lg text-xs font-black text-white hover:bg-[#181818] hover:border-gray-700 transition-all cursor-pointer outline-none"
                                  >
                                    {param.options?.map((opt: any) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                                  </select>
                                  <ChevronDownIcon className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500 pointer-events-none" />
                                </div>
                              </div>
                            );
                          };

                          return (
                            <div className="space-y-4">
                              <div className="space-y-4">
                                <div className="p-3 bg-[#1a1a1a]/50 border border-gray-800/50 rounded-xl space-y-4">
                                  {renderSelect("investorType")}
                                  <div className="flex gap-3">
                                    {renderInput("period")}
                                    {renderInput("minAmount")}
                                  </div>
                                  <button 
                                    onClick={() => {
                                      const invType = selectedBlock.params.investorType || "institutional";
                                      const memory = { ...(selectedBlock.params._investorMemory || {}) };
                                      memory[invType] = { period: getVal("period"), minAmount: getVal("minAmount") };
                                      const newParams = { ...selectedBlock.params, _investorMemory: memory };
                                      setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams } : b));
                                      setSelectedBlock({ ...selectedBlock, params: newParams });
                                    }}
                                    className="w-full py-2.5 bg-blue-600/10 border border-blue-600/40 rounded-lg text-xs font-black text-blue-400 hover:bg-blue-600/20 hover:border-blue-600/60 transition-all flex items-center justify-center gap-1.5 group/savebtn shadow-lg shadow-blue-900/10"
                                  >
                                    설정 저장
                                  </button>
                                </div>
                                <div className="px-1">
                                  {renderSelect("signalType")}
                                </div>
                              </div>

                              <div className="space-y-2">
                                <div className="flex items-center gap-2 px-1">
                                  <div className="h-px flex-1 bg-gray-800/50" />
                                  <span className="text-[10px] text-gray-500 font-extrabold uppercase tracking-widest whitespace-nowrap">저장된 투자자별 요약</span>
                                  <div className="h-px flex-1 bg-gray-800/50" />
                                </div>
                                <div className="grid grid-cols-1 gap-1.5 px-0.5">
                                  {["institutional", "foreigner", "individual"].map(type => {
                                    const data = selectedBlock.params._investorMemory?.[type];
                                    const label = type === "institutional" ? "기관" : type === "foreigner" ? "외국인" : "개인";
                                    const isActive = (selectedBlock.params.investorType || "institutional") === type;
                                    if (!data) return (
                                      <div key={type} className="px-3 py-2 bg-[#1a1a1a] border border-dashed border-gray-800/30 rounded-lg flex justify-between items-center opacity-30">
                                        <span className="text-[10px] font-black text-gray-600">{label}</span>
                                        <span className="text-[9px] font-bold text-gray-700 italic">설정 없음</span>
                                      </div>
                                    );
                                    return (
                                      <div key={type} className={`px-3 py-2 rounded-lg flex justify-between items-center border transition-all ${isActive ? "bg-blue-600/5 border-blue-600/30" : "bg-[#1a1a1a] border-gray-800/10"}`}>
                                        <div className="flex items-center gap-2">
                                          <div className={`w-1 h-3 rounded-full ${selectedBlock.type === 'entry' ? 'bg-red-500' : 'bg-blue-500'}`} />
                                          <span className={`text-[10px] font-black ${isActive ? "text-blue-400" : "text-gray-400"}`}>{label}</span>
                                        </div>
                                        <span className="text-[10px] font-bold text-gray-300 tabular-nums">{data.period}일 · {data.minAmount}억</span>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            </div>
                          );
                        }

                        // Standard UI for other blocks
                        return Object.entries(blockDef.paramSchema).map(([key, param]) => {
                          const currentValue = selectedBlock.params[key] ?? blockDef.defaultParams[key];
                          return (
                            <div key={key}>
                              <div className="flex items-center gap-1.5 mb-1.5 relative group/tooltip-row">
                                <label className="text-xs text-gray-500 font-black uppercase tracking-tight">{param.label}</label>
                                {param.tooltip && (
                                  <div 
                                    className="p-1 -m-1"
                                    onMouseEnter={(e) => setHoveredParam({ label: param.label, tooltip: param.tooltip!, rect: e.currentTarget.getBoundingClientRect() })}
                                    onMouseLeave={() => setHoveredParam(null)}
                                  >
                                    <InformationCircleIcon className="w-3.5 h-3.5 text-gray-700 hover:text-blue-500 transition-colors cursor-help" />
                                  </div>
                                )}
                              </div>
                              {param.type === "select" && param.options ? (
                                <div className="relative group/select">
                                  <select 
                                    value={currentValue} 
                                    onChange={(e) => { 
                                      const rawVal = e.target.value;
                                      const val = isNaN(parseFloat(rawVal)) ? rawVal : parseFloat(rawVal);
                                      let newParams = { ...selectedBlock.params, [key]: val };
                                      let newType = selectedBlock.type;
                                      let feedbackMessage = "✓ 저장됨";
                                      if (key === "signalType") {
                                        if (val === "buy") newType = "entry";
                                        else if (val === "sell") newType = "exit";
                                      }
                                      setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams, type: newType } : b)); 
                                      setSelectedBlock({ ...selectedBlock, params: newParams, type: newType }); 
                                    }} 
                                    className={`w-full appearance-none pl-3 ${param.suffix ? "pr-16" : "pr-10"} py-2.5 bg-[#1a1a1a] border border-gray-800/50 rounded-lg text-xs font-black text-white hover:bg-[#151515] hover:border-gray-700 transition-all cursor-pointer outline-none`}
                                  >
                                    {param.options.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                                  </select>
                                  <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
                                    {param.suffix && (
                                      <span className="text-xs font-black text-gray-600 uppercase pr-1 border-r border-gray-800/50 mr-1">
                                        {param.suffix}
                                      </span>
                                    )}
                                    <ChevronDownIcon className="w-3.5 h-3.5 text-gray-500 group-hover/select:text-gray-300 transition-colors" />
                                  </div>
                                </div>
                              ) : param.type === "boolean" ? (
                                <button 
                                  onClick={() => {
                                    const newVal = !currentValue;
                                    const newParams = { ...selectedBlock.params, [key]: newVal };
                                    setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams } : b)); 
                                    setSelectedBlock({ ...selectedBlock, params: newParams }); 
                                  }}
                                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg border transition-all ${currentValue ? "bg-blue-600/10 border-blue-600/50 text-blue-400" : "bg-[#1a1a1a] border-gray-800/50 text-gray-500 hover:border-gray-700"}`}
                                >
                                  <span className="text-xs font-black">{param.label}</span>
                                  <div className={`w-8 h-4 rounded-full relative transition-colors ${currentValue ? "bg-blue-600" : "bg-gray-800"}`}>
                                    <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-all ${currentValue ? "right-0.5" : "left-0.5"}`} />
                                  </div>
                                </button>
                              ) : (
                                 <div className="bg-[#1a1a1a] border border-gray-800/50 rounded-lg p-3 group/input hover:border-gray-700 transition-all">
                                  <div className="flex justify-between items-center mb-3 px-1">
                                    <span className="text-xs font-black text-white tabular-nums">{currentValue}</span>
                                    {param.suffix && <span className="text-xs font-black text-gray-500 uppercase">{param.suffix}</span>}
                                  </div>
                                  <div className="px-1 space-y-1.5">
                                    <input 
                                      type="range"
                                      min={param.min ?? 0}
                                      max={param.max ?? 100}
                                      step={param.step ?? 1}
                                      value={currentValue !== "" ? currentValue : 0}
                                      onChange={(e) => {
                                        const val = parseFloat(e.target.value);
                                        const newParams = { ...selectedBlock.params, [key]: val }; 
                                        setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams } : b)); 
                                        setSelectedBlock({ ...selectedBlock, params: newParams }); 
                                      }}
                                      className="w-full h-1.5 bg-gray-800/50 rounded-lg appearance-none cursor-pointer accent-blue-500 hover:accent-blue-400 transition-all opacity-70 hover:opacity-100"
                                    />
                                    <div className="flex justify-between items-center opacity-40 group-hover/input:opacity-60 transition-opacity">
                                      <span className="text-[9px] font-black text-gray-500 tabular-nums">{param.min ?? 0}</span>
                                      <span className="text-[9px] font-black text-gray-500 tabular-nums">{param.max ?? 100}</span>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        });
                      })()}
                      {/* Reset to Default Button Moved Here */}
                      <div className="pt-2 border-t border-gray-800/30">
                        <button 
                          onClick={() => {
                            if (!selectedBlock) return;
                            const blockDef = signalBlocks[selectedBlock.blockId];
                            if (blockDef) {
                              const newParams = { ...blockDef.defaultParams };
                              let newType = selectedBlock.type;
                              if (newParams.signalType) {
                                newType = newParams.signalType === "buy" ? "entry" : newParams.signalType === "sell" ? "exit" : "filter";
                              }
                              const updatedBlocks = canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams, type: newType } : b);
                              const sortedBlocks = [
                                ...updatedBlocks.filter(b => b.type === "filter"),
                                ...updatedBlocks.filter(b => b.type === "entry"),
                                ...updatedBlocks.filter(b => b.type === "exit")
                              ];
                              setCanvasBlocks(sortedBlocks); 
                            }
                          }}
                          className="w-full py-2 bg-[#1a1a1a] border border-gray-800 rounded-lg text-xs font-bold text-gray-400 hover:text-white hover:bg-gray-800 hover:border-gray-700 transition-all flex items-center justify-center gap-1.5"
                        >
                          <ArrowPathIcon className="w-3 h-3" />
                          기본값 복원
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="h-full flex flex-col items-center pt-24 text-center p-6 space-y-5 opacity-30">
                    <div className="w-20 h-20 rounded-full bg-gray-800/20 border border-gray-700/30 flex items-center justify-center">
                      <CursorArrowRaysIcon className="w-10 h-10 text-gray-600" />
                    </div>
                    <div className="space-y-2">
                      <h4 className="text-sm font-black text-gray-400">블록 선택 안 됨</h4>
                      <p className="text-xs text-gray-600 font-bold leading-relaxed">수정할 블록을 캔버스에서 <br /> 선택해 주세요.</p>
                    </div>
                  </div>
                )
              ) : (
                <div className="space-y-6">
                  <div className="space-y-7 p-1">
                    <div className="bg-[#1a1a1a]/50 rounded-xl p-5 border border-gray-800">
                      <label className="flex items-center gap-2 text-sm font-bold text-red-400 mb-3 uppercase tracking-wider">매수 결합</label>
                      <div className="flex bg-[#151515] rounded-lg p-1 mb-3">
                        <button onClick={() => setEntryLogic("AND")} className={`flex-1 py-1.5 text-xs font-bold rounded ${entryLogic === "AND" ? "bg-red-600 text-white" : "text-gray-500"}`}>AND</button>
                        <button onClick={() => setEntryLogic("OR")} className={`flex-1 py-1.5 text-xs font-bold rounded ${entryLogic === "OR" ? "bg-red-600 text-white" : "text-gray-500"}`}>OR</button>
                      </div>
                      <p className="text-[11px] text-gray-400 leading-relaxed font-medium transition-all">
                        {entryLogic === "AND" 
                          ? "모든 조건이 동시에 충족될 때 신호가 발생합니다." 
                          : "조건 중 하나라도 충족되면 신호가 발생합니다."}
                      </p>
                    </div>
                    <div className="bg-[#1a1a1a]/50 rounded-xl p-5 border border-gray-800">
                      <label className="flex items-center gap-2 text-sm font-bold text-blue-400 mb-3 uppercase tracking-wider">매도 결합</label>
                      <div className="flex bg-[#151515] rounded-lg p-1 mb-3">
                        <button onClick={() => setExitLogic("AND")} className={`flex-1 py-1.5 text-xs font-bold rounded ${exitLogic === "AND" ? "bg-blue-600 text-white" : "text-gray-500"}`}>AND</button>
                        <button onClick={() => setExitLogic("OR")} className={`flex-1 py-1.5 text-xs font-bold rounded ${exitLogic === "OR" ? "bg-blue-600 text-white" : "text-gray-500"}`}>OR</button>
                      </div>
                      <p className="text-[11px] text-gray-400 leading-relaxed font-medium transition-all">
                        {exitLogic === "AND" 
                          ? "모든 조건이 동시에 충족될 때 신호가 발생합니다." 
                          : "조건 중 하나라도 충족되면 신호가 발생합니다."}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Parameter Tooltip Overlay */}
        {hoveredParam && (
          <div 
            className="fixed z-[9999] pointer-events-none transition-all duration-200"
            style={{ 
              left: hoveredParam.rect.left - 270, 
              top: hoveredParam.rect.top + (hoveredParam.rect.height / 2),
              transform: 'translateY(-50%)'
            }}
          >
            <div className="w-64 p-4 bg-[#161616] border border-gray-800 rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] animate-in fade-in zoom-in-95 slide-in-from-right-2 duration-200 text-left">
              <div className="text-[10px] text-blue-500 font-black uppercase tracking-widest mb-2 opacity-50">{hoveredParam.label}</div>
              <p className="text-[12px] text-gray-300 font-bold leading-[1.7]">
                {hoveredParam.tooltip}
              </p>
              <div className="absolute top-1/2 -translate-y-1/2 -right-1 w-2.5 h-2.5 bg-[#161616] border-t border-r border-gray-800 rotate-45" />
            </div>
          </div>
        )}
      </div>
      {/* Global Library Management Modal */}
      {isLibraryManagementOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200" onClick={() => setIsLibraryManagementOpen(false)}>
          <div 
            className="w-full max-w-4xl h-[750px] max-h-[95vh] bg-[#161616] border border-gray-800 rounded-2xl shadow-[0_30px_60px_rgba(0,0,0,0.6)] flex flex-col animate-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Helper function for category movement */}
            {(() => {
              const handleMoveCategory = (direction: 'up' | 'down', index: number) => {
                const newOrder = [...customCategoryOrder];
                const targetIndex = direction === 'up' ? index - 1 : index + 1;
                if (targetIndex < 0 || targetIndex >= newOrder.length) return;
                
                const temp = newOrder[index];
                newOrder[index] = newOrder[targetIndex];
                newOrder[targetIndex] = temp;
                setCustomCategoryOrder(newOrder);
              };

              return null; // This is just to define the function scope-wise if needed, but better as a component method.
            })()}
            <div className="p-5 border-b border-gray-800 flex items-center justify-between bg-[#1a1a1a] rounded-t-2xl">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-500/10 rounded-lg">
                  <Squares2X2Icon className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <h3 className="text-xl font-black text-white uppercase tracking-wider">보관함 관리</h3>
                  <p className="text-xs text-gray-500 font-medium">카테고리별 블록의 순서를 변경하거나 삭제할 수 있습니다</p>
                </div>
              </div>
              <button 
                onClick={() => setIsLibraryManagementOpen(false)} 
                className="p-2 text-gray-500 hover:text-white hover:bg-white/5 rounded-full transition-all"
              >
                <XMarkIcon className="w-6 h-6" />
              </button>
            </div>
            
            <div className="flex-1 flex overflow-hidden">
              {/* Left Sidebar: Categories */}
              <div className="w-64 border-r border-gray-800 bg-[#1a1a1a]/30 flex flex-col p-3 space-y-1">
                {customCategoryOrder.map((key, index) => {
                  const group = (groupedSignalLibrary as any)[key];
                  if (!group) return null;
                  return (
                    <div 
                      key={key}
                      draggable
                      onDragStart={() => setDraggedCategoryIndex(index)}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        if (draggedCategoryIndex === null) return;
                        const newOrder = [...customCategoryOrder];
                        const item = newOrder.splice(draggedCategoryIndex, 1)[0];
                        newOrder.splice(index, 0, item);
                        setCustomCategoryOrder(newOrder);
                        setDraggedCategoryIndex(null);
                      }}
                      className={`relative group/cat-container flex items-center gap-2 px-3 py-2.5 rounded-lg transition-all cursor-move ${
                        activeMgmtCategory === key
                          ? "bg-blue-600/10 border border-blue-500/30"
                          : "hover:bg-white/5 border border-transparent"
                      } ${draggedCategoryIndex === index ? "opacity-40 scale-95" : ""}`}
                      onClick={() => setActiveMgmtCategory(key)}
                    >
                      <div className="grid grid-cols-2 gap-0.5 opacity-30 group-hover/cat-container:opacity-100 transition-opacity shrink-0">
                        <div className="w-0.5 h-0.5 bg-gray-400 rounded-full" />
                        <div className="w-0.5 h-0.5 bg-gray-400 rounded-full" />
                        <div className="w-0.5 h-0.5 bg-gray-400 rounded-full" />
                        <div className="w-0.5 h-0.5 bg-gray-400 rounded-full" />
                        <div className="w-0.5 h-0.5 bg-gray-400 rounded-full" />
                        <div className="w-0.5 h-0.5 bg-gray-400 rounded-full" />
                      </div>
                      <group.icon className={`w-4 h-4 shrink-0 ${activeMgmtCategory === key ? "text-blue-400" : "text-gray-600"}`} />
                      <div className="flex-1 flex items-baseline justify-between overflow-hidden">
                        <span className={`text-sm font-black uppercase tracking-wider truncate ${activeMgmtCategory === key ? "text-blue-400" : "text-gray-500"}`}>
                          {group.label}
                        </span>
                        <span className="text-[10px] text-blue-500/60 font-black ml-1.5 shrink-0">
                          {group.blocks.length}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Right Content: Block List */}
              <div className="flex-1 p-6 overflow-y-auto custom-scrollbar bg-[#0f0f0f]/30">
                {activeMgmtCategory && groupedSignalLibrary[activeMgmtCategory as keyof typeof groupedSignalLibrary] && (
                  <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {(() => {
                          const Icon = groupedSignalLibrary[activeMgmtCategory as keyof typeof groupedSignalLibrary].icon;
                          return <Icon className="w-5 h-5 text-blue-400/70" />;
                        })()}
                        <h4 className="text-base font-black text-gray-200 uppercase tracking-widest">
                          {groupedSignalLibrary[activeMgmtCategory as keyof typeof groupedSignalLibrary].label}
                        </h4>
                      </div>
                      <div className="text-xs text-gray-600 font-bold uppercase tracking-tighter">
                        {groupedSignalLibrary[activeMgmtCategory as keyof typeof groupedSignalLibrary].blocks.length} Blocks
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-2.5">
                      {groupedSignalLibrary[activeMgmtCategory as keyof typeof groupedSignalLibrary].blocks.map((block, index) => (
                        <div 
                          key={block.id}
                          draggable
                          onDragStart={() => handleModalItemDragStart(index)}
                          onDragOver={handleModalItemDragOver}
                          onDrop={() => handleModalItemDrop(activeMgmtCategory, index, groupedSignalLibrary[activeMgmtCategory as keyof typeof groupedSignalLibrary].blocks)}
                          className={`group flex items-center justify-between p-4 bg-[#1a1a1a] border border-gray-800 rounded-xl hover:border-blue-500/20 hover:bg-[#1d1d1d] transition-all ${draggedModalItemIndex === index ? "opacity-40 scale-95" : ""}`}
                        >
                          <div className="flex items-center gap-4 min-w-0">
                            <div className="grid grid-cols-2 gap-1 cursor-grab active:cursor-grabbing p-1.5 hover:bg-gray-800 rounded transition-colors group-hover:bg-gray-800/50">
                              <div className="w-1 h-1 bg-gray-600 rounded-full group-hover:bg-blue-400/50" />
                              <div className="w-1 h-1 bg-gray-600 rounded-full group-hover:bg-blue-400/50" />
                              <div className="w-1 h-1 bg-gray-600 rounded-full group-hover:bg-blue-400/50" />
                              <div className="w-1 h-1 bg-gray-600 rounded-full group-hover:bg-blue-400/50" />
                            </div>
                            <div className="min-w-0">
                              <div className="text-base font-bold text-gray-200 truncate">{block.name}</div>
                            </div>
                          </div>
                          <button
                            onClick={(e) => handleRemoveBlockFromBin(block.id, e)}
                            className="p-2 text-gray-600 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-all opacity-0 group-hover:opacity-100 shrink-0"
                            title="보관함에서 제거"
                          >
                            <XMarkIcon className="w-5 h-5" />
                          </button>
                        </div>
                      ))}
                      {groupedSignalLibrary[activeMgmtCategory as keyof typeof groupedSignalLibrary].blocks.length === 0 && (
                        <div className="py-20 text-center border border-dashed border-gray-800 rounded-2xl bg-[#0a0a0a]/20">
                          <Squares2X2Icon className="w-8 h-8 text-gray-800 mx-auto mb-3" />
                          <p className="text-sm text-gray-600 font-bold">등록된 블록이 없습니다.</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Global Modals */}
      {isSearchMenuOpen && (
        <StrategyBlockSearchMenu
          manuallyHiddenBlockIds={manuallyHiddenBlockIds}
          onSelect={(blockIds) => {
            const newAdditions = blockIds.filter(id => !unlockedBlockIds.includes(id) && !manuallyHiddenBlockIds.includes(id));
            const restored = blockIds.filter(id => manuallyHiddenBlockIds.includes(id));
            const existingCount = blockIds.length - newAdditions.length - restored.length;

            if (restored.length > 0) {
              setManuallyHiddenBlockIds(prev => prev.filter(id => !restored.includes(id)));
            }
            if (newAdditions.length > 0) {
              setUnlockedBlockIds(prev => [...prev, ...newAdditions]);
            }

            let message = "";
            if (newAdditions.length > 0 && restored.length > 0) {
              message = `${newAdditions.length}개의 블록이 추가되고, ${restored.length}개의 블록이 복원되었습니다.`;
            } else if (newAdditions.length > 0) {
              message = `${newAdditions.length}개의 블록이 보관함에 추가되었습니다.`;
            } else if (restored.length > 0) {
              message = `${restored.length}개의 블록이 보관함에 복원되었습니다.`;
            } else if (existingCount > 0) {
              message = "이미 보관함에 포함된 블록들입니다.";
            }

            if (message) {
              setSavedFeedback(message);
              if (feedbackTimeoutRef.current) clearTimeout(feedbackTimeoutRef.current);
              feedbackTimeoutRef.current = setTimeout(() => setSavedFeedback(null), 2000);
            }
            
            setIsSearchMenuOpen(false);
          }}
          onClose={() => setIsSearchMenuOpen(false)}
        />
      )}
    </div>
  );
}
