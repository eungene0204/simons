"use client";

import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { ArrowsClockwise, ChartLine } from "phosphor-react";
import {
  buildWalkForwardParameterDescriptors,
  buildWalkForwardParameterRanges,
  findWalkForwardRangeBoundsForLabel,
  walkForwardRangeBoundsForPath,
  MA_CROSSOVER_PERIOD_VALUES,
  type StrategyBacktestRequest,
  type WalkForwardParameterRangeOverride,
} from "../../../app/analytics/new/parsedStrategyMerge";
import ResultPlainSummary, { buildWalkForwardPlainSummary } from "./ResultPlainSummary";
import RunProgressModal from "./RunProgressModal";
import SaveValidationButton from "./SaveValidationButton";
import { saveValidation, buildWalkForwardSummary } from "../../../lib/validation-storage";
import { t } from "@/lib/i18n";

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
  // WFE 산정 기준. 현행 백엔드는 "cagr"(연환산). 없으면 구버전 저장 결과(총수익률 기준, 기간 길이 편향).
  wfe_basis?: string;
}

export interface WalkForwardRunProgress {
  stage: string;
  window?: number;
  total?: number;
  is_period?: string;
  oos_period?: string;
  message?: string;
  trial?: number;
  trial_total?: number;
  timing?: WalkForwardTiming;
}

export interface WalkForwardTiming {
  phase1: number;
  simulator: number;
  format: number;
  total: number;
  symbols: number;
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
  baseBacktestSeconds?: number;
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
  // 저장된 결과를 불러와 표시할 때 주입한다(변경 시 결과 패널이 이 값으로 대체된다).
  loadedResult?: WalkForwardResult | null;
  // 결과 저장에 쓰이는 전략 식별 정보.
  strategyName?: string;
  promptText?: string;
  cacheKey?: string;
  // 기준 백테스트(전체 기간)의 실측 소요 시간(초). 예상 소요 시간 보정에 사용한다.
  baseBacktestSeconds?: number;
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
// 기준 백테스트 실측 시간이 없을 때 쓰는 백테스트 1회당 기본 소요(초). 대략적 폴백값.
const FALLBACK_PER_BACKTEST_SEC = 0.6;
type OptimizationMethod = "bayesian" | "grid";

// 초 단위를 "약 3분", "약 1시간 20분", "1분 미만"처럼 사람이 읽는 문구로 바꾼다.
function formatDurationApprox(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return t("1분 미만");
  const totalMinutes = Math.round(seconds / 60);
  if (totalMinutes < 1) return t("1분 미만");
  if (totalMinutes < 60) return t("약 {0}분", totalMinutes);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes > 0 ? t("약 {0}시간 {1}분", hours, minutes) : t("약 {0}시간", hours);
}

// 예측은 오차가 크므로 점 추정 대신 ±범위로 보여준다. (하한 0.7배 ~ 상한 1.4배)
function formatDurationRange(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return t("1분 미만");
  const lowMin = Math.max(1, Math.round((seconds * 0.7) / 60));
  const highMin = Math.max(lowMin, Math.round((seconds * 1.4) / 60));
  const fmt = (min: number) => (min < 60 ? t("{0}분", min) : min % 60 === 0 ? t("{0}시간", min / 60) : t("{0}시간 {1}분", Math.floor(min / 60), min % 60));
  if (lowMin === highMin) return t("약 {0}", fmt(lowMin));
  return t("약 {0} ~ {1}", fmt(lowMin), fmt(highMin));
}
// 백엔드 engine/grid_optimizer.py의 MAX_GRID_COMBINATIONS와 동일한 값으로 유지한다.
const MAX_GRID_COMBINATIONS = 500;
// 백엔드 engine/walk_forward.py의 MAX_WINDOWS와 동일한 값으로 유지한다.
const MAX_WALK_FORWARD_WINDOWS = 24;
// 이보다 짧은 검증 창은 CAGR 연환산 잡음이 커진다(약 3개월 미만) — 실행은 막지 않고 안내만 한다.
const SHORT_VALIDATION_BARS = 63;

type ParameterStepConfig = {
  defaultStep: number;
  min: number;
  max: number;
  inputStep: number;
  stepOptions: number[];
  unit: string;
  // 지정 시 min~max/step 대신 이 값들만 탐색 후보로 사용한다 (예: 이동평균 일선).
  allowedValues?: number[];
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
  {
    pattern: /이동평균\s*(단기|장기)/,
    defaultStep: 0,
    min: MA_CROSSOVER_PERIOD_VALUES[0],
    max: MA_CROSSOVER_PERIOD_VALUES[MA_CROSSOVER_PERIOD_VALUES.length - 1],
    inputStep: 1,
    stepOptions: [],
    unit: "일선",
    allowedValues: MA_CROSSOVER_PERIOD_VALUES,
  },
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
  return `${formatStepValue(value)}${t(unit)}`;
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
  if (left.values || right.values) {
    const a = left.values ?? [];
    const b = right.values ?? [];
    return a.length === b.length && a.every((value, index) => value === b[index]);
  }
  return (
    left.min.toFixed(4) === right.min.toFixed(4)
    && left.max.toFixed(4) === right.max.toFixed(4)
    && left.step.toFixed(4) === right.step.toFixed(4)
  );
}

// paramLabelByKey에 없는 키(예: baseStrategy 없이 과거 결과만 표시하는 화면)를 위한 최후 폴백 —
// 변수명 그대로 노출하는 대신 최소한 사람이 읽을 수 있는 형태로 바꾼다.
function humanizeParamKey(key: string) {
  const last = key.split(".").pop() ?? key;
  return last
    .replace(/_/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .trim();
}

function formatDateLabel(date?: string) {
  if (!date) return "-";
  return date.replaceAll("-", ".");
}

function formatBarsLabel(bars: number) {
  return t("{0}거래일", bars.toLocaleString());
}

function formatApproxDuration(bars: number) {
  const years = bars / 252;
  if (years >= 1) {
    const roundedYears = years >= 2 ? Math.round(years * 10) / 10 : Math.round(years * 100) / 100;
    return t("약 {0}년", roundedYears);
  }

  const months = Math.max(1, Math.round(bars / 21));
  return t("약 {0}개월", months);
}

function deriveMinWindowBars(totalBars: number) {
  return Math.max(5, Math.min(20, Math.floor(totalBars / 4) || 5));
}

// 백엔드 _split_windows(is_bars/oos_bars)와 같은 규칙 — 롤링·확장 모두 검증 길이를 다 채우는 창만
// 센다(조각 창 없음). 여기 표시된 구간 수가 실제 실행 구간 수다(표시=실행).
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

interface WalkForwardParameterAnalysis {
  key: string;
  label: string;
  representative: number;
  mean: number;
  standardDeviation: number;
  min: number;
  max: number;
  stability: number | null;
}

function buildParameterAnalysis(
  key: string,
  label: string,
  windows: WindowResult[]
): WalkForwardParameterAnalysis | null {
  const values = windows
    .flatMap((window) => {
      const value = window.best_params?.[key];
      if ((typeof value !== "number" && typeof value !== "string") || value === "") return [];
      const numericValue = Number(value);
      return Number.isFinite(numericValue) ? [numericValue] : [];
    })
    .sort((a, b) => a - b);
  if (values.length === 0) return null;

  const mean = values.reduce((total, value) => total + value, 0) / values.length;
  const middle = Math.floor(values.length / 2);
  const representative = values.length % 2 === 0
    ? (values[middle - 1] + values[middle]) / 2
    : values[middle];
  const variance = values.reduce((total, value) => total + (value - mean) ** 2, 0) / values.length;
  const standardDeviation = Math.sqrt(variance);
  let stability: number | null = null;

  if (values.length >= 2) {
    if (standardDeviation === 0) {
      stability = 5;
    } else if (Math.abs(mean) < Number.EPSILON) {
      stability = 1;
    } else {
      const coefficientOfVariation = standardDeviation / Math.abs(mean);
      stability = coefficientOfVariation <= 0.05
        ? 5
        : coefficientOfVariation <= 0.1
          ? 4
          : coefficientOfVariation <= 0.2
            ? 3
            : coefficientOfVariation <= 0.35
              ? 2
              : 1;
    }
  }

  return {
    key,
    label,
    representative,
    mean,
    standardDeviation,
    min: values[0],
    max: values[values.length - 1],
    stability,
  };
}

function formatParameterAnalysisValue(value: number) {
  return Number(value.toFixed(2)).toLocaleString("ko-KR", { maximumFractionDigits: 2 });
}

// WFE 구간 기준 (창별 OOS CAGR 평균 ÷ 창별 IS CAGR 평균 — 연환산끼리). 뱃지·설명·기준표가 모두 이 목록을 공유한다.
// 문구는 과거 데이터에서 관측된 사실만 서술한다 — "실전에서도 재현될 가능성", "권장" 같은 전망·권유 표현은
// 규제 안전 원칙(전망·행동 제안 금지) 위반이라 2026-08-19 감사에서 제거했다. 등급명도 우열 평가어(우수·위험)
// 대신 "학습 성과가 검증에서 얼마나 남았는가"를 그대로 말하는 서술어를 쓴다.
const WFE_TIERS = [
  {
    min: 1.0,
    emoji: "🟢",
    text: "성과 유지",
    range: "≥ 100%",
    summary: "검증 성과가 학습 성과 이상이었음",
    description: "검증 구간의 연평균 수익률이 학습 구간과 같거나 더 높았습니다.",
    valueClass: "text-emerald-400",
    badgeClass: "bg-emerald-500/15 text-emerald-400",
  },
  {
    min: 0.8,
    emoji: "🟢",
    text: "대부분 유지",
    range: "80~99%",
    summary: "학습 성과의 80% 이상이 검증에서도 나타남",
    description: "학습 구간 성과의 대부분이 처음 보는 검증 구간에서도 나타났습니다.",
    valueClass: "text-emerald-400",
    badgeClass: "bg-emerald-500/15 text-emerald-400",
  },
  {
    min: 0.6,
    emoji: "🟡",
    text: "일부 감소",
    range: "60~79%",
    summary: "검증 성과가 학습 대비 20~40% 낮았음",
    description: "검증 구간 성과가 학습 구간보다 20~40% 낮았습니다.",
    valueClass: "text-yellow-400",
    badgeClass: "bg-yellow-500/15 text-yellow-400",
  },
  {
    min: 0.4,
    emoji: "🟠",
    text: "큰 폭 감소",
    range: "40~59%",
    summary: "검증 성과가 학습 대비 절반 안팎에 그침",
    description: "검증 구간 성과가 학습 구간의 절반 안팎에 그쳤습니다. 특정 구간에 맞춰진(과최적화) 결과였을 가능성이 있습니다.",
    valueClass: "text-orange-400",
    badgeClass: "bg-orange-500/15 text-orange-400",
  },
  {
    min: -Infinity,
    emoji: "🔴",
    text: "대부분 소실",
    range: "< 40%",
    summary: "학습 성과의 40% 미만만 검증에서 유지됨",
    description: "검증 구간에서는 학습 구간 성과의 40%도 유지되지 않았습니다. 과최적화 가능성이 큰 편입니다.",
    valueClass: "text-red-400",
    badgeClass: "bg-red-500/15 text-red-400",
  },
];

const getWfeTone = (wfe: number) => {
  const tier = WFE_TIERS.find((tv) => wfe >= tv.min) ?? WFE_TIERS[WFE_TIERS.length - 1];
  return {
    ...tier,
    // 음수 WFE는 학습 대비 검증이 손실이라는 뜻이므로 값 폰트를 파란색으로 구분한다.
    valueClass: wfe < 0 ? "text-blue-400" : tier.valueClass,
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
    value: "bayesian",
    label: "베이지안 최적화",
    body: "유망한 후보를 우선 탐색하며 제한된 횟수 안에서 조합을 살펴봅니다.",
  },
  {
    value: "grid",
    label: "그리드 탐색",
    body: "설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다.",
  },
];

const buttonClass = (active: boolean) =>
  `rounded-md px-3 py-2 text-sm font-black transition-colors ${
    active
      ? "bg-white/[0.08] text-white"
      : "bg-transparent text-gray-400 hover:bg-white/[0.03] hover:text-white"
  }`;

/** placement="top"은 패널 맨 아래 항목처럼 아래로 펼치면 잘리는 자리에서 쓴다
 *  (패널 루트가 overflow-hidden이라 넘친 부분이 그대로 잘린다). */
function HelpTooltip({
  label,
  children,
  placement = "bottom",
}: {
  label: string;
  children: ReactNode;
  placement?: "bottom" | "top";
}) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={t("{0} 도움말", label)}
        className="flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-white/25 text-[10px] font-black leading-none text-gray-400 transition-colors hover:border-white/50 hover:text-white focus:border-white/60 focus:text-white focus:outline-none"
      >
        ?
      </button>
      <span
        role="tooltip"
        data-placement={placement}
        className={`pointer-events-none absolute left-0 z-20 w-80 max-w-[calc(100vw-3rem)] border border-white/[0.10] bg-[#171717] p-4 text-left opacity-0 shadow-[0_18px_40px_rgba(0,0,0,0.45)] transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 ${
          placement === "top" ? "bottom-full mb-2" : "top-full mt-2"
        }`}
      >
        {children}
      </span>
    </span>
  );
}

