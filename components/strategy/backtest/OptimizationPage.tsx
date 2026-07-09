"use client";

import { useRef, useState } from "react";
import { ArrowsClockwise, Crown, FolderOpen, SignOut, Spinner } from "phosphor-react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
} from "recharts";
import type { BacktestResult } from "@/types/strategy";
import { WalkForwardPanel, type WalkForwardSettings, type WalkForwardOptimizationTarget } from "./WalkForwardModal";
import ResultPlainSummary, { buildMonteCarloPlainSummary } from "./ResultPlainSummary";
import RunProgressModal from "./RunProgressModal";
import SaveValidationButton from "./SaveValidationButton";
import SavedValidationsModal from "./SavedValidationsModal";
import type { StrategyBacktestRequest } from "@/app/analytics/new/parsedStrategyMerge";
import {
  saveValidation,
  getSavedValidation,
  buildMonteCarloSummary,
  type SavedValidationSummary,
} from "@/lib/validation-storage";

type OptimizationModel = "walkForward" | "monteCarlo";

const OPTIMIZATION_MODELS: Array<{
  id: OptimizationModel;
  label: string;
  description: string;
  example: string;
}> = [
  {
    id: "walkForward",
    label: "워크포워드",
    description: "백테스트 기간을 여러 학습(IS)/검증(OOS) 구간으로 나눠 구간별 결과를 비교합니다.",
    example: "예: 2020-2021년 데이터로 파라미터를 맞춘 뒤 2022년 구간에서 검증하고, 다음 창도 같은 방식으로 이동해 구간별 OOS 결과를 비교합니다.",
  },
  {
    id: "monteCarlo",
    label: "몬테카를로",
    description: "기존 수익률 구간을 재조합해 가능한 성과 분포와 낙폭 범위를 추정합니다.",
    example: "예: 일별 수익률 블록을 1,000번 재배열해 CAGR 중앙값, 5% 하위 시나리오, MDD가 30%를 넘는 비율을 계산합니다.",
  },
];

