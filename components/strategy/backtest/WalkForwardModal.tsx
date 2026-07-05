"use client";

import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { ArrowsClockwise, ChartLine, Warning } from "phosphor-react";
import {
  buildWalkForwardParameterDescriptors,
  buildWalkForwardParameterRanges,
  findWalkForwardRangeBoundsForLabel,
  walkForwardRangeBoundsForPath,
  type StrategyBacktestRequest,
  type WalkForwardParameterRangeOverride,
} from "../../../app/analytics/new/parsedStrategyMerge";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

export interface WalkForwardSettings {
  n_splits: number;
  train_pct: number;
  anchor: boolean;
  target_metric: string;
  n_trials: number;
  method?: "bayesian" | "grid";
  parameter_steps?: Record<string, number>;
  parameter_ranges?: Record<string, WalkForwardParameterRangeOverride>;
  // 슬라이더에서 고른 학습/검증 거래일 수 — 백엔드가 그대로 창 분할에 사용
  is_bars?: number;
  oos_bars?: number;
  // 최적화에서 제외할 파라미터 라벨 (해당 파라미터는 원래 설정값으로 고정)
  excluded_parameters?: string[];
}

export interface WalkForwardOptimizationTarget {
  id: string;
  label: string;
}

interface WindowResult {
  window: number;
  is_period: string;
  oos_period: string;
  best_params: Record<string, any>;
  is_metrics: Record<string, any>;
  oos_metrics: Record<string, any>;
  oos_equity: number[];
  oos_dates: string[];
  error?: string;
}

interface WalkForwardResult {
  status: string;
  message?: string;
  n_splits: number;
  anchor: boolean;
  target_metric: string;
  windows: WindowResult[];
  aggregate: Record<string, number>;
  combined_equity: number[];
  combined_dates: string[];
  walk_forward_efficiency: number;
  wfe_valid?: boolean;
}

export interface WalkForwardRunProgress {
  stage: string;
  window?: number;
  total?: number;
  is_period?: string;
  oos_period?: string;
  message?: string;
}

type WalkForwardRunner = (
  settings: WalkForwardSettings,
  signal?: AbortSignal,
  onProgress?: (event: WalkForwardRunProgress) => void
) => Promise<WalkForwardResult>;

interface WalkForwardModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRun: WalkForwardRunner;
  backtestDates?: string[];
  optimizationTargets?: WalkForwardOptimizationTarget[];
  baseStrategy?: StrategyBacktestRequest;
}

interface WalkForwardPanelProps {
  onRun?: WalkForwardRunner;
  backtestDates?: string[];
  optimizationTargets?: WalkForwardOptimizationTarget[];
  baseStrategy?: StrategyBacktestRequest;
  onClose?: () => void;
  maxHeightClass?: string;
  canRun?: boolean;
  disabledReason?: string;
}

interface WalkForwardFormState {
  trainBars: number;
  validationBars: number;
  anchor: boolean;
  target_metric: string;
  n_trials: number;
  optimizationMethod: OptimizationMethod;
}

const FALLBACK_TOTAL_BARS = 252 * 5;
type OptimizationMethod = "bayesian" | "grid";
// 백엔드 engine/grid_optimizer.py의 MAX_GRID_COMBINATIONS와 동일한 값으로 유지한다.
const MAX_GRID_COMBINATIONS = 500;

type ParameterStepConfig = {
  defaultStep: number;
  min: number;
  max: number;
  inputStep: number;
  stepOptions: number[];
  unit: string;
};

const DEFAULT_PARAMETER_STEP_CONFIG: ParameterStepConfig = {
  defaultStep: 5,
  min: 0.1,
  max: 100,
  inputStep: 0.1,
  stepOptions: [1, 5, 10],
  unit: "",
};

const PARAMETER_STEP_CONFIGS: Array<{ pattern: RegExp } & ParameterStepConfig> = [
  { pattern: /표준편차|stddev/i, defaultStep: 0.25, min: 0.5, max: 4, inputStep: 0.05, stepOptions: [0.1, 0.25, 0.5], unit: "σ" },
  { pattern: /pbr/i, defaultStep: 0.25, min: 0.2, max: 5, inputStep: 0.05, stepOptions: [0.1, 0.25, 0.5], unit: "" },
  { pattern: /per/i, defaultStep: 2.5, min: 3, max: 50, inputStep: 0.5, stepOptions: [1, 2.5, 5], unit: "" },
  { pattern: /roe/i, defaultStep: 2.5, min: 0, max: 40, inputStep: 0.5, stepOptions: [1, 2.5, 5], unit: "%p" },
  { pattern: /(?:rsi|스토캐스틱|stoch).*(?:기간|period)/i, defaultStep: 2, min: 2, max: 60, inputStep: 1, stepOptions: [1, 2, 5], unit: "거래일" },
  { pattern: /macd/i, defaultStep: 2, min: 2, max: 120, inputStep: 1, stepOptions: [1, 2, 5], unit: "거래일" },
  { pattern: /볼린저.*기간|돌파|거래량.*기간|cci.*기간/i, defaultStep: 5, min: 2, max: 250, inputStep: 1, stepOptions: [1, 5, 10], unit: "거래일" },
  { pattern: /rsi|stoch|스토캐스틱|cci/i, defaultStep: 5, min: 5, max: 95, inputStep: 1, stepOptions: [1, 5, 10], unit: "" },
  { pattern: /adx/i, defaultStep: 2, min: 5, max: 60, inputStep: 1, stepOptions: [1, 2, 5], unit: "" },
  { pattern: /이동평균|평균|moving|ema|sma|ma\b/i, defaultStep: 5, min: 2, max: 250, inputStep: 1, stepOptions: [1, 5, 20], unit: "거래일" },
  { pattern: /거래대금|거래량|volume|trading/i, defaultStep: 50, min: 10, max: 1000, inputStep: 10, stepOptions: [10, 50, 100], unit: "억" },
  { pattern: /부채비율|debt/i, defaultStep: 10, min: 0, max: 300, inputStep: 5, stepOptions: [5, 10, 25], unit: "%p" },
  { pattern: /손절|stop\s*loss/i, defaultStep: 2.5, min: 2, max: 30, inputStep: 0.5, stepOptions: [1, 2.5, 5], unit: "%p" },
  { pattern: /익절|take\s*profit/i, defaultStep: 5, min: 5, max: 80, inputStep: 0.5, stepOptions: [2.5, 5, 10], unit: "%p" },
  { pattern: /트레일링|trailing/i, defaultStep: 2.5, min: 3, max: 30, inputStep: 0.5, stepOptions: [1, 2.5, 5], unit: "%p" },
  { pattern: /보유기간|holding/i, defaultStep: 21, min: 5, max: 252, inputStep: 1, stepOptions: [5, 21, 63], unit: "거래일" },
  { pattern: /보유종목수|종목|positions?/i, defaultStep: 5, min: 1, max: 50, inputStep: 1, stepOptions: [1, 5, 10], unit: "종목" },
  { pattern: /리밸런싱|rebalanc/i, defaultStep: 21, min: 5, max: 252, inputStep: 1, stepOptions: [5, 21, 63], unit: "거래일" },
];

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function getParameterStepConfig(label: string): ParameterStepConfig {
  return PARAMETER_STEP_CONFIGS.find((config) => config.pattern.test(label)) ?? DEFAULT_PARAMETER_STEP_CONFIG;
}