const aggregateTone = (value?: number) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "text-white";
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
  disabledReason = t("워크포워드 분석을 실행할 수 없습니다."),
  loadedResult = null,
  strategyName,
  promptText,
  cacheKey,
  baseBacktestSeconds,
}: WalkForwardPanelProps) {
  const totalBars = backtestDates.length > 1 ? backtestDates.length : FALLBACK_TOTAL_BARS;
  const minWindowBars = deriveMinWindowBars(totalBars);
  const [formState, setFormState] = useState<WalkForwardFormState>(() =>
    buildInitialFormState(totalBars, minWindowBars)
  );
  const [isRunning, setIsRunning] = useState(false);
  const [runProgress, setRunProgress] = useState<WalkForwardRunProgress | null>(null);
  // 실행 중 실측된 백테스트 1회당 소요(초)의 지수이동평균 — 남은 시간 추정에 쓴다.
  const [avgBacktestSec, setAvgBacktestSec] = useState<number | null>(null);
  const [result, setResult] = useState<WalkForwardResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [parameterRangeOverrides, setParameterRangeOverrides] = useState<Record<string, WalkForwardParameterRangeOverride>>({});
  const [excludedTargetIds, setExcludedTargetIds] = useState<Set<string>>(() => new Set());
  const [stepModalTargetId, setStepModalTargetId] = useState<string | null>(null);
  const [stepModalDraft, setStepModalDraft] = useState<WalkForwardParameterRangeOverride | null>(null);
  const [stepModalError, setStepModalError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 저장된 결과를 불러오면 현재 결과 패널을 그 값으로 대체한다.
  useEffect(() => {
    if (loadedResult) {
      setResult(loadedResult);
      setError(null);
    }
  }, [loadedResult]);

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
  // 결과의 best_params 키(경로 또는 레거시 라벨)를 사용자가 알아볼 수 있는 한글 라벨로 되돌리는 조회표.
  // visibleTargets 밖(제외된 파라미터 등)은 커버 못 할 수 있어 렌더링 쪽에서 폴백을 둔다.
  const paramLabelByKey = visibleTargets.reduce<Record<string, string>>((acc, target) => {
    acc[settingsKeyFor(target)] = target.label;
    return acc;
  }, {});
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
    if (config.allowedValues) {
      // 이동평균 일선처럼 고정 후보값 집합만 쓰는 파라미터는 기본값 = 전체 후보 선택.
      acc[target.id] = { min, max, step: 0, values: [...config.allowedValues] };
      return acc;
    }
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

  // 이동평균 일선처럼 고정 후보값(allowedValues)만 쓰는 파라미터는 step 개념이 없다 —
  // step을 보내면 백엔드가 min~max를 그 step으로 재전개해 고정 후보 목록이 깨진다.
  const parameterSteps = activeTargets.reduce<Record<string, number>>((steps, target) => {
    if (getParameterStepConfig(target.label).allowedValues) return steps;
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

  const applyTrainBars = (value: number) => {
    const nextTrainBars = clamp(value, minWindowBars, maxTrainBars);
    setFormState((current) => {
      const nextValidationMax = Math.max(minWindowBars, totalBars - nextTrainBars);
      return {
        ...current,
        trainBars: nextTrainBars,
        validationBars: clamp(current.validationBars, minWindowBars, nextValidationMax),
      };
    });
  };

  const applyValidationBars = (value: number) => {
    const nextValidationMax = Math.max(minWindowBars, totalBars - formState.trainBars);
    setFormState((current) => ({
      ...current,
      validationBars: clamp(value, minWindowBars, nextValidationMax),
    }));
  };

  // 구간 수 상한 초과 시 안내할 두 가지 해결 예시 — 각각 검증기간/학습기간만 늘려 상한 이하로 낮추는 최소값
  const windowCountExceedsCap = derivedSettings.n_splits > MAX_WALK_FORWARD_WINDOWS;
  const suggestedValidationBars = clamp(
    Math.ceil((totalBars - formState.trainBars) / MAX_WALK_FORWARD_WINDOWS),
    minWindowBars,
    maxValidationBars
  );
  const suggestedTrainBars = clamp(
    totalBars - MAX_WALK_FORWARD_WINDOWS * formState.validationBars,
    minWindowBars,
    maxTrainBars
  );

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

  const handleRun = async () => {
    if (!onRun || !canRun) {
      setError(disabledReason);
      return;
    }

    setIsRunning(true);
    setError(null);
    setResult(null);
    setRunProgress(null);
    setAvgBacktestSec(null);

    const controller = new AbortController();
    abortRef.current = controller;

    // 진행 이벤트를 그대로 반영하면서, 백테스트 단계별 소요(timing.total)를
    // 지수이동평균으로 모아 남은 시간(라이브 ETA)을 추정한다.
    const handleProgress = (event: WalkForwardRunProgress) => {
      setRunProgress(event);
      const sample = event.timing?.total;
      if (typeof sample === "number" && sample > 0) {
        setAvgBacktestSec((prev) => (prev == null ? sample : prev * 0.6 + sample * 0.4));
      }
    };

    try {
      const res = await onRun(derivedSettings, controller.signal, handleProgress);
      if (res.status === "error") {
        setError(res.message || t("분석 중 오류가 발생했습니다."));
      } else {
        setResult(res);
      }
    } catch (e: any) {
      if (controller.signal.aborted) {
        setError(t("분석을 취소했습니다."));
      } else {
        setError(e.message || t("알 수 없는 오류가 발생했습니다."));
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

    if (config.allowedValues) {
      const selectedValues = stepModalDraft.values ?? [];
      if (selectedValues.length === 0) {
        setStepModalError(t("최소 1개 값을 선택해 주세요."));
        return;
      }
      setStepModalError(null);
      const normalized: WalkForwardParameterRangeOverride = {
        min: config.min,
        max: config.max,
        step: 0,
        values: selectedValues,
      };
      setParameterRangeOverrides((current) => {
        const defaults = defaultParameterRanges[stepModalTargetId];
        if (defaults && sameRangeOverride(normalized, defaults)) {
          const next = { ...current };
          delete next[stepModalTargetId];
          return next;
        }
        return { ...current, [stepModalTargetId]: normalized };
      });
      closeStepModal();
      return;
    }

    if (!Number.isFinite(stepModalDraft.min) || !Number.isFinite(stepModalDraft.max)) {
      setStepModalError(t("하한값과 상한값을 입력해 주세요."));
      return;
    }
    const min = Number(stepModalDraft.min.toFixed(4));
    const max = Number(stepModalDraft.max.toFixed(4));
    if (min > max) {
      setStepModalError(t("하한값은 상한값보다 클 수 없습니다."));
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

  const resultParameterKeys = Object.keys(paramLabelByKey).filter((key) =>
    result?.windows.some((window) => Object.prototype.hasOwnProperty.call(window.best_params ?? {}, key))
  );
  const parameterAnalyses = resultParameterKeys
    .map((key) => buildParameterAnalysis(key, paramLabelByKey[key], result?.windows ?? []))
    .filter((analysis): analysis is WalkForwardParameterAnalysis => analysis !== null);

  const wfe = result?.walk_forward_efficiency ?? 0;
  // 백엔드가 IS 평균 수익 ≤ 0으로 WFE 해석 불가를 알린 경우
  const wfeValid = result?.wfe_valid !== false;
  // 구버전 저장 결과(wfe_basis 없음)는 총수익률 기준이라 학습·검증 기간 길이 차이만큼 낮게 계산돼 있다.
  const wfeLegacyBasis = !!result && result.wfe_basis !== "cagr";
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
  const choiceCountForTarget = (target: WalkForwardOptimizationTarget) => {
    const config = getParameterStepConfig(target.label);
    if (config.allowedValues) {
      return currentParameterRangeForTarget(target).values?.length ?? config.allowedValues.length;
    }
    return estimateGridChoiceCount(currentParameterRangeForTarget(target));
  };
  const gridSearchEstimate = activeTargets.length > 0
    ? activeTargets.reduce((total, target) => total * choiceCountForTarget(target), 1)
    : 0;
  const gridSearchExceedsCap = isGridMethod && gridSearchEstimate > MAX_GRID_COMBINATIONS;

  // ── 예상 소요 시간 ──────────────────────────────────────────
  // 총 백테스트 수 = 준비 1회(백엔드가 창 분할 전에 기준 기간을 확인하는 백테스트) + 구간 수 × (구간당 백테스트 수 + OOS 1회).
  // 구간당 백테스트 수: 그리드=조합 수, 베이지안=시도 수(홀드아웃 부가 실행 없음 — 2026-08-19 감사로 제거).
  const PREPARE_BACKTESTS = 1;
  const backtestsPerWindow = isGridMethod ? gridSearchEstimate : formState.n_trials;
  const totalBacktests = backtestsPerWindow > 0
    ? PREPARE_BACKTESTS + derivedSettings.n_splits * (backtestsPerWindow + 1)
    : 0;
  // 워크포워드 구간은 전체 기간보다 짧지만, 실측상 백테스트 1회 비용은 기간 길이와
  // 거의 무관하다 — 비용 대부분이 종목별 데이터 로드+지표 계산 고정비(예: 970종목
  // 전체 기간 12.6s vs 그 절반 구간 11.8s). 예전처럼 구간 길이 비율로 선형 스케일하면
  // 총 소요를 수 배 과소추정해 실행 중 라이브 ETA와 크게 어긋나므로 실측 시간을 그대로 쓴다.
  const perBacktestSec = baseBacktestSeconds && baseBacktestSeconds > 0
    ? baseBacktestSeconds
    : FALLBACK_PER_BACKTEST_SEC;
  const estimatedRunSeconds = totalBacktests * perBacktestSec;
  const estimatedDurationLabel = formatDurationRange(estimatedRunSeconds);

  // 실행 중 남은 시간(라이브 ETA): 완료 백테스트 수를 빼고 실측 평균으로 곱한다.
  const completedBacktests = runProgress?.stage === "window" && runProgress.window
    ? PREPARE_BACKTESTS + (runProgress.window - 1) * (backtestsPerWindow + 1) + (runProgress.trial ?? 0)
    : 0;
  const remainingBacktests = Math.max(0, totalBacktests - completedBacktests);
  const liveEtaSeconds = avgBacktestSec != null && totalBacktests > 0
    ? remainingBacktests * avgBacktestSec
    : null;
  const runDisabledReason = gridSearchExceedsCap
    ? t("조합 수({0}개)가 상한({1}개)을 초과했습니다. 파라미터 범위나 step을 조정해 주세요.", gridSearchEstimate.toLocaleString(), MAX_GRID_COMBINATIONS.toLocaleString())
    : windowCountExceedsCap
      ? t("구간 수({0}개)가 상한({1}개)을 초과했습니다. 학습기간이나 검증기간을 늘려 주세요.", derivedSettings.n_splits, MAX_WALK_FORWARD_WINDOWS)
      : disabledReason;
  const isRunBlocked = !onRun || !canRun || gridSearchExceedsCap || windowCountExceedsCap;
  const isRunDisabled = isRunning || isRunBlocked;
  const canShowEstimate = totalBacktests > 0;

  return (
        <div data-testid="walk-forward-panel" className="w-full overflow-hidden rounded-xl border border-white/[0.08] bg-[var(--background)]">
          <RunProgressModal
            open={isRunning || !!error}
            title={t("워크포워드 분석")}
            isRunning={isRunning}
            progressRatio={
              runProgress?.total
                ? (Math.max(0, (runProgress.window ?? 1) - 1) +
                    (runProgress.trial_total ? Math.min(1, (runProgress.trial ?? 0) / runProgress.trial_total) : 0)) /
                  runProgress.total
                : undefined
            }
            progressLabel={
              runProgress?.stage === "window" && runProgress.total
                ? runProgress.trial_total
                  ? t("{0}/{1} 구간 · {2}/{3} 시도", runProgress.window, runProgress.total, runProgress.trial ?? 0, runProgress.trial_total)
                  : t("{0}/{1} 구간 분석 중", runProgress.window, runProgress.total)
                : runProgress?.stage === "prepare"
                  ? runProgress.message ?? t("백테스트 기간 데이터를 확인하는 중...")
                  : isRunning
                    ? t("분석을 준비하는 중...")
                    : undefined
            }
            detail={
              runProgress?.stage === "window" ? (
                <>
                  {runProgress.is_period && (
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-gray-500">{t("학습 구간")}</span>
                      <span className="tabular-nums text-white">{runProgress.is_period}</span>
                    </div>
                  )}
                  {runProgress.oos_period && (
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-gray-500">{t("검증 구간")}</span>
                      <span className="tabular-nums text-white">{runProgress.oos_period}</span>
                    </div>
                  )}
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-gray-500">{t("최적화 방법")}</span>
                    <span className="text-white">
                      {isGridMethod ? t("그리드 탐색") : t("베이지안 최적화 ({0}회 시도)", formState.n_trials)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-gray-500">{t("예상 남은 시간")}</span>
                    <span className="tabular-nums text-white">
                      {liveEtaSeconds != null ? formatDurationApprox(liveEtaSeconds) : t("측정 중...")}
                    </span>
                  </div>
                  {runProgress.timing && (
                    <div className="mt-1 border-t border-white/[0.06] pt-2">
                      <p className="text-[10px] font-black uppercase tracking-widest text-gray-500">
                        {t("최근 백테스트")}
                      </p>
                      <div className="mt-1.5 space-y-1 tabular-nums">
                        <div className="flex items-center justify-between gap-3">
                          <span className="flex items-center gap-1 text-gray-500">
                            Phase1
                            <HelpTooltip label="Phase1">
                              <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                                {t("Phase1 · 데이터 로드 + 신호 계산")}
                              </span>
                              <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
                                {t("어떤 날 사고 팔지 후보를 계산하는 단계입니다. 종목별로 가격 데이터를 불러오고 지표(RSI·이동평균 등)와 매매 신호를 만듭니다.")}
                              </span>
                            </HelpTooltip>
                          </span>
                          <span className="text-white">
                            {t("{0}s ({1}종목)", runProgress.timing.phase1.toFixed(2), runProgress.timing.symbols.toLocaleString())}
                          </span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="flex items-center gap-1 text-gray-500">
                            Simulator
                            <HelpTooltip label="Simulator">
                              <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                                {t("Simulator · 매매 시뮬레이션")}
                              </span>
                              <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
                                {t("계산된 신호대로 실제로 사고팔았다고 돌려보는 단계입니다. 날짜별 체결·보유 종목·현금과 손절·익절 같은 리스크 종료를 추적합니다.")}
                              </span>
                            </HelpTooltip>
                          </span>
                          <span className="text-white">{runProgress.timing.simulator.toFixed(2)}s</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="flex items-center gap-1 text-gray-500">
                            Format
                            <HelpTooltip label="Format">
                              <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                                {t("Format · 성과 지표 정리")}
                              </span>
                              <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
                                {t("돌린 결과를 CAGR·MDD 같은 숫자로 정리하는 단계입니다. 수익곡선, 종목별 통계, 벤치마크 비교도 여기서 계산합니다.")}
                              </span>
                            </HelpTooltip>
                          </span>
                          <span className="text-white">{runProgress.timing.format.toFixed(2)}s</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-gray-400">{t("총 소요")}</span>
                          <span className="font-black text-white">{runProgress.timing.total.toFixed(2)}s</span>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              ) : undefined
            }
            error={error}
            onCancel={handleCancel}
            onClose={() => setError(null)}
          />

          {/* overflow-y-auto는 모달(maxHeightClass 지정)에서만 붙인다 — 임베드 화면에서 붙이면
              opacity-0 도움말 말풍선이 넘치는 만큼 패널이 별도 스크롤 컨테이너가 되어
              페이지 스크롤이 '분석 시작' 버튼 앞에서 한 번 걸린다(2026-08-19). */}
          <div className={maxHeightClass ? `${maxHeightClass} overflow-y-auto` : undefined}>
            {!result && (
              <div className="grid grid-cols-1 divide-y divide-white/[0.08] lg:grid-cols-2 lg:divide-x lg:divide-y-0">
                <section className="p-5">
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("기본 설정")}</p>
                  <div className="mt-4 divide-y divide-white/[0.04] border-t border-white/[0.05]">
                    <div className="py-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <label htmlFor="walk-forward-train-bars" className="text-xs font-bold uppercase tracking-widest text-gray-500">
                            {t("학습기간")}
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
                        aria-label={t("학습기간")}
                        type="range"
                        min={minWindowBars}
                        max={maxTrainBars}
                        step={1}
                        value={formState.trainBars}
                        onChange={(event) => applyTrainBars(Number(event.target.value))}
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
                            {t("검증기간")}
                          </label>
                          <p className="mt-2 text-base font-black text-white font-outfit">
                            {formatBarsLabel(formState.validationBars)}
                          </p>
                          <p className="mt-1 text-xs font-bold leading-5 text-gray-400">
                            {formatApproxDuration(formState.validationBars)}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">{t("첫 검증 구간")}</p>
                          <p className="mt-2 text-xs font-bold leading-5 text-gray-300">
                            {formatDateLabel(firstValidationStart ?? undefined)} - {formatDateLabel(firstValidationEnd ?? undefined)}
                          </p>
                        </div>
                      </div>
                      <input
                        id="walk-forward-validation-bars"
                        aria-label={t("검증기간")}
                        type="range"
                        min={minWindowBars}
                        max={maxValidationBars}
                        step={1}
                        value={formState.validationBars}
                        onChange={(event) => applyValidationBars(Number(event.target.value))}
                        className="mt-4 h-2 w-full cursor-pointer appearance-none rounded-full bg-white/[0.08]"
                        style={sliderTrackStyle(formState.validationBars, minWindowBars, maxValidationBars)}
                      />
                      <div className="mt-2 flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-gray-500">
                        <span>{formatBarsLabel(minWindowBars)}</span>
                        <span>{formatBarsLabel(maxValidationBars)}</span>
                      </div>
                      {formState.validationBars < SHORT_VALIDATION_BARS && (
                        <p data-testid="walk-forward-short-validation-note" className="mt-3 text-xs font-bold leading-5 text-amber-300">
                          {t("검증기간이 {0}거래일(약 3개월)보다 짧습니다. 짧은 구간의 연평균 수익률(CAGR)은 작은 등락도 크게 연환산되어 구간별 CAGR·WFE의 잡음이 커집니다.", SHORT_VALIDATION_BARS)}
                        </p>
                      )}
                      <div data-testid="walk-forward-period-timeline" className="mt-5">
                        <div className="relative h-8 w-full">
                          <div
                            data-testid="walk-forward-timeline-train"
                            className="absolute inset-y-0 left-0 flex min-w-0 items-center justify-center rounded-md border border-white/[0.18] px-2.5 text-[9px] font-black uppercase tracking-widest text-white"
                            style={{ width: `${timelineTrainPct}%` }}
                          >
                            <span className="truncate">{t("학습기간")}</span>
                          </div>
                          <div
                            data-testid="walk-forward-timeline-validation"
                            className="absolute inset-y-0 flex min-w-0 items-center justify-center rounded-md border border-white/[0.18] bg-white/[0.08] px-2.5 text-[9px] font-black uppercase tracking-widest text-white"
                            style={{ left: `${timelineTrainPct}%`, width: `${timelineValidationPct}%` }}
                          >
                            <span className="truncate">{t("검증기간")}</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="py-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("설정 요약")}</p>
                      <div className="mt-3 grid grid-cols-1 gap-3 text-xs font-bold text-gray-300 md:grid-cols-2">
                        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                          <p className="uppercase tracking-widest text-gray-500">{t("백테스트 범위")}</p>
                          <p className="mt-2 leading-5 text-white">{formatDateLabel(periodStart)} - {formatDateLabel(periodEnd)}</p>
                        </div>
                        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                          <p className="uppercase tracking-widest text-gray-500">{t("예상 구간 수")}</p>
                          <p className="mt-2 flex items-center gap-2 leading-5">
                            <span className={windowCountExceedsCap ? "text-amber-300" : "text-white"}>
                              {t("{0}개", derivedSettings.n_splits)}
                            </span>
                            {windowCountExceedsCap && (
                              <span className="inline-flex rounded-md bg-amber-500/15 px-2 py-0.5 text-[10px] font-black uppercase tracking-widest text-amber-300">
                                {t("상한 초과")}
                              </span>
                            )}
                          </p>
                        </div>
                        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                          <p className="uppercase tracking-widest text-gray-500">{t("학습 비중")}</p>
                          <p className="mt-2 leading-5 text-white">{Math.round(derivedSettings.train_pct * 100)}%</p>
                        </div>
                        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                          <p className="uppercase tracking-widest text-gray-500">{t("총 관측치")}</p>
                          <p className="mt-2 leading-5 text-white">{formatBarsLabel(totalBars)}</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </section>

                <section className="p-5">
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("최적화 설정")}</p>
                  <div className="mt-4 divide-y divide-white/[0.04] border-t border-white/[0.05]">
                    <div className="py-4">
                      <div className="flex items-center gap-1.5">
                        <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("최적화 대상 파라미터")}</p>
                        <HelpTooltip label={t("최적화 대상 파라미터")}>
                          <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                            {t("최적화 대상 파라미터")}
                          </span>
                          <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
                            {t("현재 전략에 실제 포함된 숫자 파라미터만 표시됩니다. 각 파라미터를 눌러 탐색 범위와 step을 조정하거나 최적화에서 제외할 수 있고, 제외한 파라미터는 원래 설정값을 그대로 사용합니다.")}
                          </span>
                          <span className="mt-3 block text-xs font-bold leading-5 text-gray-400">
                            {t("예: PBR, 손절라인을 선택하면 각 학습 구간에서 PBR 임계값과 손절 비율의 조합을 다시 찾고, 보유기간·보유종목수는 기존 설정을 그대로 씁니다.")}
                          </span>
                        </HelpTooltip>
                      </div>
                      {visibleTargets.length > 0 ? (
                        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                          {visibleTargets.map((target) => {
                            const isExcluded = excludedTargetIds.has(target.id);
                            const range = currentParameterRangeForTarget(target);
                            const unit = getParameterStepConfig(target.label).unit;
                            return (
                              <button
                                key={target.id}
                                type="button"
                                aria-label={t(target.label)}
                                onClick={() => openStepModal(target)}
                                className={`flex min-h-[86px] flex-col justify-between rounded-lg p-4 text-left transition-colors focus:outline-none focus:ring-2 focus:ring-white/20 ${
                                  isExcluded
                                    ? "bg-white/[0.03] text-gray-500 line-through hover:bg-white/[0.06]"
                                    : "bg-white/[0.08] text-white hover:bg-white/[0.12]"
                                }`}
                              >
                                <span className="text-sm font-black leading-5">
                                  {t(target.label)}
                                </span>
                                <span
                                  data-testid={`walk-forward-target-range-${target.label}`}
                                  className="mt-3 text-[11px] font-bold leading-4 tabular-nums tracking-wide text-gray-500"
                                >
                                  {isExcluded
                                    ? t("제외됨")
                                    : range?.values
                                      ? range.values.map((value) => formatStepWithUnit(value, unit)).join(", ")
                                      : range
                                        ? `${formatStepWithUnit(range.min, unit)}~${formatStepWithUnit(range.max, unit)}`
                                        : ""}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="mt-3 text-sm font-bold leading-6 text-gray-400">
                          {t("현재 전략에서 조정 가능한 숫자 파라미터를 찾지 못했습니다.")}
                        </p>
                      )}
                    </div>
                    <div className="py-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("최적화 방법")}</p>
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
                                <span className="text-sm font-black text-white">{t(method.label)}</span>
                              </span>
                              <span className="mt-2 block text-left text-xs font-bold leading-5 text-gray-400">{t(method.body)}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                    {/* 그리드 조합 수와 실행 가능 여부는 아래 '예상 소요 시간' 카드 하나로 합쳤다 —
                        두 카드가 같은 상태(상한 초과 = 실행 불가)를 중복 안내했다(2026-08-19). */}
                    {!isGridMethod && (
                      <div className="py-4">
                        <div className="flex items-center gap-1.5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("베이지안 최적화 시도 횟수")}</p>
                          <HelpTooltip label={t("베이지안 최적화 시도 횟수")}>
                            <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                              {t("베이지안 최적화 시도 횟수")}
                            </span>
                            <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
                              {t("각 워크포워드 구간에서 파라미터 조합을 몇 번 탐색할지 정합니다. 횟수가 늘면 더 많은 조합을 계산하지만 실행 시간이 길어집니다.")}
                            </span>
                            <span className="mt-3 block text-xs font-bold leading-5 text-gray-400">
                              {t("예: 30회는 손절 5/7/10%, 이동평균 20/60일 같은 후보 조합을 최대 30번 평가해 과거 학습 구간의 목표 지표가 높게 나온 조합을 기록합니다.")}
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
                              {t("{0}회", value)}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {canShowEstimate && (
                      <div className="py-4">
                        <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <div className="flex items-center gap-1.5">
                                <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("예상 소요 시간")}</p>
                                <HelpTooltip label={t("예상 소요 시간")}>
                                  <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                                    {t("예상 소요 시간")}
                                  </span>
                                  <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
                                    {t("총 {0}회 백테스트(준비 1회 + 구간 {1}개 × 구간당 {2}회)를 기준 백테스트 실측 속도로 추정한 값입니다.", totalBacktests.toLocaleString(), derivedSettings.n_splits, (backtestsPerWindow + 1).toLocaleString())}
                                  </span>
                                  <span className="mt-3 block text-xs font-bold leading-5 text-gray-400">
                                    {t("실제 시간은 데이터 로딩·서버 상황·조건 조합에 따라 달라질 수 있으며, 실행을 시작하면 실측값으로 남은 시간을 다시 계산합니다.")}
                                  </span>
                                </HelpTooltip>
                              </div>
                              <p className="mt-2 text-sm font-black leading-6 text-white">
                                {isRunBlocked
                                  ? t("현재 상태에서는 실행할 수 없습니다.")
                                  : t("{0} 소요될 것으로 예상됩니다.", estimatedDurationLabel)}
                              </p>
                            </div>
                            <span
                              data-testid="walk-forward-run-capacity-badge"
                              className={`inline-flex shrink-0 rounded-md bg-white/[0.06] px-2 py-1 text-[10px] font-black uppercase tracking-widest ${
                                isRunBlocked ? "text-red-400" : "text-gray-400"
                              }`}
                            >
                              {isRunBlocked ? t("실행 불가") : t("총 {0}회", totalBacktests.toLocaleString())}
                            </span>
                          </div>
                          {/* 그리드 조합 수 — 상한 초과 시에는 아래 원인 문구가 같은 숫자를 더 자세히 말하므로 생략 */}
                          {isGridMethod && !gridSearchExceedsCap && (
                            <p
                              data-testid="walk-forward-grid-combination-note"
                              className="mt-3 text-xs font-bold leading-5 text-gray-400"
                            >
                              {t("현재 파라미터 범위 기준 약 {0}개 조합을 각 워크포워드 구간에서 전수 실행합니다.", gridSearchEstimate.toLocaleString())}
                            </p>
                          )}
                          {isRunBlocked ? (
                            <p
                              data-testid="walk-forward-run-blocked-reason"
                              className="mt-3 text-xs font-bold leading-5 text-amber-300"
                            >
                              {t("충족되지 않은 조건: {0}", runDisabledReason)}
                            </p>
                          ) : (
                            <p className="mt-3 text-xs font-bold leading-5 text-gray-400">
                              {t("시간이 오래 걸리는 작업입니다. 실행 중에는 창을 닫지 말고 진행 상황을 확인해 주세요.")}
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                    <div className="py-4">
                      <div className="flex items-center gap-1.5">
                        <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("학습 창 방식")}</p>
                        <HelpTooltip label={t("학습 창 방식")} placement="top">
                          <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                            {t("학습 창 방식")}
                          </span>
                          <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
                            {t("학습 구간은 파라미터를 맞추는 구간입니다. 롤링은 학습과 검증 창이 함께 이동하고, 확장은 학습 구간을 시작일부터 누적해 넓힙니다.")}
                          </span>
                          <span className="mt-3 block text-xs font-bold leading-5 text-gray-400">
                            {t("예: 롤링은 2020-2021 학습 후 2022 검증, 다음에는 2021-2022 학습 후 2023 검증처럼 이동합니다. 확장은 2020-2021 학습 후 2022 검증, 다음에는 2020-2022 학습 후 2023 검증처럼 누적합니다.")}
                          </span>
                        </HelpTooltip>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {[
                          { value: false, label: t("롤링") },
                          { value: true, label: t("확장") },
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
                <div className="flex items-center gap-3 px-5 py-3">
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("워크포워드 분석 결과")}</p>
                </div>
                <section className="p-5">
                  <ResultPlainSummary items={buildWalkForwardPlainSummary(result)} />
                </section>
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
                              {wfeTone.emoji} {t(wfeTone.text)}
                            </span>
                          </div>
                          <p className="mt-3 text-xs font-bold leading-5 text-gray-400">
                            {t(wfeTone.description)}
                          </p>
                          {wfeLegacyBasis && (
                            <p data-testid="walk-forward-wfe-legacy-note" className="mt-2 text-xs font-bold leading-5 text-amber-300">
                              {t("이 결과는 구버전 방식(총수익률 기준)으로 계산된 WFE입니다. 학습 구간이 검증 구간보다 긴 만큼 낮게 나올 수 있으니 다시 실행해 연환산 기준 값을 확인해 주세요.")}
                            </p>
                          )}

                          <div className="mt-5 border-t border-white/[0.06] pt-4">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                              {t("WFE란?")}
                            </p>
                            <p className="mt-2 text-xs font-bold leading-5 text-gray-400">
                              {t("워크포워드 검증은 과거 구간을 학습·검증으로 번갈아 나눠, 학습 구간에서 최적화한 설정을 그다음 검증 구간에 적용하는 방식입니다. WFE는 이때")}{" "}
                              <span className="text-gray-300">{t("검증 구간의 연평균 수익률(CAGR) 평균을 학습 구간의 연평균 수익률 평균으로 나눈 값")}</span>{t("으로, 학습 구간에 맞춘 설정이 처음 보는 구간에서도 유지되는지를 나타냅니다. 학습·검증 구간의 길이가 달라도 비교되도록 연환산 수익률끼리 비교합니다. 100%에 가까울수록 두 구간의 성과 차이가 작고, 낮을수록 특정 구간에만 맞춰진 과최적화 가능성이 큽니다.")}
                            </p>
                          </div>

                          <div className="mt-4">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                              {t("구간 기준")}
                            </p>
                            <div className="mt-2 space-y-0.5">
                              {WFE_TIERS.map((tier) => {
                                const active = tier.text === wfeTone.text;
                                return (
                                  <div
                                    key={tier.text}
                                    className={`flex items-baseline gap-2.5 rounded px-2 py-1.5 ${
                                      active ? "bg-white/[0.06]" : ""
                                    }`}
                                  >
                                    <span className="w-[52px] shrink-0 text-right font-mono text-[11px] font-bold tabular-nums text-gray-500">
                                      {tier.range}
                                    </span>
                                    <span
                                      className={`w-[68px] shrink-0 text-[11px] font-black ${
                                        active ? tier.valueClass : "text-gray-500"
                                      }`}
                                    >
                                      {tier.emoji} {t(tier.text)}
                                    </span>
                                    <span
                                      className={`flex-1 text-[11px] font-bold leading-4 ${
                                        active ? "text-gray-300" : "text-gray-600"
                                      }`}
                                    >
                                      {t(tier.summary)}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="mt-3 flex items-end gap-3">
                            <span className="text-4xl font-black tabular-nums text-gray-500 font-outfit">-</span>
                            <span className="bg-white/[0.06] px-2 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-gray-400">
                              {t("해석 불가")}
                            </span>
                          </div>
                          <p className="mt-3 text-xs font-bold leading-5 text-gray-400">
                            {t("학습 구간 평균 연평균 수익률(CAGR)이 0 이하라 검증/학습 비율을 해석할 수 없습니다. 구간별 결과를 직접 확인해 주세요.")}
                          </p>
                        </>
                      )}
                    </div>
                  </section>
                  <section className="lg:col-span-4">
                    <div className="p-5">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("검증기간 평균 성과")}</p>
                      <div className="mt-4 grid grid-cols-3 gap-x-4 gap-y-4">
                        {[
                          { key: "avg_oos_cagr", label: "CAGR", suffix: "%" },
                          { key: "avg_oos_totalReturn", label: t("총 수익률"), suffix: "%" },
                          { key: "avg_oos_maxDrawdown", label: "MDD", suffix: "%" },
                          { key: "avg_oos_sharpe", label: "Sharpe", suffix: "" },
                          { key: "avg_oos_calmar", label: "Calmar", suffix: "" },
                          { key: "avg_oos_winRate", label: t("승률"), suffix: "%" },
                          { key: "avg_oos_profitFactor", label: t("손익비"), suffix: "" },
                          { key: "avg_oos_trades", label: t("평균 거래 수"), suffix: "" },
                          { key: "avg_oos_expectancy", label: t("평균 거래손익"), suffix: "%" },
                        ].map((item) => (
                          <div key={item.key} className="space-y-1">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">{item.label}</p>
                            <p className={`text-lg font-black tabular-nums font-outfit ${aggregateTone(result.aggregate[item.key])}`}>
                              {item.suffix === "%" ? fmt(result.aggregate[item.key], "%") : fmtNum(result.aggregate[item.key])}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </section>
                  <section className="lg:col-span-3">
                    <div className="p-5">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("실행 설정")}</p>
                      <div className="mt-3 divide-y divide-white/[0.04] border-t border-white/[0.05]">
                        {[
                          { label: t("구간 수"), value: t("{0}개", result.n_splits) },
                          { label: t("학습 창 방식"), value: result.anchor ? t("확장") : t("롤링") },
                          { label: t("목표 지표"), value: t(TARGET_METRICS.find((metric) => metric.id === result.target_metric)?.label ?? result.target_metric) },
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

                <section className="p-5">
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("구간별 결과")}</p>
                  <div className="mt-4 overflow-x-auto">
                    <div className="min-w-[760px]">
                      <div className="grid grid-cols-[64px_minmax(0,1fr)_minmax(0,1fr)_88px_88px_88px_88px] gap-2 px-2">
                        {["구간", "학습 기간", "검증 기간", "학습 CAGR", "검증 CAGR", "검증 MDD", "검증 승률"].map((label, index) => (
                          <span
                            key={label}
                            className={`text-xs font-bold uppercase tracking-widest text-gray-500 ${
                              index >= 3 ? "text-center" : ""
                            }`}
                          >
                            {t(label)}
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
                                {window.error && <span className="text-[10px] font-black uppercase tracking-widest text-[var(--main-blue)]">{t("오류")}</span>}
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
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("구간별 최적 파라미터")}</p>
                  <div className="mt-4 overflow-x-auto">
                    <table
                      data-testid="walk-forward-optimal-parameters-table"
                      className="w-full table-fixed border-collapse text-left"
                      style={{ minWidth: `${Math.max(760, 520 + resultParameterKeys.length * 140)}px` }}
                    >
                      <thead>
                        <tr className="border-b border-white/[0.12]">
                          <th scope="col" className="w-20 px-3 py-4 text-xs font-black text-gray-400">{t("구간")}</th>
                          <th scope="col" className="w-52 px-3 py-4 text-xs font-black text-gray-400">{t("학습 기간")}</th>
                          <th scope="col" className="w-52 px-3 py-4 text-xs font-black text-gray-400">{t("검증 기간")}</th>
                          {resultParameterKeys.map((key) => (
                            <th key={key} scope="col" className="w-36 px-3 py-4 text-xs font-black text-gray-400">
                              {t("최적 {0}", paramLabelByKey[key] ?? humanizeParamKey(key))}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.08]">
                        {result.windows.map((window) => (
                          <tr key={window.window} className="transition-colors hover:bg-white/[0.02]">
                            <td className="px-3 py-4 text-sm font-black text-white font-outfit">
                              {window.window}
                              {window.error && <span className="ml-2 text-[10px] text-[var(--main-blue)]">{t("오류")}</span>}
                            </td>
                            <td className="px-3 py-4 text-sm font-bold tabular-nums text-gray-300">{window.is_period}</td>
                            <td className="px-3 py-4 text-sm font-bold tabular-nums text-gray-300">{window.oos_period}</td>
                            {resultParameterKeys.map((key) => (
                              <td key={key} className="px-3 py-4 text-sm font-black tabular-nums text-white font-outfit">
                                {window.best_params?.[key] === null || window.best_params?.[key] === undefined
                                  ? "-"
                                  : String(window.best_params[key])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                {parameterAnalyses.length > 0 && (
                  <section className="p-5" aria-labelledby="walk-forward-parameter-analysis-title">
                    <div className="flex items-center gap-1.5">
                      <p
                        id="walk-forward-parameter-analysis-title"
                        className="text-base font-black uppercase tracking-widest text-gray-400 font-outfit"
                      >
                        {t("워크포워드 파라미터 분석")}
                      </p>
                      <HelpTooltip label={t("워크포워드 파라미터 분석")}>
                        <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
                          {t("파라미터 분석 산정 기준")}
                        </span>
                        <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
                          {t("대표값은 구간별 최적값의 중앙값입니다. 안정성은 변동계수(표준편차 ÷ 평균 절댓값)가 5% 이하일 때 5점, 10% 이하 4점, 20% 이하 3점, 35% 이하 2점, 초과 시 1점입니다. 별점은 구간별 값의 일관성만 나타냅니다.")}
                        </span>
                      </HelpTooltip>
                    </div>
                    <div className="mt-4 grid grid-cols-1 border-l border-t border-white/[0.08] sm:grid-cols-2 xl:grid-cols-3">
                      {parameterAnalyses.map((analysis) => (
                        <article
                          key={analysis.key}
                          data-testid={`walk-forward-parameter-analysis-${analysis.key}`}
                          className="border-b border-r border-white/[0.08] p-4"
                        >
                          <h3 className="text-base font-black text-white font-outfit">{analysis.label}</h3>
                          <div className="mt-3 border-t border-white/[0.10]" />
                          <dl className="mt-3 space-y-2.5">
                            {[
                              { label: t("대표값"), value: formatParameterAnalysisValue(analysis.representative) },
                              { label: t("평균"), value: formatParameterAnalysisValue(analysis.mean) },
                              { label: t("표준편차"), value: formatParameterAnalysisValue(analysis.standardDeviation) },
                              {
                                label: t("범위"),
                                value: `${formatParameterAnalysisValue(analysis.min)} ~ ${formatParameterAnalysisValue(analysis.max)}`,
                              },
                            ].map((item) => (
                              <div key={item.label} className="grid grid-cols-[88px_minmax(0,1fr)] items-baseline gap-3">
                                <dt className="text-xs font-bold text-gray-500">{item.label}</dt>
                                <dd className="text-right text-sm font-black tabular-nums text-white font-outfit">{item.value}</dd>
                              </div>
                            ))}
                            <div className="grid grid-cols-[88px_minmax(0,1fr)] items-baseline gap-3">
                              <dt className="text-xs font-bold text-gray-500">{t("안정성")}</dt>
                              <dd
                                aria-label={analysis.stability === null ? t("안정성 계산 불가") : t("안정성 {0}점", analysis.stability)}
                                className="text-right text-sm font-black tracking-[0.12em]"
                              >
                                {analysis.stability === null ? (
                                  <span className="text-gray-500">-</span>
                                ) : (
                                  <span aria-hidden="true">
                                    <span className="text-amber-400">{"★".repeat(analysis.stability)}</span>
                                    <span className="text-gray-700">{"★".repeat(5 - analysis.stability)}</span>
                                  </span>
                                )}
                              </dd>
                            </div>
                          </dl>
                        </article>
                      ))}
                    </div>
                  </section>
                )}
              </div>
            )}
          </div>

          {stepModalTarget && stepModalDraftValue && stepModalCurrentRange && stepModalBounds && (
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="walk-forward-step-modal-title"
              className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/70 px-2 py-3 sm:px-4 lg:py-0"
            >
              <div
                data-testid="walk-forward-step-modal-panel"
                className="max-h-[calc(100dvh-1.5rem)] w-full max-w-sm overflow-y-auto rounded-xl border border-white/[0.10] bg-[#111111] p-4 shadow-[0_24px_80px_rgba(0,0,0,0.65)] sm:p-5 lg:max-h-none lg:overflow-visible"
              >
                <p id="walk-forward-step-modal-title" className="text-xs font-bold uppercase tracking-widest text-gray-500">
                  {t("{0} 값 설정", stepModalTarget.label)}
                </p>
                {stepModalConfig.allowedValues ? (
                  <>
                    <div className="mt-5">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("탐색할 일선 선택")}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {stepModalConfig.allowedValues.map((value) => {
                          const selected = (stepModalDraftValue.values ?? []).includes(value);
                          return (
                            <button
                              key={value}
                              type="button"
                              aria-pressed={selected}
                              onClick={() => {
                                setStepModalDraft((current) => {
                                  if (!current) return current;
                                  const currentValues = current.values ?? [];
                                  const nextValues = selected
                                    ? currentValues.filter((item) => item !== value)
                                    : [...currentValues, value].sort((a, b) => a - b);
                                  return { ...current, values: nextValues };
                                });
                                setStepModalError(null);
                              }}
                              className={`rounded-md px-3 py-2 text-sm font-black transition-colors font-outfit ${
                                selected
                                  ? "bg-[var(--main-blue)] text-white"
                                  : "bg-white/[0.06] text-gray-400 hover:bg-white/[0.10] hover:text-white"
                              }`}
                            >
                              {formatStepWithUnit(value, stepModalConfig.unit)}
                            </button>
                          );
                        })}
                      </div>
                      <p className="mt-3 text-xs font-bold leading-5 text-gray-500">
                        {t("이동평균은 실제 매매에서 쓰이는 표준 일선({0}) 중에서만 탐색합니다. 단기 값이 장기 값을 넘는 조합은 자동으로 제외됩니다.", stepModalConfig.allowedValues.map((value) => formatStepWithUnit(value, stepModalConfig.unit)).join("/"))}
                      </p>
                      {stepModalError && (
                        <p className="mt-2 text-xs font-bold leading-5 text-[var(--main-blue)]">{stepModalError}</p>
                      )}
                    </div>
                    <p className="mt-3 text-xs font-bold leading-5 text-gray-500">
                      {t("선택된 이동평균:{0}{1}", " ", (stepModalDraftValue.values?.length ?? 0) > 0
                        ? stepModalDraftValue.values!.map((value) => formatStepWithUnit(value, stepModalConfig.unit)).join(", ")
                        : t("없음"))}
                    </p>
                  </>
                ) : (
                  <>
                    <div className="mt-5 space-y-5">
                      <div>
                        <label htmlFor="walk-forward-parameter-min" className="block text-xs font-bold uppercase tracking-widest text-gray-500">
                          {t("하한값")}
                        </label>
                        <div className="relative mt-3">
                          <input
                            id="walk-forward-parameter-min"
                            aria-label={t("{0} 하한값", stepModalTarget.label)}
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
                              {t(stepModalConfig.unit)}
                            </span>
                          )}
                        </div>
                        <p id="walk-forward-parameter-examples" className="mt-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">
                          {t("예: {0}", stepModalInputExamples.map((value) => formatStepWithUnit(value, stepModalConfig.unit)).join(", "))}
                        </p>
                      </div>
                      <div>
                        <label htmlFor="walk-forward-parameter-max" className="block text-xs font-bold uppercase tracking-widest text-gray-500">
                          {t("상한값")}
                        </label>
                        <div className="relative mt-3">
                          <input
                            id="walk-forward-parameter-max"
                            aria-label={t("{0} 상한값", stepModalTarget.label)}
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
                              {t(stepModalConfig.unit)}
                            </span>
                          )}
                        </div>
                        <p className="mt-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">
                          {t("예: {0}", stepModalInputExamples.map((value) => formatStepWithUnit(value, stepModalConfig.unit)).join(", "))}
                        </p>
                        {stepModalError && (
                          <p id="walk-forward-parameter-error" className="mt-2 text-xs font-bold leading-5 text-[var(--main-blue)]">
                            {stepModalError}
                          </p>
                        )}
                      </div>
                      <div>
                        <label htmlFor="walk-forward-parameter-step" className="block text-xs font-bold uppercase tracking-widest text-gray-500">
                          {t("step 값")}
                        </label>
                        <div className="mt-2 flex items-end justify-between gap-3">
                          <p className="text-2xl font-black text-white font-outfit">
                            {formatStepWithUnit(stepModalDraftValue.step, stepModalConfig.unit)}
                          </p>
                          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                            {t("{0}개 후보", stepModalConfig.stepOptions.length)}
                          </p>
                        </div>
                        <div
                          id="walk-forward-parameter-step"
                          aria-label={t("{0} step 값", stepModalTarget.label)}
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
                      {t("현재 적용: {0} -{1}{2} / step{3}{4}", formatStepWithUnit(stepModalCurrentRange.min, stepModalConfig.unit), " ", formatStepWithUnit(stepModalCurrentRange.max, stepModalConfig.unit), " ", formatStepWithUnit(stepModalCurrentRange.step, stepModalConfig.unit))}
                    </p>
                  </>
                )}
                <div
                  data-testid="walk-forward-step-modal-actions"
                  className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-2"
                >
                  <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
                    <button
                      type="button"
                      onClick={resetStepModal}
                      className="rounded-md px-3 py-2 text-xs font-black text-gray-500 transition-colors hover:bg-white/[0.04] hover:text-gray-300"
                    >
                      {t("기본값")}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        toggleTargetExcluded(stepModalTarget.id);
                        closeStepModal();
                      }}
                      className="rounded-md px-3 py-2 text-xs font-black text-gray-500 transition-colors hover:bg-white/[0.04] hover:text-gray-300"
                    >
                      {excludedTargetIds.has(stepModalTarget.id) ? t("최적화에 포함") : t("최적화에서 제외")}
                    </button>
                  </div>
                  <div className="flex w-full items-center gap-2 sm:w-auto">
                    <button
                      type="button"
                      onClick={closeStepModal}
                      className="flex-1 rounded-md px-3 py-2 text-xs font-black text-gray-400 transition-colors hover:bg-white/[0.04] hover:text-white sm:flex-none"
                    >
                      {t("닫기")}
                    </button>
                    <button
                      type="button"
                      onClick={saveStepModal}
                      className="flex-1 rounded-md bg-[var(--main-blue)] px-3 py-2 text-xs font-black text-white transition-opacity hover:opacity-90 sm:flex-none"
                    >
                      {t("저장")}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="flex items-center justify-end gap-2 border-t border-white/[0.08] px-5 py-4">
            {result && (
              <>
                <button
                  onClick={() => {
                    setResult(null);
                    setError(null);
                  }}
                  className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/[0.04] px-3 py-2 text-xs font-black text-gray-200 transition-colors hover:bg-white/[0.08]"
                >
                  <ArrowsClockwise className="h-4 w-4" weight="bold" />
                  {t("재설정")}
                </button>
                <SaveValidationButton
                  onSave={async () => {
                    await saveValidation({
                      modelType: "walkForward",
                      strategyName: strategyName || t("이름 없는 전략"),
                      prompt: promptText,
                      cacheKey,
                      settings: {
                        n_splits: result.n_splits,
                        anchor: result.anchor,
                        target_metric: result.target_metric,
                      },
                      result,
                      summary: buildWalkForwardSummary(result),
                    });
                  }}
                />
              </>
            )}
            {onClose && (
              <button
                onClick={handleClose}
                disabled={isRunning}
                className="px-4 py-2 text-sm font-black text-gray-400 transition-colors hover:bg-white/[0.03] hover:text-white disabled:opacity-40"
              >
                {t("닫기")}
              </button>
            )}
            {!result && (
              <button
                onClick={handleRun}
                disabled={isRunDisabled}
                title={isRunDisabled && !isRunning ? runDisabledReason : undefined}
                className="inline-flex items-center gap-2 rounded-md bg-[var(--main-blue)] px-4 py-2 text-sm font-black text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isRunning ? (
                  <>
                    <ArrowsClockwise className="h-4 w-4 animate-spin" />
                    {runProgress?.stage === "window" && runProgress.total
                      ? t("분석 중... ({0}/{1} 구간)", runProgress.window, runProgress.total)
                      : t("분석 중... ({0}개 구간)", derivedSettings.n_splits)}
                  </>
                ) : (
                  <>
                    <ChartLine className="h-4 w-4" />
                    {t("워크포워드 분석 시작")}
                  </>
                )}
              </button>
            )}
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
  baseBacktestSeconds,
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
            baseBacktestSeconds={baseBacktestSeconds}
            onClose={() => onOpenChange(false)}
            maxHeightClass="max-h-[calc(100vh-9rem)]"
          />
        </div>
      </div>
    </div>
  );
}
