"use client";

import { type ReactNode, useRef, useState } from "react";
import { ArrowsClockwise, Crown, FolderOpen, SignOut, Spinner } from "phosphor-react";
import {
  Bar,
  BarChart,
  ReferenceLine,
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
import { t } from "@/lib/i18n";

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
        aria-label={t("{0} 도움말", label)}
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
        aria-label={t("{0} 도움말", label)}
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

// fixed      = 고정 길이 블록 부트스트랩 (blockSize 그대로)
// stationary = 가변 길이(기하분포) 블록 — 경계 효과 완화, blockSize를 평균 블록 길이로 사용
export type MonteCarloBlockMethod = "fixed" | "stationary";

interface MonteCarloSettings {
  iterations: number;
  blockSize: number;
  seed: number;
  mode: MonteCarloMode;
  /** returns 모드의 블록 방식. 미지정/구버전은 fixed로 간주. */
  blockMethod?: MonteCarloBlockMethod;
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

/**
 * 재표본하지 않은 원래 순서의 지표를 시뮬레이션과 같은 기준으로 재구성한 값과,
 * 그 값이 분포 안에서 차지하는 위치.
 *
 * 위치(백분위)는 **MDD에만** 둔다. CAGR은 성장배수의 곱이라 순서와 무관하고, 부트스트랩
 * 분포는 관측 평균을 중심으로 만들어지므로 관측 CAGR은 구조적으로 늘 분포 한가운데
 * (실측 8시드×3방식 전부 47~59 백분위)에 온다 — 백분위를 보여줘도 정보가 없고
 * "상단 치우침=순서 의존"이라는 해석은 CAGR에는 성립하지 않는다. 순서에 좌우되는
 * 것은 낙폭(MDD·언더워터)뿐이다.
 */
export interface MonteCarloObserved {
  /** 원래 순서 그대로 재구성한 CAGR (분포와 동일한 기준으로 계산, 위치 해석 없음) */
  cagr: number;
  /** 원래 순서 그대로 재구성한 MDD */
  mdd: number;
  /** 시나리오 중 관측 MDD **이하**(=더 얕은 낙폭)인 비율 (0~1). */
  mddPct: number;
}

// 연환산 기준 — 백테스트 엔진(result_handler.time_base)과 같은 규칙을 쓴다.
// 연수는 달력 기준(첫 봉~마지막 봉 경과일 ÷ 365.25), 연환산 계수는 KRX 실제 거래일 246.
// 예전처럼 봉수÷252로 세면 연수를 ~2% 적게 잡아 CAGR이 백테스트 결과보다 높게 나왔다.
export const KRX_TRADING_DAYS_PER_YEAR = 246;

/** 백테스트 결과의 dates로 달력 연수를 구한다. 날짜를 못 쓰면 봉수÷246으로 되돌린다. */
export function backtestYears(dates: string[] | undefined, barCount: number): number {
  const fallback = Math.max(1e-6, barCount / KRX_TRADING_DAYS_PER_YEAR);
  if (!dates || dates.length < 2) return fallback;
  const first = Date.parse(dates[0]);
  const last = Date.parse(dates[dates.length - 1]);
  if (!Number.isFinite(first) || !Number.isFinite(last)) return fallback;
  const spanDays = (last - first) / 86_400_000;
  if (spanDays <= 0) return fallback;
  return spanDays / 365.25;
}

/** 표본 충분성 — 이 분포를 해석하기에 재표본 단위가 충분한지. */
export interface MonteCarloSufficiency {
  /** 근사 독립 표본 수(블록/거래 기준). 작을수록 분포 신뢰도가 낮다. */
  effectiveSamples: number;
  /** effectiveSamples < 임계치(30)면 true. */
  low: boolean;
}

interface MonteCarloResult {
  status: "ok";
  nIterations: number;
  blockSize: number;
  mode: MonteCarloMode;
  /** 재현에 사용한 시드. 구버전 저장 결과에는 없을 수 있다. */
  seed?: number;
  /** returns 모드의 블록 방식. 구버전 저장 결과에는 없을 수 있다(=fixed). */
  blockMethod?: MonteCarloBlockMethod;
  /** trades 모드에서 재표본에 사용한 완결 거래 수 */
  tradeCount?: number;
  /** trades 모드의 사이징 반영 방식: equity-weighted(자본 대비 기여도) / price-return(사이징 정보 없음) */
  tradeSizing?: "equity-weighted" | "price-return";
  /**
   * trades 모드의 거래 비용 반영: net(엔진이 준 순손익 — 수수료·거래세 차감) /
   * gross(체결가 차액만 — 비용 전). 구버전 결과·pnl 없는 체결 기록은 gross.
   */
  tradeCosts?: "net" | "gross";
  cagr: MonteCarloSummary;
  sharpe: MonteCarloSummary;
  mdd: MonteCarloSummary;
  probPositiveCagr: number;
  probMddOver30pct: number;
  cagrHistogram: MonteCarloHistogramBin[];
  mddHistogram: MonteCarloHistogramBin[];
  /** 실제 백테스트(원래 순서) 지표의 분포 내 위치. 구버전 저장 결과에는 없을 수 있다. */
  observed?: MonteCarloObserved;
  /** 낙폭 지속(회복까지) 스텝 수 분포 — returns 모드는 거래일, trades 모드는 거래 건. 구버전엔 없을 수 있다. */
  underwater?: MonteCarloSummary;
  /** 표본 충분성 지표. 구버전 저장 결과에는 없을 수 있다. */
  sufficiency?: MonteCarloSufficiency;
}

/** 분포 values 중 x 이하인 값의 비율(0~1). x가 분포 상단이면 1에 가깝다. */
function percentileRank(values: number[], x: number): number {
  if (values.length === 0) return 0;
  let count = 0;
  for (const value of values) if (value <= x) count += 1;
  return count / values.length;
}

/** 성장배수 스텝(로그수익률→exp, 거래수익률→1+r)을 순서대로 곱해 CAGR·MDD를 재구성한다. */
function reconstructPathMetrics(
  steps: number[],
  toGrowth: (step: number) => number,
  years: number,
  initialEquity: number
): { cagr: number; mdd: number } {
  let equity = initialEquity;
  let peak = initialEquity;
  let worstDrawdown = 0;
  for (const step of steps) {
    equity *= toGrowth(step);
    if (equity > peak) peak = equity;
    const drawdown = (equity - peak) / peak;
    if (drawdown < worstDrawdown) worstDrawdown = drawdown;
  }
  const cagr = equity > 0 ? (equity / initialEquity) ** (1 / years) - 1 : -1;
  return { cagr, mdd: Math.abs(worstDrawdown) };
}

// 이 값 미만의 근사 독립 표본(블록/거래)이면 분포 신뢰도가 낮다고 본다.
const MC_MIN_EFFECTIVE_SAMPLES = 30;

/**
 * 원본 수익률 시계열에서 원본과 같은 길이의 재표본 경로를 만든다.
 *   - fixed:      길이 blockSize 고정 블록을 이어 붙인다(경계에서 잘라 정확히 원본 길이).
 *   - stationary: 각 스텝을 확률 p=1/blockSize로 새 시작점, 아니면 다음 인덱스(원형)로 이어
 *                 평균 blockSize의 기하분포 가변 블록을 만든다(Politis–Romano stationary bootstrap).
 */
function sampleReturnBlockPath(
  source: number[],
  method: MonteCarloBlockMethod,
  blockSize: number,
  rng: () => number
): number[] {
  const n = source.length;
  const out: number[] = [];

  if (method === "stationary") {
    const p = 1 / Math.max(1, blockSize);
    let index = Math.floor(rng() * n);
    for (let k = 0; k < n; k += 1) {
      out.push(source[index]);
      index = rng() < p ? Math.floor(rng() * n) : (index + 1) % n;
    }
    return out;
  }

  const nBlocks = Math.ceil(n / blockSize);
  const maxStart = n - blockSize + 1;
  for (let block = 0; block < nBlocks; block += 1) {
    const start = Math.floor(rng() * maxStart);
    for (let offset = 0; offset < blockSize && out.length < n; offset += 1) {
      out.push(source[start + offset]);
    }
  }
  return out;
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
    let tv = Math.imul(state ^ (state >>> 15), 1 | state);
    tv ^= tv + Math.imul(tv ^ (tv >>> 7), 61 | tv);
    return ((tv ^ (tv >>> 14)) >>> 0) / 4294967296;
  };
}

const MONTE_CARLO_CHUNK_SIZE = 200;
const MIN_COMPLETED_TRADES = 20;

interface TradeReturnRecord {
  date: string;
  symbol: string;
  side: "buy" | "sell";
  price: number;
  quantity: number;
  /** 매도 체결의 순손익(원, 수수료·거래세 차감). 없으면 체결가 차액(비용 전)으로 계산한다. */
  pnl?: number;
}

// 체결 기록(tradesList, 없으면 signals)에서 종목별 수량 기반 FIFO 매칭으로 완결 거래를 복원한다.
// 각 완결 거래는 **자본 대비 기여도(return-on-equity)** = 손익금 / 진입시점 계좌자산 으로 환산한다.
//   - 이렇게 하면 실제 포지션 사이징(전액이 아닌 일부만 투입, 동시 다종목 보유)이 반영되어
//     거래 재표본 복리가 다종목 전략의 CAGR·MDD를 과장하지 않는다.
//   - 손익금은 엔진이 매도 체결에 실어 준 **순손익(pnl, 수수료·거래세 차감)**을 우선 쓴다.
//     체결가 차액(수량×(매도가−매수가))은 비용 전 총손익이라 왕복 0.45%(수수료 0.15%×2+
//     거래세 0.15%)가 빠져 회전율 높은 전략일수록 분포가 낙관적으로 치우친다. pnl이 없는
//     구버전 결과만 차액으로 강등하고 netOfFees=false 로 표시한다.
//   - 체결 수량이나 일별 자산곡선이 없어 사이징을 복원할 수 없으면 가격수익률로 강등하고
//     sized=false 로 표시한다(UI가 한계를 고지).
export function extractTradeReturns(backtestResult: BacktestResult): {
  returns: number[];
  sized: boolean;
  /** 모든 완결 거래의 손익이 순손익(pnl) 기준이면 true. 하나라도 차액 폴백이면 false. */
  netOfFees: boolean;
} {
  const fromTrades: TradeReturnRecord[] = (backtestResult.tradesList ?? []).map((tv) => ({
    date: tv.date,
    symbol: tv.symbol,
    side: tv.type,
    price: tv.price,
    quantity: tv.quantity ?? 0,
    pnl: tv.pnl,
  }));
  const fromSignals: TradeReturnRecord[] = (backtestResult.signals ?? []).map((s) => ({
    date: s.date,
    symbol: s.symbol,
    side: s.type === "entry" ? ("buy" as const) : ("sell" as const),
    price: s.price,
    quantity: s.quantity ?? 0,
    pnl: s.pnl,
  }));
  const records = fromTrades.length > 0 ? fromTrades : fromSignals;

  const dates = backtestResult.dates ?? [];
  const equity = backtestResult.equity ?? [];
  const equityByDate = new Map<string, number>();
  for (let i = 0; i < dates.length && i < equity.length; i += 1) {
    equityByDate.set(dates[i], equity[i]);
  }
  const fallbackEquity =
    backtestResult.initialCapital ??
    (Number.isFinite(equity[0]) && equity[0] > 0 ? equity[0] : undefined);

  // 사이징 복원 조건: 체결 수량과 진입시점 자산을 참조할 수 있어야 한다.
  const hasQuantity = records.some((record) => (record.quantity ?? 0) > 0);
  const hasEquity = equityByDate.size > 0 || fallbackEquity !== undefined;
  const sized = hasQuantity && hasEquity;

  const sorted = [...records].sort((a, b) => (a.date ?? "").localeCompare(b.date ?? ""));
  const openLots: Record<string, Array<{ price: number; quantity: number; date: string }>> = {};
  const returns: number[] = [];
  let netOfFees = true;

  for (const record of sorted) {
    if (!Number.isFinite(record.price) || record.price <= 0) continue;

    if (record.side === "buy") {
      const quantity = sized ? Math.max(0, record.quantity) : 1;
      (openLots[record.symbol] ??= []).push({ price: record.price, quantity, date: record.date });
      continue;
    }

    // 매도: 오래된 롯부터 수량만큼 소진하며 완결 조각별로 수익률을 기록한다.
    let sellQty = sized ? Math.max(0, record.quantity) : 1;
    const lots = openLots[record.symbol];
    // 순손익이 있으면 주당 순손익으로 환산해 매칭 수량만큼 배분한다(부분 체결 대응).
    const netPnlPerShare =
      typeof record.pnl === "number" && Number.isFinite(record.pnl) && record.quantity > 0
        ? record.pnl / record.quantity
        : undefined;
    while (lots && lots.length > 0 && sellQty > 0) {
      const lot = lots[0];
      const matchedQty = sized ? Math.min(lot.quantity, sellQty) : 1;

      if (sized) {
        const equityAtEntry = equityByDate.get(lot.date) ?? fallbackEquity;
        if (equityAtEntry && equityAtEntry > 0 && matchedQty > 0) {
          let pnl: number;
          if (netPnlPerShare !== undefined) {
            pnl = matchedQty * netPnlPerShare;
          } else {
            pnl = matchedQty * (record.price - lot.price);
            netOfFees = false;
          }
          returns.push(pnl / equityAtEntry);
        }
        lot.quantity -= matchedQty;
        sellQty -= matchedQty;
        if (lot.quantity <= 1e-9) lots.shift();
      } else {
        // 사이징 정보 없음 → 가격수익률(한 롯당 한 건, 비용 전)
        returns.push(record.price / lot.price - 1);
        netOfFees = false;
        lots.shift();
        sellQty -= 1;
      }
    }
  }

  return {
    returns: returns.filter((value) => Number.isFinite(value) && value > -1),
    sized,
    netOfFees,
  };
}

// 거래 재표본 모드: 완결 거래 수익률을 복원추출로 재배열해 CAGR/MDD 분포를 추정한다.
// MDD는 거래 단위 equity 경로 기준(거래 도중 낙폭은 반영되지 않음 — UI에 명시).
async function runTradeResampleSimulation(
  backtestResult: BacktestResult,
  settings: MonteCarloSettings,
  onProgress?: (completedRatio: number) => void,
  shouldCancel?: () => boolean
): Promise<{ status: "error"; message: string } | { status: "cancelled" } | MonteCarloResult> {
  const { returns: tradeReturns, sized, netOfFees } = extractTradeReturns(backtestResult);
  if (tradeReturns.length < MIN_COMPLETED_TRADES) {
    return {
      status: "error",
      message: t("거래 재표본에는 완결된 거래가 최소 {0}건 필요합니다 (현재 {1}건). 일별 수익률 방식을 사용해 주세요.", MIN_COMPLETED_TRADES, tradeReturns.length),
    };
  }

  const iterations = Math.max(100, Math.floor(settings.iterations));
  const barCount = (backtestResult.dates ?? []).length || (backtestResult.equity ?? []).length;
  const years = backtestYears(backtestResult.dates, barCount);
  const tradesPerYear = tradeReturns.length / years;
  const rng = createSeededRng(settings.seed);
  const n = tradeReturns.length;
  const cagrs: number[] = [];
  const sharpes: number[] = [];
  const mdds: number[] = [];
  const underwaters: number[] = [];

  for (let iteration = 0; iteration < iterations; iteration += 1) {
    if (iteration % MONTE_CARLO_CHUNK_SIZE === 0 && iteration > 0) {
      onProgress?.(iteration / iterations);
      await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
      if (shouldCancel?.()) return { status: "cancelled" };
    }

    let equity = 1;
    let peak = 1;
    let worstDrawdown = 0;
    let underwaterRun = 0;
    let longestUnderwater = 0;
    let sum = 0;
    let sumSq = 0;
    for (let i = 0; i < n; i += 1) {
      const sampled = tradeReturns[Math.floor(rng() * n)];
      equity *= 1 + sampled;
      if (equity >= peak) {
        peak = equity;
        underwaterRun = 0;
      } else {
        underwaterRun += 1;
        if (underwaterRun > longestUnderwater) longestUnderwater = underwaterRun;
        const drawdown = (equity - peak) / peak;
        if (drawdown < worstDrawdown) worstDrawdown = drawdown;
      }
      sum += sampled;
      sumSq += sampled * sampled;
    }

    const mean = sum / n;
    const variance = n > 1 ? Math.max(0, (sumSq - n * mean * mean) / (n - 1)) : 0;
    const std = Math.sqrt(variance);

    cagrs.push(equity > 0 ? equity ** (1 / years) - 1 : -1);
    // 거래 단위 샤프: 거래당 평균/표준편차 × √(연간 거래 수). 일별 샤프와 정의가 다르므로
    // 표에서 '거래 단위'로 구분 표기한다.
    sharpes.push(std > 1e-12 ? (mean / std) * Math.sqrt(tradesPerYear) : 0);
    mdds.push(Math.abs(worstDrawdown));
    underwaters.push(longestUnderwater);
  }

  onProgress?.(1);

  // 관측(원래 거래 순서) 지표를 동일 기준으로 재구성해 분포 내 위치를 계산한다.
  const observedPath = reconstructPathMetrics(tradeReturns, (r) => 1 + r, years, 1);

  return {
    status: "ok",
    nIterations: iterations,
    blockSize: settings.blockSize,
    seed: settings.seed,
    mode: "trades",
    tradeCount: tradeReturns.length,
    tradeSizing: sized ? "equity-weighted" : "price-return",
    tradeCosts: netOfFees ? "net" : "gross",
    cagr: summarizeMonteCarlo(cagrs),
    sharpe: summarizeMonteCarlo(sharpes),
    mdd: summarizeMonteCarlo(mdds),
    probPositiveCagr: cagrs.filter((value) => value > 0).length / cagrs.length,
    probMddOver30pct: mdds.filter((value) => value > 0.3).length / mdds.length,
    cagrHistogram: buildMonteCarloHistogram(cagrs),
    mddHistogram: buildMonteCarloHistogram(mdds),
    observed: {
      cagr: observedPath.cagr,
      mdd: observedPath.mdd,
      mddPct: percentileRank(mdds, observedPath.mdd),
    },
    underwater: summarizeMonteCarlo(underwaters),
    sufficiency: {
      effectiveSamples: n,
      low: n < MC_MIN_EFFECTIVE_SAMPLES,
    },
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
      message: t("몬테카를로 시뮬레이션에는 최소 {0}개의 유효 equity 포인트가 필요합니다.", minPoints),
    };
  }

  const logReturns: number[] = [];
  for (let i = 1; i < equity.length; i += 1) {
    logReturns.push(Math.log(equity[i] / equity[i - 1]));
  }

  if (logReturns.length < minPoints - 1) {
    return {
      status: "error",
      message: t("유효한 수익률 구간이 부족해 몬테카를로 시뮬레이션을 실행할 수 없습니다."),
    };
  }

  const blockMethod: MonteCarloBlockMethod = settings.blockMethod ?? "fixed";
  const iterations = Math.max(100, Math.floor(settings.iterations));
  const years = backtestYears(backtestResult.dates, equity.length);
  const initialEquity = backtestResult.initialCapital || equity[0];
  const rng = createSeededRng(settings.seed);
  const cagrs: number[] = [];
  const sharpes: number[] = [];
  const mdds: number[] = [];
  const underwaters: number[] = [];

  for (let iteration = 0; iteration < iterations; iteration += 1) {
    // UI가 진행률을 그리고 취소에 반응할 수 있도록 일정 주기로 이벤트 루프에 양보한다.
    if (iteration % MONTE_CARLO_CHUNK_SIZE === 0 && iteration > 0) {
      onProgress?.(iteration / iterations);
      await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
      if (shouldCancel?.()) return { status: "cancelled" };
    }

    const sampled = sampleReturnBlockPath(logReturns, blockMethod, blockSize, rng);

    let currentEquity = initialEquity;
    let peakEquity = initialEquity;
    let worstDrawdown = 0;
    let underwaterRun = 0;
    let longestUnderwater = 0;
    for (const value of sampled) {
      currentEquity *= Math.exp(value);
      if (currentEquity >= peakEquity) {
        peakEquity = currentEquity;
        underwaterRun = 0;
      } else {
        underwaterRun += 1;
        if (underwaterRun > longestUnderwater) longestUnderwater = underwaterRun;
        const drawdown = (currentEquity - peakEquity) / peakEquity;
        if (drawdown < worstDrawdown) worstDrawdown = drawdown;
      }
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
    sharpes.push(std > 1e-12 ? (avgReturn / std) * Math.sqrt(KRX_TRADING_DAYS_PER_YEAR) : 0);
    mdds.push(Math.abs(worstDrawdown));
    underwaters.push(longestUnderwater);
  }

  onProgress?.(1);

  // 관측(원래 순서) 지표를 시뮬레이션과 동일한 기준(연수·초기자본)으로 재구성한다.
  const observedPath = reconstructPathMetrics(logReturns, Math.exp, years, initialEquity);
  // 근사 독립 표본 = 수익률 포인트 수 ÷ 블록 길이(일별 재표본이면 blockSize 1로 포인트 수 그대로).
  const effectiveSamples = logReturns.length / Math.max(1, blockSize);

  return {
    status: "ok",
    nIterations: iterations,
    blockSize,
    seed: settings.seed,
    blockMethod,
    mode: "returns",
    cagr: summarizeMonteCarlo(cagrs),
    sharpe: summarizeMonteCarlo(sharpes),
    mdd: summarizeMonteCarlo(mdds),
    probPositiveCagr: cagrs.filter((value) => value > 0).length / cagrs.length,
    probMddOver30pct: mdds.filter((value) => value > 0.3).length / mdds.length,
    cagrHistogram: buildMonteCarloHistogram(cagrs),
    mddHistogram: buildMonteCarloHistogram(mdds),
    observed: {
      cagr: observedPath.cagr,
      mdd: observedPath.mdd,
      mddPct: percentileRank(mdds, observedPath.mdd),
    },
    underwater: summarizeMonteCarlo(underwaters),
    sufficiency: {
      effectiveSamples,
      low: effectiveSamples < MC_MIN_EFFECTIVE_SAMPLES,
    },
  };
}

function formatRatioAsPercent(value: number, digits = 2): string {
  return `${(value * 100).toFixed(digits)}%`;
}

// 실행 결과 자체에서 재표본 방식 라벨을 만든다(실행 후 설정이 바뀌어도 결과와 어긋나지 않도록).
export function formatMonteCarloMethodLabel(
  result: Pick<MonteCarloResult, "mode" | "blockMethod" | "blockSize">
): string {
  if (result.mode === "trades") return t("거래 재표본");
  if (result.blockMethod === "stationary") return t("평균 {0}일 가변 블록", result.blockSize);
  if (result.blockSize <= 1) return t("일별 재표본");
  return t("{0}일 블록", result.blockSize);
}

function SummaryChip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-bold text-gray-200">
      {children}
    </span>
  );
}

