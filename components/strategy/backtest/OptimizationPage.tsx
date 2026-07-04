"use client";

import { useState } from "react";
import { ArrowsClockwise, Spinner } from "phosphor-react";
import type { BacktestResult } from "@/types/strategy";
import { WalkForwardPanel, type WalkForwardSettings, type WalkForwardOptimizationTarget } from "./WalkForwardModal";
import type { StrategyBacktestRequest } from "@/app/analytics/new/parsedStrategyMerge";

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

interface MonteCarloSettings {
  iterations: number;
  blockSize: number;
  seed: number;
}

interface MonteCarloSummary {
  median: number;
  mean: number;
  p05: number;
  p25: number;
  p75: number;
  p95: number;
  std: number;
}

interface MonteCarloResult {
  status: "ok";
  nIterations: number;
  blockSize: number;
  cagr: MonteCarloSummary;
  sharpe: MonteCarloSummary;
  mdd: MonteCarloSummary;
  probPositiveCagr: number;
  probMddOver30pct: number;
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
    p05: percentile(sorted, 0.05),
    p25: percentile(sorted, 0.25),
    p75: percentile(sorted, 0.75),
    p95: percentile(sorted, 0.95),
    std: Math.sqrt(Math.max(variance, 0)),
  };
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

function runMonteCarloSimulation(
  backtestResult: BacktestResult,
  settings: MonteCarloSettings
): { status: "error"; message: string } | MonteCarloResult {
  const blockSize = Math.max(2, Math.floor(settings.blockSize));
  const equity = (backtestResult.equity ?? []).filter((value) => Number.isFinite(value) && value > 0);
  if (equity.length < blockSize * 3) {
    return {
      status: "error",
      message: `몬테카를로 시뮬레이션에는 최소 ${blockSize * 3}개의 유효 equity 포인트가 필요합니다.`,
    };
  }

  const logReturns: number[] = [];
  for (let i = 1; i < equity.length; i += 1) {
    logReturns.push(Math.log(equity[i] / equity[i - 1]));
  }

  if (logReturns.length < blockSize * 3) {
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

  return {
    status: "ok",
    nIterations: iterations,
    blockSize,
    cagr: summarizeMonteCarlo(cagrs),
    sharpe: summarizeMonteCarlo(sharpes),
    mdd: summarizeMonteCarlo(mdds),
    probPositiveCagr: cagrs.filter((value) => value > 0).length / cagrs.length,
    probMddOver30pct: mdds.filter((value) => value > 0.3).length / mdds.length,
  };
}

function formatRatioAsPercent(value: number, digits = 2): string {
  return `${(value * 100).toFixed(digits)}%`;
}

interface OptimizationPageProps {
  result: BacktestResult;
  onWalkForward?: (settings: WalkForwardSettings) => Promise<any>;
  walkForwardOptimizationTargets: WalkForwardOptimizationTarget[];
  baseStrategy?: StrategyBacktestRequest;
  isPlanLoading: boolean;
  isPremiumValidationEnabled: boolean;
}

export default function OptimizationPage({
  result,
  onWalkForward,
  walkForwardOptimizationTargets,
  baseStrategy,
  isPlanLoading,
  isPremiumValidationEnabled,
}: OptimizationPageProps) {
  const [selectedModel, setSelectedModel] = useState<OptimizationModel>("walkForward");

  const [monteCarloSettings, setMonteCarloSettings] = useState<MonteCarloSettings>({
    iterations: 1000,
    blockSize: 21,
    seed: 42,
  });
  const [monteCarloResult, setMonteCarloResult] = useState<MonteCarloResult | null>(null);
  const [monteCarloError, setMonteCarloError] = useState<string | null>(null);
  const [isMonteCarloRunning, setIsMonteCarloRunning] = useState(false);

  const handleRunMonteCarlo = async () => {
    setIsMonteCarloRunning(true);
    setMonteCarloError(null);
    setMonteCarloResult(null);
    await new Promise<void>((resolve) => window.setTimeout(resolve, 0));

    const simulation = runMonteCarloSimulation(result, monteCarloSettings);
    if (simulation.status === "error") {
      setMonteCarloError(simulation.message);
    } else {
      setMonteCarloResult(simulation);
    }
    setIsMonteCarloRunning(false);
  };

  return (
    <div data-testid="backtest-optimization-page" className="flex flex-col gap-4 px-6 py-4 md:flex-row md:items-start">
      <aside className="w-full flex-shrink-0 md:w-64">
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
                  ? "border-sky-400/40 bg-sky-500/10"
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
              <div className="inline-flex items-center gap-2 rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1 text-[11px] font-black uppercase tracking-[0.22em] text-sky-300">
                <ArrowsClockwise className="h-4 w-4" />
                Premium Validation
              </div>
              <h3 className="text-xl font-black text-white">몬테카를로 시뮬레이션</h3>
              <p className="max-w-2xl text-sm font-bold leading-6 text-gray-300">
                현재 equity curve의 일별 수익률을 블록 단위로 재표본해 성과 분포를 확인합니다.
                결과는 과거 데이터 기반 시뮬레이션이며 미래 성과를 보장하지 않습니다.
              </p>
            </div>

            {isPlanLoading && (
              <div className="mt-5 rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm font-bold text-gray-300">
                플랜 권한을 확인하는 중입니다.
              </div>
            )}

            {!isPlanLoading && !isPremiumValidationEnabled && (
              <div className="mt-5 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4">
                <p className="text-sm font-black text-amber-300">프리미엄 전용 검증 기능입니다.</p>
                <p className="mt-1 text-sm font-bold leading-6 text-amber-100/90">
                  몬테카를로 시뮬레이션은 PREMIUM 플랜에서만 실행할 수 있습니다.
                </p>
                <a
                  href="/pricing"
                  className="mt-3 inline-flex items-center rounded-lg border border-amber-300/30 px-3 py-2 text-xs font-black text-amber-100 transition-colors hover:bg-amber-300/10"
                >
                  요금제 보기
                </a>
              </div>
            )}

            {!isPlanLoading && isPremiumValidationEnabled && (
              <>
                <div className="mt-5 grid gap-4 lg:grid-cols-[1.1fr,0.9fr]">
                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                    <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">반복 횟수</p>
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
                    <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">블록 크기</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {[
                        { value: 5, label: "5일" },
                        { value: 10, label: "10일" },
                        { value: 21, label: "21일" },
                      ].map(({ value, label }) => (
                        <button
                          key={value}
                          onClick={() => setMonteCarloSettings((prev) => ({ ...prev, blockSize: value }))}
                          className={`rounded-lg border px-3 py-1.5 text-sm font-black transition-colors ${
                            monteCarloSettings.blockSize === value
                              ? "border-white/20 bg-white/10 text-white"
                              : "border-white/10 bg-white/[0.03] text-gray-400 hover:text-white"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
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
                    seed {monteCarloSettings.seed} 고정, block bootstrap 방식
                  </p>
                </div>

                {monteCarloError && (
                  <div className="mt-5 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm font-bold text-red-200">
                    {monteCarloError}
                  </div>
                )}

                {monteCarloResult && (
                  <>
                    <div className="mt-5 grid gap-3 md:grid-cols-4">
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">중앙 CAGR</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.cagr.median)}</p>
                      </div>
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">5% CAGR</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.cagr.p05)}</p>
                      </div>
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">95% MDD</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.mdd.p95)}</p>
                      </div>
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">양수 CAGR 확률</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.probPositiveCagr)}</p>
                      </div>
                    </div>

                    <div className="mt-5 overflow-hidden rounded-xl border border-white/[0.08] bg-white/[0.03]">
                      <table className="w-full text-left">
                        <thead className="bg-white/[0.04]">
                          <tr>
                            <th className="px-4 py-3 text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">지표</th>
                            <th className="px-4 py-3 text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">중앙값</th>
                            <th className="px-4 py-3 text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">5%</th>
                            <th className="px-4 py-3 text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">95%</th>
                            <th className="px-4 py-3 text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">표준편차</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[
                            ["CAGR", monteCarloResult.cagr, true] as const,
                            ["Sharpe", monteCarloResult.sharpe, false] as const,
                            ["MDD", monteCarloResult.mdd, true] as const,
                          ].map(([label, summary, isPercent]) => (
                            <tr key={String(label)} className="border-t border-white/[0.06]">
                              <td className="px-4 py-3 text-sm font-black text-white">{label}</td>
                              <td className="px-4 py-3 text-sm font-bold text-gray-300">
                                {isPercent ? formatRatioAsPercent((summary as MonteCarloSummary).median) : (summary as MonteCarloSummary).median.toFixed(2)}
                              </td>
                              <td className="px-4 py-3 text-sm font-bold text-gray-300">
                                {isPercent ? formatRatioAsPercent((summary as MonteCarloSummary).p05) : (summary as MonteCarloSummary).p05.toFixed(2)}
                              </td>
                              <td className="px-4 py-3 text-sm font-bold text-gray-300">
                                {isPercent ? formatRatioAsPercent((summary as MonteCarloSummary).p95) : (summary as MonteCarloSummary).p95.toFixed(2)}
                              </td>
                              <td className="px-4 py-3 text-sm font-bold text-gray-300">
                                {isPercent ? formatRatioAsPercent((summary as MonteCarloSummary).std) : (summary as MonteCarloSummary).std.toFixed(2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="mt-4 rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm font-bold text-gray-300">
                      최대낙폭이 30%를 초과할 확률은 {formatRatioAsPercent(monteCarloResult.probMddOver30pct)} 입니다.
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