function formatStepValue(value: number) {
  return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function formatStepWithUnit(value: number, unit: string) {
  return `${formatStepValue(value)}${unit}`;
}

function formatParameterInputValue(value: number) {
  return Number.isFinite(value) ? String(value) : "";
}

function parseParameterInputValue(value: string) {
  return value === "" ? Number.NaN : Number(value);
}

function sameRangeOverride(
  left: WalkForwardParameterRangeOverride,
  right: WalkForwardParameterRangeOverride
) {
  return (
    left.min.toFixed(4) === right.min.toFixed(4)
    && left.max.toFixed(4) === right.max.toFixed(4)
    && left.step.toFixed(4) === right.step.toFixed(4)
  );
}

function formatDateLabel(date?: string) {
  if (!date) return "-";
  return date.replaceAll("-", ".");
}

function formatBarsLabel(bars: number) {
  return `${bars.toLocaleString()}거래일`;
}

function formatApproxDuration(bars: number) {
  const years = bars / 252;
  if (years >= 1) {
    const roundedYears = years >= 2 ? Math.round(years * 10) / 10 : Math.round(years * 100) / 100;
    return `약 ${roundedYears}년`;
  }

  const months = Math.max(1, Math.round(bars / 21));
  return `약 ${months}개월`;
}

function deriveMinWindowBars(totalBars: number) {
  return Math.max(5, Math.min(20, Math.floor(totalBars / 4) || 5));
}

function deriveSplitCount(totalBars: number, trainBars: number, validationBars: number) {
  if (validationBars <= 0 || totalBars <= trainBars) return 1;
  return Math.max(1, Math.floor((totalBars - trainBars) / validationBars));
}

function deriveTrainPct(totalBars: number, trainBars: number, validationBars: number, anchor: boolean) {
  const denominator = anchor ? Math.max(totalBars, 1) : Math.max(trainBars + validationBars, 1);
  return clamp(trainBars / denominator, 0.05, 0.95);
}

function buildInitialFormState(totalBars: number, minWindowBars: number): WalkForwardFormState {
  const maxTrainBars = Math.max(minWindowBars, totalBars - minWindowBars);
  const trainBars = clamp(Math.round(totalBars * 0.5), minWindowBars, maxTrainBars);
  const remainingBars = Math.max(minWindowBars, totalBars - trainBars);
  const validationBars = clamp(Math.round(totalBars * 0.15), minWindowBars, remainingBars);

  return {
    trainBars,
    validationBars,
    anchor: false,
    target_metric: "cagr",
    n_trials: 30,
    optimizationMethod: "bayesian",
  };
}

function estimateGridChoiceCount(range: WalkForwardParameterRangeOverride) {
  if (range.step <= 0 || range.max <= range.min) return 0;
  return Math.floor((range.max - range.min) / range.step) + 1;
}

function buildParameterInputExamples(range: WalkForwardParameterRangeOverride, step: number) {
  const span = range.max - range.min;
  const values = [range.min, range.min + span / 2, range.max].map((value) =>
    Number((Math.round(value / step) * step).toFixed(4))
  );
  return Array.from(new Set(values));
}

function sliderTrackStyle(value: number, min: number, max: number) {
  const ratio = max <= min ? 1 : (value - min) / (max - min);
  const pct = `${Math.max(0, Math.min(100, ratio * 100))}%`;
  return {
    background: `linear-gradient(90deg, var(--main-blue) 0%, var(--main-blue) ${pct}, rgba(255,255,255,0.08) ${pct}, rgba(255,255,255,0.08) 100%)`,
  };
}

const fmt = (v: any, suffix = "%") => {
  if (v === null || v === undefined) return "-";
  const n = typeof v === "number" ? v : Number(v);
  if (Number.isNaN(n)) return "-";
  return `${n.toFixed(2)}${suffix}`;
};

const fmtNum = (v: any, decimals = 2) => {
  if (v === null || v === undefined) return "-";
  const n = typeof v === "number" ? v : Number(v);
  if (Number.isNaN(n)) return "-";
  return n.toFixed(decimals);
};

const getWfeTone = (wfe: number) => {
  if (wfe >= 0.7) {
    return {
      text: "안정적",
      valueClass: "text-emerald-400",
      badgeClass: "bg-emerald-500/15 text-emerald-400",
    };
  }
  if (wfe >= 0.4) {
    return {
      text: "중립",
      valueClass: "text-blue-400",
      badgeClass: "bg-sky-500/15 text-sky-400",
    };
  }
  return {
    text: "점검 필요",
    valueClass: "text-amber-400",
    badgeClass: "bg-amber-500/15 text-amber-400",
  };
};

const TARGET_METRICS = [
  { id: "cagr", label: "CAGR" },
  { id: "sharpe", label: "샤프 지수" },
  { id: "totalReturn", label: "총 수익률" },
  { id: "profitFactor", label: "손익비" },
  { id: "winRate", label: "승률" },
];

const OPTIMIZATION_METHOD_OPTIONS: Array<{
  value: OptimizationMethod;
  label: string;
  body: string;
}> = [
  {
    value: "grid",
    label: "그리드 탐색",
    body: "설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다.",
  },
  {
    value: "bayesian",
    label: "베이지안 최적화",
    body: "유망한 후보를 우선 탐색하며 제한된 횟수 안에서 조합을 살펴봅니다.",
  },
];

const buttonClass = (active: boolean) =>
  `rounded-md px-3 py-2 text-sm font-black transition-colors ${
    active
      ? "bg-white/[0.08] text-white"
      : "bg-transparent text-gray-400 hover:bg-white/[0.03] hover:text-white"
  }`;

function HelpTooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={`${label} 도움말`}
        className="flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-white/25 text-[10px] font-black leading-none text-gray-400 transition-colors hover:border-white/50 hover:text-white focus:border-white/60 focus:text-white focus:outline-none"
      >
        ?
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-20 mt-2 w-80 max-w-[calc(100vw-3rem)] border border-white/[0.10] bg-[#171717] p-4 text-left opacity-0 shadow-[0_18px_40px_rgba(0,0,0,0.45)] transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {children}
      </span>
    </span>
  );
}

const aggregateTone = (key: string, value?: number) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "text-white";
  if (key.includes("Drawdown")) {
    return value <= -15 ? "text-[var(--main-blue)]" : "text-white";
  }
  if (value > 0) return "text-[var(--main-red)]";
  if (value < 0) return "text-[var(--main-blue)]";
  return "text-white";
};

