"use client";

import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { ArrowsClockwise, ChartLine, Warning } from "phosphor-react";
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
  parameter_steps?: Record<string, number>;
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
}

interface WalkForwardModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRun: (settings: WalkForwardSettings) => Promise<WalkForwardResult>;
  backtestDates?: string[];
  optimizationTargets?: WalkForwardOptimizationTarget[];
}

interface WalkForwardPanelProps {
  onRun?: (settings: WalkForwardSettings) => Promise<WalkForwardResult>;
  backtestDates?: string[];
  optimizationTargets?: WalkForwardOptimizationTarget[];
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
}

const FALLBACK_TOTAL_BARS = 252 * 5;

type ParameterStepConfig = {
  defaultStep: number;
  min: number;
  max: number;
  inputStep: number;
  unit: string;
};

const DEFAULT_PARAMETER_STEP_CONFIG: ParameterStepConfig = {
  defaultStep: 1,
  min: 0.1,
  max: 50,
  inputStep: 0.1,
  unit: "",
};

const PARAMETER_STEP_CONFIGS: Array<{ pattern: RegExp } & ParameterStepConfig> = [
  { pattern: /pbr/i, defaultStep: 0.1, min: 0.05, max: 1, inputStep: 0.05, unit: "" },
  { pattern: /per/i, defaultStep: 1, min: 0.5, max: 10, inputStep: 0.5, unit: "" },
  { pattern: /roe/i, defaultStep: 1, min: 0.5, max: 10, inputStep: 0.5, unit: "%p" },
  { pattern: /손절|stop\s*loss/i, defaultStep: 1, min: 0.1, max: 20, inputStep: 0.1, unit: "%p" },
  { pattern: /익절|take\s*profit/i, defaultStep: 5, min: 0.5, max: 50, inputStep: 0.5, unit: "%p" },
  { pattern: /트레일링|trailing/i, defaultStep: 1, min: 0.5, max: 10, inputStep: 0.5, unit: "%p" },
  { pattern: /보유기간|holding/i, defaultStep: 5, min: 1, max: 60, inputStep: 1, unit: "거래일" },
  { pattern: /보유종목수|종목|positions?/i, defaultStep: 1, min: 1, max: 20, inputStep: 1, unit: "종목" },
  { pattern: /리밸런싱|rebalanc/i, defaultStep: 5, min: 1, max: 60, inputStep: 1, unit: "거래일" },
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
  };
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
  const [result, setResult] = useState<WalkForwardResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [parameterStepOverrides, setParameterStepOverrides] = useState<Record<string, number>>({});
  const [stepModalTargetId, setStepModalTargetId] = useState<string | null>(null);
  const [stepDraft, setStepDraft] = useState("");
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

  const parameterSteps = optimizationTargets.reduce<Record<string, number>>((steps, target) => {
    steps[target.label] = parameterStepOverrides[target.id] ?? getParameterStepConfig(target.label).defaultStep;
    return steps;
  }, {});

  const derivedSettings: WalkForwardSettings = {
    n_splits: deriveSplitCount(totalBars, formState.trainBars, formState.validationBars),
    train_pct: deriveTrainPct(totalBars, formState.trainBars, formState.validationBars, formState.anchor),
    anchor: formState.anchor,
    target_metric: formState.target_metric,
    n_trials: formState.n_trials,
    ...(optimizationTargets.length > 0 ? { parameter_steps: parameterSteps } : {}),
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

    try {
      const res = await onRun(derivedSettings);
      if (res.status === "error") {
        setError(res.message || "분석 중 오류가 발생했습니다.");
      } else {
        setResult(res);
      }
    } catch (e: any) {
      setError(e.message || "알 수 없는 오류가 발생했습니다.");
    } finally {
      setIsRunning(false);
      abortRef.current = null;
    }
  };

  const handleClose = () => {
    if (!isRunning) onClose?.();
  };

  const openStepModal = (target: WalkForwardOptimizationTarget) => {
    const config = getParameterStepConfig(target.label);
    setStepModalTargetId(target.id);
    setStepDraft((parameterStepOverrides[target.id] ?? config.defaultStep).toString());
  };

  const closeStepModal = () => {
    setStepModalTargetId(null);
    setStepDraft("");
  };

  const resetStepModal = () => {
    if (!stepModalTargetId) return;
    setParameterStepOverrides((current) => {
      const next = { ...current };
      delete next[stepModalTargetId];
      return next;
    });
    closeStepModal();
  };

  const saveStepModal = () => {
    if (!stepModalTargetId) return;
    const target = optimizationTargets.find((item) => item.id === stepModalTargetId);
    if (!target) return;
    const config = getParameterStepConfig(target.label);
    const trimmed = stepDraft.trim();
    if (!trimmed) {
      resetStepModal();
      return;
    }

    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setStepDraft(config.defaultStep.toString());
      return;
    }

    setParameterStepOverrides((current) => ({
      ...current,
      [stepModalTargetId]: Number(clamp(parsed, config.min, config.max).toFixed(4)),
    }));
    closeStepModal();
  };

  const chartData = result?.combined_dates?.map((date, index) => ({
    date,
    equity: result.combined_equity[index] ?? null,
  })) ?? [];

  const xTickFormatter = (value: string) => value?.slice(0, 7) ?? "";
  const wfe = result?.walk_forward_efficiency ?? 0;
  const wfeTone = getWfeTone(wfe);
  const isRunDisabled = isRunning || !onRun || !canRun;
  const stepModalTarget = optimizationTargets.find((target) => target.id === stepModalTargetId) ?? null;
  const stepModalConfig = stepModalTarget ? getParameterStepConfig(stepModalTarget.label) : DEFAULT_PARAMETER_STEP_CONFIG;
  const stepModalCurrentValue =
    stepModalTarget && parameterStepOverrides[stepModalTarget.id] !== undefined
      ? parameterStepOverrides[stepModalTarget.id]
      : stepModalConfig.defaultStep;
  const parsedStepDraft = Number(stepDraft);
  const stepModalDraftValue = Number.isFinite(parsedStepDraft)
    ? clamp(parsedStepDraft, stepModalConfig.min, stepModalConfig.max)
    : stepModalCurrentValue;

  return (
        <div data-testid="walk-forward-panel" className="w-full border border-white/[0.08] bg-[var(--background)]">
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
                  </div>
                </section>

                <section className="p-5">
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">최적화 설정</p>
                  <div className="mt-4 divide-y divide-white/[0.04] border-t border-white/[0.05]">
                    <div className="py-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">최적화 대상 파라미터</p>
                      {optimizationTargets.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {optimizationTargets.map((target) => (
                            <button
                              type="button"
                              key={target.id}
                              onClick={() => openStepModal(target)}
	                              className="rounded-md bg-white/[0.08] px-3 py-2 text-left text-sm font-black text-white transition-colors hover:bg-white/[0.12] focus:outline-none focus:ring-2 focus:ring-white/20"
	                            >
	                              <span className="block">{target.label}</span>
	                              <span className="mt-1 block text-[10px] font-bold uppercase tracking-widest text-gray-500">
	                                {formatStepWithUnit(parameterSteps[target.label], getParameterStepConfig(target.label).unit)}
	                              </span>
	                            </button>
                          ))}
                        </div>
                      ) : (
                        <p className="mt-3 text-sm font-bold leading-6 text-gray-400">
                          현재 전략 요약 배지가 없습니다.
                        </p>
                      )}
                    </div>
                    <div className="py-4">
                      <div className="flex items-center gap-1.5">
                        <p className="text-xs font-bold uppercase tracking-widest text-gray-500">Optuna 시도 횟수</p>
                        <HelpTooltip label="Optuna 시도 횟수">
                          <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                            Optuna 시도 횟수
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
                    <div className="py-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">분석 메모</p>
                      <p className="mt-3 text-sm font-black leading-6 text-white">
                        현재 백테스트 구간은 {formatDateLabel(periodStart)} - {formatDateLabel(periodEnd)}이며, 예상 구간 수는 {derivedSettings.n_splits}개입니다.
                      </p>
                      <p className="mt-2 text-xs font-bold leading-5 text-gray-400">
                        {formState.anchor
                          ? `확장 방식은 첫 ${formatBarsLabel(formState.trainBars)}을 기준 IS로 두고 이후 검증기간만큼 앞으로 넓혀갑니다.`
                          : `롤링 방식은 학습 ${formatBarsLabel(formState.trainBars)} + 검증 ${formatBarsLabel(formState.validationBars)} 창을 함께 앞으로 이동시킵니다.`}
                      </p>
                      <div className="mt-4 grid grid-cols-1 gap-3 border border-white/[0.06] bg-white/[0.02] p-4 text-xs font-bold text-gray-300 md:grid-cols-3">
                        <div>
                          <p className="uppercase tracking-widest text-gray-500">백테스트 범위</p>
                          <p className="mt-2 leading-5 text-white">{formatDateLabel(periodStart)} - {formatDateLabel(periodEnd)}</p>
                        </div>
                        <div>
                          <p className="uppercase tracking-widest text-gray-500">파생 훈련 비율</p>
                          <p className="mt-2 leading-5 text-white">{Math.round(derivedSettings.train_pct * 100)}%</p>
                        </div>
                        <div>
                          <p className="uppercase tracking-widest text-gray-500">총 관측치</p>
                          <p className="mt-2 leading-5 text-white">{formatBarsLabel(totalBars)}</p>
                        </div>
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
                    </div>
                  </section>
                  <section className="lg:col-span-4">
                    <div className="p-5">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">OOS 평균 성과</p>
                      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-4">
                        {[
                          { key: "avg_oos_cagr", label: "CAGR", suffix: "%" },
                          { key: "avg_oos_totalReturn", label: "총 수익률", suffix: "%" },
                          { key: "avg_oos_maxDrawdown", label: "MDD", suffix: "%" },
                          { key: "avg_oos_sharpe", label: "Sharpe", suffix: "" },
                          { key: "avg_oos_winRate", label: "승률", suffix: "%" },
                          { key: "avg_oos_profitFactor", label: "손익비", suffix: "" },
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

          {stepModalTarget && (
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="walk-forward-step-modal-title"
              className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/70 px-4"
            >
              <div className="w-full max-w-sm rounded-xl border border-white/[0.10] bg-[#111111] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.65)]">
                <p id="walk-forward-step-modal-title" className="text-xs font-bold uppercase tracking-widest text-gray-500">
                  {stepModalTarget.label} step 설정
                </p>
                <label htmlFor="walk-forward-parameter-step" className="mt-5 block text-xs font-bold uppercase tracking-widest text-gray-500">
                  step 값
                </label>
                <div className="mt-2 flex items-end justify-between gap-3">
                  <p className="text-2xl font-black text-white font-outfit">
                    {formatStepWithUnit(stepModalDraftValue, stepModalConfig.unit)}
                  </p>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                    {formatStepWithUnit(stepModalConfig.min, stepModalConfig.unit)} -{" "}
                    {formatStepWithUnit(stepModalConfig.max, stepModalConfig.unit)}
                  </p>
                </div>
                <input
                  id="walk-forward-parameter-step"
                  aria-label={`${stepModalTarget.label} step 값`}
                  type="range"
                  min={stepModalConfig.min}
                  max={stepModalConfig.max}
                  step={stepModalConfig.inputStep}
                  value={stepModalDraftValue}
                  onChange={(event) => setStepDraft(event.target.value)}
                  style={sliderTrackStyle(stepModalDraftValue, stepModalConfig.min, stepModalConfig.max)}
                  className="mt-4 h-2 w-full cursor-pointer appearance-none rounded-full bg-white/[0.08]"
                />
                <p className="mt-2 text-xs font-bold leading-5 text-gray-500">
                  현재 적용:{" "}
                  {formatStepWithUnit(stepModalCurrentValue, stepModalConfig.unit)}
                </p>
                <div className="mt-5 flex items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={resetStepModal}
                    className="rounded-md px-3 py-2 text-xs font-black text-gray-500 transition-colors hover:bg-white/[0.04] hover:text-gray-300"
                  >
                    기본값
                  </button>
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
              {!result && (
                <button
                  onClick={handleRun}
                  disabled={isRunDisabled}
                  title={isRunDisabled && !isRunning ? disabledReason : undefined}
                  className="inline-flex items-center gap-2 bg-[var(--main-blue)] px-4 py-2 text-sm font-black text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isRunning ? (
                    <>
                      <ArrowsClockwise className="h-4 w-4 animate-spin" />
                      분석 중... ({derivedSettings.n_splits}개 구간)
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
            onClose={() => onOpenChange(false)}
            maxHeightClass="max-h-[calc(100vh-9rem)]"
          />
        </div>
      </div>
    </div>
  );
}
