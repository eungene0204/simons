"use client";

import { useState, useEffect, useCallback, useRef, Fragment } from "react";
import {
  X,
  PlayCircle,
  DownloadSimple,
  CheckCircle,
  ArrowRight,
  ArrowLeft,
  Sparkle,
  Sliders,
  ChartBar,
  Cube,
  Cpu,
  Warning,
  Plus,
  Minus,
  CaretDown,
  CaretUp,
  Info,
  Lightning,
  TrendUp,
  Globe,
  Check,
  ChartPie,
  ShieldCheck,
  SquaresFour,
  Tag,
  DotsThreeOutline,
  HandPointing,
} from "phosphor-react";
import { StrategyDSL, Condition, ConditionType, BacktestResult, CanvasBlock, RiskManagement } from "@/types/strategy";
import { signalBlocks } from "@/lib/strategy-blocks";
import { BacktestService } from "@/lib/strategy/BacktestService";
import BacktestChart from "@/components/strategy/BacktestChart";
import RiskManagementEditor from "./RiskManagementEditor";
import Step1Universe from "./steps/Step1Universe";
import Step2Conditions from "./steps/Step2Conditions";
import Step3PositionRisk from "./steps/Step3PositionRisk";
import Step4Backtest from "./steps/Step4Backtest";
import Step5Report from "./steps/Step5Report";