// 이 검증(MC·워크포워드)이 대상으로 삼는 전략의 구성(진입·청산 조건, 유니버스, 리스크)을 보여준다.
// 어떤 지표(PBR/PER/MACD 등)를 쓴 전략을 검증 중인지 사용자가 결과와 함께 확인할 수 있게 한다.
function StrategyConditionSummary({
  summary,
  strategyName,
  promptText,
}: {
  summary?: OptimizationStrategySummary;
  strategyName?: string;
  promptText?: string;
}) {
  const entryBlocks = summary?.entryBlocks ?? [];
  const exitBlocks = summary?.exitBlocks ?? [];
  const universeName = summary?.universeName?.trim();
  const metaChips = [summary?.positionText, summary?.rebalancingText, summary?.riskText].filter(
    (value): value is string => Boolean(value)
  );
  const name = strategyName?.trim() || summary?.strategyName?.trim();
  const hasStructured =
    entryBlocks.length > 0 || exitBlocks.length > 0 || !!universeName || metaChips.length > 0;

  if (!hasStructured && !promptText && !name) return null;

  return (
    <div
      data-testid="optimization-strategy-summary"
      className="mt-4 rounded-xl border border-white/[0.08] bg-white/[0.03] p-4"
    >
      <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">{t("검증 대상 전략")}</p>
      {name && <p className="mt-1.5 text-sm font-black text-white">{name}</p>}

      {universeName && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-black text-gray-500">{t("유니버스")}</span>
          <SummaryChip>{universeName}</SummaryChip>
        </div>
      )}

      {entryBlocks.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-black text-gray-500">{t("진입 신호")}</span>
          {entryBlocks.map((block, index) => (
            <SummaryChip key={`entry-${index}`}>
              {block}
            </SummaryChip>
          ))}
        </div>
      )}

      {exitBlocks.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-black text-gray-500">{t("청산")}</span>
          {exitBlocks.map((block, index) => (
            <SummaryChip key={`exit-${index}`}>
              {block}
            </SummaryChip>
          ))}
        </div>
      )}

      {metaChips.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-black text-gray-500">{t("운용")}</span>
          {metaChips.map((chip, index) => (
            <SummaryChip key={`meta-${index}`}>{chip}</SummaryChip>
          ))}
        </div>
      )}

      {!hasStructured && promptText && (
        <p className="mt-2 text-xs font-bold leading-5 text-gray-400">{promptText}</p>
      )}
    </div>
  );
}