export function WalkForwardPanel({
  onRun,
  backtestDates = [],
  optimizationTargets = [],
  baseStrategy,
  onClose,
  maxHeightClass = "",
  canRun = true,
  disabledReason = "워크포워드 분석을 실행할 수 없습니다.",
}: WalkForwardPanelProps) {
  const totalBars = backtestDates.length > 1 ? backtestDates.length : FALLBACK_TOTAL_BARS;
  const minWindowBars = deriveMinWindowBars(totalBars);
  const [formState, setFormState] = useState<WalkForwardFormState>(() =>
    buildInitialFormState(totalBars, minWindowBars)
  );
  const [isRunning, setIsRunning] = useState(false);
  const [runProgress, setRunProgress] = useState<WalkForwardRunProgress | null>(null);
  const [result, setResult] = useState<WalkForwardResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [parameterRangeOverrides, setParameterRangeOverrides] = useState<Record<string, WalkForwardParameterRangeOverride>>({});
  const [excludedTargetIds, setExcludedTargetIds] = useState<Set<string>>(() => new Set());
  const [stepModalTargetId, setStepModalTargetId] = useState<string | null>(null);
  const [stepModalDraft, setStepModalDraft] = useState<WalkForwardParameterRangeOverride | null>(null);
  const [stepModalError, setStepModalError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setFormState((current) => {
      const nextTrainBars = clamp(current.trainBars, minWindowBars, Math.max(minWindowBars, totalBars - minWindowBars));
      const nextValidationMax = Math.max(minWindowBars, totalBars - nextTrainBars);
      const nextValidationBars = clamp(current.validationBars, minWindowBars, nextValidationMax);
      return {
        ...current,
        trainBars: nextTrainBars,
        validationBars: nextValidationBars,
      };
    });
  }, [minWindowBars, totalBars]);

  const baseParameterRanges = baseStrategy ? buildWalkForwardParameterRanges(baseStrategy) : {};
  // 실제 탐색 공간(자동 생성 range)의 경로에서 칩을 직접 생성한다 — 배지 텍스트 라벨
  // 매칭 방식은 기술지표 파라미터(MACD 기간 등)를 노출하지 못하는 유령/누락의 원인이었다.
  // 디스크립터 모드에서는 target.id == range 경로이므로 오버라이드/제외가 정확히 그 경로에만 적용된다.
  const descriptorTargets: WalkForwardOptimizationTarget[] = baseStrategy
    ? buildWalkForwardParameterDescriptors(baseStrategy, baseParameterRanges).map((descriptor) => ({
        id: descriptor.path,
        label: descriptor.label,
      }))
    : [];
  const useDescriptors = descriptorTargets.length > 0;
  const visibleTargets = useDescriptors
    ? descriptorTargets
    : baseStrategy
      ? optimizationTargets.filter(
          (target) => findWalkForwardRangeBoundsForLabel(baseStrategy, target.label, baseParameterRanges) !== null
        )
      : optimizationTargets;
  // 설정 payload의 키 — 디스크립터 모드는 경로, 레거시 모드는 라벨 매칭용 라벨
  const settingsKeyFor = (target: WalkForwardOptimizationTarget) =>
    useDescriptors ? target.id : target.label;
  const defaultParameterRanges = visibleTargets.reduce<Record<string, WalkForwardParameterRangeOverride>>((acc, target) => {
    const config = getParameterStepConfig(target.label);
    const bounds = useDescriptors
      ? walkForwardRangeBoundsForPath(baseParameterRanges, target.id)
      : baseStrategy
        ? findWalkForwardRangeBoundsForLabel(baseStrategy, target.label, baseParameterRanges)
        : null;
    // 기본값은 실제로 적용되는 자동 생성 범위 그대로 보여준다 (표시 = 실행).
    const min = bounds?.min ?? config.min;
    const max = bounds?.max ?? config.max;
    const span = Math.max(config.inputStep, Number((max - min).toFixed(4)));
    acc[target.id] = {
      min: Number(min.toFixed(4)),
      max: Number(max.toFixed(4)),
      step: Number(Math.min(config.defaultStep, span).toFixed(4)),
    };
    return acc;
  }, {});

  const activeTargets = visibleTargets.filter((target) => !excludedTargetIds.has(target.id));
  const excludedLabels = visibleTargets
    .filter((target) => excludedTargetIds.has(target.id))
    .map(settingsKeyFor);

  const parameterSteps = activeTargets.reduce<Record<string, number>>((steps, target) => {
    steps[settingsKeyFor(target)] = (parameterRangeOverrides[target.id] ?? defaultParameterRanges[target.id]).step;
    return steps;
  }, {});

  const parameterRanges = activeTargets.reduce<Record<string, WalkForwardParameterRangeOverride>>((ranges, target) => {
    const current = parameterRangeOverrides[target.id];
    const defaults = defaultParameterRanges[target.id];
    if (current && defaults && !sameRangeOverride(current, defaults)) {
      ranges[settingsKeyFor(target)] = current;
    }
    return ranges;
  }, {});

  const hasRealDates = backtestDates.length > 1;
  const derivedSettings: WalkForwardSettings = {
    n_splits: deriveSplitCount(totalBars, formState.trainBars, formState.validationBars),
    train_pct: deriveTrainPct(totalBars, formState.trainBars, formState.validationBars, formState.anchor),
    anchor: formState.anchor,
    target_metric: formState.target_metric,
    n_trials: formState.n_trials,
    method: formState.optimizationMethod,
    ...(hasRealDates ? { is_bars: formState.trainBars, oos_bars: formState.validationBars } : {}),
    ...(activeTargets.length > 0 ? { parameter_steps: parameterSteps } : {}),
    ...(Object.keys(parameterRanges).length > 0 ? { parameter_ranges: parameterRanges } : {}),
    ...(excludedLabels.length > 0 ? { excluded_parameters: excludedLabels } : {}),
  };

  const maxTrainBars = Math.max(minWindowBars, totalBars - minWindowBars);
  const maxValidationBars = Math.max(minWindowBars, totalBars - formState.trainBars);
  const firstTrainStart = backtestDates[0];
  const firstTrainEndIndex = Math.max(0, formState.trainBars - 1);
  const firstValidationStartIndex = Math.min(backtestDates.length - 1, formState.trainBars);
  const firstValidationEndIndex = Math.min(backtestDates.length - 1, formState.trainBars + formState.validationBars - 1);
  const firstTrainEnd = backtestDates[firstTrainEndIndex];
  const firstValidationStart = backtestDates[firstValidationStartIndex] ?? null;
  const firstValidationEnd = backtestDates[firstValidationEndIndex] ?? null;
  const periodStart = backtestDates[0];
  const periodEnd = backtestDates[backtestDates.length - 1];
  const timelineTrainPct = (formState.trainBars / totalBars) * 100;
  const timelineValidationPct = (formState.validationBars / totalBars) * 100;
  const timelineMaxIndex = Math.max(backtestDates.length - 1, 1);
  const timelinePositionForIndex = (index: number) => clamp((index / timelineMaxIndex) * 100, 0, 100);
  const timelineTrainLabelPct = timelinePositionForIndex(firstTrainEndIndex / 2);
  const timelineValidationLabelPct = timelinePositionForIndex((firstValidationStartIndex + firstValidationEndIndex) / 2);

  const handleRun = async () => {
    if (!onRun || !canRun) {
      setError(disabledReason);
      return;
    }

    setIsRunning(true);
    setError(null);
    setResult(null);
    setRunProgress(null);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await onRun(derivedSettings, controller.signal, setRunProgress);
      if (res.status === "error") {
        setError(res.message || "분석 중 오류가 발생했습니다.");
      } else {
        setResult(res);
      }
    } catch (e: any) {
      if (controller.signal.aborted) {
        setError("분석을 취소했습니다.");
      } else {
        setError(e.message || "알 수 없는 오류가 발생했습니다.");
      }
    } finally {
      setIsRunning(false);
      abortRef.current = null;
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
  };

  const handleClose = () => {
    if (!isRunning) onClose?.();
  };

  const toggleTargetExcluded = (targetId: string) => {
    setExcludedTargetIds((current) => {
      const next = new Set(current);
      if (next.has(targetId)) next.delete(targetId);
      else next.add(targetId);
      return next;
    });
  };

  const currentParameterRangeForTarget = (target: WalkForwardOptimizationTarget) =>
    parameterRangeOverrides[target.id] ?? defaultParameterRanges[target.id];

  const openStepModal = (target: WalkForwardOptimizationTarget) => {
    setStepModalTargetId(target.id);
    setStepModalDraft(currentParameterRangeForTarget(target));
    setStepModalError(null);
  };

  const closeStepModal = () => {
    setStepModalTargetId(null);
    setStepModalDraft(null);
    setStepModalError(null);
  };

  const resetStepModal = () => {
    if (!stepModalTargetId) return;
    setParameterRangeOverrides((current) => {
      const next = { ...current };
      delete next[stepModalTargetId];
      return next;
    });
    closeStepModal();
  };

  const saveStepModal = () => {
    if (!stepModalTargetId || !stepModalDraft) return;
    const target = visibleTargets.find((item) => item.id === stepModalTargetId);
    if (!target) return;
    const config = getParameterStepConfig(target.label);
    if (!Number.isFinite(stepModalDraft.min) || !Number.isFinite(stepModalDraft.max)) {
      setStepModalError("하한값과 상한값을 입력해 주세요.");
      return;
    }
    const min = Number(stepModalDraft.min.toFixed(4));
    const max = Number(stepModalDraft.max.toFixed(4));
    if (min > max) {
      setStepModalError("하한값은 상한값보다 클 수 없습니다.");
      return;
    }
    setStepModalError(null);
    const maxStep = Math.max(config.inputStep, Number((max - min).toFixed(4)));
    const normalized: WalkForwardParameterRangeOverride = {
      min,
      max,
      step: Number(clamp(stepModalDraft.step, config.inputStep, maxStep).toFixed(4)),
    };

    setParameterRangeOverrides((current) => {
      const defaults = defaultParameterRanges[stepModalTargetId];
      if (defaults && sameRangeOverride(normalized, defaults)) {
        const next = { ...current };
        delete next[stepModalTargetId];
        return next;
      }
      return {
        ...current,
        [stepModalTargetId]: normalized,
      };
    });
    closeStepModal();
  };

  const chartData = result?.combined_dates?.map((date, index) => ({
    date,
    equity: result.combined_equity[index] ?? null,
  })) ?? [];

  const xTickFormatter = (value: string) => value?.slice(0, 7) ?? "";
  const wfe = result?.walk_forward_efficiency ?? 0;
  // 백엔드가 IS 평균 수익 ≤ 0으로 WFE 해석 불가를 알린 경우
  const wfeValid = result?.wfe_valid !== false;
  const wfeTone = getWfeTone(wfe);
  const isGridMethod = formState.optimizationMethod === "grid";
  const stepModalTarget = visibleTargets.find((target) => target.id === stepModalTargetId) ?? null;
  const stepModalConfig = stepModalTarget ? getParameterStepConfig(stepModalTarget.label) : DEFAULT_PARAMETER_STEP_CONFIG;
  const stepModalCurrentRange = stepModalTarget
    ? currentParameterRangeForTarget(stepModalTarget)
    : null;
  const stepModalBounds = stepModalTarget
    ? defaultParameterRanges[stepModalTarget.id] ?? null
    : null;
  const stepModalDraftValue = stepModalDraft ?? stepModalCurrentRange;
  const stepModalInputExamples = stepModalBounds
    ? buildParameterInputExamples(stepModalBounds, stepModalConfig.inputStep)
    : [];
  const gridSearchEstimate = activeTargets.length > 0
    ? activeTargets.reduce((total, target) => total * estimateGridChoiceCount(currentParameterRangeForTarget(target)), 1)
    : 0;
  const gridSearchExceedsCap = isGridMethod && gridSearchEstimate > MAX_GRID_COMBINATIONS;
  const runDisabledReason = gridSearchExceedsCap
    ? `조합 수(${gridSearchEstimate.toLocaleString()}개)가 상한(${MAX_GRID_COMBINATIONS.toLocaleString()}개)을 초과했습니다. 파라미터 범위나 step을 조정해 주세요.`
    : disabledReason;
  const isRunDisabled = isRunning || !onRun || !canRun || gridSearchExceedsCap;

  return (
        <div data-testid="walk-forward-panel" className="w-full overflow-hidden rounded-xl border border-white/[0.08] bg-[var(--background)]">
          <div className={`${maxHeightClass} overflow-y-auto`}>
            {error && (
              <div className="border-b border-white/[0.08] bg-[var(--main-blue)]/10 px-5 py-4">
                <div className="flex items-start gap-3">
                  <Warning className="mt-0.5 h-4 w-4 shrink-0 text-[var(--main-blue)]" />
                  <div>
                    <p className="text-xs font-bold uppercase tracking-widest text-[var(--main-blue)]">실행 오류</p>
                    <p className="mt-1 text-sm font-black leading-6 text-white">{error}</p>
                  </div>
                </div>
              </div>
            )}

            {!result && (
              <div className="grid grid-cols-1 divide-y divide-white/[0.08] lg:grid-cols-2 lg:divide-x lg:divide-y-0">
                <section className="p-5">
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">기본 설정</p>
                  <div className="mt-4 divide-y divide-white/[0.04] border-t border-white/[0.05]">
                    <div className="py-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <label htmlFor="walk-forward-train-bars" className="text-xs font-bold uppercase tracking-widest text-gray-500">
                            학습기간
                          </label>
                          <p className="mt-2 text-base font-black text-white font-outfit">
                            {formatBarsLabel(formState.trainBars)}
                          </p>
                          <p className="mt-1 text-xs font-bold leading-5 text-gray-400">
                            {formatApproxDuration(formState.trainBars)}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="mt-2 text-xs font-bold leading-5 text-gray-300">
                            {formatDateLabel(firstTrainStart)} - {formatDateLabel(firstTrainEnd)}
                          </p>
                        </div>
                      </div>
                      <input
                        id="walk-forward-train-bars"
                        aria-label="학습기간"
                        type="range"
                        min={minWindowBars}
                        max={maxTrainBars}
                        step={1}
                        value={formState.trainBars}
                        onChange={(event) => {
                          const nextTrainBars = clamp(Number(event.target.value), minWindowBars, maxTrainBars);
                          setFormState((current) => {
                            const nextValidationMax = Math.max(minWindowBars, totalBars - nextTrainBars);
                            return {
                              ...current,
                              trainBars: nextTrainBars,
                              validationBars: clamp(current.validationBars, minWindowBars, nextValidationMax),
                            };
                          });
                        }}
                        className="mt-4 h-2 w-full cursor-pointer appearance-none rounded-full bg-white/[0.08]"
                        style={sliderTrackStyle(formState.trainBars, minWindowBars, maxTrainBars)}
                      />
                      <div className="mt-2 flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-gray-500">
                        <span>{formatBarsLabel(minWindowBars)}</span>
                        <span>{formatBarsLabel(maxTrainBars)}</span>
                      </div>
                    </div>
                    <div className="py-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <label htmlFor="walk-forward-validation-bars" className="text-xs font-bold uppercase tracking-widest text-gray-500">
                            검증기간
                          </label>
                          <p className="mt-2 text-base font-black text-white font-outfit">
                            {formatBarsLabel(formState.validationBars)}
                          </p>
                          <p className="mt-1 text-xs font-bold leading-5 text-gray-400">
                            {formatApproxDuration(formState.validationBars)}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">첫 검증 구간</p>
                          <p className="mt-2 text-xs font-bold leading-5 text-gray-300">
                            {formatDateLabel(firstValidationStart ?? undefined)} - {formatDateLabel(firstValidationEnd ?? undefined)}
                          </p>
                        </div>
                      </div>
                      <input
                        id="walk-forward-validation-bars"
                        aria-label="검증기간"
                        type="range"
                        min={minWindowBars}
                        max={maxValidationBars}
                        step={1}
                        value={formState.validationBars}
                        onChange={(event) => {
                          const nextValidationMax = Math.max(minWindowBars, totalBars - formState.trainBars);
                          setFormState((current) => ({
                            ...current,
                            validationBars: clamp(Number(event.target.value), minWindowBars, nextValidationMax),
                          }));
                        }}
                        className="mt-4 h-2 w-full cursor-pointer appearance-none rounded-full bg-white/[0.08]"
                        style={sliderTrackStyle(formState.validationBars, minWindowBars, maxValidationBars)}
                      />
                      <div className="mt-2 flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-gray-500">
                        <span>{formatBarsLabel(minWindowBars)}</span>
                        <span>{formatBarsLabel(maxValidationBars)}</span>
                      </div>
                      <div data-testid="walk-forward-period-timeline" className="mt-5">
                        <div className="relative h-8 w-full">
                          <div
                            data-testid="walk-forward-timeline-train"
                            className="absolute inset-y-0 left-0 flex min-w-0 items-center justify-center rounded-md bg-[#3f78b5] px-2.5 text-[9px] font-black uppercase tracking-widest text-black"
                            style={{ width: `${timelineTrainPct}%` }}
                            title={`${formatDateLabel(firstTrainStart)} - ${formatDateLabel(firstTrainEnd)}`}
                          >
                            <span className="truncate">학습기간</span>
                          </div>
                          <div
                            data-testid="walk-forward-timeline-validation"
                            className="absolute inset-y-0 flex min-w-0 items-center justify-center rounded-md bg-[#c84b36] px-2.5 text-[9px] font-black uppercase tracking-widest text-black"
                            style={{ left: `${timelineTrainPct}%`, width: `${timelineValidationPct}%` }}
                            title={`${formatDateLabel(firstValidationStart ?? undefined)} - ${formatDateLabel(firstValidationEnd ?? undefined)}`}
                          >
                            <span className="truncate">검증기간</span>
                          </div>
                        </div>
                        <div className="mt-4 pt-3">
                          <div className="relative h-6">
                            <span
                              data-testid="walk-forward-timeline-axis-train-dates"
                              className="absolute top-0 max-w-[45%] -translate-x-1/2 text-center text-[11px] font-black leading-4 tabular-nums text-gray-500"
                              style={{ left: `${timelineTrainLabelPct}%` }}
                            >
                              <span className="block whitespace-nowrap">{formatDateLabel(firstTrainStart)} - {formatDateLabel(firstTrainEnd)}</span>
                            </span>
                            <span
                              data-testid="walk-forward-timeline-axis-validation-dates"
                              className="absolute top-0 max-w-[45%] -translate-x-1/2 text-center text-[11px] font-black leading-4 tabular-nums text-gray-500"
                              style={{ left: `${timelineValidationLabelPct}%` }}
                            >
                              <span className="block whitespace-nowrap">{formatDateLabel(firstValidationStart ?? undefined)} - {formatDateLabel(firstValidationEnd ?? undefined)}</span>
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="py-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">설정 요약</p>
                      <div className="mt-3 grid grid-cols-1 gap-3 text-xs font-bold text-gray-300 md:grid-cols-2">
                        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                          <p className="uppercase tracking-widest text-gray-500">백테스트 범위</p>
                          <p className="mt-2 leading-5 text-white">{formatDateLabel(periodStart)} - {formatDateLabel(periodEnd)}</p>
                        </div>
                        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                          <p className="uppercase tracking-widest text-gray-500">예상 구간 수</p>
                          <p className="mt-2 leading-5 text-white">{derivedSettings.n_splits}개</p>
                        </div>
                        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                          <p className="uppercase tracking-widest text-gray-500">훈련 비율</p>
                          <p className="mt-2 leading-5 text-white">{Math.round(derivedSettings.train_pct * 100)}%</p>
                        </div>
                        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                          <p className="uppercase tracking-widest text-gray-500">총 관측치</p>
                          <p className="mt-2 leading-5 text-white">{formatBarsLabel(totalBars)}</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </section>

                <section className="p-5">
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">최적화 설정</p>
                  <div className="mt-4 divide-y divide-white/[0.04] border-t border-white/[0.05]">
                    <div className="py-4">
                      <div className="flex items-center gap-1.5">
                        <p className="text-xs font-bold uppercase tracking-widest text-gray-500">최적화 대상 파라미터</p>
                        <HelpTooltip label="최적화 대상 파라미터">
                          <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                            최적화 대상 파라미터
                          </span>
                          <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
                            현재 전략에 실제 포함된 숫자 파라미터만 표시됩니다. 각 파라미터를 눌러 탐색 범위와 step을 조정하거나 최적화에서 제외할 수 있고, 제외한 파라미터는 원래 설정값을 그대로 사용합니다.
                          </span>
                          <span className="mt-3 block text-xs font-bold leading-5 text-gray-400">
                            예: PBR, 손절라인을 선택하면 각 IS 구간에서 PBR 임계값과 손절 비율의 조합을 다시 찾고, 보유기간·보유종목수는 기존 설정을 그대로 씁니다.
                          </span>
                        </HelpTooltip>
                      </div>
                      {visibleTargets.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {visibleTargets.map((target) => {
                            const isExcluded = excludedTargetIds.has(target.id);
                            const range = currentParameterRangeForTarget(target);
                            const unit = getParameterStepConfig(target.label).unit;
                            return (
                              <div key={target.id} className="flex flex-col gap-1">
                                <button
                                  type="button"
                                  onClick={() => openStepModal(target)}
                                  className={`rounded-md px-3 py-2 text-left text-sm font-black transition-colors focus:outline-none focus:ring-2 focus:ring-white/20 ${
                                    isExcluded
                                      ? "bg-white/[0.03] text-gray-500 line-through hover:bg-white/[0.06]"
                                      : "bg-white/[0.08] text-white hover:bg-white/[0.12]"
                                  }`}
                                >
                                  {target.label}
                                </button>
                                <span
                                  data-testid={`walk-forward-target-range-${target.label}`}
                                  className="px-1 text-[10px] font-bold tabular-nums tracking-wide text-gray-500"
                                >
                                  {isExcluded
                                    ? "제외됨"
                                    : range
                                      ? `${formatStepWithUnit(range.min, unit)}~${formatStepWithUnit(range.max, unit)}`
                                      : ""}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="mt-3 text-sm font-bold leading-6 text-gray-400">
                          현재 전략에서 조정 가능한 숫자 파라미터를 찾지 못했습니다.
                        </p>
                      )}
                    </div>
                    <div className="py-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">최적화 방법</p>
                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                        {OPTIMIZATION_METHOD_OPTIONS.map((method) => {
                          const active = formState.optimizationMethod === method.value;
                          return (
                            <button
                              type="button"
                              key={method.value}
                              aria-pressed={active}
                              onClick={() => setFormState((current) => ({ ...current, optimizationMethod: method.value }))}
                              className={`block cursor-pointer rounded-xl border p-4 transition-colors ${
                                active
                                  ? "border-sky-400/35 bg-white/[0.03]"
                                  : "border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.05]"
                              }`}
                            >
                              <span className="flex items-center justify-center">
                                <span className="text-sm font-black text-white">{method.label}</span>
                              </span>
                              <span className="mt-2 block text-left text-xs font-bold leading-5 text-gray-400">{method.body}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                    <div className="py-4">
                      {isGridMethod ? (
                        <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <p className="text-xs font-bold uppercase tracking-widest text-gray-500">그리드 탐색 예상</p>
                              <p className="mt-2 text-sm font-black leading-6 text-white">
                                현재 파라미터 범위 기준으로 약 {gridSearchEstimate.toLocaleString()}개 조합을 확인할 수 있습니다.
                              </p>
                            </div>
                            <span
                              className={`inline-flex rounded-md px-2 py-1 text-[10px] font-black uppercase tracking-widest ${
                                gridSearchExceedsCap
                                  ? "bg-amber-500/15 text-amber-300"
                                  : "bg-white/[0.06] text-gray-400"
                              }`}
                            >
                              {gridSearchExceedsCap ? "상한 초과" : "실행 가능"}
                            </span>
                          </div>
                          <p className="mt-3 text-xs font-bold leading-5 text-gray-400">
                            {gridSearchExceedsCap
                              ? `조합 수가 상한(${MAX_GRID_COMBINATIONS.toLocaleString()}개)을 초과해 실행할 수 없습니다. 파라미터 범위나 step을 조정해 조합 수를 줄여 주세요.`
                              : "설정한 범위 안의 모든 조합을 각 워크포워드 구간에서 전수 실행합니다."}
                          </p>
                        </div>
                      ) : (
                        <>
                          <div className="flex items-center gap-1.5">
                            <p className="text-xs font-bold uppercase tracking-widest text-gray-500">베이지안 최적화 시도 횟수</p>
                            <HelpTooltip label="베이지안 최적화 시도 횟수">
                              <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                                베이지안 최적화 시도 횟수
                              </span>
                              <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
                                각 워크포워드 구간에서 파라미터 조합을 몇 번 탐색할지 정합니다. 횟수가 늘면 더 많은 조합을 계산하지만 실행 시간이 길어집니다.
                              </span>
                              <span className="mt-3 block text-xs font-bold leading-5 text-gray-400">
                                예: 30회는 손절 5/7/10%, 이동평균 20/60일 같은 후보 조합을 최대 30번 평가해 과거 IS 구간의 목표 지표가 높게 나온 조합을 기록합니다.
                              </span>
                            </HelpTooltip>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {[20, 30, 50].map((value) => (
                              <button
                                key={value}
                                onClick={() => setFormState((current) => ({ ...current, n_trials: value }))}
                                className={buttonClass(formState.n_trials === value)}
                              >
                                {value}회
                              </button>
                            ))}
                          </div>
                        </>
                      )}
                    </div>
                    <div className="py-4">
                      <div className="flex items-center gap-1.5">
                        <p className="text-xs font-bold uppercase tracking-widest text-gray-500">IS 창 방식</p>
                        <HelpTooltip label="IS 창 방식">
                          <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                            IS 창 방식
                          </span>
                          <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
                            IS(In-Sample)는 파라미터를 맞추는 학습 구간입니다. 롤링은 학습과 검증 창이 함께 이동하고, 확장은 학습 구간을 시작일부터 누적해 넓힙니다.
                          </span>
                          <span className="mt-3 block text-xs font-bold leading-5 text-gray-400">
                            예: 롤링은 2020-2021 학습 후 2022 검증, 다음에는 2021-2022 학습 후 2023 검증처럼 이동합니다. 확장은 2020-2021 학습 후 2022 검증, 다음에는 2020-2022 학습 후 2023 검증처럼 누적합니다.
                          </span>
                        </HelpTooltip>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {[
                          { value: false, label: "롤링" },
                          { value: true, label: "확장" },
                        ].map((item) => (
                          <button
                            key={String(item.value)}
                            onClick={() => setFormState((current) => ({ ...current, anchor: item.value }))}
                            className={buttonClass(formState.anchor === item.value)}
                          >
                            {item.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>
              </div>
            )}

            {result && (
              <div className="divide-y divide-white/[0.08]">
                <div className="grid grid-cols-1 divide-y divide-white/[0.08] lg:grid-cols-10 lg:divide-x lg:divide-y-0">
                  <section className="lg:col-span-3">
                    <div className="p-5">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">Walk-Forward Efficiency</p>
                      {wfeValid ? (
                        <>
                          <div className="mt-3 flex items-end gap-3">
                            <span className={`text-4xl font-black tabular-nums font-outfit ${wfeTone.valueClass}`}>
                              {(wfe * 100).toFixed(1)}%
                            </span>
                            <span className={`px-2 py-1 text-[10px] font-black uppercase tracking-[0.16em] ${wfeTone.badgeClass}`}>
                              {wfeTone.text}
                            </span>
                          </div>
                          <p className="mt-3 text-xs font-bold leading-5 text-gray-400">
                            평균 OOS 수익률과 평균 IS 수익률의 비율입니다. 1.0에 가까울수록 구간 간 편차가 작게 나타난 편입니다.
                          </p>
                        </>
                      ) : (
                        <>
                          <div className="mt-3 flex items-end gap-3">
                            <span className="text-4xl font-black tabular-nums text-gray-500 font-outfit">-</span>
                            <span className="bg-white/[0.06] px-2 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-gray-400">
                              해석 불가
                            </span>
                          </div>
                          <p className="mt-3 text-xs font-bold leading-5 text-gray-400">
                            학습(IS) 구간 평균 수익률이 0 이하라 OOS/IS 비율을 해석할 수 없습니다. 구간별 결과를 직접 확인해 주세요.
                          </p>
                        </>
                      )}
                    </div>
                  </section>
                  <section className="lg:col-span-4">
                    <div className="p-5">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">OOS 평균 성과</p>
                      <div className="mt-4 grid grid-cols-3 gap-x-4 gap-y-4">
                        {[
                          { key: "avg_oos_cagr", label: "CAGR", suffix: "%" },
                          { key: "avg_oos_totalReturn", label: "총 수익률", suffix: "%" },
                          { key: "avg_oos_maxDrawdown", label: "MDD", suffix: "%" },
                          { key: "avg_oos_sharpe", label: "Sharpe", suffix: "" },
                          { key: "avg_oos_calmar", label: "Calmar", suffix: "" },
                          { key: "avg_oos_winRate", label: "승률", suffix: "%" },
                          { key: "avg_oos_profitFactor", label: "손익비", suffix: "" },
                          { key: "avg_oos_trades", label: "평균 거래 수", suffix: "" },
                          { key: "avg_oos_expectancy", label: "평균 거래손익", suffix: "%" },
                        ].map((item) => (
                          <div key={item.key} className="space-y-1">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">{item.label}</p>
                            <p className={`text-lg font-black tabular-nums font-outfit ${aggregateTone(item.key, result.aggregate[item.key])}`}>
                              {item.suffix === "%" ? fmt(result.aggregate[item.key], "%") : fmtNum(result.aggregate[item.key])}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </section>
                  <section className="lg:col-span-3">
                    <div className="p-5">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">실행 설정</p>
                      <div className="mt-3 divide-y divide-white/[0.04] border-t border-white/[0.05]">
                        {[
                          { label: "분할 수", value: `${result.n_splits}개` },
                          { label: "IS 창 방식", value: result.anchor ? "확장" : "롤링" },
                          { label: "목표 지표", value: TARGET_METRICS.find((metric) => metric.id === result.target_metric)?.label ?? result.target_metric },
                        ].map((item) => (
                          <div key={item.label} className="flex items-center justify-between gap-3 py-3">
                            <span className="text-xs font-bold uppercase tracking-widest text-gray-500">{item.label}</span>
                            <span className="text-sm font-black text-white font-outfit">{item.value}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </section>
                </div>

                {chartData.length > 0 && (
                  <section className="p-5">
                    <p className="text-xs font-bold uppercase tracking-widest text-gray-500">연속 OOS 에퀴티 커브</p>
                    <div className="mt-4 h-56 border border-white/[0.08] bg-white/[0.02] p-4">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                          <XAxis
                            dataKey="date"
                            tickFormatter={xTickFormatter}
                            tick={{ fontSize: 10, fill: "#6b7280", fontWeight: 700 }}
                            tickLine={false}
                            axisLine={false}
                            interval={Math.max(0, Math.floor(chartData.length / 6))}
                          />
                          <YAxis
                            tick={{ fontSize: 10, fill: "#6b7280", fontWeight: 700 }}
                            tickLine={false}
                            axisLine={false}
                            tickFormatter={(value) => `${value.toFixed(0)}`}
                            width={44}
                          />
                          <Tooltip
                            contentStyle={{
                              background: "#111111",
                              border: "1px solid rgba(255,255,255,0.08)",
                              borderRadius: 0,
                              fontSize: 11,
                              color: "#e5e7eb",
                            }}
                            labelStyle={{ color: "#9ca3af" }}
                            formatter={(value: any) => [`${Number(value).toFixed(2)}`, "자산"]}
                          />
                          <ReferenceLine y={chartData[0]?.equity ?? 1} stroke="rgba(255,255,255,0.12)" strokeDasharray="3 3" />
                          <Line
                            type="monotone"
                            dataKey="equity"
                            stroke="rgb(239, 68, 68)"
                            strokeWidth={2}
                            dot={false}
                            activeDot={{ r: 3, fill: "rgb(239, 68, 68)" }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </section>
                )}

                <section className="p-5">
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">구간별 결과</p>
                  <div className="mt-4 overflow-x-auto">
                    <div className="min-w-[760px]">
                      <div className="grid grid-cols-[64px_minmax(0,1fr)_minmax(0,1fr)_88px_88px_88px_88px] gap-2 px-2">
                        {["구간", "IS 기간", "OOS 기간", "IS CAGR", "OOS CAGR", "OOS MDD", "OOS 승률"].map((label) => (
                          <span key={label} className="text-xs font-bold uppercase tracking-widest text-gray-500">
                            {label}
                          </span>
                        ))}
                      </div>
                      <div className="mt-2 border-t border-white/[0.05]" />
                      <div className="divide-y divide-white/[0.04]">
                        {result.windows.map((window) => {
                          const oosCagr = Number(window.oos_metrics?.cagr);
                          const isPositive = !Number.isNaN(oosCagr) && oosCagr > 0;
                          return (
                            <div
                              key={window.window}
                              className="grid grid-cols-[64px_minmax(0,1fr)_minmax(0,1fr)_88px_88px_88px_88px] items-center gap-2 px-2 py-3 transition-colors hover:bg-white/[0.02]"
                            >
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-black text-white font-outfit">W{window.window}</span>
                                {window.error && <span className="text-[10px] font-black uppercase tracking-widest text-[var(--main-blue)]">오류</span>}
                              </div>
                              <span className="truncate text-xs font-bold text-gray-400 tabular-nums">{window.is_period}</span>
                              <span className="truncate text-xs font-bold text-gray-400 tabular-nums">{window.oos_period}</span>
                              <span className="text-right text-sm font-black tabular-nums text-white font-outfit">{fmt(window.is_metrics?.cagr, "%")}</span>
                              <span className={`text-right text-sm font-black tabular-nums font-outfit ${isPositive ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                                {fmt(window.oos_metrics?.cagr, "%")}
                              </span>
                              <span className="text-right text-sm font-black tabular-nums text-[var(--main-blue)] font-outfit">{fmt(window.oos_metrics?.maxDrawdown, "%")}</span>
                              <span className="text-right text-sm font-black tabular-nums text-white font-outfit">{fmt(window.oos_metrics?.winRate, "%")}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </section>

                <section className="p-5">
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">구간별 최적 파라미터</p>
                  <div className="mt-4 divide-y divide-white/[0.04] border-t border-white/[0.05]">
                    {result.windows.map((window) => {
                      const params = Object.entries(window.best_params ?? {});
                      if (params.length === 0) return null;

                      return (
                        <div key={window.window} className="grid grid-cols-1 gap-3 py-4 lg:grid-cols-[72px_minmax(0,1fr)]">
                          <span className="text-sm font-black uppercase tracking-widest text-white font-outfit">W{window.window}</span>
                          <div className="flex flex-wrap gap-2">
                            {params.slice(0, 8).map(([key, value]) => {
                              const shortKey = key.split(".").pop() ?? key;
                              return (
                                <span
                                  key={key}
                                  className="inline-flex items-center gap-1 bg-white/[0.04] px-2 py-1 text-[10px] font-black text-gray-300"
                                >
                                  <span className="uppercase tracking-widest text-gray-500">{shortKey}</span>
                                  <span className="text-white">{String(value)}</span>
                                </span>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>
              </div>
            )}
          </div>

          {stepModalTarget && stepModalDraftValue && stepModalCurrentRange && stepModalBounds && (
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="walk-forward-step-modal-title"
              className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/70 px-4"
            >
              <div className="w-full max-w-sm rounded-xl border border-white/[0.10] bg-[#111111] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.65)]">
                <p id="walk-forward-step-modal-title" className="text-xs font-bold uppercase tracking-widest text-gray-500">
                  {stepModalTarget.label} 값 설정
                </p>
                <div className="mt-5 space-y-5">
                  <div>
                    <label htmlFor="walk-forward-parameter-min" className="block text-xs font-bold uppercase tracking-widest text-gray-500">
                      하한값
                    </label>
                    <div className="relative mt-3">
                      <input
                        id="walk-forward-parameter-min"
                        aria-label={`${stepModalTarget.label} 하한값`}
                        aria-invalid={stepModalError ? "true" : undefined}
                        aria-describedby="walk-forward-parameter-examples walk-forward-parameter-error"
                        type="number"
                        step={stepModalConfig.inputStep}
                        value={formatParameterInputValue(stepModalDraftValue.min)}
                        onChange={(event) => {
                          const nextMin = parseParameterInputValue(event.target.value);
                          setStepModalDraft((current) => {
                            if (!current) return current;
                            return {
                              ...current,
                              min: nextMin,
                            };
                          });
                          setStepModalError(null);
                        }}
                        className={`w-full rounded-md border-0 bg-white/[0.04] py-3 pl-3 text-xl font-black text-white shadow-none outline-none transition-colors font-outfit focus:border-0 focus:ring-0 focus:shadow-none ${
                          stepModalConfig.unit ? "pr-16" : "pr-3"
                        }`}
                      />
                      {stepModalConfig.unit && (
                        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm font-black text-gray-500">
                          {stepModalConfig.unit}
                        </span>
                      )}
                    </div>
                    <p id="walk-forward-parameter-examples" className="mt-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">
                      예: {stepModalInputExamples.map((value) => formatStepWithUnit(value, stepModalConfig.unit)).join(", ")}
                    </p>
                  </div>
                  <div>
                    <label htmlFor="walk-forward-parameter-max" className="block text-xs font-bold uppercase tracking-widest text-gray-500">
                      상한값
                    </label>
                    <div className="relative mt-3">
                      <input
                        id="walk-forward-parameter-max"
                        aria-label={`${stepModalTarget.label} 상한값`}
                        aria-invalid={stepModalError ? "true" : undefined}
                        aria-describedby="walk-forward-parameter-examples walk-forward-parameter-error"
                        type="number"
                        step={stepModalConfig.inputStep}
                        value={formatParameterInputValue(stepModalDraftValue.max)}
                        onChange={(event) => {
                          const nextMax = parseParameterInputValue(event.target.value);
                          setStepModalDraft((current) => {
                            if (!current) return current;
                            return {
                              ...current,
                              max: nextMax,
                            };
                          });
                          setStepModalError(null);
                        }}
                        className={`w-full rounded-md border-0 bg-white/[0.04] py-3 pl-3 text-xl font-black text-white shadow-none outline-none transition-colors font-outfit focus:border-0 focus:ring-0 focus:shadow-none ${
                          stepModalConfig.unit ? "pr-16" : "pr-3"
                        }`}
                      />
                      {stepModalConfig.unit && (
                        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm font-black text-gray-500">
                          {stepModalConfig.unit}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">
                      예: {stepModalInputExamples.map((value) => formatStepWithUnit(value, stepModalConfig.unit)).join(", ")}
                    </p>
                    {stepModalError && (
                      <p id="walk-forward-parameter-error" className="mt-2 text-xs font-bold leading-5 text-[var(--main-blue)]">
                        {stepModalError}
                      </p>
                    )}
                  </div>
                  <div>
                    <label htmlFor="walk-forward-parameter-step" className="block text-xs font-bold uppercase tracking-widest text-gray-500">
                      step 값
                    </label>
                    <div className="mt-2 flex items-end justify-between gap-3">
                      <p className="text-2xl font-black text-white font-outfit">
                        {formatStepWithUnit(stepModalDraftValue.step, stepModalConfig.unit)}
                      </p>
                      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                        {stepModalConfig.stepOptions.length}개 후보
                      </p>
                    </div>
                    <div
                      id="walk-forward-parameter-step"
                      aria-label={`${stepModalTarget.label} step 값`}
                      className="mt-4 grid grid-cols-3 gap-2"
                    >
                      {stepModalConfig.stepOptions.map((option) => {
                        const active = option.toFixed(4) === stepModalDraftValue.step.toFixed(4);
                        return (
                          <button
                            key={option}
                            type="button"
                            aria-pressed={active}
                            onClick={() => {
                              setStepModalDraft((current) => current ? { ...current, step: option } : current);
                            }}
                            className={`rounded-md px-3 py-2 text-xs font-black transition-colors ${
                              active
                                ? "bg-[var(--main-blue)] text-white"
                                : "bg-white/[0.06] text-gray-400 hover:bg-white/[0.10] hover:text-white"
                            }`}
                          >
                            {formatStepWithUnit(option, stepModalConfig.unit)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
                <p className="mt-3 text-xs font-bold leading-5 text-gray-500">
                  현재 적용: {formatStepWithUnit(stepModalCurrentRange.min, stepModalConfig.unit)} -{" "}
                  {formatStepWithUnit(stepModalCurrentRange.max, stepModalConfig.unit)} / step{" "}
                  {formatStepWithUnit(stepModalCurrentRange.step, stepModalConfig.unit)}
                </p>
                <div className="mt-5 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={resetStepModal}
                      className="rounded-md px-3 py-2 text-xs font-black text-gray-500 transition-colors hover:bg-white/[0.04] hover:text-gray-300"
                    >
                      기본값
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        toggleTargetExcluded(stepModalTarget.id);
                        closeStepModal();
                      }}
                      className="rounded-md px-3 py-2 text-xs font-black text-gray-500 transition-colors hover:bg-white/[0.04] hover:text-gray-300"
                    >
                      {excludedTargetIds.has(stepModalTarget.id) ? "최적화에 포함" : "최적화에서 제외"}
                    </button>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={closeStepModal}
                      className="rounded-md px-3 py-2 text-xs font-black text-gray-400 transition-colors hover:bg-white/[0.04] hover:text-white"
                    >
                      닫기
                    </button>
                    <button
                      type="button"
                      onClick={saveStepModal}
                      className="rounded-md bg-[var(--main-blue)] px-3 py-2 text-xs font-black text-white transition-opacity hover:opacity-90"
                    >
                      저장
	                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="flex items-center justify-between gap-3 border-t border-white/[0.08] px-5 py-4">
            {result ? (
              <button
                onClick={() => {
                  setResult(null);
                  setError(null);
                }}
                className="px-4 py-2 text-sm font-black text-gray-400 transition-colors hover:bg-white/[0.03] hover:text-white"
              >
                재설정
              </button>
            ) : (
              <div />
            )}
            <div className="flex items-center gap-2">
              {onClose && (
                <button
                  onClick={handleClose}
                  disabled={isRunning}
                  className="px-4 py-2 text-sm font-black text-gray-400 transition-colors hover:bg-white/[0.03] hover:text-white disabled:opacity-40"
                >
                  닫기
                </button>
              )}
              {!result && isRunning && (
                <>
                  {runProgress?.stage === "window" && runProgress.total ? (
                    <div className="flex items-center gap-2">
                      <div
                        role="progressbar"
                        aria-label="워크포워드 진행률"
                        aria-valuemin={0}
                        aria-valuemax={runProgress.total}
                        aria-valuenow={runProgress.window ?? 0}
                        className="h-2 w-32 overflow-hidden rounded-full bg-white/[0.08]"
                      >
                        <div
                          className="h-full rounded-full bg-[var(--main-blue)] transition-[width]"
                          style={{ width: `${Math.round((((runProgress.window ?? 1) - 1) / runProgress.total) * 100)}%` }}
                        />
                      </div>
                      <span className="text-[11px] font-black tabular-nums text-gray-400">
                        {runProgress.window}/{runProgress.total} 구간
                      </span>
                    </div>
                  ) : null}
                  <button
                    onClick={handleCancel}
                    className="px-4 py-2 text-sm font-black text-gray-400 transition-colors hover:bg-white/[0.03] hover:text-white"
                  >
                    취소
                  </button>
                </>
              )}
              {!result && (
                <button
                  onClick={handleRun}
                  disabled={isRunDisabled}
                  title={isRunDisabled && !isRunning ? runDisabledReason : undefined}
                  className="inline-flex items-center gap-2 bg-[var(--main-blue)] px-4 py-2 text-sm font-black text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isRunning ? (
                    <>
                      <ArrowsClockwise className="h-4 w-4 animate-spin" />
                      {runProgress?.stage === "window" && runProgress.total
                        ? `분석 중... (${runProgress.window}/${runProgress.total} 구간)`
                        : `분석 중... (${derivedSettings.n_splits}개 구간)`}
                    </>
                  ) : (
                    <>
                      <ChartLine className="h-4 w-4" />
                      워크포워드 분석 시작
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        </div>
  );
}

export default function WalkForwardModal({
  open,
  onOpenChange,
  onRun,
  backtestDates = [],
  optimizationTargets = [],
  baseStrategy,
}: WalkForwardModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[9999] overflow-y-auto bg-black/80 p-2 md:p-3">
      <div className="flex min-h-full items-start justify-center pt-14 md:pt-20">
        <div className="w-full max-w-6xl">
          <WalkForwardPanel
            onRun={onRun}
            backtestDates={backtestDates}
            optimizationTargets={optimizationTargets}
            baseStrategy={baseStrategy}
            onClose={() => onOpenChange(false)}
            maxHeightClass="max-h-[calc(100vh-9rem)]"
          />
        </div>
      </div>
    </div>
  );
}