function ModelHelpTooltip({ label, description, example }: { label: string; description: string; example: string }) {
  return (
    <span className="group relative z-20 inline-flex">
      <button
        type="button"
        aria-label={`${label} 도움말`}
        onClick={(event) => event.stopPropagation()}
        className="flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-white/25 text-[10px] font-black leading-none text-gray-400 transition-colors hover:border-white/50 hover:text-white focus:border-white/60 focus:text-white focus:outline-none"
      >
        ?
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-50 mt-2 w-80 max-w-[calc(100vw-3rem)] border border-white/[0.10] bg-[#171717] p-4 text-left opacity-0 shadow-[0_18px_40px_rgba(0,0,0,0.45)] transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">{label}</span>
        <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">{description}</span>
        <span className="mt-3 block text-xs font-bold leading-5 text-gray-400">{example}</span>
      </span>
    </span>
  );
}

function SettingHelpTooltip({ label, description }: { label: string; description: string }) {
  return (
    <span className="group relative z-20 inline-flex">
      <button
        type="button"
        aria-label={`${label} 도움말`}
        onClick={(event) => event.stopPropagation()}
        className="flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-white/25 text-[10px] font-black leading-none text-gray-400 transition-colors hover:border-white/50 hover:text-white focus:border-white/60 focus:text-white focus:outline-none"
      >
        ?
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-50 mt-2 w-72 max-w-[calc(100vw-3rem)] border border-white/[0.10] bg-[#171717] p-4 text-left opacity-0 shadow-[0_18px_40px_rgba(0,0,0,0.45)] transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">{label}</span>
        <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">{description}</span>
      </span>
    </span>
  );
}

// returns = equity curve 일별 수익률 재표본 (blockSize 1=독립, >1=블록 부트스트랩)
// trades  = 체결 기록에서 추정한 거래별 수익률 재표본 (거래 수가 적은 전략에 유용)
export type MonteCarloMode = "returns" | "trades";

interface MonteCarloSettings {
  iterations: number;
  blockSize: number;
  seed: number;
  mode: MonteCarloMode;
}

interface MonteCarloSummary {
  median: number;
  mean: number;
  min: number;
  max: number;
  p05: number;
  p25: number;
  p75: number;
  p95: number;
  std: number;
}

export interface MonteCarloHistogramBin {
  /** 구간 시작/끝 (비율 단위) */
  x0: number;
  x1: number;
  count: number;
}

interface MonteCarloResult {
  status: "ok";
  nIterations: number;
  blockSize: number;
  mode: MonteCarloMode;
  /** trades 모드에서 재표본에 사용한 완결 거래 수 */
  tradeCount?: number;
  cagr: MonteCarloSummary;
  sharpe: MonteCarloSummary;
  mdd: MonteCarloSummary;
  probPositiveCagr: number;
  probMddOver30pct: number;
  cagrHistogram: MonteCarloHistogramBin[];
  mddHistogram: MonteCarloHistogramBin[];
}

function percentile(sortedValues: number[], q: number): number {
  if (sortedValues.length === 0) return 0;
  const index = (sortedValues.length - 1) * q;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sortedValues[lower];
  const weight = index - lower;
  return sortedValues[lower] * (1 - weight) + sortedValues[upper] * weight;
}

function summarizeMonteCarlo(values: number[]): MonteCarloSummary {
  const sorted = [...values].sort((a, b) => a - b);
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance =
    values.length > 1
      ? values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1)
      : 0;

  return {
    median: percentile(sorted, 0.5),
    mean,
    min: sorted[0] ?? 0,
    max: sorted[sorted.length - 1] ?? 0,
    p05: percentile(sorted, 0.05),
    p25: percentile(sorted, 0.25),
    p75: percentile(sorted, 0.75),
    p95: percentile(sorted, 0.95),
    std: Math.sqrt(Math.max(variance, 0)),
  };
}

export function buildMonteCarloHistogram(values: number[], bins = 24): MonteCarloHistogramBin[] {
  if (values.length === 0) return [];
  let min = Infinity;
  let max = -Infinity;
  for (const value of values) {
    if (value < min) min = value;
    if (value > max) max = value;
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];

  const span = max - min;
  if (span <= 0) {
    return [{ x0: min, x1: max, count: values.length }];
  }

  const width = span / bins;
  const counts = new Array<number>(bins).fill(0);
  for (const value of values) {
    const index = Math.min(bins - 1, Math.floor((value - min) / width));
    counts[index] += 1;
  }

  return counts.map((count, index) => ({
    x0: min + index * width,
    x1: min + (index + 1) * width,
    count,
  }));
}

function createSeededRng(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t ^= t + Math.imul(t ^ (t >>> 7), 61 | t);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const MONTE_CARLO_CHUNK_SIZE = 200;
const MIN_COMPLETED_TRADES = 20;

// 체결 기록(tradesList, 없으면 signals)에서 종목별 FIFO 매칭으로 완결 거래의
// 수익률을 추정한다. 분할 청산은 근사(수량 무시, 가격 기준)로 처리한다.
export function extractTradeReturns(backtestResult: BacktestResult): number[] {
  const fromTrades = (backtestResult.tradesList ?? []).map((t) => ({
    date: t.date,
    symbol: t.symbol,
    side: t.type,
    price: t.price,
  }));
  const fromSignals = (backtestResult.signals ?? []).map((s) => ({
    date: s.date,
    symbol: s.symbol,
    side: s.type === "entry" ? ("buy" as const) : ("sell" as const),
    price: s.price,
  }));
  const records = fromTrades.length > 0 ? fromTrades : fromSignals;

  const sorted = [...records].sort((a, b) => (a.date ?? "").localeCompare(b.date ?? ""));
  const openEntries: Record<string, number[]> = {};
  const returns: number[] = [];

  for (const record of sorted) {
    if (!Number.isFinite(record.price) || record.price <= 0) continue;
    if (record.side === "buy") {
      (openEntries[record.symbol] ??= []).push(record.price);
    } else {
      const entryPrice = openEntries[record.symbol]?.shift();
      if (entryPrice !== undefined) {
        returns.push(record.price / entryPrice - 1);
      }
    }
  }

  return returns.filter((value) => Number.isFinite(value) && value > -1);
}

// 거래 재표본 모드: 완결 거래 수익률을 복원추출로 재배열해 CAGR/MDD 분포를 추정한다.
// MDD는 거래 단위 equity 경로 기준(거래 도중 낙폭은 반영되지 않음 — UI에 명시).
async function runTradeResampleSimulation(
  backtestResult: BacktestResult,
  settings: MonteCarloSettings,
  onProgress?: (completedRatio: number) => void,
  shouldCancel?: () => boolean
): Promise<{ status: "error"; message: string } | { status: "cancelled" } | MonteCarloResult> {
  const tradeReturns = extractTradeReturns(backtestResult);
  if (tradeReturns.length < MIN_COMPLETED_TRADES) {
    return {
      status: "error",
      message: `거래 재표본에는 완결된 거래가 최소 ${MIN_COMPLETED_TRADES}건 필요합니다 (현재 ${tradeReturns.length}건). 일별 수익률 방식을 사용해 주세요.`,
    };
  }

  const iterations = Math.max(100, Math.floor(settings.iterations));
  const barCount = (backtestResult.dates ?? []).length || (backtestResult.equity ?? []).length;
  const years = Math.max(1e-6, barCount / 252);
  const tradesPerYear = tradeReturns.length / years;
  const rng = createSeededRng(settings.seed);
  const n = tradeReturns.length;
  const cagrs: number[] = [];
  const sharpes: number[] = [];
  const mdds: number[] = [];

  for (let iteration = 0; iteration < iterations; iteration += 1) {
    if (iteration % MONTE_CARLO_CHUNK_SIZE === 0 && iteration > 0) {
      onProgress?.(iteration / iterations);
      await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
      if (shouldCancel?.()) return { status: "cancelled" };
    }

    let equity = 1;
    let peak = 1;
    let worstDrawdown = 0;
    let sum = 0;
    let sumSq = 0;
    for (let i = 0; i < n; i += 1) {
      const sampled = tradeReturns[Math.floor(rng() * n)];
      equity *= 1 + sampled;
      if (equity > peak) peak = equity;
      const drawdown = (equity - peak) / peak;
      if (drawdown < worstDrawdown) worstDrawdown = drawdown;
      sum += sampled;
      sumSq += sampled * sampled;
    }

    const mean = sum / n;
    const variance = n > 1 ? Math.max(0, (sumSq - n * mean * mean) / (n - 1)) : 0;
    const std = Math.sqrt(variance);

    cagrs.push(equity > 0 ? equity ** (1 / years) - 1 : -1);
    sharpes.push(std > 1e-12 ? (mean / std) * Math.sqrt(tradesPerYear) : 0);
    mdds.push(Math.abs(worstDrawdown));
  }

  onProgress?.(1);

  return {
    status: "ok",
    nIterations: iterations,
    blockSize: settings.blockSize,
    mode: "trades",
    tradeCount: tradeReturns.length,
    cagr: summarizeMonteCarlo(cagrs),
    sharpe: summarizeMonteCarlo(sharpes),
    mdd: summarizeMonteCarlo(mdds),
    probPositiveCagr: cagrs.filter((value) => value > 0).length / cagrs.length,
    probMddOver30pct: mdds.filter((value) => value > 0.3).length / mdds.length,
    cagrHistogram: buildMonteCarloHistogram(cagrs),
    mddHistogram: buildMonteCarloHistogram(mdds),
  };
}

export async function runMonteCarloSimulation(
  backtestResult: BacktestResult,
  settings: MonteCarloSettings,
  onProgress?: (completedRatio: number) => void,
  shouldCancel?: () => boolean
): Promise<{ status: "error"; message: string } | { status: "cancelled" } | MonteCarloResult> {
  if (settings.mode === "trades") {
    return runTradeResampleSimulation(backtestResult, settings, onProgress, shouldCancel);
  }

  // blockSize 1 = 일별 수익률 독립 재표본, >1 = 블록 부트스트랩(자기상관 보존)
  const blockSize = Math.max(1, Math.floor(settings.blockSize));
  const minPoints = Math.max(30, blockSize * 3);
  const equity = (backtestResult.equity ?? []).filter((value) => Number.isFinite(value) && value > 0);
  if (equity.length < minPoints) {
    return {
      status: "error",
      message: `몬테카를로 시뮬레이션에는 최소 ${minPoints}개의 유효 equity 포인트가 필요합니다.`,
    };
  }

  const logReturns: number[] = [];
  for (let i = 1; i < equity.length; i += 1) {
    logReturns.push(Math.log(equity[i] / equity[i - 1]));
  }

  if (logReturns.length < minPoints - 1) {
    return {
      status: "error",
      message: "유효한 수익률 구간이 부족해 몬테카를로 시뮬레이션을 실행할 수 없습니다.",
    };
  }

  const iterations = Math.max(100, Math.floor(settings.iterations));
  const years = Math.max(1e-6, logReturns.length / 252);
  const initialEquity = backtestResult.initialCapital || equity[0];
  const nBlocks = Math.ceil(logReturns.length / blockSize);
  const maxStart = logReturns.length - blockSize + 1;
  const rng = createSeededRng(settings.seed);
  const cagrs: number[] = [];
  const sharpes: number[] = [];
  const mdds: number[] = [];

  for (let iteration = 0; iteration < iterations; iteration += 1) {
    // UI가 진행률을 그리고 취소에 반응할 수 있도록 일정 주기로 이벤트 루프에 양보한다.
    if (iteration % MONTE_CARLO_CHUNK_SIZE === 0 && iteration > 0) {
      onProgress?.(iteration / iterations);
      await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
      if (shouldCancel?.()) return { status: "cancelled" };
    }

    const sampled: number[] = [];
    for (let block = 0; block < nBlocks; block += 1) {
      const start = Math.floor(rng() * maxStart);
      for (let offset = 0; offset < blockSize && sampled.length < logReturns.length; offset += 1) {
        sampled.push(logReturns[start + offset]);
      }
    }

    let currentEquity = initialEquity;
    let peakEquity = initialEquity;
    let worstDrawdown = 0;
    for (const value of sampled) {
      currentEquity *= Math.exp(value);
      if (currentEquity > peakEquity) peakEquity = currentEquity;
      const drawdown = (currentEquity - peakEquity) / peakEquity;
      if (drawdown < worstDrawdown) worstDrawdown = drawdown;
    }

    const avgReturn = sampled.reduce((sum, value) => sum + value, 0) / sampled.length;
    const std =
      sampled.length > 1
        ? Math.sqrt(
            sampled.reduce((sum, value) => sum + (value - avgReturn) ** 2, 0) /
              (sampled.length - 1)
          )
        : 0;

    cagrs.push(currentEquity > 0 ? (currentEquity / initialEquity) ** (1 / years) - 1 : -1);
    sharpes.push(std > 1e-12 ? (avgReturn / std) * Math.sqrt(252) : 0);
    mdds.push(Math.abs(worstDrawdown));
  }

  onProgress?.(1);

  return {
    status: "ok",
    nIterations: iterations,
    blockSize,
    mode: "returns",
    cagr: summarizeMonteCarlo(cagrs),
    sharpe: summarizeMonteCarlo(sharpes),
    mdd: summarizeMonteCarlo(mdds),
    probPositiveCagr: cagrs.filter((value) => value > 0).length / cagrs.length,
    probMddOver30pct: mdds.filter((value) => value > 0.3).length / mdds.length,
    cagrHistogram: buildMonteCarloHistogram(cagrs),
    mddHistogram: buildMonteCarloHistogram(mdds),
  };
}

function formatRatioAsPercent(value: number, digits = 2): string {
  return `${(value * 100).toFixed(digits)}%`;
}

function MonteCarloHistogramChart({
  title,
  bins,
  xAxisLabel,
  signColored = false,
}: {
  title: string;
  bins: MonteCarloHistogramBin[];
  xAxisLabel: string;
  /** true면 0 기준으로 음수 구간은 파랑, 양수 구간은 빨강 (앱의 등락 색 관례) */
  signColored?: boolean;
}) {
  if (bins.length === 0) return null;

  const data = bins.map((bin) => ({
    ...bin,
    label: `${(bin.x0 * 100).toFixed(1)}%`,
    mid: (bin.x0 + bin.x1) / 2,
  }));

  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
      <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">{title}</p>
      <div className="mt-3 h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} barCategoryGap={1}>
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10, fill: "#6b7280", fontWeight: 700 }}
              tickLine={false}
              axisLine={false}
              interval={Math.max(0, Math.floor(data.length / 6))}
              height={42}
              label={{
                value: xAxisLabel,
                position: "insideBottom",
                offset: -2,
                fill: "#6b7280",
                fontSize: 11,
                fontWeight: 800,
              }}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#6b7280", fontWeight: 700 }}
              tickLine={false}
              axisLine={false}
              allowDecimals={false}
              width={36}
            />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
              contentStyle={{
                background: "#111111",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 0,
                fontSize: 11,
                color: "#e5e7eb",
              }}
              labelStyle={{ color: "#9ca3af" }}
              formatter={(value: any) => [`${Number(value).toLocaleString()}회`, "빈도"]}
              labelFormatter={(_, payload) => {
                const bin = payload?.[0]?.payload as (MonteCarloHistogramBin & { label: string }) | undefined;
                if (!bin) return "";
                return `${(bin.x0 * 100).toFixed(1)}% ~ ${(bin.x1 * 100).toFixed(1)}%`;
              }}
            />
            <Bar dataKey="count" radius={[2, 2, 0, 0]}>
              {data.map((bin, index) => (
                <Cell
                  key={index}
                  fill={
                    signColored
                      ? bin.mid >= 0
                        ? "rgba(239, 68, 68, 0.75)"
                        : "rgba(96, 165, 250, 0.75)"
                      : "rgba(96, 165, 250, 0.75)"
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-bold text-gray-500">
        <span>x축: {xAxisLabel}</span>
        <span>y축: 시나리오 수</span>
      </div>
    </div>
  );
}

interface OptimizationPageProps {
  result: BacktestResult;
  onWalkForward?: (settings: WalkForwardSettings) => Promise<any>;
  walkForwardOptimizationTargets: WalkForwardOptimizationTarget[];
  baseStrategy?: StrategyBacktestRequest;
  isPlanLoading: boolean;
  isPremiumValidationEnabled: boolean;
  strategyName?: string;
  promptText?: string;
  onClose?: () => void;
}

export default function OptimizationPage({
  result,
  onWalkForward,
  walkForwardOptimizationTargets,
  baseStrategy,
  isPlanLoading,
  isPremiumValidationEnabled,
  strategyName,
  promptText,
  onClose,
}: OptimizationPageProps) {
  const [selectedModel, setSelectedModel] = useState<OptimizationModel>("walkForward");
  const [loadedWalkForward, setLoadedWalkForward] = useState<any | null>(null);
  const [isSavedListOpen, setIsSavedListOpen] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const validationCacheKey = (result as { cacheKey?: string }).cacheKey;

  const [monteCarloSettings, setMonteCarloSettings] = useState<MonteCarloSettings>({
    iterations: 1000,
    blockSize: 21,
    seed: 42,
    mode: "returns",
  });
  const [monteCarloResult, setMonteCarloResult] = useState<MonteCarloResult | null>(null);
  const [monteCarloError, setMonteCarloError] = useState<string | null>(null);
  const [isMonteCarloRunning, setIsMonteCarloRunning] = useState(false);
  const [monteCarloProgress, setMonteCarloProgress] = useState(0);
  const monteCarloCancelRef = useRef(false);

  const handleRunMonteCarlo = async () => {
    setIsMonteCarloRunning(true);
    setMonteCarloError(null);
    setMonteCarloResult(null);
    setMonteCarloProgress(0);
    monteCarloCancelRef.current = false;
    await new Promise<void>((resolve) => window.setTimeout(resolve, 0));

    const simulation = await runMonteCarloSimulation(
      result,
      monteCarloSettings,
      (ratio) => setMonteCarloProgress(ratio),
      () => monteCarloCancelRef.current
    );
    if (simulation.status === "error") {
      setMonteCarloError(simulation.message);
    } else if (simulation.status === "ok") {
      setMonteCarloResult(simulation);
    }
    setIsMonteCarloRunning(false);
  };

  const handleCancelMonteCarlo = () => {
    monteCarloCancelRef.current = true;
  };

  // 저장 목록에서 항목 선택 → 해당 모델 화면으로 전환하고 결과를 주입한다.
  const handleLoadSaved = async (item: SavedValidationSummary) => {
    setLoadError(null);
    try {
      const detail = await getSavedValidation(item.id);
      if (detail.modelType === "walkForward") {
        setSelectedModel("walkForward");
        // 참조가 매번 바뀌도록 새 객체로 주입(같은 항목 재선택도 반영).
        setLoadedWalkForward({ ...(detail.result as object) });
      } else {
        setSelectedModel("monteCarlo");
        const mc = detail.result as MonteCarloResult;
        setMonteCarloResult(mc);
        setMonteCarloError(null);
        setMonteCarloSettings((prev) => ({
          ...prev,
          iterations: mc.nIterations ?? prev.iterations,
          blockSize: mc.blockSize ?? prev.blockSize,
          mode: mc.mode ?? prev.mode,
        }));
      }
      setIsSavedListOpen(false);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "불러오기에 실패했습니다.");
    }
  };

  const monteCarloModeLabel =
    monteCarloSettings.mode === "trades"
      ? "거래 재표본"
      : monteCarloSettings.blockSize <= 1
        ? "일별 재표본"
        : `${monteCarloSettings.blockSize}일 블록 재표본`;
  const monteCarloCompletedIterations = Math.min(
    monteCarloSettings.iterations,
    Math.round(monteCarloProgress * monteCarloSettings.iterations)
  );

  // 프리미엄 전용 기능 게이트: PREMIUM이 아니면 최적화 화면 대신 안내와 플랜 변경 유도를 노출한다.
  if (!isPlanLoading && !isPremiumValidationEnabled) {
    return (
      <div
        data-testid="backtest-optimization-page"
        className="flex min-h-[320px] items-center justify-center px-6 py-10"
      >
        <div className="w-full max-w-2xl p-8 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-amber-400/30 bg-amber-500/10">
            <Crown className="h-6 w-6 text-amber-300" weight="fill" />
          </div>
          <h3 className="mt-4 text-lg font-black text-white">전략 최적화는 프리미엄 플랜 전용 기능입니다</h3>
          <p className="mt-2 whitespace-nowrap text-sm font-bold leading-6 text-gray-400">
            프리미엄 플랜을 이용하시면 워크포워드 분석과 몬테카를로 시뮬레이션을 통해 더 깊은 검증을 할 수 있습니다.
          </p>
          <a
            href="/pricing"
            className="mt-6 inline-flex items-center justify-center rounded-lg border border-gray-500 px-5 py-2.5 text-sm font-black text-gray-300 transition-colors hover:bg-white/[0.05]"
          >
            플랜 변경
          </a>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="backtest-optimization-page" className="flex flex-col gap-4 px-6 py-4 md:flex-row md:items-start">
      <aside className="w-full flex-shrink-0 md:w-64">
        <button
          type="button"
          onClick={() => setIsSavedListOpen(true)}
          className="mb-3 flex w-full items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[0.04] px-4 py-2.5 text-xs font-black text-gray-200 transition-colors hover:bg-white/[0.08]"
        >
          <FolderOpen className="h-4 w-4" weight="bold" />
          저장된 검증 결과 불러오기
        </button>
        {loadError && (
          <p className="mb-3 rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-xs font-bold text-red-300">
            {loadError}
          </p>
        )}
        <div className="space-y-2">
          {OPTIMIZATION_MODELS.map((model) => (
            <div
              key={model.id}
              role="button"
              tabIndex={0}
              aria-label={model.label}
              onClick={() => setSelectedModel(model.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setSelectedModel(model.id);
                }
              }}
              className={`block w-full cursor-pointer rounded-xl border p-4 text-left transition-colors ${
                selectedModel === model.id
                  ? "border-sky-400/40 bg-transparent"
                  : "border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.05]"
              }`}
            >
              <span className="flex items-center gap-1.5">
                <span className="block text-sm font-black text-white">{model.label}</span>
                <ModelHelpTooltip label={model.label} description={model.description} example={model.example} />
              </span>
              <span className="mt-1.5 block text-xs font-bold leading-5 text-gray-400">
                {model.description}
              </span>
            </div>
          ))}
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        {selectedModel === "walkForward" && (
          <div data-testid="backtest-walk-forward-section" className="flex flex-col">
            <WalkForwardPanel
              onRun={onWalkForward}
              backtestDates={result.dates}
              optimizationTargets={walkForwardOptimizationTargets}
              baseStrategy={baseStrategy}
              baseBacktestSeconds={result.executionTime}
              loadedResult={loadedWalkForward}
              strategyName={strategyName}
              promptText={promptText}
              cacheKey={validationCacheKey}
              canRun={!isPlanLoading && isPremiumValidationEnabled && !!onWalkForward}
              disabledReason={
                isPlanLoading
                  ? "플랜 권한을 확인하는 중입니다."
                  : !isPremiumValidationEnabled
                    ? "워크포워드 분석은 PREMIUM 플랜에서만 실행할 수 있습니다."
                    : "이 결과 화면에서는 워크포워드 실행을 지원하지 않습니다."
              }
            />
          </div>
        )}

        {selectedModel === "monteCarlo" && (
          <div className="rounded-2xl border border-white/[0.08] bg-[#0f0f10] p-5 md:p-6">
            <div className="space-y-2">
              <h3 className="text-xl font-black text-white">몬테카를로 시뮬레이션</h3>
              <p className="max-w-2xl text-sm font-bold leading-6 text-gray-300">
                백테스트 결과를 여러 방식으로 다시 섞어 보며 수익률과 손실 폭이 얼마나 달라질 수 있는지 확인합니다.
                여러 날을 묶어서 섞는 방식도 선택할 수 있어 연속된 시장 흐름을 일부 반영합니다.
              </p>
            </div>

            {isPlanLoading && (
              <div className="mt-5 rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm font-bold text-gray-300">
                플랜 권한을 확인하는 중입니다.
              </div>
            )}

            {!isPlanLoading && isPremiumValidationEnabled && (
              <>
                <div className="mt-5 grid gap-4 lg:grid-cols-[1.1fr,0.9fr]">
                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                    <div className="flex items-center gap-1.5">
                      <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">반복 횟수</p>
                      <SettingHelpTooltip
                        label="반복 횟수"
                        description="과거 데이터를 재조합해 만드는 가상 시나리오의 개수입니다. 횟수가 많을수록 수익률·낙폭 분포가 더 안정적으로 추정되지만 계산 시간은 늘어납니다."
                      />
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {[500, 1000, 2000].map((value) => (
                        <button
                          key={value}
                          onClick={() => setMonteCarloSettings((prev) => ({ ...prev, iterations: value }))}
                          className={`rounded-lg border px-3 py-1.5 text-sm font-black transition-colors ${
                            monteCarloSettings.iterations === value
                              ? "border-white/20 bg-white/10 text-white"
                              : "border-white/10 bg-white/[0.03] text-gray-400 hover:text-white"
                          }`}
                        >
                          {value.toLocaleString()}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                    <div className="flex items-center gap-1.5">
                      <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">시뮬레이션 방식</p>
                      <SettingHelpTooltip
                        label="시뮬레이션 방식"
                        description="과거 수익률을 다시 섞는 방법입니다. 일별 재표본은 하루 단위로 독립 추출하고, N일 블록은 며칠간 이어지는 등락 패턴을 함께 보존하며, 거래 재표본은 개별 체결 수익률을 재배열합니다."
                      />
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {[
                        { mode: "returns" as const, blockSize: 1, label: "일별 재표본" },
                        { mode: "returns" as const, blockSize: 5, label: "5일 블록" },
                        { mode: "returns" as const, blockSize: 10, label: "10일 블록" },
                        { mode: "returns" as const, blockSize: 21, label: "21일 블록" },
                        { mode: "trades" as const, blockSize: 21, label: "거래 재표본" },
                      ].map(({ mode, blockSize, label }) => {
                        const active =
                          monteCarloSettings.mode === mode &&
                          (mode === "trades" || monteCarloSettings.blockSize === blockSize);
                        return (
                          <button
                            key={label}
                            onClick={() => setMonteCarloSettings((prev) => ({ ...prev, mode, blockSize }))}
                            className={`rounded-lg border px-3 py-1.5 text-sm font-black transition-colors ${
                              active
                                ? "border-white/20 bg-white/10 text-white"
                                : "border-white/10 bg-white/[0.03] text-gray-400 hover:text-white"
                            }`}
                          >
                            {label}
                          </button>
                        );
                      })}
                    </div>
                    <p className="mt-3 text-xs font-bold leading-5 text-gray-500">
                      {monteCarloSettings.mode === "trades"
                        ? "체결 기록에서 추정한 거래별 수익률을 복원추출로 재배열합니다 (trade bootstrap). MDD는 거래 단위 경로 기준입니다."
                        : monteCarloSettings.blockSize <= 1
                          ? "하루 단위로 독립 재표본합니다 (i.i.d. bootstrap)."
                          : `${monteCarloSettings.blockSize}거래일 단위로 수익률 흐름을 다시 조합해, 며칠간 이어지는 상승과 하락 패턴도 함께 살펴봅니다.`}
                    </p>
                  </div>
                </div>

                <div className="mt-5 flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => void handleRunMonteCarlo()}
                    disabled={isMonteCarloRunning}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--main-blue)] px-4 py-2.5 text-sm font-black text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isMonteCarloRunning ? <Spinner className="h-4 w-4 animate-spin" /> : <ArrowsClockwise className="h-4 w-4" />}
                    몬테카를로 실행
                  </button>
                  <p className="text-xs font-bold text-gray-500">
                    seed {monteCarloSettings.seed} 고정 · 동일 설정이면 같은 결과가 재현됩니다
                  </p>
                </div>

                <RunProgressModal
                  open={isMonteCarloRunning || !!monteCarloError}
                  title="몬테카를로 시뮬레이션"
                  isRunning={isMonteCarloRunning}
                  progressRatio={monteCarloProgress}
                  progressLabel={
                    isMonteCarloRunning
                      ? `${monteCarloCompletedIterations.toLocaleString()}/${monteCarloSettings.iterations.toLocaleString()}회 완료 (${Math.round(monteCarloProgress * 100)}%)`
                      : undefined
                  }
                  detail={
                    isMonteCarloRunning ? (
                      <>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-gray-500">시뮬레이션 방식</span>
                          <span className="text-white">{monteCarloModeLabel}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-gray-500">seed</span>
                          <span className="tabular-nums text-white">{monteCarloSettings.seed}</span>
                        </div>
                      </>
                    ) : undefined
                  }
                  error={monteCarloError}
                  onCancel={handleCancelMonteCarlo}
                  onClose={() => setMonteCarloError(null)}
                />

                {monteCarloResult && (
                  <>
                    <div className="mt-5 flex items-center justify-between gap-3">
                      <p className="text-sm font-black text-white">시뮬레이션 결과</p>
                      <div className="flex items-center gap-2">
                        <SaveValidationButton
                          onSave={async () => {
                            await saveValidation({
                              modelType: "monteCarlo",
                              strategyName: strategyName || "이름 없는 전략",
                              prompt: promptText,
                              cacheKey: validationCacheKey,
                              settings: {
                                iterations: monteCarloResult.nIterations,
                                blockSize: monteCarloResult.blockSize,
                                mode: monteCarloResult.mode,
                                seed: monteCarloSettings.seed,
                              },
                              result: monteCarloResult,
                              summary: buildMonteCarloSummary(monteCarloResult),
                            });
                          }}
                        />
                        {onClose && (
                          <button
                            type="button"
                            onClick={onClose}
                            title="결과 닫기"
                            className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/[0.05] px-4 py-1.5 text-sm font-bold text-gray-300 transition-all hover:border-white/10 hover:bg-white/10 hover:text-white active:scale-95"
                          >
                            <SignOut className="h-4 w-4" />
                            결과 닫기
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-3">
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">중앙 CAGR</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.cagr.median)}</p>
                      </div>
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">하위 5% CAGR</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.cagr.p05)}</p>
                      </div>
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">최악 CAGR</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.cagr.min)}</p>
                      </div>
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">양수 CAGR 확률</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.probPositiveCagr)}</p>
                      </div>
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">상위 95% MDD</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.mdd.p95)}</p>
                      </div>
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">최악 MDD</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.mdd.max)}</p>
                      </div>
                    </div>

                    <div className="mt-5 grid gap-3 lg:grid-cols-2">
                      <MonteCarloHistogramChart
                        title="CAGR 분포"
                        bins={monteCarloResult.cagrHistogram}
                        xAxisLabel="CAGR 구간"
                        signColored
                      />
                      <MonteCarloHistogramChart
                        title="MDD 분포"
                        bins={monteCarloResult.mddHistogram}
                        xAxisLabel="MDD 구간"
                      />
                    </div>

                    <div className="mt-5 overflow-x-auto rounded-xl border border-white/[0.08] bg-white/[0.03]">
                      <table className="w-full min-w-[640px] text-left">
                        <thead className="bg-white/[0.04]">
                          <tr>
                            {["지표", "최소", "5%", "25%", "중앙값", "75%", "95%", "최대", "표준편차"].map((label) => (
                              <th key={label} className="px-4 py-3 text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">
                                {label}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {[
                            ["CAGR", monteCarloResult.cagr, true] as const,
                            ["Sharpe", monteCarloResult.sharpe, false] as const,
                            ["MDD", monteCarloResult.mdd, true] as const,
                          ].map(([label, summary, isPercent]) => {
                            const fmtCell = (value: number) =>
                              isPercent ? formatRatioAsPercent(value) : value.toFixed(2);
                            return (
                              <tr key={String(label)} className="border-t border-white/[0.06]">
                                <td className="px-4 py-3 text-sm font-black text-white">{label}</td>
                                {[summary.min, summary.p05, summary.p25, summary.median, summary.p75, summary.p95, summary.max, summary.std].map(
                                  (value, index) => (
                                    <td key={index} className="px-4 py-3 text-sm font-bold tabular-nums text-gray-300">
                                      {fmtCell(value)}
                                    </td>
                                  )
                                )}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>

                    <div className="mt-4">
                      <ResultPlainSummary items={buildMonteCarloPlainSummary(monteCarloResult)} />
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        )}
      </div>

      <SavedValidationsModal
        open={isSavedListOpen}
        onClose={() => setIsSavedListOpen(false)}
        onSelect={(item) => void handleLoadSaved(item)}
      />
    </div>
  );
}
