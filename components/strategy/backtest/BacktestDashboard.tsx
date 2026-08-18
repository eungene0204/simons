"use client";

import { BacktestResult } from "@/types/strategy";
import BacktestChart from "@/components/strategy/BacktestChart";
import { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";
import {
  Table,
  ArrowsClockwise,
  ShieldCheck,
  Warning,
  Info,
  List,
  Check,
  CaretUp,
  CaretDown,
  X,
  FloppyDisk,
  SignOut,
  Spinner,
  Crown,
  DownloadSimple,
} from "phosphor-react";


import { useState, useEffect, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import XAIModal from "./XAIModal";
import { WalkForwardSettings, type WalkForwardOptimizationTarget } from "./WalkForwardModal";
import OptimizationPage from "./OptimizationPage";
import BacktestSummaryCard from "./BacktestSummaryCard";
import QuantileGroupsSection from "./QuantileGroupsSection";
import RebalanceComparisonSection from "./RebalanceComparisonSection";
import { buildAiReportMetrics, hasAiReportArtifact } from "./aiReportMetrics";
import { formatProfitFactor, profitFactorForRanking } from "@/lib/format-profit-factor";
import {
  type AiReportData,
  reportFromSummaryResponse,
  reportToPersistedFields,
} from "./aiReport";
import { buildAutoSaveHistoryPayload, buildHistoryConditions } from "@/lib/backtest-history";
import { invalidateBacktestHistoryCache } from "@/lib/backtest-history-cache";
import { resolveUniverseDisplayName } from "@/lib/strategy-summary";
import { buildPromptSummaryRows } from "./promptSummaryRows";
import { buildMonthlyReturnTableData } from "./monthlyReturns";
import { buildRollingReturnSeries, buildRollingWindowStatsTable } from "./rollingReturns";
import RollingReturnTable from "./RollingReturnTable";
import { ROLLING_WINDOW_OPTIONS, rollingWindowLabel } from "./rollingReturnLabels";
import {
  normalizeLegacyBreakoutStrategy,
  resolveTradeReason,
} from "@/components/strategy/legacyBreakout";
import {
  exportFileName,
  type BacktestExportPayload,
  type ExportFormat,
} from "@/lib/backtest-export";
import { t } from "@/lib/i18n";

const processedExecutionIds = new Set<string>();

function calculateScore(r: {
  cagr?: number; maxDrawdown?: number; sharpe?: number;
  profitFactor?: number | null; winRate?: number;
}): number {
  const scoreCagr = (v?: number) => {
    if (v == null) return 50;
    if (v >= 20) return 100; if (v >= 10) return 70;
    return Math.max(0, Math.round(v / 10 * 70));
  };
  const scoreMdd = (v?: number) => {
    if (v == null) return 50;
    const a = Math.abs(v);
    if (a <= 10) return 100; if (a <= 20) return 70; if (a <= 30) return 40;
    return Math.max(0, Math.round(100 - a * 2));
  };
  const scoreSharpe = (v?: number) => {
    if (v == null) return 50;
    if (v >= 1.5) return 100; if (v >= 1.0) return 70; if (v >= 0.5) return 40;
    return Math.max(0, Math.round(v / 1.5 * 100));
  };
  const scorePf = (v?: number) => {
    if (v == null) return 50;
    if (v >= 2.0) return 100; if (v >= 1.5) return 70; if (v >= 1.0) return 40;
    return Math.max(0, Math.round(v / 2.0 * 100));
  };
  const scoreWr = (v?: number) => {
    if (v == null) return 50;
    if (v >= 55) return 100; if (v >= 50) return 70; if (v >= 45) return 40;
    return Math.max(0, Math.round(v / 55 * 100));
  };
  return Math.round(
    scoreCagr(r.cagr) * 0.30 +
    scoreMdd(r.maxDrawdown) * 0.25 +
    scoreSharpe(r.sharpe) * 0.20 +
    scorePf(profitFactorForRanking(r.profitFactor)) * 0.15 +
    scoreWr(r.winRate) * 0.10
  );
}

function metricValueColor(value: number): string {
  if (value > 0) return "text-[var(--main-red)]";
  if (value < 0) return "text-[var(--main-blue)]";
  return "text-white";
}

// 엔진(v12.0)과 같은 연환산 기준 — KRX 실측 연 246 거래일. 이 폴백들은 엔진 값이
// 없는 구버전 저장 결과에서만 쓰이지만, 기준이 다르면 같은 지표가 화면마다 어긋난다.
const KRX_TRADING_DAYS_PER_YEAR = 246;

function calculateAnnualizedVolatility(equity: number[]): number {
  const dailyReturns: number[] = [];

  for (let index = 1; index < equity.length; index += 1) {
    const previous = equity[index - 1];
    const current = equity[index];
    if (!Number.isFinite(previous) || !Number.isFinite(current) || previous === 0) continue;
    dailyReturns.push((current - previous) / previous);
  }

  if (dailyReturns.length < 2) return 0;

  const mean = dailyReturns.reduce((sum, value) => sum + value, 0) / dailyReturns.length;
  // 표본 표준편차(ddof=1) — 엔진과 동일. 모집단 기준(n)은 변동성을 과소평가한다.
  const variance = dailyReturns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (dailyReturns.length - 1);

  return Math.sqrt(variance) * Math.sqrt(KRX_TRADING_DAYS_PER_YEAR) * 100;
}

function calculateSortinoRatio(equity: number[]): number {
  const dailyReturns: number[] = [];

  for (let index = 1; index < equity.length; index += 1) {
    const previous = equity[index - 1];
    const current = equity[index];
    if (!Number.isFinite(previous) || !Number.isFinite(current) || previous === 0) continue;
    dailyReturns.push((current - previous) / previous);
  }

  if (dailyReturns.length === 0) return 0;

  const meanReturn = dailyReturns.reduce((sum, value) => sum + value, 0) / dailyReturns.length;
  const downsideDeviation = Math.sqrt(
    dailyReturns.reduce((sum, value) => sum + Math.min(value, 0) ** 2, 0) / dailyReturns.length
  );

  return downsideDeviation > 0 ? (meanReturn * Math.sqrt(KRX_TRADING_DAYS_PER_YEAR)) / downsideDeviation : 0;
}

function calculateTurnoverRate(trades: BacktestResult["tradesList"], equity: number[]): number {
  const validEquity = equity.filter((value) => Number.isFinite(value) && value > 0);
  if (validEquity.length === 0) return 0;

  const totalTradedAmount = trades.reduce((sum, trade) => {
    const reportedAmount = Math.abs(Number(trade.amount));
    const calculatedAmount = Math.abs(Number(trade.price) * Number(trade.quantity));
    const tradeAmount = Number.isFinite(reportedAmount) && reportedAmount > 0
      ? reportedAmount
      : calculatedAmount;

    return sum + (Number.isFinite(tradeAmount) ? tradeAmount : 0);
  }, 0);
  const averageAssets = validEquity.reduce((sum, value) => sum + value, 0) / validEquity.length;

  return averageAssets > 0 ? (totalTradedAmount / 2 / averageAssets) * 100 : 0;
}

function addOptimizationTarget(
  targets: WalkForwardOptimizationTarget[],
  seen: Set<string>,
  label: string
) {
  const normalized = label.trim();
  if (!normalized || seen.has(normalized)) return;
  seen.add(normalized);
  targets.push({ id: `summary-${targets.length}`, label: normalized });
}

function walkForwardTargetLabelsFromBadge(label: string): string[] {
  const normalized = label.trim();
  if (!normalized) return [];

  const targets: string[] = [];
  const add = (target: string) => {
    if (!targets.includes(target)) targets.push(target);
  };

  if (/pbr/i.test(normalized)) add("PBR");
  if (/per/i.test(normalized)) add("PER");
  if (/roe/i.test(normalized)) add("ROE");
  if (/손절|stop\s*loss/i.test(normalized)) add("손절라인");
  if (/익절|take\s*profit/i.test(normalized)) add("익절라인");
  if (/보유|holding/i.test(normalized)) add("보유기간");
  if (/종목|positions?/i.test(normalized)) add("보유종목수");
  if (/트레일링|trailing/i.test(normalized)) add("트레일링 스탑");
  if (/리밸런싱|rebalanc/i.test(normalized)) add("리밸런싱 주기");

  return targets.length > 0 ? targets : [normalized.replace(/\s*[<>=≤]+.*$/, "")];
}

function buildWalkForwardOptimizationTargetsFromSummary(
  strategySummary: BacktestDashboardProps["strategySummary"]
): WalkForwardOptimizationTarget[] {
  const targets: WalkForwardOptimizationTarget[] = [];
  const seen = new Set<string>();

  const entryLabels = strategySummary?.entryBlocks?.length
    ? strategySummary.entryBlocks
    : strategySummary?.blockNames ?? [];

  [
    ...entryLabels,
    ...(strategySummary?.exitBlocks ?? []),
    strategySummary?.positionText,
    strategySummary?.riskText,
  ].forEach((label) => {
    if (!label) return;
    walkForwardTargetLabelsFromBadge(label).forEach((targetLabel) => {
      addOptimizationTarget(targets, seen, targetLabel);
    });
  });

  return targets;
}

type ValidationTab = "chart" | "log" | "assets" | "report";

const VALIDATION_TABS: Array<{
  id: ValidationTab;
  label: string;
  help?: {
    title: string;
    body: string;
    example: string;
  };
}> = [
  { id: "chart", label: "개요" },
  { id: "assets", label: "종목 분석" },
  { id: "log", label: "매매 기록" },
  { id: "report", label: "AI 리포트" },
];

function ValidationTabHelp({ label, title, body, example }: {
  label: string;
  title: string;
  body: string;
  example: string;
}) {
  return (
    <span className="group relative z-20 mr-2 inline-flex">
      <button
        type="button"
        aria-label={t("{0} 탭 도움말", label)}
        className="flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-white/25 text-[10px] font-black leading-none text-gray-400 transition-colors hover:border-white/50 hover:text-white focus:border-white/60 focus:text-white focus:outline-none"
      >
        ?
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-50 mt-2 w-80 max-w-[calc(100vw-3rem)] -translate-x-1/2 border border-white/[0.10] bg-[#171717] p-4 text-left opacity-0 shadow-[0_18px_40px_rgba(0,0,0,0.45)] transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        <span className="block text-[11px] font-black uppercase tracking-widest text-sky-400">
          {title}
        </span>
        <span className="mt-2 block text-xs font-bold leading-5 text-gray-300">
          {body}
        </span>
        <span className="mt-3 block text-xs font-bold leading-5 text-gray-400">
          {example}
        </span>
      </span>
    </span>
  );
}

interface BacktestDashboardProps {
  result: BacktestResult;
  onRestart: () => void;
  onRun?: (options: BacktestConfigOptions) => void;
  onSave?: () => void;
  onWalkForward?: (settings: WalkForwardSettings) => Promise<any>;
  currentOptions?: BacktestConfigOptions;
  isRunning?: boolean;
  backtestDsl?: any; // 전략 저장 시 사용할 원본 DSL/요청 객체
  aiSummary?: string;
  aiScore?: number;
  aiStrengths?: string[];
  aiWeaknesses?: string[];
  aiImprovements?: string[];
  advisorScore?: number | null;
  riskScore?: number | null;
  overfitRisk?: string | null;
  disableHistorySave?: boolean; // true이면 히스토리 자동 저장 비활성화 (저장된 전략 조회 시)
  promptText?: string; // 사용자 프롬프트 (툴팁으로 표시)
  parsedStrategy?: Record<string, unknown>; // NLStrategyParser 결과 — AI 리포트 advisor 진단에 사용
  strategySummary?: {
    universeName: string;
    blockNames: string[];
    strategyName: string;
    entryLogic?: string;
    exitLogic?: string;
    entryBlocks?: string[];
    exitBlocks?: string[];
    positionText?: string;
    riskText?: string;
    rebalancingText?: string;
    backtestPeriodText?: string;
    initialCapitalText?: string;
  };
}

type BaseMetricDescriptions = {
  cagr: string;
  mdd: string;
  sharpe: string;
  sortino: string;
  profitFactor: string;
  totalReturn: string;
  buyHold: (label: string) => string;
  excessReturn: (label: string) => string;
  volatility: string;
  calmar: string;
  avgHoldingDays: string;
  exposure: string;
  turnover: string;
  maxDrawdownDuration: string;
  expectancy: string;
  recoveryFactor: string;
};

export function metricTooltip(definition: string, formula: string, guideline: string): string {
  return `${definition}\n\n${t("[ 공식 ]")}\n${formula}\n\n${guideline}`;
}

// 렌더 시점에 만든다 — 모듈 상수로 두면 t()가 프로세스 첫 언어로 고정된다(i18n 규칙).
function baseMetricDescriptions(): BaseMetricDescriptions {
  return {
  cagr: metricTooltip(t("연평균수익률(CAGR)은 전체 수익률을 연간 복리 성장률로 환산한 값입니다."), t("CAGR = ((최종 자산 / 초기 자본)^(1 / 기간(년)) - 1) × 100"), t("🟢 높음: 20% 이상\n🟡 중간: 10% ~ 20%\n🔴 낮음: 10% 미만")),
  mdd: metricTooltip(t("최대 낙폭(MDD)은 전고점 대비 가장 크게 하락한 비율입니다."), t("MDD = min((기간별 자산 / 이전 최고 자산 - 1) × 100)"), t("🟢 낮음: 10% 미만\n🟡 중간: 10% ~ 20%\n🔴 높음: 20% 초과")),
  sharpe: metricTooltip(t("샤프 지수는 전체 변동성 대비 초과 수익의 비율입니다."), t("Sharpe = (일별 초과수익 평균 / 일별 수익률 표준편차) × √246 (KRX 연 거래일)"), t("🟢 높음: 1.5 이상\n🟡 중간: 1.0 ~ 1.5\n🔴 낮음: 1.0 미만")),
  sortino: metricTooltip(t("소티노 지수는 목표 수익률(기본 0%)보다 낮은 수익률의 하방편차만 고려한 위험 대비 수익 지표입니다."), t("Sortino = (일별 초과수익 평균 / 하방편차) × √246 (KRX 연 거래일)"), t("🟢 높음: 2.0 이상\n🟡 중간: 1.0 ~ 2.0\n🔴 낮음: 1.0 미만")),
  profitFactor: metricTooltip(t("손익비는 총 이익을 총 손실로 나눈 값입니다."), t("손익비 = 총 이익 / |총 손실|"), t("🟢 높음: 2.0 이상\n🟡 중간: 1.5 ~ 2.0\n🔴 낮음: 1.5 미만")),
  totalReturn: metricTooltip(t("투자 수익률(ROI)은 백테스트 시작부터 종료까지의 누적 자산 변동 비율입니다."), t("ROI = ((최종 자산 - 초기 자본) / 초기 자본) × 100"), t("🟢 양수: 시작 자본보다 최종 자산이 큼\n🟡 0%: 시작 자본과 최종 자산이 같음\n🔴 음수: 시작 자본보다 최종 자산이 작음")),
  buyHold: (label: string) =>
    metricTooltip(t("벤치마크({0})를 백테스트 기간 동안 매수 후 보유했을 때의 수익률입니다.", label), t("벤치마크 수익률 = (({0} 최종 가격 / 시작 가격) - 1) × 100", label), t("🟢 양수: 벤치마크 지수가 상승\n🟡 0%: 벤치마크 지수의 변동이 없음\n🔴 음수: 벤치마크 지수가 하락")),
  excessReturn: (label: string) =>
    metricTooltip(
      t("전략 수익률과 벤치마크({0}) 매수 후 보유 수익률의 차이입니다. 과거 데이터 기준 사실 표시이며, 미래 성과를 뜻하지 않습니다.", label),
      t("초과수익률 = 전략 수익률(%) - 벤치마크 수익률(%)  → 단위는 %p(퍼센트 포인트)"),
      t("🟢 양수: 전략 수익률이 벤치마크보다 높았음\n🟡 0%p 부근: 벤치마크와 비슷했음\n🔴 음수: 전략 수익률이 벤치마크보다 낮았음\n\n※ 두 값이 모두 음수일 때 양수인 초과수익률은 '덜 하락했다'는 뜻이며 이익을 의미하지 않습니다."),
    ),
  volatility: metricTooltip(t("연간 변동성은 일별 수익률의 표준편차를 연간 단위로 환산한 값입니다."), t("변동성 = 일별 수익률 표준편차 × √246 × 100 (KRX 연 거래일)"), t("🟢 낮음: 15% 미만\n🟡 중간: 15% ~ 25%\n🔴 높음: 25% 초과")),
  calmar: metricTooltip(t("칼마 비율은 최대 낙폭 대비 연평균수익률의 비율입니다."), t("칼마 비율 = CAGR / |MDD|"), t("🟢 높음: 1.0 이상\n🟡 중간: 0.5 ~ 1.0\n🔴 낮음: 0.5 미만")),
  avgHoldingDays: metricTooltip(t("평균 보유일은 진입 후 청산까지의 평균 보유 거래일입니다."), t("평균 보유일 = 완료 거래의 총 보유일 / 완료 거래 수"), t("🟢 단기: 1 ~ 3일\n🟡 중기: 5 ~ 20일\n🔴 장기: 20일 초과")),
  exposure: metricTooltip(t("시장 노출도는 백테스트 기간 중 포지션을 하나라도 보유한 날의 비율입니다."), t("시장 노출도 = 포지션 보유일 수 / 전체 거래일 수 × 100"), t("🟢 낮음: 30% 미만\n🟡 중간: 30% ~ 70%\n🔴 높음: 70% 초과")),
  turnover: metricTooltip(t("회전율은 백테스트 기간 동안 평균 자산 대비 매매에 사용된 자산의 비율입니다."), t("회전율 = ((총 매수 체결금액 + 총 매도 체결금액) / 2) / 기간 평균 자산 × 100"), t("🟢 낮음: 50% 미만\n🟡 중간: 50% ~ 200%\n🔴 높음: 200% 초과")),
  maxDrawdownDuration: metricTooltip(t("최장 낙폭 기간은 전고점 아래에 머문 가장 긴 연속 거래일 수입니다."), t("최장 낙폭 기간 = 자산이 이전 최고 자산을 회복하지 못한 최대 연속 거래일 수"), t("🟢 짧음: 63거래일 이하\n🟡 중간: 64 ~ 252거래일\n🔴 김: 252거래일 초과")),
  expectancy: metricTooltip(t("기대값은 거래 1회당 평균 수익률입니다."), t("기대값 = 승률 × 평균 수익률 - 패률 × 평균 손실률"), t("🟢 양수: 과거 거래 평균이 이익\n🟡 0% 부근: 과거 거래 평균이 손익분기 근처\n🔴 음수: 과거 거래 평균이 손실")),
  recoveryFactor: metricTooltip(t("회복 계수는 최대 낙폭 금액 대비 순이익의 비율입니다."), t("회복 계수 = 순이익 / 최대 낙폭 금액"), t("🟢 높음: 3.0 이상\n🟡 중간: 1.0 ~ 3.0\n🔴 낮음: 1.0 미만"))
  };
}

function benchmarkLabelForResult(result: BacktestResult): string {
  // 엔진이 내려준 라벨이 정본이다 — 벤치마크는 universeId만이 아니라 보유 종목의
  // 실제 시장으로도 결정되므로(지정 종목·테마 유니버스는 universeId가 비어 있다),
  // universeId로 프론트가 다시 추정하면 백엔드와 어긋난다.
  if (result.benchmarkLabel) return result.benchmarkLabel;
  const universeId = result.universeId?.toLowerCase();
  if (universeId === "kospi") return t("KODEX 코스피 (226490)");
  if (universeId === "kosdaq") return "KODEX KOSDAQ 150 (229200)";
  return "KODEX 200 (069500)";
}

export default function BacktestDashboard({
  result,
  onRestart,
  onRun,
  onSave,
  onWalkForward,
  currentOptions,
  isRunning,
  backtestDsl,
  aiSummary: initialAiSummaryProp,
  aiScore: initialAiScoreProp,
  aiStrengths: initialAiStrengthsProp,
  aiWeaknesses: initialAiWeaknessesProp,
  aiImprovements: initialAiImprovementsProp,
  advisorScore: initialAdvisorScoreProp,
  riskScore: initialRiskScoreProp,
  overfitRisk: initialOverfitRiskProp,
  strategySummary,
  disableHistorySave,
  promptText,
  parsedStrategy,
}: BacktestDashboardProps) {
  // 백엔드 엔진 응답에는 finalEquity/initialCapital이 비어 있고 totalProfit/equity[]로만
  // 자산 규모가 전달되는 경우가 있다(저장된 기록 재조회 시 특히). equity 배열의 양끝값으로 보완한다.
  const resolvedInitialCapital = result.initialCapital || result.equity?.[0] || 0;
  const resolvedFinalEquity = result.finalEquity || result.equity?.[result.equity.length - 1] || 0;

  const router = useRouter();
  const [activeTab, setActiveTab] = useState<ValidationTab>("chart");
  const [isOptimizationPageOpen, setIsOptimizationPageOpen] = useState(false);
  const [promptTooltipOpen, setPromptTooltipOpen] = useState(false);
  const promptTooltipRef = useRef<HTMLDivElement>(null);
  const [planId, setPlanId] = useState<string>("FREE");
  const [isPlanLoading, setIsPlanLoading] = useState(true);
  // AI 리포트는 프로/프리미엄 전용 기능 — 무료 플랜은 탭 대신 플랜 변경 안내를 노출한다.
  const isAiReportEnabled = planId !== "FREE";

  const [localOptions, setLocalOptions] = useState<BacktestConfigOptions | null>(currentOptions || null);
  const [stockMetadata, setStockMetadata] = useState<Record<string, { name: string, sector: string }>>({});
  const [sortConfig, setSortConfig] = useState<{ key: 'profit' | 'totalReturn' | 'trades' | null, direction: 'asc' | 'desc' }>({ key: null, direction: 'desc' });
  const [hoveredMetric, setHoveredMetric] = useState<{ label: string, description: string, rect: DOMRect } | null>(null);

  const [xaiTarget, setXaiTarget] = useState<{ symbol: string; date: string } | null>(null);
  const lastProcessedResultRef = useRef<string | null>(null);
  const isSavingRef = useRef(false);
  // 백그라운드에서 진행 중인 AI 리포트 생성 요청. 저장 시 중복 요청 없이 이 약속을 재사용한다.
  const aiReportPromiseRef = useRef<Promise<AiReportData | null> | null>(null);

  // AI 요약 캐시 — prop 우선, 없으면 result 객체에서 (캐시 히트 응답에 포함된 경우).
  // 과거에 <think>/지시문 복창이 저장된 오염 레코드는 표시하지 않는다(→ 재생성 트리거).
  const initialAiSummaryRaw = initialAiSummaryProp ?? result.aiSummary ?? undefined;
  const initialAiSummary = hasAiReportArtifact(initialAiSummaryRaw) ? undefined : initialAiSummaryRaw;

  // 저장/캐시된 리포트를 단일 객체로 하이드레이트한다. summary+score 둘 다 있어야 유효.
  const buildReportFromResult = (): AiReportData | null => {
    const summary = hasAiReportArtifact(result.aiSummary) ? undefined : result.aiSummary ?? undefined;
    const score = result.aiScore ?? undefined;
    if (!summary || score == null) return null;
    return {
      summary,
      score,
      strengths: result.aiStrengths ?? [],
      weaknesses: result.aiWeaknesses ?? [],
      improvements: result.aiImprovements ?? [],
      advisorScore: result.advisorScore ?? null,
      riskScore: result.riskScore ?? null,
      overfitRisk: result.overfitRisk ?? null,
      topInsights: result.aiTopInsights ?? undefined,
      hiddenRisks: result.aiHiddenRisks ?? undefined,
      overfittingAnalysis: result.aiOverfittingAnalysis ?? undefined,
      strategyProfile: result.aiStrategyProfile ?? undefined,
      strategyProfileNote: result.aiStrategyProfileNote ?? undefined,
      validationRoadmap: result.aiValidationRoadmap ?? undefined,
      finalVerdict: result.aiFinalVerdict ?? undefined,
    };
  };

  const initialReport: AiReportData | null =
    initialAiSummary && (initialAiScoreProp ?? result.aiScore) != null
      ? {
          summary: initialAiSummary,
          score: (initialAiScoreProp ?? result.aiScore) as number,
          strengths: initialAiStrengthsProp ?? result.aiStrengths ?? [],
          weaknesses: initialAiWeaknessesProp ?? result.aiWeaknesses ?? [],
          improvements: initialAiImprovementsProp ?? result.aiImprovements ?? [],
          advisorScore: initialAdvisorScoreProp ?? result.advisorScore ?? null,
          riskScore: initialRiskScoreProp ?? result.riskScore ?? null,
          overfitRisk: initialOverfitRiskProp ?? result.overfitRisk ?? null,
          topInsights: result.aiTopInsights ?? undefined,
          hiddenRisks: result.aiHiddenRisks ?? undefined,
          overfittingAnalysis: result.aiOverfittingAnalysis ?? undefined,
          strategyProfile: result.aiStrategyProfile ?? undefined,
          strategyProfileNote: result.aiStrategyProfileNote ?? undefined,
          validationRoadmap: result.aiValidationRoadmap ?? undefined,
          finalVerdict: result.aiFinalVerdict ?? undefined,
        }
      : null;
  const [cachedReport, setCachedReport] = useState<AiReportData | null>(initialReport);

  // 전략 저장 모달
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [saveStrategyName, setSaveStrategyName] = useState("");
  const [saveDescription, setSaveDescription] = useState("");
  const [isSavingStrategy, setIsSavingStrategy] = useState(false);
  const [saveResult, setSaveResult] = useState<{ ok: boolean; message: string } | null>(null);

  // 결과 다운로드 모달 (Pro/Premium 전용)
  const [isDownloadModalOpen, setIsDownloadModalOpen] = useState(false);
  const [downloadingFormat, setDownloadingFormat] = useState<ExportFormat | null>(null);
  const [toast, setToast] = useState<{ type: "info" | "success" | "error"; message: string } | null>(null);
  const isDownloadEnabled = planId === "PRO" || planId === "PREMIUM";

  // 성공/실패 토스트는 잠시 후 자동으로 닫는다("준비 중" 안내는 다음 상태로 대체되므로 유지).
  useEffect(() => {
    if (!toast || toast.type === "info") return;
    const timer = setTimeout(() => setToast(null), 3200);
    return () => clearTimeout(timer);
  }, [toast]);
  const normalizedBacktestDsl = useMemo(
    () => (backtestDsl ? normalizeLegacyBreakoutStrategy(backtestDsl) : backtestDsl),
    [backtestDsl]
  );
  const walkForwardOptimizationTargets = useMemo(
    () => buildWalkForwardOptimizationTargetsFromSummary(strategySummary),
    [strategySummary]
  );


  // 백테스트 완료 시 자동으로 히스토리에 저장 (isAutoSave=true → 기존 이름 보존)
  useEffect(() => {
    if (!promptTooltipOpen) return;
    const handler = (e: MouseEvent) => {
      if (promptTooltipRef.current && !promptTooltipRef.current.contains(e.target as Node)) {
        setPromptTooltipOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [promptTooltipOpen]);

  useEffect(() => {
    let cancelled = false;

    const fetchPlan = async () => {
      try {
        const response = await fetch("/api/user/plan");
        const data = response.ok ? await response.json() : null;
        const nextPlanId =
          typeof data?.plan?.planId === "string" ? data.plan.planId.toUpperCase() : "FREE";
        if (!cancelled) {
          setPlanId(nextPlanId);
        }
      } catch {
        if (!cancelled) {
          setPlanId("FREE");
        }
      } finally {
        if (!cancelled) {
          setIsPlanLoading(false);
        }
      }
    };

    void fetchPlan();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (disableHistorySave) return;
    if (!strategySummary) return;
    if (processedExecutionIds.has(result.executionId)) return;
    processedExecutionIds.add(result.executionId);

    // 이 시점부터 기록 목록 캐시는 이 백테스트가 빠진 옛 목록이다 — 버린다.
    invalidateBacktestHistoryCache();
    fetch("/api/backtest/history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildAutoSaveHistoryPayload(result, strategySummary, promptText)),
    }).catch(() => {/* 자동 저장 실패는 무시 */});
  }, [result.executionId]);

  // AI 리포트 생성 요청 1회 수행 → 결과를 캐시 상태에 반영하고 반환. 실패 시 null.
  const generateAiReport = async (): Promise<AiReportData | null> => {
    try {
      const res = await fetch("/api/backtest/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cacheKey: result.cacheKey,
          metrics: buildAiReportMetrics(result),
          strategySummary,
          parsedStrategy,
          userPrompt: promptText,
        }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      // degraded = 백엔드가 LLM 출력 파싱에 실패한 폴백 — 캐시/PATCH하지 않고 실패로 처리해
      // '다시 생성'으로 재시도할 수 있게 한다.
      const report = reportFromSummaryResponse(data);
      if (!report) return null;
      setCachedReport(report);
      if (result.cacheKey) {
        fetch("/api/backtest/ai-report", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cacheKey: result.cacheKey, ...reportToPersistedFields(report) }),
        }).catch(() => {});
      }
      return report;
    } catch {
      return null;
    }
  };

  // 진행 중인 AI 리포트 생성을 재사용(없으면 새로 시작). 저장과 자동생성이 같은 요청을 공유한다.
  const ensureAiReport = (): Promise<AiReportData | null> => {
    if (!aiReportPromiseRef.current) {
      aiReportPromiseRef.current = generateAiReport().then((report) => {
        if (!report) aiReportPromiseRef.current = null; // 실패 시 재시도 허용
        return report;
      });
    }
    return aiReportPromiseRef.current;
  };

  // 백테스트 완료 시 AI 리포트를 백그라운드에서 즉시 생성 시작
  const aiReportExecutionIdRef = useRef(result.executionId);
  useEffect(() => {
    const isNewExecution = aiReportExecutionIdRef.current !== result.executionId;
    if (isNewExecution) {
      aiReportExecutionIdRef.current = result.executionId;
      aiReportPromiseRef.current = null; // 새 백테스트 → 이전 in-flight 요청 무효화
      // 같은 화면에서 재실행 — 이전 전략의 리포트가 새 결과에 남지 않도록 초기화
      setCachedReport(buildReportFromResult());
    }
    // 프로/프리미엄 전용 — 플랜 확인 전이거나 무료 플랜이면 백그라운드 생성을 하지 않는다.
    // (플랜은 비동기로 로드되므로 확인이 끝나면 이 이펙트가 다시 실행되어 생성을 시작한다.)
    if (isPlanLoading || !isAiReportEnabled) return;
    if (isNewExecution) {
      const usableSummary = result.aiSummary && !hasAiReportArtifact(result.aiSummary);
      if (!(usableSummary && result.aiScore != null)) ensureAiReport();
      return;
    }
    if (cachedReport) return; // 이미 캐시된 경우 스킵
    ensureAiReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result.executionId, isPlanLoading, isAiReportEnabled]);

  useEffect(() => {
    const fetchStockMetadata = async () => {
      try {
        const response = await fetch("/api/stocks/names");
        if (response.ok) {
          const data = await response.json();
          setStockMetadata(data);
        }
      } catch (error) {
        console.error("Failed to fetch stock metadata:", error);
      }
    };
    fetchStockMetadata();
  }, []);

  const formatKRW = (val: number) => {
    const num = Number(val);
    if (isNaN(num) || num === 0) return t("0원");
    return t("{0}원", Math.round(num).toLocaleString());
  };

  const calculateMonthlyReturns = () => {
    if (!result.dates || !result.equity || result.dates.length === 0) return {};
    
    const monthlyData: { [year: string]: { [month: string]: number } } = {};
    const monthEndEquity: { [key: string]: number } = {};
    
    result.dates.forEach((dateStr, i) => {
      // dateStr is expected to be "YYYY-MM-DD"
      const parts = dateStr.split('-');
      if (parts.length < 2) return;
      const year = parts[0];
      const month = parseInt(parts[1], 10).toString();
      const key = `${year}-${month}`;
      monthEndEquity[key] = result.equity[i];
    });
    
    const keys = Object.keys(monthEndEquity).sort((a, b) => {
      const [ya, ma] = a.split('-').map(Number);
      const [yb, mb] = b.split('-').map(Number);
      return ya !== yb ? ya - yb : ma - mb;
    });

    let prevEquity = resolvedInitialCapital;
    
    keys.forEach(key => {
      const [year, month] = key.split("-");
      const currentEquity = monthEndEquity[key];
      const monthlyReturn = ((currentEquity / prevEquity) - 1) * 100;
      
      if (!monthlyData[year]) monthlyData[year] = {};
      monthlyData[year][month] = monthlyReturn;
      
      prevEquity = currentEquity;
    });
    
    return monthlyData;
  };

  const monthlyReturns = calculateMonthlyReturns();
  const monthlyReturnRows = useMemo(
    () => buildMonthlyReturnTableData(monthlyReturns),
    [monthlyReturns]
  );

  const [returnsView, setReturnsView] = useState<"monthly" | "rolling" | "rebalance">("monthly");
  // 롤링 수익률 표 — 탭이 열렸을 때만 계산한다(투자 기간 7개 × 매 거래일 창 MDD).
  const rollingWindowRows = useMemo(
    () =>
      returnsView === "rolling"
        ? buildRollingWindowStatsTable(result.dates ?? [], result.equity ?? [], ROLLING_WINDOW_OPTIONS)
        : [],
    [returnsView, result.dates, result.equity]
  );
  // 표 위 라인 차트 — 선택한 투자 기간의 매 거래일 롤링 수익률(전체 구간). 표에 행이 있는 기간만 선택 가능.
  const [rollingWindowMonths, setRollingWindowMonths] = useState(12);
  const availableRollingWindows = rollingWindowRows.map((r) => r.windowMonths);
  const effectiveRollingWindow = availableRollingWindows.includes(rollingWindowMonths)
    ? rollingWindowMonths
    : availableRollingWindows[availableRollingWindows.length - 1] ?? null;
  const rollingReturnSeries = useMemo(
    () =>
      effectiveRollingWindow == null
        ? []
        : buildRollingReturnSeries(result.dates ?? [], result.equity ?? [], effectiveRollingWindow),
    [result.dates, result.equity, effectiveRollingWindow]
  );

  const sortedSymbols = useMemo(() => {
    if (!result.symbols) return [];
    
    // 1. Filter out symbols with 0 trades
    let symbols = result.symbols.filter(sym => {
      const stats = result.perAssetStats?.[sym];
      return stats && stats.trades > 0;
    });

    if (!sortConfig.key) return symbols;

    // 2. Sort remaining symbols
    return symbols.sort((a, b) => {
      const key = sortConfig.key;
      if (!key) return 0;
      
      const statsA = result.perAssetStats?.[a];
      const statsB = result.perAssetStats?.[b];
      
      const valA = statsA ? (statsA[key as keyof typeof statsA] as number || 0) : 0;
      const valB = statsB ? (statsB[key as keyof typeof statsB] as number || 0) : 0;

      if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
      if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [result.symbols, result.perAssetStats, sortConfig]);

  // 종목별 평균 매수가/매도가 — tradesList(개별 체결)에서 매수·매도 체결가의 산술평균을 계산한다.
  const symbolTradePrices = useMemo(() => {
    const acc: Record<string, { entrySum: number; entryCount: number; exitSum: number; exitCount: number }> = {};
    for (const tv of result.tradesList ?? []) {
      const bucket = acc[tv.symbol] ?? (acc[tv.symbol] = { entrySum: 0, entryCount: 0, exitSum: 0, exitCount: 0 });
      if (tv.type === "buy") {
        bucket.entrySum += tv.price;
        bucket.entryCount += 1;
      } else if (tv.type === "sell") {
        bucket.exitSum += tv.price;
        bucket.exitCount += 1;
      }
    }
    const out: Record<string, { entryPrice: number | null; exitPrice: number | null }> = {};
    for (const [sym, b] of Object.entries(acc)) {
      out[sym] = {
        entryPrice: b.entryCount > 0 ? b.entrySum / b.entryCount : null,
        exitPrice: b.exitCount > 0 ? b.exitSum / b.exitCount : null,
      };
    }
    return out;
  }, [result.tradesList]);

  const handleSort = (key: 'profit' | 'totalReturn' | 'trades') => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  const SortIcon = ({ column }: { column: 'profit' | 'totalReturn' | 'trades' }) => {
    const isActive = sortConfig.key === column;
    const Icon = sortConfig.direction === 'asc' ? CaretUp : CaretDown;
    
    return (
      <div className={`w-3.5 h-3.5 transition-opacity ${isActive ? 'opacity-100 text-white' : 'opacity-0 group-hover:opacity-40 text-gray-400'}`}>
        <Icon className="w-3.5 h-3.5" />
      </div>
    );
  };
  useEffect(() => {
    if (currentOptions) setLocalOptions(currentOptions);
  }, [currentOptions]);

  const isPremiumValidationEnabled = planId === "PREMIUM";

  const handleOpenSaveModal = () => {
    setSaveStrategyName("");
    setSaveDescription(promptText || strategySummary?.strategyName || "");
    setSaveResult(null);
    setIsSaveModalOpen(true);
  };

  const handleSaveStrategy = async () => {
    if (!saveStrategyName.trim()) return;
    setIsSavingStrategy(true);
    setSaveResult(null);
    try {
      // AI 요약이 아직 없으면 저장 전에 먼저 생성
      let finalReport = cachedReport;
      if (!finalReport?.summary && isAiReportEnabled) {
        // 백그라운드 생성이 진행 중이면 그 요청을 그대로 기다리고, 없으면 새로 시작한다.
        // (이미 완료됐다면 즉시 반환되어 바로 저장된다. 무료 플랜은 AI 리포트 없이 저장한다.)
        finalReport = await ensureAiReport();
      }
      const persistedReport = finalReport ? reportToPersistedFields(finalReport) : {};

      const res = await fetch("/api/strategy/save-with-backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: saveStrategyName.trim(),
          description: saveDescription.trim(),
          dsl: normalizedBacktestDsl ?? {},
          backtestResult: result,
          ...persistedReport,
          score: calculateScore(result),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || t("저장 실패"));

      // 저장 버튼을 누른 시점에 BacktestHistory 생성 (저장 목록에 노출)
      if (strategySummary) {
        // 목록이 바뀐다 — 옛 목록 캐시를 버려 다음 진입이 서버에서 새로 받게 한다.
        invalidateBacktestHistoryCache();
        fetch("/api/backtest/history", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            strategyName: saveStrategyName.trim() || strategySummary.strategyName || t("이름 없는 전략"),
            prompt: promptText?.trim() || undefined,
            universe: strategySummary.universeName,
            conditions: buildHistoryConditions(strategySummary),
            metrics: {
              totalReturn: result.totalReturn || 0,
              cagr: result.cagr || 0,
              mdd: result.maxDrawdown || 0,
              winRate: result.winRate || 0,
              profitFactor: result.profitFactor ?? null,
              buyHold: result.buyAndHoldReturn || 0,
              trades: result.trades || 0,
              executionTime: result.executionTime ?? 0,
              score: calculateScore(result),
              perAssetStats: result.perAssetStats || {},
              ...persistedReport,
            },
            result,
            // result.cacheKey 가 없으면 save-with-backtest 가 strategy.id(=data.strategyId)를
            // cacheKey 로 써서 행을 만든다. 동일 fallback 을 써야 그 행을 찾아 표시용 배지
            // conditions 로 갱신한다(미일치 시 배지 없는 중복 카드가 생성됨).
            cacheKey: result.cacheKey ?? data.strategyId,  // 기존 숨김/raw DSL 레코드를 표시용으로 승격
          }),
        }).catch(() => {/* 히스토리 저장 실패는 무시 */});
      }

      setSaveResult({ ok: true, message: t("전략이 저장되었습니다.") });
      onSave?.();
      setTimeout(() => setIsSaveModalOpen(false), 1200);
    } catch (e: any) {
      setSaveResult({ ok: false, message: e.message || t("저장 중 오류가 발생했습니다.") });
    } finally {
      setIsSavingStrategy(false);
    }
  };

  const dateRangeLabel = result.dates[0] && result.dates[result.dates.length - 1]
    ? `${result.dates[0]} → ${result.dates[result.dates.length - 1]}`
    : "";
  const totalProfit = result.totalProfit ?? (resolvedFinalEquity - resolvedInitialCapital);
  const investmentRoi = resolvedInitialCapital > 0
    ? ((resolvedFinalEquity - resolvedInitialCapital) / resolvedInitialCapital) * 100
    : result.totalReturn || 0;
  const reportedVolatility = Number(result.volatility);
  const annualizedVolatility = Number.isFinite(reportedVolatility)
    ? reportedVolatility
    : calculateAnnualizedVolatility(result.equity ?? []);
  const reportedSortino = Number(result.sortino);
  const sortinoRatio = Number.isFinite(reportedSortino)
    ? reportedSortino
    : calculateSortinoRatio(result.equity ?? []);
  const turnoverRate = calculateTurnoverRate(result.tradesList ?? [], result.equity ?? []);
  const benchmarkLabel = benchmarkLabelForResult(result);
  // 초과수익률 = 전략 총수익률 - 벤치마크 총수익률 (단위 %p). 벤치마크가 백테스트
  // 구간의 일부만 덮으면(지수 ETF 상장 이전 포함) 두 수익률의 기간이 달라 차이가
  // 비교값이 되지 못하므로 숫자를 내지 않는다 — 경고 문구로만 사실을 알린다.
  const excessReturn = result.benchmarkPartial
    ? null
    : Number(result.totalReturn) - Number(result.buyAndHoldReturn ?? 0);
  const modalPromptPreview = saveDescription.trim() || promptText?.trim() || "";
  const modalUniverseLabel = strategySummary
    ? resolveUniverseDisplayName(strategySummary.universeName, modalPromptPreview)
    : null;

  // "프롬프트" 팝오버의 전략 요약 행 — 라벨 하나에 값 여러 개를 세로로 쌓는 구조라
  // 렌더 쪽에서 조건 분기를 반복하지 않도록 행 목록으로 만든다(promptSummaryRows.ts).
  const promptSummaryRows = buildPromptSummaryRows(strategySummary, promptText, result.dates);

  const downloadStrategyName =
    strategySummary?.strategyName?.trim() || promptText?.trim() || t("백테스트 전략");
  const downloadPeriodLabel =
    result.dates[0] && result.dates[result.dates.length - 1]
      ? `${result.dates[0]} ~ ${result.dates[result.dates.length - 1]}`
      : "";

  // 화면에 표시되는 데이터(현재 정렬/필터 반영)를 그대로 내보내기 payload로 변환한다.
  // 전략명은 metadata에만 한 번 포함하고 각 행에는 넣지 않는다.
  // section: 종목 분석 탭에서 받으면 stockAnalysis만, 매매 기록 탭에서 받으면 tradeHistory만 채운다.
  const buildExportPayload = (section: "assets" | "log"): BacktestExportPayload => {
    // KST(+09:00) ISO 문자열 생성 — 파일명 날짜와 metadata 생성시간에 사용
    const kst = new Date(Date.now() + 9 * 60 * 60 * 1000);
    const exportedAt = `${kst.toISOString().slice(0, 19)}+09:00`;
    const universeLabel =
      (strategySummary && resolveUniverseDisplayName(strategySummary.universeName, promptText)) ||
      result.universeId?.toUpperCase() ||
      strategySummary?.universeName ||
      "-";
    // 전략 배지 — 결과 화면 상단 "프롬프트" 팝오버와 동일한 조건 요약을 metadata에 함께 담는다.
    const entrySignals = strategySummary?.entryBlocks?.length
      ? strategySummary.entryBlocks
      : strategySummary?.blockNames;

    return {
      metadata: {
        strategyName: downloadStrategyName,
        backtestId: result.cacheKey ?? result.executionId,
        exportedAt,
        period: {
          from: result.dates[0] ?? "",
          to: result.dates[result.dates.length - 1] ?? "",
        },
        universe: universeLabel,
        initialCapital: resolvedInitialCapital,
        finalEquity: resolvedFinalEquity,
        commission:
          localOptions?.commissionPct != null ? localOptions.commissionPct / 100 : undefined,
        slippage:
          localOptions?.slippagePct != null ? localOptions.slippagePct / 100 : undefined,
        benchmark: benchmarkLabel,
        entrySignals: entrySignals?.length ? entrySignals : undefined,
        exitSignals: strategySummary?.exitBlocks?.length ? strategySummary.exitBlocks : undefined,
        position: strategySummary?.positionText || undefined,
        rebalancing: strategySummary?.rebalancingText || undefined,
        risk: strategySummary?.riskText || undefined,
      },
      // 종목 분석 — sortedSymbols 는 이미 매매 0건 제외 + 현재 정렬 상태를 반영한다.
      // perAssetStats 의 winRate/totalReturn 은 퍼센트(%)라 소수로 환산한다.
      stockAnalysis:
        section === "assets"
          ? sortedSymbols.map((sym) => {
              const stats = result.perAssetStats?.[sym];
              const prices = symbolTradePrices[sym];
              return {
                symbol: sym,
                name: stockMetadata[sym]?.name || sym,
                tradeCount: stats?.trades ?? 0,
                winRate: (stats?.winRate ?? 0) / 100,
                totalReturn: (stats?.totalReturn ?? 0) / 100,
                totalProfit: stats?.profit ?? 0,
                avgBuyPrice: prices?.entryPrice ?? null,
                avgSellPrice: prices?.exitPrice ?? null,
              };
            })
          : undefined,
      // 매매 기록 — 화면과 동일하게 tradesList(개별 체결 이벤트) 순서를 유지한다.
      tradeHistory:
        section === "log"
          ? (result.tradesList ?? []).map((tv) => ({
              date: tv.date,
              symbol: tv.symbol,
              name: stockMetadata[tv.symbol]?.name || tv.symbol,
              type: tv.type,
              price: Number(tv.price) || 0,
              quantity: Number(tv.quantity) || 0,
              amount: tv.amount || 0,
              reason: resolveTradeReason(tv.reason, tv.type, normalizedBacktestDsl) ?? tv.reason ?? "",
            }))
          : undefined,
    };
  };

  const handleOpenDownloadModal = () => {
    setToast(null);
    setIsDownloadModalOpen(true);
  };

  const handleExportAction = (format: ExportFormat, section: "assets" | "log") => {
    if (!isDownloadEnabled) {
      handleOpenDownloadModal();
      return;
    }
    void handleDownload(format, section);
  };

  const handleDownload = async (format: ExportFormat, section: "assets" | "log") => {
    setDownloadingFormat(format);
    setToast({ type: "info", message: t("다운로드를 준비하고 있어요.") });
    try {
      const payload = buildExportPayload(section);
      const res = await fetch("/api/backtest/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format, payload }),
      });
      if (!res.ok) throw new Error("download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = exportFileName(payload, format);
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setToast({ type: "success", message: t("결과 파일 다운로드가 완료되었습니다.") });
      setIsDownloadModalOpen(false);
    } catch {
      setToast({ type: "error", message: t("다운로드에 실패했습니다. 잠시 후 다시 시도해주세요.") });
    } finally {
      setDownloadingFormat(null);
    }
  };

  const BASE_METRIC_DESCRIPTIONS = baseMetricDescriptions();
  const overviewMetrics = [
    {
      label: t("총 수익"),
      englishLabel: "Total Profit",
      value: formatKRW(totalProfit),
      valueClass: totalProfit > 0 ? "text-[var(--main-red)]" : totalProfit < 0 ? "text-[var(--main-blue)]" : "text-white",
      description: metricTooltip(t("총 수익은 백테스트 종료 시점의 순손익입니다."), t("총 수익 = 최종 자산 - 초기 자본"), t("🟢 양수: 순이익\n🟡 0원: 손익 없음\n🔴 음수: 순손실")),
    },
    {
      label: t("총 거래 수"),
      englishLabel: "Trades",
      value: t("{0}회", result.trades || 0),
      valueClass: "text-[#FF9933]",
      description: metricTooltip(t("총 거래 수는 백테스트에서 완료된 거래의 집계 건수입니다."), t("총 거래 수 = 백테스트 기간의 완료 거래 건수"), t("🔴 30건 미만: 표본 수가 적어 해석에 주의\n🟡 30 ~ 99건: 중간 표본\n🟢 100건 이상: 상대적으로 큰 표본")),
    },
    {
      label: t("연평균수익률"),
      englishLabel: "CAGR",
      value: `${result.cagr.toFixed(2)}%`,
      valueClass: result.cagr > 0 ? "text-[var(--main-red)]" : result.cagr < 0 ? "text-[var(--main-blue)]" : "text-white",
      description: BASE_METRIC_DESCRIPTIONS.cagr,
    },
    {
      label: t("최대낙폭"),
      englishLabel: "MDD",
      value: `${result.maxDrawdown.toFixed(2)}%`,
      valueClass: "text-[var(--main-blue)]",
      description: BASE_METRIC_DESCRIPTIONS.mdd,
    },
    {
      label: t("투자 수익률"),
      englishLabel: "ROI",
      value: `${investmentRoi >= 0 ? "+" : ""}${investmentRoi.toFixed(2)}%`,
      valueClass: investmentRoi > 0 ? "text-[var(--main-red)]" : investmentRoi < 0 ? "text-[var(--main-blue)]" : "text-white",
      description: BASE_METRIC_DESCRIPTIONS.totalReturn,
    },
    {
      label: t("샤프 비율"),
      englishLabel: "Sharpe",
      value: result.sharpe.toFixed(2),
      valueClass: result.sharpe > 0 ? "text-[var(--main-red)]" : result.sharpe < 0 ? "text-[var(--main-blue)]" : "text-white",
      description: BASE_METRIC_DESCRIPTIONS.sharpe,
    },
    {
      label: t("소티노 지수"),
      englishLabel: "Sortino",
      value: sortinoRatio.toFixed(2),
      valueClass: sortinoRatio > 0 ? "text-[var(--main-red)]" : sortinoRatio < 0 ? "text-[var(--main-blue)]" : "text-white",
      description: BASE_METRIC_DESCRIPTIONS.sortino,
    },
    {
      label: t("벤치마크"),
      englishLabel: benchmarkLabel.replace(/\s*\(\d+\)$/, ""),
      value: `${(result.buyAndHoldReturn || 0) >= 0 ? "+" : ""}${(result.buyAndHoldReturn || 0).toFixed(2)}%`,
      valueClass: (result.buyAndHoldReturn || 0) > 0 ? "text-[var(--main-red)]" : (result.buyAndHoldReturn || 0) < 0 ? "text-[var(--main-blue)]" : "text-white",
      description: BASE_METRIC_DESCRIPTIONS.buyHold(benchmarkLabel),
    },
    {
      label: t("승률"),
      englishLabel: "Win Rate",
      value: `${(result.winRate || 0).toFixed(1)}%`,
      valueClass: (result.winRate || 0) > 0 ? "text-[var(--main-red)]" : "text-white",
      description: metricTooltip(t("승률은 완료 거래 중 수익으로 끝난 거래의 비율입니다."), t("승률 = 수익 거래 수 / 완료 거래 수 × 100"), t("🟢 높음: 60% 이상\n🟡 중간: 40% ~ 60%\n🔴 낮음: 40% 미만\n승률은 평균 수익·손실과 함께 해석")),
    },
    {
      label: t("손익비"),
      englishLabel: "Profit Factor",
      value: formatProfitFactor(result.profitFactor),
      valueClass: (result.profitFactor ?? Infinity) > 1 ? "text-[var(--main-red)]" : (result.profitFactor ?? Infinity) < 1 ? "text-[var(--main-blue)]" : "text-white",
      description: BASE_METRIC_DESCRIPTIONS.profitFactor,
    },
  ];

  // 벤치마크 지수가 존재하지 않는 구간은 null로 내려온다(엔진 v11.0). undefined로
  // 바꿔야 차트가 그 지점을 건너뛴다 — null을 그대로 넘기면 isFinite(null)이 true라
  // 0원으로 그려져 가짜 폭락 구간이 생긴다.
  const equityCurveData = result.dates.map((d: string, i: number) => ({
    time: d,
    equity: result.equity[i],
    buyHold: result.benchmarkEquity?.[i] ?? undefined,
  }));
  const hasBenchmarkCurve = equityCurveData.some((p) => p.buyHold !== undefined);

  return (
    <div
      className="flex flex-1 flex-col min-w-0 animate-in fade-in zoom-in-95 duration-300"
      style={{ minHeight: "calc(100vh - var(--top-menu-bar-height, 76px))" }}
    >

      {/* 전략 저장 모달 */}
      <AnimatePresence>
        {isSaveModalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            data-testid="backtest-save-modal-backdrop"
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-2 backdrop-blur-sm lg:p-0"
            onClick={(e) => { if (e.target === e.currentTarget) setIsSaveModalOpen(false); }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 8 }}
              transition={{ type: "spring", bounce: 0.2, duration: 0.35 }}
              data-testid="backtest-save-modal-panel"
              className="max-h-[calc(100dvh-1rem)] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-[#111111] p-4 shadow-2xl lg:mx-4 lg:max-h-none lg:overflow-visible lg:p-6"
            >
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-2.5">
                  <FloppyDisk size={18} className="text-gray-300" weight="fill" />
                  <h3 className="text-base font-black text-white">{t("전략 저장")}</h3>
                </div>
                <button
                  onClick={() => setIsSaveModalOpen(false)}
                  className="p-1.5 rounded-lg hover:bg-white/10 text-gray-500 hover:text-white transition-colors"
                >
                  <X size={16} />
                </button>
              </div>

              {/* 저장될 주요 지표 미리보기 */}
              <div
                data-testid="backtest-save-modal-metrics"
                className="mb-5 grid grid-cols-2 gap-3 rounded-xl border border-white/5 bg-white/[0.03] p-4 sm:grid-cols-3"
              >
                <div className="text-center">
                  <p className="text-xs text-gray-500 mb-1">{t("총 수익률")}</p>
                  <p className={`text-xl font-black ${metricValueColor(result.totalReturn)}`}>
                    {result.totalReturn >= 0 ? "+" : ""}{result.totalReturn.toFixed(1)}%
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-gray-500 mb-1">CAGR</p>
                  <p className={`text-xl font-black ${metricValueColor(result.cagr)}`}>
                    {result.cagr >= 0 ? "+" : ""}{result.cagr.toFixed(1)}%
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-gray-500 mb-1">MDD</p>
                  <p className={`text-xl font-black ${metricValueColor(result.maxDrawdown)}`}>{result.maxDrawdown.toFixed(1)}%</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-gray-500 mb-1">{t("점수")}</p>
                  <p className="text-xl font-black text-white">{calculateScore(result)}</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-gray-500 mb-1">{t("거래 수")}</p>
                  <p className="text-xl font-black text-white">{t("{0}건", result.trades)}</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-gray-500 mb-1">{t("종목 수")}</p>
                  <p className="text-xl font-black text-white">{t("{0}개", result.symbols?.length ?? 0)}</p>
                </div>
              </div>

              {(modalPromptPreview || strategySummary) && (
                <div className="mb-5 space-y-3 rounded-xl border border-white/5 bg-white/[0.03] p-4">
                  {modalPromptPreview && (
                    <div className="space-y-1.5">
                      <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-gray-600">
                        {t("프롬프트")}
                      </p>
                      <p className="whitespace-pre-wrap text-sm font-bold leading-6 text-white">
                        {modalPromptPreview}
                      </p>
                    </div>
                  )}

                  {strategySummary && (
                    <div className="space-y-2.5">
                      {modalUniverseLabel && (
                        <div className="flex flex-wrap items-start gap-2">
                          <span className="w-16 flex-shrink-0 pt-1 text-[10px] font-bold uppercase tracking-widest text-gray-600">
                            {t("유니버스")}
                          </span>
                          <div className="flex flex-1 flex-wrap gap-1">
                            <span className="inline-flex items-center rounded-md border border-white/[0.08] bg-white/[0.05] px-2 py-0.5 text-[11px] font-black text-white">
                              {modalUniverseLabel}
                            </span>
                          </div>
                        </div>
                      )}

                      {(strategySummary.entryBlocks?.length || strategySummary.blockNames?.length) && (
                        <div className="flex flex-wrap items-start gap-2">
                          <span className="w-16 flex-shrink-0 pt-1 text-[10px] font-bold uppercase tracking-widest text-gray-600">
                            {t("진입 신호")}
                          </span>
                          <div className="flex flex-1 flex-wrap gap-1">
                            {(strategySummary.entryBlocks?.length
                              ? strategySummary.entryBlocks
                              : strategySummary.blockNames
                            )!.map((name) => (
                              <span
                                key={`save-entry-${name}`}
                                className="inline-flex items-center rounded-md border border-white/[0.08] bg-white/[0.05] px-2 py-0.5 text-[11px] font-black text-white"
                              >
                                {name}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {strategySummary.exitBlocks?.length ? (
                        <div className="flex flex-wrap items-start gap-2">
                          <span className="w-16 flex-shrink-0 pt-1 text-[10px] font-bold uppercase tracking-widest text-gray-600">
                            {t("청산 신호")}
                          </span>
                          <div className="flex flex-1 flex-wrap gap-1">
                            {strategySummary.exitBlocks.map((name) => (
                              <span
                                key={`save-exit-${name}`}
                                className="inline-flex items-center rounded-md border border-white/[0.08] bg-white/[0.05] px-2 py-0.5 text-[11px] font-black text-white"
                              >
                                {name}
                              </span>
                            ))}
                          </div>
                        </div>
                      ) : null}

                      {(strategySummary.positionText || strategySummary.riskText || strategySummary.rebalancingText) && (
                        <div className="flex flex-wrap items-start gap-2">
                          <span className="w-16 flex-shrink-0 pt-1 text-[10px] font-bold uppercase tracking-widest text-gray-600">
                            {t("리스크")}
                          </span>
                          <div className="flex flex-1 flex-wrap gap-1">
                            {strategySummary.positionText && (
                              <span className="inline-flex items-center rounded-md border border-white/[0.08] bg-white/[0.05] px-2 py-0.5 text-[11px] font-black text-white">
                                {strategySummary.positionText}
                              </span>
                            )}
                            {strategySummary.rebalancingText && (
                              <span className="inline-flex items-center rounded-md border border-white/[0.08] bg-white/[0.05] px-2 py-0.5 text-[11px] font-black text-white">
                                {strategySummary.rebalancingText}
                              </span>
                            )}
                            {strategySummary.riskText && (
                              <span className="inline-flex items-center rounded-md border border-white/[0.08] bg-white/[0.05] px-2 py-0.5 text-[11px] font-black text-white">
                                {strategySummary.riskText}
                              </span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              <div className="space-y-3 mb-5">
                <div>
                  <label className="block text-xs font-bold text-gray-400 mb-1.5">{t("전략 이름 *")}</label>
                  <input
                    type="text"
                    value={saveStrategyName}
                    onChange={(e) => setSaveStrategyName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && saveStrategyName.trim()) handleSaveStrategy(); }}
                    placeholder={t("전략 이름을 입력하세요")}
                    maxLength={50}
                    className="w-full px-3 py-2.5 bg-[#1a1a1a] border border-white/10 rounded-xl text-sm text-white placeholder-gray-600 focus:outline-none focus:border-white/20 transition-colors"
                    autoFocus
                  />
                </div>
              </div>

              {saveResult && (
                <div className={`mb-4 px-3 py-2.5 rounded-xl text-xs font-bold flex items-center gap-2 ${
                  saveResult.ok
                    ? "text-green-400"
                    : "text-red-400 border border-red-500/20"
                }`}>
                  {saveResult.ok ? <Check size={14} weight="bold" /> : <Warning size={14} weight="fill" />}
                  {saveResult.message}
                </div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => setIsSaveModalOpen(false)}
                  className="flex-1 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white text-sm font-bold transition-colors"
                >
                  {t("취소")}
                </button>
                <button
                  onClick={handleSaveStrategy}
                  disabled={!saveStrategyName.trim() || isSavingStrategy || saveResult?.ok === true}
                  className="flex-1 py-2.5 rounded-xl bg-[var(--main-blue)] text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-bold transition-colors flex items-center justify-center gap-2"
                >
                  {isSavingStrategy ? (
                    <>
                      <Spinner size={14} className="animate-spin" />
                      {!cachedReport ? t("AI 리포트 생성 중...") : t("저장 중...")}
                    </>
                  ) : (
                    <>
                      <FloppyDisk size={14} />
                      {t("저장")}
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 결과 다운로드 모달 — Pro/Premium: 형식 선택 / Free: 업그레이드 안내 */}
      <AnimatePresence>
        {isDownloadModalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={(e) => { if (e.target === e.currentTarget && !downloadingFormat) setIsDownloadModalOpen(false); }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 8 }}
              transition={{ type: "spring", bounce: 0.2, duration: 0.35 }}
              className="bg-[#111111] border border-white/10 rounded-2xl p-6 w-full max-w-md mx-4 shadow-2xl"
              role="dialog"
              aria-modal="true"
            >
              <div className="mb-5">
                <h3 className="text-base font-black text-white">
                  {isDownloadEnabled ? t("백테스트 결과 익스포트") : t("백테스트 결과 익스포트는 Pro 플랜 이상에서 사용할 수 있어요")}
                </h3>
              </div>

              <div className="mb-5 space-y-1.5 rounded-xl border border-white/5 bg-white/[0.03] p-4">
                <div className="flex gap-2 text-sm">
                  <span className="w-14 flex-shrink-0 pt-0.5 text-[11px] font-bold uppercase tracking-widest text-gray-600">{t("전략명")}</span>
                  <span className="font-bold text-white">{downloadStrategyName}</span>
                </div>
                {downloadPeriodLabel && (
                  <div className="flex gap-2 text-sm">
                    <span className="w-14 flex-shrink-0 pt-0.5 text-[11px] font-bold uppercase tracking-widest text-gray-600">{t("기간")}</span>
                    <span className="font-mono font-bold text-gray-300">{downloadPeriodLabel}</span>
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <a
                  href="/pricing"
                  className="flex-1 py-2.5 rounded-xl bg-[var(--main-blue)] text-white hover:opacity-90 text-sm font-bold transition-colors text-center"
                >
                  {t("요금제 보기")}
                </a>
                <button
                  type="button"
                  onClick={() => setIsDownloadModalOpen(false)}
                  className="flex-1 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white text-sm font-bold transition-colors"
                >
                  {t("닫기")}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 다운로드 상태 토스트 */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            className="fixed bottom-6 left-1/2 z-[1100] -translate-x-1/2"
          >
            <div
              className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-bold shadow-2xl backdrop-blur-sm ${
                toast.type === "success"
                  ? "border-green-500/20 bg-[#0f1a12] text-green-300"
                  : toast.type === "error"
                    ? "border-red-500/20 bg-[#1a0f0f] text-red-300"
                    : "border-white/10 bg-[#151515] text-gray-200"
              }`}
              role="status"
            >
              {toast.type === "success" ? (
                <Check size={15} weight="bold" />
              ) : toast.type === "error" ? (
                <Warning size={15} weight="fill" />
              ) : (
                <Spinner size={15} className="animate-spin" />
              )}
              {toast.message}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="relative flex flex-col gap-1 px-4 pt-8 pb-4 sm:px-6">
        <h2 className="text-3xl font-black text-white tracking-tight">
          {t("백테스트 결과")}
        </h2>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-sm font-mono text-gray-500 font-normal">
            {result.dates[0] && result.dates[result.dates.length-1] && `${result.dates[0]} ~ ${result.dates[result.dates.length-1]}`}
          </span>
        </div>

        <div
          data-testid="backtest-result-toolbar"
          className="flex w-full flex-col items-stretch gap-3 lg:flex-row lg:items-center lg:justify-between lg:gap-0"
        >
          <div className="flex w-full flex-wrap items-center gap-1.5 md:gap-2 lg:w-fit">
            {VALIDATION_TABS.map(tab => (
              <div
                key={tab.id}
                className={`relative flex min-h-[34px] items-center overflow-visible rounded-[8px] transition-colors ${
                  !isOptimizationPageOpen && activeTab === tab.id
                    ? "text-white"
                    : "text-[#6f7481] hover:text-[#a7adba]"
                }`}
              >
                {!isOptimizationPageOpen && activeTab === tab.id && (
                  <motion.div
                    layoutId="active-tab-backtest"
                    className="absolute inset-0 rounded-[8px] bg-[#232323] z-0"
                    transition={{ type: "tween", ease: [0.22, 1, 0.36, 1], duration: 0.22 }}
                  />
                )}
                <button
                  type="button"
                  onClick={() => {
                    setActiveTab(tab.id);
                    setIsOptimizationPageOpen(false);
                  }}
                  className="relative z-10 min-h-[34px] px-3.5 text-sm font-black tracking-tight md:px-4"
                >
                  {t(tab.label)}
                </button>
                {tab.help && (
                  <ValidationTabHelp
                    label={t(tab.label)}
                    title={t(tab.help.title)}
                    body={t(tab.help.body)}
                    example={t(tab.help.example)}
                  />
                )}
              </div>
            ))}
          </div>

          <div
            data-testid="backtest-result-actions"
            className="flex w-full flex-wrap items-center gap-2 lg:w-auto lg:flex-nowrap"
          >
            <button
              type="button"
              onClick={() => setIsOptimizationPageOpen((open) => !open)}
              className={`px-4 py-1.5 text-sm font-bold rounded-lg transition-all border flex items-center gap-2 active:scale-95 ${
                isOptimizationPageOpen
                  ? "bg-white/10 text-white border-white/20"
                  : "bg-white/[0.05] hover:bg-white/10 text-gray-300 hover:text-white border-white/5 hover:border-white/10"
              }`}
            >
              <ArrowsClockwise className="w-4 h-4" />
              {t("전략 최적화")}
            </button>
            {(promptText || strategySummary) && (
              <div className="static lg:relative" ref={promptTooltipRef}>
                <button
                  type="button"
                  onClick={() => setPromptTooltipOpen((v) => !v)}
                  className="px-4 py-1.5 bg-white/[0.04] hover:bg-white/[0.08] text-gray-300 hover:text-white text-sm font-bold rounded-lg transition-colors border border-white/10 hover:border-white/15 active:scale-95 flex items-center gap-1.5"
                >
                  <Info className="w-4 h-4" />
                  {t("프롬프트")}
                </button>
                {promptTooltipOpen && (
                  <div
                    data-testid="backtest-prompt-popover"
                    className="absolute left-4 right-4 top-full z-50 mt-2 rounded-xl border border-white/[0.10] bg-[#111318] p-4 shadow-2xl space-y-2.5 lg:left-auto lg:right-0 lg:w-96"
                  >
                    {promptText && (
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">{t("프롬프트")}</span>
                        <p className="text-xs text-gray-200 leading-5 whitespace-pre-wrap">{promptText}</p>
                      </div>
                    )}
                    {promptSummaryRows.length > 0 && (
                      /* 라벨 폭이 제각각이면 값이 계단처럼 흩어진다 — 대화 화면의 '전략 요약'
                         카드(BuilderStrategyOverview)와 같은 규칙으로 라벨 열을 고정한 그리드에
                         값을 한 줄에 하나씩 쌓아 세로줄을 맞춘다. */
                      <dl className="border-t border-white/[0.06] pt-1">
                        {promptSummaryRows.map((row) => (
                          <div
                            key={row.label}
                            className="grid grid-cols-[64px_minmax(0,1fr)] gap-3 py-1.5 text-xs leading-relaxed"
                          >
                            <dt className="break-keep font-bold text-[var(--text-label)]">{row.label}</dt>
                            <dd className="min-w-0 break-keep font-bold text-gray-200">
                              <span className="flex flex-col gap-0.5">
                                {row.values.map((value, i) => (
                                  <span key={`${value}-${i}`}>{value}</span>
                                ))}
                              </span>
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </div>
                )}
              </div>
            )}
            <button
              onClick={handleOpenSaveModal}
              disabled={isRunning}
              className="px-4 py-1.5 bg-white/[0.05] hover:bg-white/10 text-gray-300 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed text-sm font-bold rounded-lg transition-all border border-white/5 hover:border-white/10 flex items-center gap-2 active:scale-95"
            >
              <FloppyDisk className="w-4 h-4" />
              {t("전략 저장")}
            </button>
            <button
              type="button"
              onClick={onRestart}
              title={t("백테스트 결과 닫기")}
              className="px-4 py-1.5 bg-white/[0.05] hover:bg-white/10 text-gray-300 hover:text-white text-sm font-bold rounded-lg transition-all border border-white/5 hover:border-white/10 flex items-center gap-2 active:scale-95"
            >
              <SignOut className="w-4 h-4" />
              {t("결과 닫기")}
            </button>
          </div>
        </div>
      </div>

      {/* 2. Main Content Area */}
      <div className="flex flex-col min-w-0">
        {isOptimizationPageOpen ? (
          <OptimizationPage
            result={result}
            onWalkForward={onWalkForward}
            walkForwardOptimizationTargets={walkForwardOptimizationTargets}
            baseStrategy={backtestDsl}
            isPlanLoading={isPlanLoading}
            isPremiumValidationEnabled={isPremiumValidationEnabled}
            strategyName={strategySummary?.strategyName}
            promptText={promptText}
            strategySummary={strategySummary}
            onClose={() => setIsOptimizationPageOpen(false)}
          />
        ) : (
        <div data-testid="backtest-tab-content" className="flex flex-col min-w-0">

           {/* Chart View */}
            {activeTab === "chart" && (
              <>
              <div className="border border-white/[0.08]">
                <div className="relative overflow-hidden lg:pr-[420px]">
                  <div className="min-w-0">
                    <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
                      {overviewMetrics.map((metric, index) => (
                        <OverviewMetricCard
                          key={metric.label}
                          label={metric.label}
                          englishLabel={metric.englishLabel}
                          value={metric.value}
                          valueClass={metric.valueClass}
                          className={[
                            index === 0 ? "col-span-2" : "",
                            index < 4 ? "lg:border-b-0" : "lg:border-b",
                            index < 6 ? "xl:border-b-0" : "xl:border-b",
                          ].join(" ")}
                          description={metric.description}
                          onHover={(rect) => setHoveredMetric(rect ? { label: metric.label, description: metric.description, rect } : null)}
                        />
                      ))}
                    </div>

                    <div className="relative border-t border-white/[0.08]">
                      <div className="pointer-events-none absolute left-5 top-4 z-10 flex flex-col gap-1.5">
                        <div className="flex items-center gap-2 rounded-md bg-black/25 px-2.5 py-1.5 backdrop-blur-sm">
                          <span className="h-2.5 w-2.5 rounded-full bg-[#ef4444]" />
                          <span className="text-xs font-bold text-white/75">
                            {t("나의 수익률")}
                          </span>
                        </div>
                        {hasBenchmarkCurve && (
                          <div className="flex items-center gap-2 self-start rounded-md bg-black/25 px-2.5 py-1.5 backdrop-blur-sm">
                            <span className="h-2.5 w-2.5 rounded-full bg-[var(--main-green)]" />
                            <span className="text-xs font-bold text-white/75">
                              {t("벤치마크 · {0}", benchmarkLabel.replace(/\s*\(\d+\)$/, ""))}
                            </span>
                          </div>
                        )}
                      </div>
                      {dateRangeLabel && (
                        <div className="pointer-events-none absolute right-16 top-4 z-10">
                          <span className="rounded-md bg-black/25 px-2.5 py-1 text-xs font-mono text-white/45 backdrop-blur-sm">
                            {dateRangeLabel}
                          </span>
                        </div>
                      )}
                      <BacktestChart
                        type="equity"
                        height={340}
                        equityData={equityCurveData}
                        hideLegend
                      />
                    </div>
                  </div>

                  <div className="border-t border-white/[0.08] min-h-0 lg:absolute lg:inset-y-0 lg:right-0 lg:w-[420px] lg:border-t-0 lg:border-l lg:border-white/[0.08]">
                    <div className="flex h-full min-h-0 flex-col">
                      <BacktestTerminalLog result={result} stockMetadata={stockMetadata} fill />
                    </div>
                  </div>
                </div>

                {result.quantileGroups && (
                  <QuantileGroupsSection data={result.quantileGroups} />
                )}

                {result.vbtResult && (
                  <div className="border-t border-white/[0.08] p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <ArrowsClockwise className="w-4 h-4 text-gray-400" />
                      <h4 className="text-base font-black uppercase tracking-widest text-white">{t("엔진 비교")}</h4>
                      <span className="text-[10px] text-gray-500 font-bold ml-1">{t("자체 엔진 vs VectorBT 네이티브")}</span>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse">
                        <thead>
                          <tr className="bg-white/[0.06]">
                            <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest w-[140px] rounded-l-lg">{t("지표")}</th>
                            <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">
                              <span className="inline-flex items-center gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-main-red inline-block" />{t("자체 엔진")}
                              </span>
                            </th>
                            <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">
                              <span className="inline-flex items-center gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-white/40 inline-block" />VectorBT
                              </span>
                            </th>
                            <th className="py-2 px-3 text-xs font-bold text-gray-400 uppercase tracking-widest text-right rounded-r-lg">{t("차이")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[
                            { label: "CAGR", ours: result.cagr, vbt: result.vbtResult.cagr, fmt: (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`, unit: "%" },
                            { label: t("총수익률"), ours: result.totalReturn, vbt: result.vbtResult.totalReturn, fmt: (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`, unit: "%" },
                            { label: "MDD", ours: result.maxDrawdown, vbt: result.vbtResult.maxDrawdown, fmt: (v: number) => `${v.toFixed(2)}%`, unit: "%", invertDiff: true },
                            { label: "Sharpe", ours: result.sharpe, vbt: result.vbtResult.sharpe, fmt: (v: number) => v.toFixed(2), unit: "" },
                            { label: "Sortino", ours: result.sortino, vbt: result.vbtResult.sortino, fmt: (v: number) => v.toFixed(2), unit: "" },
                            { label: t("승률"), ours: result.winRate, vbt: result.vbtResult.winRate, fmt: (v: number) => `${v.toFixed(1)}%`, unit: "%" },
                            // 손익비만 ours가 무한대(손실 0건)일 수 있다 — fmt/차이 표기가 Infinity를 견뎌야 한다
                            { label: t("손익비"), ours: result.profitFactor ?? Infinity, vbt: result.vbtResult.profitFactor, fmt: (v: number) => (Number.isFinite(v) ? v.toFixed(2) : "∞"), unit: "" },
                            { label: t("거래 수"), ours: result.trades, vbt: result.vbtResult.trades, fmt: (v: number) => `${v}`, unit: "" },
                            { label: t("변동성"), ours: (result.volatility || 0), vbt: (result.vbtResult.volatility || 0), fmt: (v: number) => `${v.toFixed(2)}%`, unit: "%", invertDiff: true },
                          ].map((row) => {
                            const diff = row.vbt - row.ours;
                            const absDiff = Math.abs(diff);
                            const isVbtBetter = row.invertDiff ? diff < -0.01 : diff > 0.01;
                            const isVbtWorse = row.invertDiff ? diff > 0.01 : diff < -0.01;
                            const diffColor = isVbtBetter ? "text-white" : isVbtWorse ? "text-gray-500" : "text-gray-600";

                            return (
                              <tr key={row.label} className="hover:bg-white/[0.02] transition-colors">
                                <td className="py-2 px-3 text-xs font-bold text-gray-400">{t(row.label)}</td>
                                <td className={`py-2 px-3 text-sm font-black text-right font-mono ${row.label === "MDD" || row.label === "변동성" ? "text-white" :
                                  row.ours >= 0 ? "text-white" : "text-[var(--main-blue)]"}`}>
                                  {row.fmt(row.ours)}
                                </td>
                                <td className={`py-2 px-3 text-sm font-black text-right font-mono ${row.label === "MDD" || row.label === "변동성" ? "text-gray-200" :
                                  row.vbt >= 0 ? "text-gray-200" : "text-gray-500"}`}>
                                  {row.fmt(row.vbt)}
                                </td>
                                <td className={`py-2 px-3 text-xs font-bold text-right font-mono ${diffColor}`}>
                                  {!Number.isFinite(diff) || absDiff < 0.01 ? "-" : `${diff >= 0 ? "+" : ""}${row.unit === "%" ? diff.toFixed(2) + "%" : diff.toFixed(2)}`}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    <p className="mt-3 text-[10px] text-gray-600 leading-relaxed">
                      {t("* 자체 엔진: 당일 종가 기반 현실적 리스크 관리 (SL/TP/TS를 종가로 감지 후 종가로 청산). VectorBT: 네이티브 SL/TP/TS 사용 (정확한 스탑 가격에서 이상적으로 체결).")}
                    </p>
                  </div>
                )}

                {/* 월별/롤링 수익률 추이 */}
                <div className="border-t border-white/[0.08] p-5 pb-4">
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="flex shrink-0 items-center gap-1 rounded-[8px] bg-white/[0.04] p-0.5">
                        {([
                          { id: "monthly", label: t("월별 수익률") },
                          { id: "rolling", label: t("롤링 수익률") },
                          { id: "rebalance", label: t("리밸런싱 기간별 결과") },
                        ] as const).map((tab) => (
                          <button
                            key={tab.id}
                            type="button"
                            onClick={() => setReturnsView(tab.id)}
                            className={`min-h-[30px] rounded-[6px] px-3 text-sm font-black tracking-tight transition-colors ${
                              returnsView === tab.id
                                ? "bg-[#232323] text-white"
                                : "text-[#6f7481] hover:text-[#a7adba]"
                            }`}
                          >
                            {t(tab.label)}
                          </button>
                        ))}
                      </div>
                      <p className="truncate text-xs text-gray-500">
                        {returnsView === "monthly"
                          ? (() => {
                              const allYears = Object.keys(monthlyReturns).sort((a, b) => Number(a) - Number(b));
                              if (allYears.length > 0) return t("{0} ~ {1} · 최근 {2}년", allYears[0], allYears[allYears.length - 1], monthlyReturnRows.length);
                              return t("데이터 없음");
                            })()
                          : returnsView === "rebalance"
                          ? t("매일·매주·매월·분기·반기·연간 6주기 재실행 비교")
                          : rollingWindowRows.length > 0
                          ? t("투자 기간별 롤링 구간 수익률·MDD 분포")
                          : t("데이터 없음")}
                      </p>
                    </div>
                    {returnsView === "monthly" ? (
                      <Table size={18} className="shrink-0 text-gray-600" />
                    ) : returnsView === "rebalance" ? (
                      <ArrowsClockwise size={18} className="shrink-0 text-gray-600" />
                    ) : (
                      <div className="flex shrink-0 items-center gap-1">
                        {ROLLING_WINDOW_OPTIONS.map((w) => {
                          const enabled = availableRollingWindows.includes(w);
                          return (
                            <button
                              key={w}
                              type="button"
                              disabled={!enabled}
                              onClick={() => setRollingWindowMonths(w)}
                              className={`rounded-md px-2 py-1 text-[10px] font-bold transition-colors ${
                                effectiveRollingWindow === w
                                  ? "bg-[#232323] text-white"
                                  : enabled
                                  ? "text-gray-500 hover:text-gray-300"
                                  : "cursor-not-allowed text-gray-700"
                              }`}
                            >
                              {rollingWindowLabel(w)}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                  {returnsView === "rolling" && (
                    <RollingReturnTable
                      rows={rollingWindowRows}
                      chart={
                        rollingReturnSeries.length > 0 && effectiveRollingWindow != null ? (
                          <div>
                            <BacktestChart type="rolling_returns" height={280} rollingData={rollingReturnSeries} />
                            <p className="mt-2 text-[10px] leading-relaxed text-gray-600">
                              {t("* 각 지점은 해당일 기준 직전 {0} 구간의 수익률입니다. 위 버튼으로 투자 기간을 바꿔 볼 수 있습니다.", rollingWindowLabel(effectiveRollingWindow))}
                            </p>
                          </div>
                        ) : null
                      }
                    />
                  )}
                  {/* 리밸런싱 기간별 결과(FR-BT-064) — 엔진이 결과에 동봉한 6주기 재시뮬레이션 비교표. */}
                  {returnsView === "rebalance" && (
                    <RebalanceComparisonSection
                      data={result.rebalanceComparison}
                      current={{
                        cagr: result.cagr,
                        maxDrawdown: result.maxDrawdown,
                        sharpe: result.sharpe,
                        profitFactor: result.profitFactor,
                        trades: result.trades,
                        turnoverRate,
                      }}
                    />
                  )}
                  <div className={`w-full overflow-x-auto ${returnsView === "monthly" ? "" : "hidden"}`}>
                    <table className="w-full min-w-[1040px] border-collapse">
                      <thead>
                        <tr>
                          <th className="sticky left-0 z-30 bg-[var(--background)] text-left text-xs font-bold text-gray-600 uppercase tracking-widest py-2 pl-2 pr-4">
                            {t("연도")}
                          </th>
                          {["1월","2월","3월","4월","5월","6월","7월","8월","9월","10월","11월","12월"].map((label) => (
                            <th key={label} className="px-3 py-2 text-right text-xs font-bold text-gray-600 uppercase tracking-widest">
                              {t(label)}
                            </th>
                          ))}
                          <th className="text-right text-xs font-bold text-gray-600 uppercase tracking-widest py-2 pl-4 pr-2">
                            {t("연간 누적")}
                          </th>
                        </tr>
                        <tr><td colSpan={14}><div className="border-t border-white/[0.05]" /></td></tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.04]">
                        {monthlyReturnRows.length > 0 ? (
                          monthlyReturnRows.map((row) => (
                            <tr key={row.year} className="hover:bg-white/[0.02] transition-colors duration-150">
                              <td className="sticky left-0 z-10 bg-[var(--background)] pl-2 pr-4 py-3 text-sm font-black text-white tabular-nums font-outfit">
                                {row.year}
                              </td>
                              {row.months.map((cell) => (
                                <td key={`${row.year}-${cell.month}`} className="px-3 py-3 text-right">
                                  <span className={`text-sm font-black tabular-nums font-outfit ${
                                    cell.value == null ? "text-gray-600"
                                    : cell.value > 0 ? "text-[var(--main-red)]"
                                    : cell.value < 0 ? "text-[var(--main-blue)]"
                                    : "text-white"
                                  }`}>
                                    {cell.value == null ? "-" : `${cell.value > 0 ? "+" : ""}${cell.value.toFixed(2)}%`}
                                  </span>
                                </td>
                              ))}
                              <td className="pl-4 pr-2 py-3 text-right">
                                <span className={`text-sm font-black tabular-nums font-outfit ${
                                  row.annualReturn == null ? "text-gray-600"
                                  : row.annualReturn > 0 ? "text-[var(--main-red)]"
                                  : row.annualReturn < 0 ? "text-[var(--main-blue)]"
                                  : "text-white"
                                }`}>
                                  {row.annualReturn == null ? "-" : `${row.annualReturn > 0 ? "+" : ""}${row.annualReturn.toFixed(2)}%`}
                                </span>
                              </td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={14} className="px-4 py-16 text-center text-sm text-gray-500">
                              {t("월별 수익률 데이터가 없습니다.")}
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* 리스크 및 성과 분석 */}
                <div className="border-t border-white/[0.08]">
                  {([
                    [
                      // formatKRW가 이미 "원"을 붙이므로 sub를 주면 "원 원"이 된다.
                      { label: t("초기 자본"), value: formatKRW(resolvedInitialCapital), sub: null, desc: null },
                      { label: t("최종 자산"), value: formatKRW(resolvedFinalEquity), sub: null, desc: null },
                      {
                        label: t("초과수익률"),
                        value: excessReturn == null ? "-" : `${excessReturn >= 0 ? "+" : ""}${excessReturn.toFixed(2)}`,
                        sub: excessReturn == null ? null : "%p",
                        desc: BASE_METRIC_DESCRIPTIONS.excessReturn(benchmarkLabel),
                      },
                      { label: t("변동성"), value: annualizedVolatility.toFixed(2), sub: "%", desc: BASE_METRIC_DESCRIPTIONS.volatility },
                      { label: t("칼마 비율"), value: (result.calmar ?? (result.maxDrawdown !== 0 ? result.cagr / Math.abs(result.maxDrawdown) : 0)).toFixed(2), sub: null, desc: BASE_METRIC_DESCRIPTIONS.calmar },
                      { label: t("평균 보유일"), value: t("{0}일", Math.round(result.avgHoldingDays ?? 0)), sub: null, desc: BASE_METRIC_DESCRIPTIONS.avgHoldingDays },
                    ],
                    [
                      { label: t("시장 노출도"), value: (result.exposure ?? 0).toFixed(1), sub: "%", desc: BASE_METRIC_DESCRIPTIONS.exposure },
                      { label: t("회전율"), value: turnoverRate.toFixed(1), sub: "%", desc: BASE_METRIC_DESCRIPTIONS.turnover },
                      { label: t("최장 낙폭 기간"), value: `${result.maxDrawdownDuration ?? 0}`, sub: t("거래일"), desc: BASE_METRIC_DESCRIPTIONS.maxDrawdownDuration },
                      { label: t("기대값"), value: `${(result.expectancy ?? 0) >= 0 ? "+" : ""}${(result.expectancy ?? 0).toFixed(2)}`, sub: "%", desc: BASE_METRIC_DESCRIPTIONS.expectancy },
                      { label: t("회복 계수"), value: (result.recoveryFactor ?? 0).toFixed(2), sub: null, desc: BASE_METRIC_DESCRIPTIONS.recoveryFactor },
                    ],
                  ] as const).map((row, rowIdx) => (
                    <div key={rowIdx} className={`flex divide-x divide-white/[0.08] ${rowIdx > 0 ? "border-t border-white/[0.08]" : ""}`}>
                      {row.map((s) => (
                        <div key={s.label} className="flex-1 flex flex-col gap-1 px-5 py-4">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-gray-500">{s.label}</span>
                            {s.desc && (
                              <Info
                                className="w-3 h-3 text-gray-700 hover:text-gray-500 cursor-help transition-colors"
                                onMouseEnter={(e) => setHoveredMetric({ label: s.label, description: s.desc!, rect: e.currentTarget.getBoundingClientRect() })}
                                onMouseLeave={() => setHoveredMetric(null)}
                              />
                            )}
                          </div>
                          <div className="flex items-baseline gap-1">
                            <p className="text-base font-black tabular-nums font-outfit text-white leading-tight">{s.value}</p>
                            {s.sub && <span className="text-[8px] font-bold text-gray-600">{s.sub}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>

                {/* 매매 통계 */}
                <div className="border-t border-white/[0.08]">
                  <div className="flex divide-x divide-white/[0.08]">
                    {[
                      // avgProfit/avgLoss는 거래별 평균 수익률·손실률(%)이다. 원이 아닌 %로 표시한다.
                      // (손실은 백엔드에서 양수 절댓값으로 내려오므로 음수로 표시)
                      { label: t("평균 수익"), value: `+${(result.avgProfit || 0).toFixed(2)}`, sub: "%" },
                      { label: t("평균 손실"), value: `-${(result.avgLoss || 0).toFixed(2)}`, sub: "%" },
                      { label: t("최대 연속 수익"), value: `${result.maxConsecutiveWins || 0}`, sub: t("회") },
                      { label: t("최대 연속 손실"), value: `${result.maxConsecutiveLosses || 0}`, sub: t("회") },
                    ].map((s) => (
                      <div key={s.label} className="flex-1 flex flex-col gap-1 px-5 py-4">
                        <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-gray-500">{s.label}</span>
                        <div className="flex items-baseline gap-1">
                          <p className="text-base font-black tabular-nums font-outfit text-white leading-tight">{s.value}</p>
                          <span className="text-[8px] font-bold text-gray-600">{s.sub}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

              </div>
              </>
           )}

           {/* Report View */}
           {activeTab === "report" && (
             <div className="flex flex-1 flex-col py-4">
               {isPlanLoading ? (
                 <div className="flex min-h-[320px] items-center justify-center text-sm font-bold text-gray-500">
                   <Spinner className="mr-2 h-4 w-4 animate-spin" />
                   {t("플랜 정보를 확인하는 중...")}
                 </div>
               ) : !isAiReportEnabled ? (
                 <div className="flex min-h-[320px] items-center justify-center px-6 py-10">
                   <div className="w-full max-w-2xl p-8 text-center">
                     <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-amber-400/30 bg-amber-500/10">
                       <Crown className="h-6 w-6 text-amber-300" weight="fill" />
                     </div>
                     <h3 className="mt-4 text-lg font-black text-white">
                       {t("AI 리포트는 프로/프리미엄 플랜 전용 기능입니다")}
                     </h3>
                     <p className="mt-2 text-sm font-bold leading-6 text-gray-400">
                       {t("프로 또는 프리미엄 플랜을 이용하시면 백테스트 결과에 대한 AI 분석 리포트를 확인할 수 있습니다.")}
                     </p>
                     <a
                       href="/pricing"
                       className="mt-6 inline-flex items-center justify-center rounded-lg border border-gray-500 px-5 py-2.5 text-sm font-black text-gray-300 transition-colors hover:bg-white/[0.05]"
                     >
                       {t("플랜 변경")}
                     </a>
                   </div>
                 </div>
               ) : (
               <BacktestSummaryCard
                 key={result.executionId}
                 result={result}
                 strategySummary={strategySummary}
                 initialReport={cachedReport}
                 parsedStrategy={parsedStrategy}
                 promptText={promptText}
                 onSummaryReady={(report) => {
                   setCachedReport(report);
                   if (result.cacheKey) {
                     fetch("/api/backtest/ai-report", {
                       method: "PATCH",
                       headers: { "Content-Type": "application/json" },
                       body: JSON.stringify({ cacheKey: result.cacheKey, ...reportToPersistedFields(report) }),
                     }).catch(() => {/* 저장 실패는 무시 */});
                   }
                 }}
               />
               )}
             </div>
           )}

            {/* Assets View (Symbol Summary) */}
            {activeTab === "assets" && (

             <div className="h-full overflow-y-auto custom-scrollbar">
                <div className="mb-3 pt-3 flex items-center gap-3 pl-5">
                  <h3 className="text-3xl font-black tracking-tight text-white">{t("종목별 매매 분석")}</h3>
                  <div className="flex flex-nowrap gap-2">
                    {([
                      { format: "csv" as const, label: t("CSV 내보내기") },
                      { format: "json" as const, label: t("JSON 내보내기") },
                    ]).map(({ format, label }) => (
                      <button
                        key={format}
                        type="button"
                        onClick={() => handleExportAction(format, "assets")}
                        disabled={isRunning || isPlanLoading || !!downloadingFormat}
                        className="inline-flex min-h-[36px] items-center justify-center gap-1.5 rounded-md border border-white/10 bg-white/[0.05] px-3.5 text-sm font-black text-gray-200 transition-all hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {downloadingFormat === format ? (
                          <Spinner className="h-4 w-4 animate-spin" />
                        ) : (
                          <DownloadSimple className="h-4 w-4 text-gray-400" weight="bold" />
                        )}
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0f0f10] shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
                   <table className="w-full text-left border-collapse">
                      <thead className="bg-white/[0.06] sticky top-0 z-10">
                         <tr>
                            <th className="p-4 pl-5 text-xs font-bold text-gray-400 uppercase tracking-[0.18em] rounded-tl-2xl">{t("종목")}</th>
                            <th className="p-4 text-xs font-bold text-gray-400 uppercase tracking-[0.18em] text-right">{t("평균 매수가")}</th>
                            <th className="p-4 text-xs font-bold text-gray-400 uppercase tracking-[0.18em] text-right">{t("평균 매도가")}</th>
                             <th className="p-4 text-xs font-bold text-gray-400 uppercase tracking-[0.18em] text-right">
                                <div
                                  className="inline-flex items-center justify-end gap-1 cursor-pointer transition-colors group"
                                  onClick={() => handleSort('profit')}
                                >
                                   {t("수익금 ")}<SortIcon column="profit" />
                                </div>
                             </th>
                             <th className="p-4 text-xs font-bold text-gray-400 uppercase tracking-[0.18em] text-right">
                                <div
                                  className="inline-flex items-center justify-end gap-1 cursor-pointer transition-colors group"
                                  onClick={() => handleSort('totalReturn')}
                                >
                                   {t("수익률 ")}<SortIcon column="totalReturn" />
                                </div>
                             </th>
                             <th className="p-4 pr-5 text-xs font-bold text-gray-400 uppercase tracking-[0.18em] text-right rounded-tr-2xl">
                                <div
                                  className="inline-flex items-center justify-end gap-1 cursor-pointer transition-colors group"
                                  onClick={() => handleSort('trades')}
                                >
                                   {t("매매 횟수 ")}<SortIcon column="trades" />
                                </div>
                             </th>
                         </tr>
                      </thead>
                       <tbody>
                          {sortedSymbols.length > 0 ? sortedSymbols.map(sym => {
                             const stats = result.perAssetStats?.[sym];
                             const meta = stockMetadata[sym];
                             const prices = symbolTradePrices[sym];

                             return (
                               <tr
                                 key={sym}
                                 onClick={() => router.push(`/stock-order?symbol=${encodeURIComponent(sym)}&name=${encodeURIComponent(meta?.name || sym)}`)}
                                 className="cursor-pointer hover:bg-white/[0.02] transition-colors duration-150"
                               >
                                  <td className="px-4 py-2.5 pl-5">
                                     <div className="flex flex-col">
                                        <span className="text-sm font-bold text-white truncate">{meta?.name || sym}</span>
                                        <span className="text-[10px] text-gray-500 font-mono">{sym}</span>
                                     </div>
                                  </td>
                                  <td className="px-4 py-2.5 text-sm font-bold text-gray-400 text-right tabular-nums">
                                     {prices?.entryPrice != null ? formatKRW(prices.entryPrice) : "-"}
                                  </td>
                                  <td className="px-4 py-2.5 text-sm font-bold text-gray-400 text-right tabular-nums">
                                     {prices?.exitPrice != null ? formatKRW(prices.exitPrice) : "-"}
                                  </td>
                                  <td className={`px-4 py-2.5 text-sm font-bold text-right tabular-nums ${(stats?.profit || 0) > 0 ? 'text-[var(--main-red)]' : (stats?.profit || 0) < 0 ? 'text-[var(--main-blue)]' : 'text-white'}`}>
                                     {stats ? formatKRW(stats.profit) : "-"}
                                  </td>
                                  <td className={`px-4 py-2.5 text-sm font-bold text-right tabular-nums ${(stats?.totalReturn || 0) > 0 ? 'text-[var(--main-red)]' : (stats?.totalReturn || 0) < 0 ? 'text-[var(--main-blue)]' : 'text-white'}`}>
                                     {stats ? `${stats.totalReturn.toFixed(2)}%` : "-"}
                                  </td>
                                  <td className="px-4 py-2.5 text-sm font-bold text-white text-right tabular-nums pr-5">
                                     {stats ? t("{0}회", stats.trades) : "-"}
                                  </td>
                               </tr>
                             );
                          }) : (
                             <tr>
                                <td colSpan={6} className="p-12 text-center text-gray-500">
                                   <div className="flex flex-col items-center gap-2">
                                      <List className="w-8 h-8 opacity-20" />
                                      <span className="text-sm font-medium">{t("매매 결과가 있는 종목이 부재합니다.")}</span>
                                   </div>
                                </td>
                             </tr>
                          )}
                       </tbody>
                   </table>
                </div>
             </div>
           )}

           {/* Stats View (Heatmap + Detailed Grid) */}

           {/* Log View */}
           {activeTab === "log" && (
              <div className="h-full overflow-y-auto custom-scrollbar">
                <div className="mb-3 pt-3 flex items-center gap-3 pl-5">
                  <h3 className="text-3xl font-black tracking-tight text-white">{t("종목별 매매 기록")}</h3>
                  <div className="flex flex-nowrap gap-2">
                    {([
                      { format: "csv" as const, label: t("CSV 내보내기") },
                      { format: "json" as const, label: t("JSON 내보내기") },
                    ]).map(({ format, label }) => (
                      <button
                        key={format}
                        type="button"
                        onClick={() => handleExportAction(format, "log")}
                        disabled={isRunning || isPlanLoading || !!downloadingFormat}
                        className="inline-flex min-h-[36px] items-center justify-center gap-1.5 rounded-md border border-white/10 bg-white/[0.05] px-3.5 text-sm font-black text-gray-200 transition-all hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {downloadingFormat === format ? (
                          <Spinner className="h-4 w-4 animate-spin" />
                        ) : (
                          <DownloadSimple className="h-4 w-4 text-gray-400" weight="bold" />
                        )}
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                 {result.tradesList?.length > 0 ? (
                    <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0f0f10] shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
                      <table className="w-full text-left border-collapse">
                        <thead className="bg-white/[0.06] sticky top-0 z-10">
                           <tr>
                              <th className="p-3 pl-4 text-xs font-bold text-gray-400 uppercase tracking-[0.18em] rounded-tl-2xl">{t("날짜")}</th>
                              <th className="p-3 text-xs font-bold text-gray-400 uppercase tracking-[0.18em]">{t("종목")}</th>
                              <th className="p-3 text-xs font-bold text-gray-400 uppercase tracking-[0.18em]">{t("구분")}</th>
                              <th className="p-3 text-xs font-bold text-gray-400 uppercase tracking-[0.18em]">{t("체결가")}</th>
                               <th className="p-3 text-xs font-bold text-gray-400 uppercase tracking-[0.18em]">{t("수량")}</th>
                               <th className="p-3 text-xs font-bold text-gray-400 uppercase tracking-[0.18em]">{t("매매사유")}</th>
                               <th className="p-3 pr-4 text-xs font-bold text-gray-400 uppercase tracking-[0.18em] text-right rounded-tr-2xl">{t("거래금액")}</th>
                           </tr>
                        </thead>
                        <tbody>
                            {result.tradesList.map((tv, i) => {
                               const tradeAmount = tv.amount || 0;
                               return (
                                <tr key={`${tv.symbol}-${tv.date}-${tv.type}-${i}`} className="hover:bg-white/[0.02] transition-colors duration-150">
                                   <td className="p-3 pl-4 text-sm font-bold text-gray-300 tabular-nums">{tv.date}</td>
                                   <td className="p-3 text-sm font-bold text-white">
                                      <div className="flex flex-col">
                                         <span className="truncate">{stockMetadata[tv.symbol]?.name || tv.symbol}</span>
                                         <span className="text-[10px] text-gray-500 font-mono">{tv.symbol}</span>
                                      </div>
                                   </td>
                                    <td className="p-3">
                                      <span className={`px-2 py-0.5 rounded-md text-xs font-bold ${tv.type==='buy' ? 'bg-[var(--main-red)]/10 text-[var(--main-red)]' : 'bg-[var(--main-blue)]/10 text-[var(--main-blue)]'}`}>
                                         {tv.type === 'buy' ? t("매수") : t("매도")}
                                      </span>
                                   </td>
                                   <td className="p-3 text-sm font-bold text-gray-300 tabular-nums">{Math.round(Number(tv.price)).toLocaleString()}</td>
                                    <td className="p-3 text-sm font-bold text-gray-400 tabular-nums">
                                      {t("{0}주", Math.floor(Number(tv.quantity)).toLocaleString())}
                                    </td>
                                    <td className="p-3 text-xs font-bold text-gray-500">{resolveTradeReason(tv.reason, tv.type, normalizedBacktestDsl)}</td>
                                   <td className="p-3 pr-4 text-sm font-bold text-right tabular-nums text-white">
                                      {formatKRW(tradeAmount)}
                                   </td>
                                </tr>
                               );
                            })}
                        </tbody>
                      </table>
                    </div>
                 ) : (
                    <div className="h-full flex flex-col items-center justify-center text-gray-600 space-y-2 pb-20">
                       <ShieldCheck className="w-12 h-12 text-gray-800" />
                       <p className="text-lg font-bold">{t("기록이 없습니다")}</p>
                       <p className="text-sm">{t("백테스트 기간 동안 매매 조건이 충족되지 않았습니다.")}</p>
                    </div>
                 )}
              </div>
           )}

        </div>
        )}
      </div>

      <div data-testid="backtest-dashboard-footer" className="mt-auto border-t border-white/[0.08] bg-[#050505] px-0 py-3">
        <p className="text-center text-xs font-bold leading-relaxed text-gray-500">
          {t("모든 결과는 과거 데이터의 모의 시뮬레이션 결과이며 미래 수익을 보장하지 않습니다. 실제 매매에서는 체결가·거래비용·슬리피지·유동성 및 데이터 한계로 인해 시뮬레이션 결과와 차이가 발생할 수 있습니다.")}
        </p>
      </div>

      {hoveredMetric && (
        <div 
          className="fixed z-[1000] pointer-events-none" 
          style={(() => {
            const rect = hoveredMetric.rect;
            const tooltipWidth = 256; // w-64 is 256px
            let left = rect.left + rect.width / 2;
            const padding = 16;

            if (typeof window !== 'undefined') {
              if (left - tooltipWidth / 2 < padding) {
                left = tooltipWidth / 2 + padding;
              } else if (left + tooltipWidth / 2 > window.innerWidth - padding) {
                left = window.innerWidth - tooltipWidth / 2 - padding;
              }
            }

            return { 
              left: `${left}px`, 
              top: `${rect.top - 8}px`,
              transform: 'translate(-50%, -100%)'
            };
          })()}
        >
          <div className="w-64 p-4 bg-[#161616] rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 slide-in-from-bottom-2 duration-200 backdrop-blur-2xl border border-white/10">
            <div className="text-[10px] text-[var(--main-blue)] font-bold uppercase tracking-widest mb-1.5 opacity-80">{hoveredMetric.label}</div>
            <p className="text-xs text-white/75 font-bold leading-relaxed whitespace-pre-wrap">{hoveredMetric.description}</p>
          </div>
        </div>
      )}

      <XAIModal
        isOpen={!!xaiTarget}
        onClose={() => setXaiTarget(null)}
        symbol={xaiTarget?.symbol || ""}
        date={xaiTarget?.date || ""}
      />

    </div>
  );
}

function BacktestTerminalLog({
  result,
  stockMetadata,
  fill,
}: {
  result: BacktestResult;
  stockMetadata: Record<string, { name: string; sector: string }>;
  fill?: boolean;
}) {
  const now = result.dates?.[result.dates.length - 1] ?? "----/--/--";
  const start = result.dates?.[0] ?? "----/--/--";
  const totalDays = result.dates?.length ?? 0;
  const symbolCount = result.symbols?.length ?? (result.symbol ? 1 : 0);

  type LogLevel = "INFO" | "WARN" | "ERROR" | "SUCCESS";
  const logs: { level: LogLevel; message: string; ts?: string }[] = [];

  const ts = (_i: number) => start.slice(0, 10);

  // 초기화
  logs.push({ level: "INFO", ts: ts(0), message: t("백테스트 엔진 초기화 완료") });
  logs.push({ level: "INFO", ts: ts(1), message: t("기간: {0} ~ {1} ({2}일)", start, now, totalDays) });
  const UNIVERSE_NAMES: Record<string, string> = {
    kospi: "KOSPI", kospi200: "KOSPI 200", kosdaq: "KOSDAQ", kosdaq150: "KOSDAQ 150",
    kospi_kosdaq: "KOSPI+KOSDAQ", kosdaq_kospi: "KOSPI+KOSDAQ",
  };
  const universeLabel = result.universeId
    ? (UNIVERSE_NAMES[result.universeId] ?? result.universeId.toUpperCase())
    : "KOSPI";
  const logInitialCapital = result.initialCapital || result.equity?.[0] || 0;
  logs.push({ level: "INFO", ts: ts(2), message: t("유니버스: {0} / 초기자금: {1}원", universeLabel, logInitialCapital.toLocaleString()) });

  // 매수 신호 통계
  const buyCount = result.tradesList?.filter(tv => tv.type === "buy").length ?? 0;
  const sellCount = result.tradesList?.filter(tv => tv.type === "sell").length ?? 0;
  logs.push({ level: "INFO", ts: ts(3), message: t("시그널 처리 완료 — 매수 {0}회 / 매도 {1}회", buyCount, sellCount) });

  // 연도별 수익률
  if (result.yearlyReturns && Object.keys(result.yearlyReturns).length > 0) {
    const years = Object.keys(result.yearlyReturns).sort();
    years.forEach((yr, i) => {
      const ret = result.yearlyReturns[yr];
      const sign = ret >= 0 ? "+" : "";
      logs.push({ level: ret >= 0 ? "SUCCESS" : "WARN", ts: ts(4 + i), message: t("{0}년 수익률: {1}{2}%", yr, sign, ret.toFixed(2)) });
    });
  }

  // 리스크 지표
  logs.push({ level: "INFO", ts: ts(20), message: t("MDD: {0}% / Sharpe: {1} / Calmar: {2} / 평균보유일: {3}일", (result.maxDrawdown ?? 0).toFixed(2), (result.sharpe ?? 0).toFixed(2), (result.calmar ?? 0).toFixed(2), Math.round(result.avgHoldingDays ?? 0)) });
  logs.push({ level: "INFO", ts: ts(21), message: t("승률: {0}% / 손익비: {1} / CAGR: {2}%", (result.winRate ?? 0).toFixed(1), formatProfitFactor(result.profitFactor), (result.cagr ?? 0).toFixed(2)) });

  if ((result.avgProfit ?? 0) !== 0 || (result.avgLoss ?? 0) !== 0) {
    logs.push({ level: "INFO", ts: ts(22), message: t("평균수익: +{0}% / 평균손실: -{1}%", (result.avgProfit ?? 0).toFixed(2), (result.avgLoss ?? 0).toFixed(2)) });
  }
  if ((result.maxConsecutiveWins ?? 0) > 0 || (result.maxConsecutiveLosses ?? 0) > 0) {
    logs.push({ level: "INFO", ts: ts(23), message: t("최대 연속수익: {0}회 / 최대 연속손실: {1}회", result.maxConsecutiveWins ?? 0, result.maxConsecutiveLosses ?? 0) });
  }

  // 상위 종목
  if (result.perAssetStats) {
    const traded = Object.values(result.perAssetStats).filter(s => s.trades > 0);
    const sorted = traded.sort((a, b) => b.profit - a.profit);
    const top3 = sorted.slice(0, 3);
    const bot3 = sorted.slice(-3).reverse();
    top3.forEach((s, i) => {
      const name = stockMetadata[s.symbol]?.name ?? s.symbol;
      logs.push({ level: "INFO", ts: ts(30 + i), message: t("TOP{0} {1}({2}): +{3}원 / 수익률 {4}% / {5}거래", i+1, name, s.symbol, Math.round(s.profit).toLocaleString(), s.totalReturn.toFixed(1), s.trades) });
    });
    bot3.forEach((s, i) => {
      const name = stockMetadata[s.symbol]?.name ?? s.symbol;
      logs.push({ level: "INFO", ts: ts(33 + i), message: t("BOT{0} {1}({2}): {3}원 / 수익률 {4}% / {5}거래", i+1, name, s.symbol, Math.round(s.profit).toLocaleString(), s.totalReturn.toFixed(1), s.trades) });
    });
  }

  // 데이터 해결 로그 (DataResolver)
  const resLogs = (result as any).resolution_logs as Array<{ level: string; message: string }> | undefined;
  if (resLogs && resLogs.length > 0) {
    // 중복 제거 (동일 메시지가 여러 심볼에서 반복될 수 있음) — 최대 20개
    const seen = new Set<string>();
    let count = 0;
    for (const rl of resLogs) {
      if (seen.has(rl.message) || count >= 20) continue;
      seen.add(rl.message);
      count++;
      const lvl = (rl.level === "SUCCESS" ? "SUCCESS" : rl.level === "ERROR" ? "ERROR" : rl.level === "WARN" ? "WARN" : "INFO") as LogLevel;
      let msg = rl.message;
      const symMatch = msg.match(/^\[([0-9A-Z]{6})\]/);
      if (symMatch) {
        const sym = symMatch[1];
        const name = stockMetadata[sym]?.name;
        if (name) msg = msg.replace(`[${sym}]`, `[${name}(${sym})]`);
      }
      logs.push({ level: lvl, ts: ts(36 + count * 0.5), message: msg });
    }
  }

  // 경고
  if (result.warnings && result.warnings.length > 0) {
    result.warnings.forEach((w, i) => {
      let msg = w;
      const symMatch = w.match(/^([0-9A-Z]{6}):/);
      if (symMatch) {
        const sym = symMatch[1];
        const name = stockMetadata[sym]?.name;
        if (name) msg = w.replace(sym, `${name}(${sym})`);
      }
      logs.push({ level: "WARN", ts: ts(40 + i), message: msg });
    });
  }

  // 완료
  const logFinalEquity = result.finalEquity || result.equity?.[result.equity.length - 1] || 0;
  logs.push({ level: "SUCCESS", ts: ts(99), message: t("백테스트 완료 — 총 {0}회 거래 / 최종자산 {1}원 / 수익률 {2}%", result.trades ?? 0, logFinalEquity.toLocaleString(), (result.totalReturn ?? 0).toFixed(2)) });

  const levelStyle: Record<LogLevel, string> = {
    INFO: "text-blue-400",
    WARN: "text-orange-400",
    ERROR: "text-red-400",
    SUCCESS: "text-[var(--main-green)]",
  };

  return (
    <div className={`flat-card overflow-hidden flex flex-col ${fill ? "flex-1 min-h-0" : "mx-2 mb-2"}`}>
      <div className="px-4 py-3 border-b border-white/[0.05] flex-none">
        <p className="text-base font-black uppercase tracking-widest text-white">{t("백테스트 로그")}</p>
      </div>
      <div className={`px-4 py-3 overflow-y-auto custom-scrollbar font-mono text-xs ${fill ? "flex-1 min-h-0 space-y-1" : "max-h-64 space-y-1"}`}>
        {logs.map((log, i) => (
          <div key={i} className="flex gap-3 leading-relaxed">
            <span className="text-gray-600 shrink-0">[{log.ts ?? now}]</span>
            <span className={`font-bold shrink-0 ${levelStyle[log.level]}`}>[{log.level}]</span>
            <span className="text-gray-300">{log.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Sub-components for Cleaner Code

function OverviewMetricCard({
  label,
  englishLabel,
  value,
  valueClass,
  className,
  description,
  onHover,
}: {
  label: string;
  englishLabel?: string;
  value: string;
  valueClass?: string;
  className?: string;
  description?: string;
  onHover?: (rect: DOMRect | null) => void;
}) {
  return (
    <div className={`min-h-[110px] border-r border-b border-white/[0.08] px-5 py-5 md:px-6 md:py-6 ${className || ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="text-xs font-bold uppercase tracking-[0.16em] text-gray-500">
            {label}
          </div>
          {englishLabel && (
            <div className="text-[10px] font-bold text-gray-600 tracking-wider">
              {englishLabel}
            </div>
          )}
        </div>
        {description && onHover && (
          <Info
            className="mt-0.5 h-3.5 w-3.5 cursor-help text-white/25 transition-colors hover:text-white/55"
            onMouseEnter={(e) => onHover(e.currentTarget.getBoundingClientRect())}
            onMouseLeave={() => onHover(null)}
          />
        )}
      </div>
      <div className={`mt-5 text-[clamp(1.25rem,2vw,2.2rem)] font-black leading-[0.95] tracking-tight [overflow-wrap:anywhere] ${valueClass || "text-white"}`}>
        {value}
      </div>
    </div>
  );
}

function StatRow({ 
  label, 
  value, 
  result, 
  isNeutral, 
  colorOverride,
  description,
  onHover
}: { 
  label: string, 
  value: string, 
  result: any, 
  isNeutral?: boolean, 
  colorOverride?: string,
  description?: string,
  onHover?: (rect: DOMRect | null) => void
}) {
  const dynamicColor = colorOverride 
    ? colorOverride
    : (isNeutral 
        ? "text-white" 
        : (value.includes("-") ? "text-[var(--main-blue)]" : (parseFloat(value) === 0 ? "text-white" : "text-[var(--main-red)]")));

  return (
    <div className="bg-[#0d0d0d] rounded-lg px-3 pt-2 pb-2 flex flex-col justify-center flex-1">
       <div className="flex items-center justify-between mb-0.5">
          <div className="text-xs text-gray-400 font-bold">{label}</div>
          {description && onHover && (
             <Info
               className="w-3 h-3 text-gray-700 hover:text-gray-500 cursor-help transition-colors"
               onMouseEnter={(e) => onHover(e.currentTarget.getBoundingClientRect())}
               onMouseLeave={() => onHover(null)}
             />
          )}
       </div>
       <div className={`text-2xl font-black leading-tight ${dynamicColor}`}>{value}</div>
    </div>
  );
}

function StatItem({ 
  label, 
  value, 
  sub,
  description,
  onHover
}: { 
  label: string, 
  value: string, 
  sub?: string,
  description?: string,
  onHover?: (rect: DOMRect | null) => void
}) {
   return (
      <div className="flex justify-between items-center py-1">
         <div className="flex items-center gap-1.5">
            <span className="text-sm font-bold text-gray-400">{label}</span>
            {description && onHover && (
               <Info 
                 className="w-4 h-4 text-gray-700 hover:text-gray-500 cursor-help transition-colors"
                 onMouseEnter={(e) => onHover(e.currentTarget.getBoundingClientRect())}
                 onMouseLeave={() => onHover(null)}
               />
            )}
         </div>
         <div className="text-right">
            <div className="text-sm font-bold text-white tabular-nums">{value}</div>
            {sub && <div className="text-xs font-bold text-gray-600">{sub}</div>}
         </div>
      </div>
   );
}