// 전략의 평균 보유기간을 근거로 재표본 블록 길이 기본값을 제안한다.
// (검증 방식 선택을 돕는 통계적 제안일 뿐, 투자 판단이 아니다. 화면 어휘도 '추천'을 쓰지 않는다.)
export interface MonteCarloRecommendation {
  blockSize: number;
  label: string;
  reason: string;
}

export function recommendMonteCarloMethod(
  result: Pick<BacktestResult, "avgHoldingDays">
): MonteCarloRecommendation | null {
  const holding = Math.round(result.avgHoldingDays ?? 0);
  if (!Number.isFinite(holding) || holding <= 0) return null;

  let blockSize: number;
  if (holding >= 16) blockSize = 21;
  else if (holding >= 8) blockSize = 10;
  else if (holding >= 2) blockSize = 5;
  else blockSize = 1;

  const label = blockSize <= 1 ? t("일별 재표본") : t("{0}일 블록", blockSize);
  return {
    blockSize,
    label,
    reason: t("평균 보유기간이 약 {0}일이라 {1} 방식이 연속된 흐름을 적절히 보존합니다.", holding, label),
  };
}

function MonteCarloHistogramChart({
  title,
  bins,
  xAxisLabel,
  signColored = false,
  observedValue,
}: {
  title: string;
  bins: MonteCarloHistogramBin[];
  xAxisLabel: string;
  /** true면 0 기준으로 음수 구간은 파랑, 양수 구간은 빨강 (앱의 등락 색 관례) */
  signColored?: boolean;
  /** 원래 순서(재표본 안 함) 값 — 해당 구간 위에 세로 기준선으로 표시한다. */
  observedValue?: number;
}) {
  if (bins.length === 0) return null;

  const data = bins.map((bin) => ({
    ...bin,
    label: `${(bin.x0 * 100).toFixed(1)}%`,
    mid: (bin.x0 + bin.x1) / 2,
  }));

  // 관측값이 속한 구간(범위를 벗어나면 양끝으로 클램프)을 기준선 위치로 잡는다.
  let observedLabel: string | null = null;
  if (observedValue !== undefined && Number.isFinite(observedValue)) {
    let index = bins.findIndex((bin) => observedValue >= bin.x0 && observedValue <= bin.x1);
    if (index === -1) index = observedValue < bins[0].x0 ? 0 : bins.length - 1;
    observedLabel = data[index]?.label ?? null;
  }

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
              itemStyle={{ color: "#9ca3af" }}
              formatter={(value: any) => [t("{0}회", Number(value).toLocaleString()), t("빈도")]}
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
            {observedLabel !== null && (
              <ReferenceLine
                x={observedLabel}
                stroke="#fbbf24"
                strokeWidth={2}
                strokeDasharray="4 3"
                label={{ value: t("원래 순서"), position: "top", fill: "#fbbf24", fontSize: 10, fontWeight: 800 }}
              />
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-bold text-gray-500">
        <span>{t("x축: {0}", xAxisLabel)}</span>
        <span>{t("y축: 시나리오 수")}</span>
        {observedLabel !== null && <span className="text-amber-300/90">{t("노란 선 = 원래 순서(재표본 안 함) 값")}</span>}
      </div>
    </div>
  );
}

// 검증 대상 전략을 사람이 읽을 수 있는 라벨(PBR≤1, MACD 골든크로스 등)로 담은 요약.
// BacktestDashboard가 이미 만들어 두는 값을 그대로 넘겨받는다(별도 파싱 없음).
export interface OptimizationStrategySummary {
  universeName?: string;
  strategyName?: string;
  entryBlocks?: string[];
  exitBlocks?: string[];
  positionText?: string;
  riskText?: string;
  rebalancingText?: string;
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
  /** 검증 대상 전략 요약(진입·청산 조건 라벨 등). MC/워크포워드 화면에 표시한다. */
  strategySummary?: OptimizationStrategySummary;
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
  strategySummary,
  onClose,
}: OptimizationPageProps) {
  const [selectedModel, setSelectedModel] = useState<OptimizationModel>("walkForward");
  const [loadedWalkForward, setLoadedWalkForward] = useState<any | null>(null);
  const [isSavedListOpen, setIsSavedListOpen] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const validationCacheKey = (result as { cacheKey?: string }).cacheKey;

  const monteCarloRecommendation = recommendMonteCarloMethod(result);
  const [monteCarloSettings, setMonteCarloSettings] = useState<MonteCarloSettings>({
    iterations: 1000,
    blockSize: 21,
    seed: 42,
    mode: "returns",
    blockMethod: "fixed",
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
          blockMethod: mc.blockMethod ?? "fixed",
          seed: mc.seed ?? prev.seed,
        }));
      }
      setIsSavedListOpen(false);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t("불러오기에 실패했습니다."));
    }
  };

  const monteCarloModeLabel =
    monteCarloSettings.mode === "trades"
      ? t("거래 재표본")
      : monteCarloSettings.blockMethod === "stationary"
        ? t("평균 {0}일 가변 블록", monteCarloSettings.blockSize)
        : monteCarloSettings.blockSize <= 1
          ? t("일별 재표본")
          : t("{0}일 블록 재표본", monteCarloSettings.blockSize);
  const monteCarloCompletedIterations = Math.min(
    monteCarloSettings.iterations,
    Math.round(monteCarloProgress * monteCarloSettings.iterations)
  );

  // 프리미엄 전용 기능 게이트: PREMIUM이 아니면 최적화 화면 대신 안내와 플랜 변경 유도를 노출한다.
  if (!isPlanLoading && !isPremiumValidationEnabled) {
    return (
      <div
        data-testid="backtest-optimization-page"
        className="flex min-h-[320px] items-center justify-center px-4 py-8 lg:px-6 lg:py-10"
      >
        <div className="w-full max-w-2xl p-5 text-center sm:p-6 lg:p-8">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-amber-400/30 bg-amber-500/10">
            <Crown className="h-6 w-6 text-amber-300" weight="fill" />
          </div>
          <h3 className="mt-4 text-lg font-black text-white">{t("전략 최적화는 프리미엄 플랜 전용 기능입니다")}</h3>
          <p className="mt-2 text-sm font-bold leading-6 text-gray-400 lg:whitespace-nowrap">
            {t("프리미엄 플랜을 이용하시면 워크포워드 분석과 몬테카를로 시뮬레이션을 통해 더 깊은 검증을 할 수 있습니다.")}
          </p>
          <a
            href="/pricing"
            className="mt-6 inline-flex items-center justify-center rounded-lg border border-gray-500 px-5 py-2.5 text-sm font-black text-gray-300 transition-colors hover:bg-white/[0.05]"
          >
            {t("플랜 변경")}
          </a>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="backtest-optimization-page" className="flex flex-col gap-3 px-3 py-3 sm:px-4 lg:flex-row lg:items-start lg:gap-4 lg:px-6 lg:py-4">
      <aside className="w-full flex-shrink-0 lg:w-64">
        <button
          type="button"
          onClick={() => setIsSavedListOpen(true)}
          className="mb-3 flex w-full items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[0.04] px-4 py-2.5 text-xs font-black text-gray-200 transition-colors hover:bg-white/[0.08]"
        >
          <FolderOpen className="h-4 w-4" weight="bold" />
          {t("저장된 검증 결과 불러오기")}
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
              aria-label={t(model.label)}
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
                <span className="block text-sm font-black text-white">{t(model.label)}</span>
                <ModelHelpTooltip label={t(model.label)} description={t(model.description)} example={t(model.example)} />
              </span>
              <span className="mt-1.5 block text-xs font-bold leading-5 text-gray-400">
                {t(model.description)}
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
                  ? t("플랜 권한을 확인하는 중입니다.")
                  : !isPremiumValidationEnabled
                    ? t("워크포워드 분석은 PREMIUM 플랜에서만 실행할 수 있습니다.")
                    : !baseStrategy
                      ? t("이 백테스트 결과에는 워크포워드 분석에 필요한 전략 설정이 저장되어 있지 않습니다.")
                      : t("이 결과 화면에는 워크포워드 실행 경로가 연결되어 있지 않습니다.")
              }
            />
          </div>
        )}

        {selectedModel === "monteCarlo" && (
          <div className="rounded-2xl border border-white/[0.08] bg-[#0f0f10] p-4 sm:p-5 lg:p-6">
            <div className="space-y-2">
              <h3 className="text-xl font-black text-white">{t("몬테카를로 시뮬레이션")}</h3>
              <p className="max-w-2xl text-sm font-bold leading-6 text-gray-300">
                {t("백테스트 결과를 여러 방식으로 다시 섞어 보며 수익률과 손실 폭이 얼마나 달라질 수 있는지 확인합니다. 여러 날을 묶어서 섞는 방식도 선택할 수 있어 연속된 시장 흐름을 일부 반영합니다.")}
              </p>
            </div>

            <StrategyConditionSummary
              summary={strategySummary}
              strategyName={strategyName}
              promptText={promptText}
            />

            {isPlanLoading && (
              <div className="mt-5 rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm font-bold text-gray-300">
                {t("플랜 권한을 확인하는 중입니다.")}
              </div>
            )}

            {!isPlanLoading && isPremiumValidationEnabled && (
              <>
                <div className="mt-5 grid gap-4 lg:grid-cols-[1.1fr,0.9fr]">
                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                    <div className="flex items-center gap-1.5">
                      <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">{t("반복 횟수")}</p>
                      <SettingHelpTooltip
                        label={t("반복 횟수")}
                        description={t("과거 데이터를 재조합해 만드는 가상 시나리오의 개수입니다. 횟수가 많을수록 수익률·낙폭 분포가 더 안정적으로 추정되지만 계산 시간은 늘어납니다.")}
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
                      <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">{t("시뮬레이션 방식")}</p>
                      <SettingHelpTooltip
                        label={t("시뮬레이션 방식")}
                        description={t("과거 수익률을 다시 섞는 방법입니다. 일별 재표본은 하루 단위로 독립 추출하고, N일 블록은 며칠간 이어지는 등락 패턴을 함께 보존합니다. 가변 블록(Stationary)은 블록 길이를 고정하지 않고 평균 길이만 맞춰(기하분포) 고정 블록의 경계 효과를 줄입니다. 거래 재표본은 개별 체결 수익률을 재배열합니다.")}
                      />
                    </div>
                    {monteCarloRecommendation && (
                      <button
                        type="button"
                        onClick={() =>
                          setMonteCarloSettings((prev) => ({
                            ...prev,
                            mode: "returns",
                            blockMethod: "fixed",
                            blockSize: monteCarloRecommendation.blockSize,
                          }))
                        }
                        title={monteCarloRecommendation.reason}
                        className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-sky-400/30 px-2.5 py-1 text-[11px] font-black transition-colors"
                      >
                        {t("보유기간 기준 블록 길이: {0} 적용", monteCarloRecommendation.label)}
                      </button>
                    )}
                    <div className="mt-3 flex flex-wrap gap-2">
                      {[
                        { mode: "returns" as const, blockMethod: "fixed" as const, blockSize: 1, label: t("일별 재표본") },
                        { mode: "returns" as const, blockMethod: "fixed" as const, blockSize: 5, label: t("5일 블록") },
                        { mode: "returns" as const, blockMethod: "fixed" as const, blockSize: 10, label: t("10일 블록") },
                        { mode: "returns" as const, blockMethod: "fixed" as const, blockSize: 21, label: t("21일 블록") },
                        { mode: "returns" as const, blockMethod: "stationary" as const, blockSize: 10, label: t("가변 블록") },
                        { mode: "trades" as const, blockMethod: "fixed" as const, blockSize: 21, label: t("거래 재표본") },
                      ].map(({ mode, blockMethod, blockSize, label }) => {
                        const currentMethod = monteCarloSettings.blockMethod ?? "fixed";
                        const active =
                          monteCarloSettings.mode === mode &&
                          (mode === "trades"
                            ? true
                            : blockMethod === "stationary"
                              ? currentMethod === "stationary"
                              : currentMethod === "fixed" && monteCarloSettings.blockSize === blockSize);
                        return (
                          <button
                            key={label}
                            onClick={() =>
                              setMonteCarloSettings((prev) => ({
                                ...prev,
                                mode,
                                blockMethod,
                                // 가변 블록으로 전환 시 이미 가변이면 평균값 유지, 아니면 기본 10일.
                                blockSize:
                                  blockMethod === "stationary"
                                    ? prev.blockMethod === "stationary"
                                      ? prev.blockSize
                                      : 10
                                    : blockSize,
                              }))
                            }
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

                    {monteCarloSettings.mode === "returns" &&
                      monteCarloSettings.blockMethod === "stationary" && (
                        <div className="mt-3">
                          <div className="flex items-center gap-1.5">
                            <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">{t("평균 블록 길이")}</p>
                            <SettingHelpTooltip
                              label={t("평균 블록 길이")}
                              description={t("가변 블록의 평균 지속 길이(거래일)입니다. 각 스텝에서 1/평균 확률로 새 시작점을 뽑아 블록 길이가 평균값을 중심으로 무작위로 정해집니다. 전략의 평균 보유기간·리밸런싱 주기와 비슷하게 두는 것이 일반적입니다.")}
                            />
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {[5, 10, 21].map((value) => (
                              <button
                                key={value}
                                onClick={() => setMonteCarloSettings((prev) => ({ ...prev, blockSize: value }))}
                                className={`rounded-lg border px-3 py-1.5 text-sm font-black transition-colors ${
                                  monteCarloSettings.blockSize === value
                                    ? "border-white/20 bg-white/10 text-white"
                                    : "border-white/10 bg-white/[0.03] text-gray-400 hover:text-white"
                                }`}
                              >
                                {t("{0}일", value)}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                    <p className="mt-3 text-xs font-bold leading-5 text-gray-500">
                      {monteCarloSettings.mode === "trades"
                        ? t("체결 기록에서 완결 거래의 자본 대비 기여도(포지션 크기 반영)를 복원추출로 재배열합니다 (trade bootstrap). MDD는 거래 단위 경로 기준으로, 거래 도중의 낙폭은 반영되지 않습니다.")
                        : monteCarloSettings.blockMethod === "stationary"
                          ? t("평균 {0}거래일 길이의 가변 블록으로 재조합합니다 (stationary bootstrap). 블록 경계가 매번 달라져 고정 블록의 경계 효과를 완화하면서 연속된 흐름을 보존합니다.", monteCarloSettings.blockSize)
                          : monteCarloSettings.blockSize <= 1
                            ? t("하루 단위로 독립 재표본합니다 (i.i.d. bootstrap). 각 날짜를 독립으로 뽑으므로 연속된 흐름(자기상관·변동성 군집·추세)은 깨집니다 — 이를 보존하려면 N일 블록이나 가변 블록을 선택하세요.")
                            : t("{0}거래일 단위로 수익률 흐름을 다시 조합해, 며칠간 이어지는 상승과 하락 패턴도 함께 살펴봅니다.", monteCarloSettings.blockSize)}
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
                    {t("몬테카를로 실행")}
                  </button>
                  <p className="text-xs font-bold text-gray-500">
                    {t("seed {0} 고정 · 동일 설정이면 같은 결과가 재현됩니다", monteCarloSettings.seed)}
                  </p>
                </div>

                <RunProgressModal
                  open={isMonteCarloRunning || !!monteCarloError}
                  title={t("몬테카를로 시뮬레이션")}
                  isRunning={isMonteCarloRunning}
                  progressRatio={monteCarloProgress}
                  progressLabel={
                    isMonteCarloRunning
                      ? t("{0}/{1}회 완료 ({2}%)", monteCarloCompletedIterations.toLocaleString(), monteCarloSettings.iterations.toLocaleString(), Math.round(monteCarloProgress * 100))
                      : undefined
                  }
                  detail={
                    isMonteCarloRunning ? (
                      <>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-gray-500">{t("시뮬레이션 방식")}</span>
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
                    <div
                      data-testid="monte-carlo-result-header"
                      className="mt-5 flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-center"
                    >
                      <p className="text-sm font-black text-white">{t("시뮬레이션 결과")}</p>
                      <div className="flex items-center gap-2">
                        <SaveValidationButton
                          onSave={async () => {
                            await saveValidation({
                              modelType: "monteCarlo",
                              strategyName: strategyName || t("이름 없는 전략"),
                              prompt: promptText,
                              cacheKey: validationCacheKey,
                              settings: {
                                iterations: monteCarloResult.nIterations,
                                blockSize: monteCarloResult.blockSize,
                                blockMethod: monteCarloResult.blockMethod ?? "fixed",
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
                            title={t("결과 닫기")}
                            className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/[0.05] px-4 py-1.5 text-sm font-bold text-gray-300 transition-all hover:border-white/10 hover:bg-white/10 hover:text-white active:scale-95"
                          >
                            <SignOut className="h-4 w-4" />
                            {t("결과 닫기")}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* 이 결과를 만든 실행 파라미터 — 결과 객체에서 직접 읽어 표시(설정 변경과 무관하게 일관).
                        거래 재표본의 사이징·비용 강등도 여기서 고지한다(SRS FR-BT-050 실행 설정 표시). */}
                    <div
                      data-testid="monte-carlo-run-params"
                      className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-xs font-bold text-gray-400"
                    >
                      <span className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">{t("실행 설정")}</span>
                      <span>
                        {t("방식")} <span className="text-gray-200">{formatMonteCarloMethodLabel(monteCarloResult)}</span>
                      </span>
                      <span>
                        {t("반복")} <span className="tabular-nums text-gray-200">{t("{0}회", monteCarloResult.nIterations.toLocaleString())}</span>
                      </span>
                      <span>
                        seed <span className="tabular-nums text-gray-200">{monteCarloResult.seed ?? monteCarloSettings.seed}</span>
                      </span>
                      {monteCarloResult.mode === "trades" && monteCarloResult.tradeCount !== undefined && (
                        <span>
                          {t("완결 거래")} <span className="tabular-nums text-gray-200">{t("{0}건", monteCarloResult.tradeCount.toLocaleString())}</span>
                        </span>
                      )}
                      {monteCarloResult.mode === "trades" && monteCarloResult.tradeSizing && (
                        <span>
                          {t("사이징")}{" "}
                          <span className={monteCarloResult.tradeSizing === "equity-weighted" ? "text-gray-200" : "text-amber-300"}>
                            {monteCarloResult.tradeSizing === "equity-weighted"
                              ? t("포지션 크기 반영")
                              : t("가격수익률(사이징 정보 없음)")}
                          </span>
                        </span>
                      )}
                      {monteCarloResult.mode === "trades" && (
                        <span>
                          {t("거래 비용")}{" "}
                          <span className={monteCarloResult.tradeCosts === "net" ? "text-gray-200" : "text-amber-300"}>
                            {monteCarloResult.tradeCosts === "net"
                              ? t("수수료·거래세 차감")
                              : t("미반영(비용 전 손익)")}
                          </span>
                        </span>
                      )}
                    </div>

                    {monteCarloResult.sufficiency?.low && (
                      <div className="mt-3 rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-xs font-bold leading-5 text-amber-200">
                        {t("재표본에 쓰인 독립 단위가 약 {0}개로 적어, 이 분포는 참고용으로 보는 것이 적절합니다. 표본이 적을수록 분위수·확률 추정이 흔들립니다.", Math.round(monteCarloResult.sufficiency.effectiveSamples))}
                      </div>
                    )}
                    <div className="mt-3 grid gap-3 md:grid-cols-3">
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">{t("CAGR 중앙값")}</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.cagr.median)}</p>
                        <p className="mt-1 text-[11px] font-bold text-gray-500">
                          {t("하위 5% 경계 {0}", formatRatioAsPercent(monteCarloResult.cagr.p05))}
                        </p>
                      </div>
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">{t("양수 CAGR 확률")}</p>
                        <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.probPositiveCagr)}</p>
                      </div>
                      {monteCarloResult.observed ? (
                        <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                          <div className="flex items-center gap-1.5">
                            <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">{t("원래 순서 MDD")}</p>
                            <SettingHelpTooltip
                              label={t("원래 순서 MDD의 분포 내 위치")}
                              description={t("재표본하지 않은 원래 순서의 최대 낙폭을 시뮬레이션과 같은 기준으로 재구성한 값과, 그 값이 시나리오 분포에서 차지하는 위치입니다. 낙폭은 수익률이 어떤 순서로 이어졌는지에 따라 달라지므로, 시나리오 상당수가 이보다 더 깊은 낙폭을 겪었다면 원래 순서가 낙폭 면에서 유리한 편이었다는 뜻입니다. (CAGR은 순서와 무관해 위치를 표시하지 않습니다.)")}
                            />
                          </div>
                          <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.observed.mdd)}</p>
                          <p className="mt-1 text-[11px] font-bold text-gray-500">
                            {t("시나리오 {0}%가 이보다 깊음", Math.round((1 - monteCarloResult.observed.mddPct) * 100))}
                          </p>
                        </div>
                      ) : (
                        <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                          <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">{t("표본 최대 MDD")}</p>
                          <p className="mt-2 text-2xl font-black text-white">{formatRatioAsPercent(monteCarloResult.mdd.max)}</p>
                        </div>
                      )}
                    </div>

                    <div className="mt-5 grid gap-3 lg:grid-cols-2">
                      <MonteCarloHistogramChart
                        title={t("CAGR 분포")}
                        bins={monteCarloResult.cagrHistogram}
                        xAxisLabel={t("CAGR 구간")}
                        signColored
                      />
                      <MonteCarloHistogramChart
                        title={t("MDD 분포")}
                        bins={monteCarloResult.mddHistogram}
                        xAxisLabel={t("MDD 구간")}
                        observedValue={monteCarloResult.observed?.mdd}
                      />
                    </div>

                    <div className="mt-5 overflow-x-auto rounded-xl border border-white/[0.08] bg-white/[0.03]">
                      <table className="w-full min-w-[640px] text-left">
                        <thead className="bg-white/[0.04]">
                          <tr>
                            {[t("지표"), t("최소"), "5%", "25%", t("중앙값"), "75%", "95%", t("최대"), t("표준편차")].map((label) => (
                              <th key={label} className="px-4 py-3 text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">
                                {label}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {[
                            ["CAGR", monteCarloResult.cagr, true] as const,
                            [monteCarloResult.mode === "trades" ? t("Sharpe(거래 단위)") : "Sharpe", monteCarloResult.sharpe, false] as const,
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
                    {monteCarloResult.mode === "trades" && (
                      <p className="mt-2 text-[11px] font-bold leading-5 text-gray-500">
                        {t("Sharpe(거래 단위) = 거래당 수익률 평균 ÷ 표준편차 × √(연간 거래 수). 일별 수익률로 계산하는 백테스트 결과의 샤프 지수와 정의가 달라 직접 비교할 수 없습니다.")}
                      </p>
                    )}

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