interface StrategyComposerV2Props {
  onSave: (strategy: StrategyDSL) => void;
  onCancel: () => void;
  onQuickPreview?: () => void;
  onQuickBacktest?: () => void;
  onFullBacktest?: () => void;
  initialStrategy?: StrategyDSL | null;
  currentStep: 1 | 2 | 3 | 4 | 5;
  setCurrentStep: (step: 1 | 2 | 3 | 4 | 5) => void;
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
  currentStep,
  setCurrentStep,
}: StrategyComposerV2Props) {
  // Header state
  const [strategyName, setStrategyName] = useState("");
  const [strategyStatus, setStrategyStatus] = useState<StrategyStatus>("draft");

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
  const [riskManagement, setRiskManagement] = useState<RiskManagement>({
    position_size_pct: 10,
    max_positions: 10,
    min_cash_reserve_pct: 10,
    max_daily_buy_pct: 20,
    stop_loss_pct: 10,
    take_profit_pct: 20,
    trailing_stop_pct: 0,
    liquidity_limit_pct: 10,
    max_holding_days: 0,
    max_daily_loss_pct: 5,
    max_total_exposure_pct: 50,
    max_sector_exposure_pct: 30,
    max_mdd_limit_pct: 15,
    execution_timing: "next_open",
    allocation_type: "equal",
    skip_risk_management: true,
    skip_position_setting: true,
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
  const [lastDsl, setLastDsl] = useState<StrategyDSL | null>(null);
  const isRunningRef = useRef(false);

  // Responsive Canvas State
  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasWidth, setCanvasWidth] = useState(1000);

  // Scroll to top when step changes
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [currentStep]);

  // Sync Step 3 position & risk settings into the riskManagement object
  useEffect(() => {
    let perPosSize = allocationValue;
    if (allocationType === "equal") {
      perPosSize = Math.floor(100 / maxPositions);
    }
    
    setRiskManagement(prev => ({
      ...prev,
      position_size_pct: perPosSize,
      max_positions: maxPositions,
      allocation_type: allocationType,
      execution_timing: executionTiming,
      rebalancing_period: rebalancingPeriod,
    }));
  }, [allocationType, maxPositions, allocationValue, executionTiming, rebalancingPeriod]);

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

  // Reset backtest dashboard state when leaving step 4 or 5
  useEffect(() => {
    if (currentStep !== 4 && currentStep !== 5) {
      setIsBacktestDashboard(false);
    }
  }, [currentStep]);

  const [backtestOptions, setBacktestOptions] = useState<any>({
    period: "5Y",
    initialCapital: 10000000,
    commissionPct: 0.015,
    slippagePct: 0.05
  });

  const getResolvedRisk = useCallback(() => {
    let resolved = { 
      ...riskManagement, 
      max_positions: maxPositions,
      allocation_type: allocationType,
      position_size_pct: allocationType === 'equal' ? Math.floor(100 / maxPositions) : allocationValue
    };

    // Map risk blocks from canvas to specific risk parameters (Overrides Step 4)
    canvasBlocks.forEach(b => {
      if (b.blockId === 'price_limit_exit') {
        if (b.params.stopLossPct) resolved.stop_loss_pct = b.params.stopLossPct;
        if (b.params.takeProfitPct) resolved.take_profit_pct = b.params.takeProfitPct;
      } else if (b.blockId === 'max_holding_days') {
        if (b.params.value) resolved.max_holding_days = b.params.value;
      } else if (b.blockId === 'trailing_stop') {
        if (b.params.percentage) resolved.trailing_stop_pct = b.params.percentage;
      }
    });

    return resolved;
  }, [riskManagement, maxPositions, allocationType, allocationValue, canvasBlocks]);

  const getSummaryData = useCallback(() => {
    return {
      strategyName: strategyName,
      universeName: universe === "US_TECH_TOP10" ? "미국 테크 Top 10" :
                    universe === "KOR_KOSPI200" ? "KOSPI 200" :
                    universe === "KOR_KOSDAQ150" ? "KOSDAQ 150" :
                    universe === "CRYPTO_TOP10" ? "크립토 Top 10" :
                    universe === "kospi" ? "KOSPI" :
                    universe === "kosdaq" ? "KOSDAQ" :
                    universe === "kospi200" ? "KOSPI 200" : universe,
      universeSettings: {
        ...universeFilters,
      },
      universeFiltersCount: Object.keys(universeFilters).length,
      entryBlocks: canvasBlocks
        .filter(b => {
          const blockDef = signalBlocks[b.blockId];
          const name = blockDef ? blockDef.name : "";
          const isRisk = name.includes("손절") || name.includes("익절") || name.includes("Risk") || name.includes("Stop");
          return (b.type === "entry" || b.type === "filter") && !isRisk;
        })
        .map(b => {
          const blockDef = signalBlocks[b.blockId];
          return blockDef ? blockDef.name : b.blockId;
        }),
      exitBlocks: canvasBlocks
        .filter(b => {
          const blockDef = signalBlocks[b.blockId];
          const name = blockDef ? blockDef.name : "";
          const isRisk = name.includes("손절") || name.includes("익절") || name.includes("Risk") || name.includes("Stop");
          return b.type === "exit" || isRisk;
        })
        .map(b => {
          const blockDef = signalBlocks[b.blockId];
          return blockDef ? blockDef.name : b.blockId;
        }),
      blockNames: canvasBlocks.map(b => {
        const blockDef = signalBlocks[b.blockId];
        return blockDef ? blockDef.name : b.blockId;
      }),
      positionText: riskManagement.skip_position_setting 
        ? "포지션/비중 설정 안 함"
        : `${allocationType === 'equal' ? '동일 비중' : `고정 비중 ${allocationValue}%`} (최대 ${maxPositions}종목)`,
      riskText: riskManagement.skip_risk_management
        ? "리스크 관리 안 함"
        : (
          [
            riskManagement.stop_loss_pct ? `손절 -${riskManagement.stop_loss_pct}%` : null,
            riskManagement.take_profit_pct ? `익절 +${riskManagement.take_profit_pct}%` : null,
            riskManagement.max_mdd_limit_pct ? `MDD -${riskManagement.max_mdd_limit_pct}%` : null,
          ].filter(Boolean).join(" / ") || "설정 없음"
        ),
      canvasBlocks: canvasBlocks,
      riskSettings: {
        maxPositions,
        allocationType,
        allocationValue,
        executionTiming,
        rebalancingPeriod,
        skip_position_setting: riskManagement.skip_position_setting,
      },
      riskManagement: getResolvedRisk()
    };
  }, [strategyName, universe, universeFilters, canvasBlocks, riskManagement, allocationType, allocationValue, maxPositions, executionTiming, rebalancingPeriod, getResolvedRisk]);

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
    console.error(`[DEBUG-TRACE] runSimulation CALLED with options:`, options);
    if (isRunningRef.current) {
      console.error("[DEBUG-RUN] runSimulation BLOCKED: already running");
      return;
    }

    const runId = Math.random().toString(36).substr(2, 5);
    console.error(`[DEBUG-RUN] runSimulation START (ID: ${runId})`, {
      options,
      currentStep,
      strategyName
    });
    
    try {
      isRunningRef.current = true;
      setIsBacktesting(true);
      setBacktestError(null);
      setBacktestOptions(options);
      
      console.error(`[DEBUG-RUN] Preparing payload for ID: ${runId}`);

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
          conditions: entryConditionsMap
        },
        exit: {
          conditions: exitConditionsMap
        },
        risk: getResolvedRisk()
      };

      console.error(`[DEBUG-RUN] Strategy for ID: ${runId}`, {
        risk: strategy.risk,
        entryCount: strategy.entry.conditions.length
      });

      const engine = new BacktestService();
      const result = await engine.run(strategy, options);

      console.error(`[DEBUG-RUN] Result received for ID: ${runId}`, {
        totalReturn: result.totalReturn,
        trades: result.trades
      });

      setLastDsl(strategy);
      setBacktestResult(result);
      // Automatically move to Step 5 (Report) after successful backtest
      setCurrentStep(5);
    } catch (e: any) {
      console.error(`[DEBUG-RUN] Error in ID: ${runId}`, e);
    } finally {
      setIsBacktesting(false);
      isRunningRef.current = false;
      console.error(`[DEBUG-RUN] runSimulation FINISHED (ID: ${runId})`);
    }
  }, [strategyName, universe, canvasBlocks, universeFilters, getResolvedRisk]);

  const handleOptimize = async (prompt: string, targetMetric: string, nTrials: number = 50, signal?: AbortSignal) => {
    try {
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

      // Generate localized search space ranges for Optuna
      const ranges: Record<string, any> = {};
      
      canvasBlocks.forEach((block, index) => {
        let basePath = "";
        if (block.type === "filter" || block.type === "entry") {
          const arrIndex = canvasBlocks.filter(b => b.type === "entry" || b.type === "filter").indexOf(block);
          basePath = `entry.conditions.${arrIndex}.params`;
        } else if (block.type === "exit") {
          const arrIndex = canvasBlocks.filter(b => b.type === "exit").indexOf(block);
          basePath = `exit.conditions.${arrIndex}.params`;
        }
        
        const defBlock = signalBlocks[block.blockId];
        Object.keys(block.params).forEach(paramKey => {
            const currentVal = block.params[paramKey];
            const schema = defBlock?.paramSchema?.[paramKey];
            
            // 1. Handle numeric parameters
            if (typeof currentVal === "number") {
              const step = schema?.step || 1;
              const min = schema?.min !== undefined ? schema.min : (currentVal > 0 ? currentVal * 0.5 : currentVal - 10);
              const max = schema?.max !== undefined ? schema.max : (currentVal > 0 ? currentVal * 1.5 : currentVal + 10);

              if (max > min) {
                ranges[`${basePath}.${paramKey}`] = { type: "number", min, max, step };
              }
            } 
            // 2. Handle select parameters
            else if (schema?.type === "select" && schema.options) {
              const options = schema.options.map(o => o.value);
              if (options.length > 1) {
                ranges[`${basePath}.${paramKey}`] = options;
              }
            }
            // 3. Handle boolean parameters
            else if (typeof currentVal === "boolean" || schema?.type === "boolean") {
              ranges[`${basePath}.${paramKey}`] = [true, false];
            }
          });
      });

      if (Object.keys(ranges).length === 0) {
        throw new Error("최적화할 수 있는 변수가 없습니다. 블록의 설정을 확인해주세요.");
      }

      const strategy: StrategyDSL = {
        id: initialStrategy?.id || "temp_opt",
        name: strategyName || "Opt Strategy",
        description: "",
        version: "1.0",
        created_at: new Date().toISOString(),
        universe: { id: universe, filters: universeFilters },
        updated_at: new Date().toISOString(),
        entry: { conditions: entryConditionsMap },
        exit: { conditions: exitConditionsMap },
        risk: getResolvedRisk()
      };

      const engine = new BacktestService();
      return await engine.optimize(strategy, backtestOptions, prompt, targetMetric, ranges, nTrials, signal);
    } catch (error: any) {
      throw error;
    }
  };

  const handleWalkForward = async (wfaSettings: any) => {
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

    // Build ranges same as optimizer
    const ranges: Record<string, any> = {};
    canvasBlocks.forEach((block) => {
      let basePath = "";
      if (block.type === "filter" || block.type === "entry") {
        const arrIndex = canvasBlocks.filter(b => b.type === "entry" || b.type === "filter").indexOf(block);
        basePath = `entry.conditions.${arrIndex}.params`;
      } else if (block.type === "exit") {
        const arrIndex = canvasBlocks.filter(b => b.type === "exit").indexOf(block);
        basePath = `exit.conditions.${arrIndex}.params`;
      }
      const defBlock = signalBlocks[block.blockId];
      Object.keys(block.params).forEach(paramKey => {
        const currentVal = block.params[paramKey];
        const schema = defBlock?.paramSchema?.[paramKey];
        if (typeof currentVal === "number") {
          const step = schema?.step || 1;
          const min = schema?.min !== undefined ? schema.min : (currentVal > 0 ? currentVal * 0.5 : currentVal - 10);
          const max = schema?.max !== undefined ? schema.max : (currentVal > 0 ? currentVal * 1.5 : currentVal + 10);
          if (max > min) ranges[`${basePath}.${paramKey}`] = { type: "number", min, max, step };
        } else if (schema?.type === "select" && schema.options) {
          const options = schema.options.map((o: any) => o.value);
          if (options.length > 1) ranges[`${basePath}.${paramKey}`] = options;
        } else if (typeof currentVal === "boolean" || schema?.type === "boolean") {
          ranges[`${basePath}.${paramKey}`] = [true, false];
        }
      });
    });

    if (Object.keys(ranges).length === 0) {
      throw new Error("최적화할 수 있는 변수가 없습니다. 블록의 설정을 확인해주세요.");
    }

    const strategy: StrategyDSL = {
      id: initialStrategy?.id || "temp_wfa",
      name: strategyName || "WFA Strategy",
      description: "",
      version: "1.0",
      created_at: new Date().toISOString(),
      universe: { id: universe, filters: universeFilters },
      updated_at: new Date().toISOString(),
      entry: { conditions: entryConditionsMap },
      exit: { conditions: exitConditionsMap },
      risk: getResolvedRisk(),
    };

    const engine = new BacktestService();
    return await engine.walkForward(strategy, backtestOptions, ranges, wfaSettings);
  };

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
        execution_timing: initialStrategy.risk.execution_timing ?? "next_open",
        allocation_type: initialStrategy.risk.allocation_type ?? "equal",
        skip_risk_management: initialStrategy.risk.skip_risk_management ?? false,
        skip_position_setting: initialStrategy.risk.skip_position_setting ?? false,
      });

      // Also sync top-level states
      if (initialStrategy.risk.max_positions) setMaxPositions(initialStrategy.risk.max_positions);
      if (initialStrategy.risk.allocation_type) setAllocationType(initialStrategy.risk.allocation_type as any);
      if (initialStrategy.risk.position_size_pct && initialStrategy.risk.allocation_type === "fixed_pct") {
        setAllocationValue(initialStrategy.risk.position_size_pct);
      }
      if (initialStrategy.risk.execution_timing) setExecutionTiming(initialStrategy.risk.execution_timing as any);
      if (initialStrategy.risk.rebalancing_period) setRebalancingPeriod(initialStrategy.risk.rebalancing_period);
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
        conditions: entryConditionsMap,
      },
      exit: {
        conditions: exitConditionsMap,
      },
      risk: getResolvedRisk(),
      created_at: initialStrategy?.created_at || new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    onSave(strategy);
    setStrategyStatus("saved");
  };

  const stepLabels = [
    { num: 1, label: "유니버스" },
    { num: 2, label: "매매 조건" },
    { num: 3, label: "포지션/리스크" },
    { num: 4, label: "백테스트" },
    { num: 5, label: "결과 리포트" },
  ];


  return (
    <div className={`flex flex-col bg-[#050505] transition-all duration-500 relative min-h-screen`}>
      <div className="flex-1 flex flex-col relative z-10">



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
              onOptimize={handleOptimize}
              feedbackTimeoutRef={feedbackTimeoutRef}
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
              <Step3PositionRisk
                riskManagement={riskManagement}
                setRiskManagement={setRiskManagement}
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
            <Step4Backtest
              strategyName={strategyName}
              isBacktesting={isBacktesting}
              onPrev={() => setCurrentStep(3)}
              onRunBacktest={runSimulation}
              configOptions={backtestOptions}
              summaryData={getSummaryData()}
            />
          )}

          {currentStep === 5 && (
            <Step5Report
              strategyName={strategyName}
              backtestResult={backtestResult}
              isBacktesting={isBacktesting}
              onPrev={() => setCurrentStep(4)}
              onRestart={() => setCurrentStep(4)}
              onSave={handleSave}
              onRunBacktest={runSimulation}
              onWalkForward={handleWalkForward}
              configOptions={backtestOptions}
              summaryData={getSummaryData()}
              backtestDsl={lastDsl}
            />
          )}

          {backtestError && (
             <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-50 animate-in fade-in slide-in-from-bottom-4">
                <div className="bg-red-500/10 border border-red-500/50 backdrop-blur-md px-6 py-4 rounded-2xl flex items-center gap-4 shadow-2xl">
                   <Warning size={24} className="text-red-500 shrink-0" />
                   <div className="flex flex-col">
                      <span className="text-sm font-bold text-white">시뮬레이션 오류</span>
                      <span className="text-xs text-red-400">{backtestError}</span>
                   </div>
                   <button 
                      onClick={() => setBacktestError(null)}
                      className="ml-4 p-1 hover:bg-white/10 rounded-full transition-colors"
                   >
                     <X size={16} className="text-gray-400" />
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
