"use client";

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  useImperativeHandle,
  forwardRef,
  memo,
  Suspense,
} from "react";
import { flushSync } from "react-dom";
import dynamic from "next/dynamic";
import { createClient } from "@supabase/supabase-js";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { StrategyExampleTabs } from "@/components/strategy/StrategyExampleTabs";
import { StrategyWaveBackground } from "@/components/strategy/StrategyWaveBackground";
import {
  PENDING_STRATEGY_PROMPT_KEY,
  STRATEGY_CHAT_STATE_KEY,
  STRATEGY_LAB_CHAT_VIEW_EVENT,
} from "@/components/strategy/strategyTemplateSession";
import { BacktestResult, type OptimizationResponse } from "@/types/strategy";
import { mapRawBacktestResult } from "./backtestResultMapper";
import {
  ArrowUp,
  ArrowRight,
  ArrowLeft,
  ArrowsClockwise,
  CheckCircle,
  Warning,
  ChartLineUp,
  Question,
  Info,
  GoogleLogo,
  X,
} from "phosphor-react";
import {
  buildStrategySummaryFromRequest,
  FUNDAMENTAL_FILTER_SECTION_LABEL,
  formatFundamentalFilter,
  formatInitialCapital,
  getDisplayExitLabels,
  getDisplayUniverseLabels,
  getPositionLabel,
  getRankingLabel,
  getSignalLabel,
  hasBuyCriteria,
  PERIOD_LABELS,
  REBAL_LABELS,
  type ParsedSummary,
} from "./strategySummary";
import {
  buildWalkForwardParameterDescriptors,
  buildWalkForwardParameterRanges,
  buildWalkForwardRequest,
  hasWalkForwardParameterRanges,
  mergeStrategyModification,
  walkForwardRangeBoundsForPath,
  type AdvisorWalkForwardSettings,
  type StrategyBacktestRequest,
} from "./parsedStrategyMerge";
import { computeChatScrollDelta, scrollChatViewToEnd } from "./chatScroll";
import {
  buildResearchMetricIntro,
  buildResearchMetricSummary,
  decideConversationTurn,
  getResearchMetricLabel,
  parseMetricOptimizationRange,
  type MetricOptimizationRange,
  type ResearchMetric,
  type HoldingPeriodHorizon,
  type SemanticClassification,
  type StrategyAssumptions,
} from "./conversationDecision";
import {
  getNextMissingBacktestCondition,
  isBacktestReady,
} from "./backtestReadiness";
import {
  presentStrategyClarification,
  shouldContinueWithSingleAssetBuilder,
} from "./clarificationPresentation";
import { normalizeCoachMessage } from "./coachMessage";
import { parseCoachSegments } from "./coachText";
import { runButtonPlacement } from "./runButtonPlacement";
import { parseSseBlocks } from "./sseEvents";
import { runWalkForwardStream, type WalkForwardProgressHandler } from "./walkForwardStream";
import { installBacktestResultBackHandler } from "./backtestResultHistory";
import {
  beginStrategyChatNavigation,
  selectPersistableChatMessages,
  shouldBeginStrategyChatNavigation,
  shouldShowChatInputBox,
} from "./chatNavigation";
import { selectClassifierHistory } from "./chatHistory";
import { applyParsedValueStrategySeed } from "./builderSeed";
import {
  buildBuilderTurnPresentation,
  getDisplayBuilderProgressItems,
  type BuilderProgressItem,
  type BuilderSummaryItem,
  type BuilderTurnPresentation,
} from "./builderProgressPresentation";
import { applyDeterministicConditionChoice } from "./deterministicConditionFlow";

// 되묻기 게이트가 provenance(사용자가 실제로 말했나)를 요구하는 설정 필드.
// backtestReadiness.ExplicitField와 같은 목록이며, 칩 답변을 그 채널에 기록할 때 쓴다.
const EXPLICIT_GATE_FIELDS: readonly string[] = [
  "universe",
  "max_positions",
  "rebalancing",
  "backtest_period",
  "initial_capital",
];
import { buildStrategyRestatement } from "./strategyRestatement";

const BacktestDashboard = dynamic(
  () => import("@/components/strategy/backtest/BacktestDashboard"),
  { ssr: false }
);

type Stage = "idle" | "ready" | "running" | "done";
// ranking-fix-v3: risk.ranking_metric를 스키마가 버리던 버그 수정(모멘텀 랭킹 0거래) →
// 같은 strategy_id로 캐시된 잘못된 0거래 결과를 무효화하기 위해 버전을 올린다.
const BACKTEST_ENGINE_VERSION = "audit-fixes-v4";
const OPTIMIZATION_BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const RUN_METRIC_OPTIMIZATION_CHIP = "이 범위로 계산";
const CANCEL_METRIC_OPTIMIZATION_CHIP = "계산 취소";
const MAX_METRIC_OPTIMIZATION_PARAMETERS = 3;
const OAUTH_QUERY_PARAMS = {
  access_type: "offline",
  prompt: "select_account",
};
let analyticsSupabaseClient:
  | ReturnType<typeof createClient>
  | null = null;

interface ChatMessage {
  role: "user" | "assistant";
  content?: string;
  parsed?: ParsedSummary;
  coachText?: string;
  clarification?: string;
  clarificationSuggestions?: string[];
  coachLoading?: boolean;  // coach response is being generated
  isLoading?: boolean;
  // 분석 로딩 단계: 'parsing'(NL 파서 규칙 파싱) → 'thinking'(LLM 처리) → 'validating'(LLM 검증).
  // 'kg_lookup'은 개념 해석 체인(지식그래프 조회 포함) 진입, 'searching'은 용어 그라운딩이
  // 인터넷 검색에 진입했을 때(FR-STR-069).
  // 미설정이면 기본 '분석 중...'을 표시한다(빌더/분류 등 비파싱 로딩).
  loadingStage?: "parsing" | "thinking" | "validating" | "searching" | "kg_lookup";
  error?: string;
  // 파싱 실패 시 같은 턴을 다시 실행할 수 있는 '다시 시도' 버튼용 컨텍스트.
  // LLM 콜드스타트(scale-to-zero, 첫 파스 ~2분)로 스트림이 타임아웃에 끊긴 경우가 주 대상 —
  // 재시도 시점엔 서버가 웜 상태라 두 번째 시도는 수 초 안에 끝난다.
  retryPrompt?: string;
  retryAssumptions?: StrategyAssumptions;
  infoText?: string;  // 일반 투자 답변 또는 전략 전환 안내
  infoSuggestions?: string[];  // 전략 빌더 옵션 칩(클릭 시 그 답으로 전송)
  builderQuestion?: boolean;  // 복원 후에도 진행 중인 빌더 질문임을 식별
  builderPresentation?: {
    summaryItems: BuilderSummaryItem[];
    progressItems: BuilderProgressItem[];
  };
  strategyConfirmation?: boolean;
  // 조건 옵션 버블에서 '돌아가기'로 되돌아갈 이전 단계 상태(유니버스 질문 제외 전 단계에 설정).
  previousStepState?: {
    parsed: ParsedSummary;
    allowNoRebalancing: boolean;
    // 답을 되돌리면 그 필드의 '사용자가 말했다'(provenance)도 함께 되돌려야 한다 —
    // 남겨두면 게이트가 되돌아온 질문을 이미 답한 것으로 보고 건너뛴다.
    explicitFields: string[];
  };
  // 전략 요약을 막지 않는 보정 안내(예: 초기자금 하한선 보정). 요약 카드와 함께 표시된다.
  notices?: string[];
  // 사용자의 자연어를 백테스트 가능한 전략 개념으로 재정리한 첫 문장("…전략이군요.").
  restatement?: string;
}

type MetricOptimizationProgressState = {
  startedAt: number;
  totalTrials: number;
};

type SingleAssetBuilderContext = {
  symbol: string;
  label: string;
  builderUniverse: "KOSPI" | "KOSDAQ" | "KOSPI200" | "KOSPI_KOSDAQ" | "ETF";
};

type BuilderConfirmedData = {
  parsed: ParsedSummary;
  backtest_request: any;
  prompt?: string;
  notices?: string[];
};

const BUILDER_SLOT_KEYS = [
  "single_symbol",
  "single_label",
  "universe",
  "sector",
  "strategy_type",
  "lookback_days",
  "lookback_label",
  "holding_count",
  "rebalance_cycle",
  "entry_rule",
  "rsi_period",
  "rsi_oversold",
  "rsi_overbought",
  "ma_kind",
  "ma_short",
  "ma_long",
  "macd_mode",
  "cci_period",
  "cci_threshold",
  "volume_period",
  "value_pbr",
  "value_roe",
  "filters_asked",
  "trend_filter_ma",
  "liquidity_min",
  "rsi_filter",
  "stop_loss_pct",
  "take_profit_pct",
  "trailing_stop_pct",
  "hold_period_days",
  "risk_done",
] as const;

function hasBuilderSlotValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "" && value !== false;
}

// 빌더 슬롯 → 게이트 필드 provenance. 빌더는 슬롯을 하나씩 묻고 채우는 대화라
// 채워진 슬롯 자체가 "사용자가 답했다"는 기록이다(LLM 레인의 explicit_fields와 같은 역할).
// 기간·초기 자본은 빌더가 묻지 않으므로 파스 레인의 explicit_fields가 담당한다.
const BUILDER_SLOT_EXPLICIT_FIELDS: Record<string, string> = {
  universe: "universe",
  sector: "universe",
  single_symbol: "universe",
  holding_count: "max_positions",
  rebalance_cycle: "rebalancing",
};

function builderStateExplicitFields(state: Record<string, any>): string[] {
  return Array.from(
    new Set(
      Object.entries(BUILDER_SLOT_EXPLICIT_FIELDS)
        .filter(([slot]) => hasBuilderSlotValue(state?.[slot]))
        .map(([, field]) => field),
    ),
  );
}

function mergeBuilderState(
  previous: Record<string, any>,
  next: Record<string, any> | null | undefined,
): Record<string, any> {
  const merged = { ...previous, ...(next ?? {}) };
  for (const key of BUILDER_SLOT_KEYS) {
    if (hasBuilderSlotValue(previous[key]) && !hasBuilderSlotValue(next?.[key])) {
      merged[key] = previous[key];
    }
  }
  return merged;
}

function hasActiveBuilderQuestion(messages: ChatMessage[]): boolean {
  const lastAssistant = [...messages].reverse().find((message) => message.role === "assistant");
  return lastAssistant?.builderQuestion === true;
}

function hasBuilderProgress(state: Record<string, any>): boolean {
  return BUILDER_SLOT_KEYS.some((key) => hasBuilderSlotValue(state[key]));
}

function getSingleAssetBuilderContext(
  parsed?: ParsedSummary | null,
  backtestRequest?: {
    target_stocks?: Array<{ symbol: string; name?: string }> | null;
  } | null,
): SingleAssetBuilderContext | null {
  const targetSymbols = parsed?.target_symbols?.filter(Boolean) ?? [];
  if (targetSymbols.length !== 1) return null;

  const symbol = targetSymbols[0];
  const targetStock = backtestRequest?.target_stocks?.find((stock) => stock.symbol === symbol);
  const label = targetStock?.name ? `${targetStock.name} (${symbol})` : symbol;
  const parsedUniverse = parsed?.universe?.[0];
  const builderUniverse =
    parsedUniverse === "KOSPI" ||
    parsedUniverse === "KOSDAQ" ||
    parsedUniverse === "KOSPI200" ||
    parsedUniverse === "ETF"
      ? parsedUniverse
      : "KOSPI_KOSDAQ";

  return { symbol, label, builderUniverse };
}

function withSingleAssetSummaryLabel(
  presentation: BuilderTurnPresentation,
  parsed: ParsedSummary,
  backtestRequest: {
    target_stocks?: Array<{ symbol: string; name?: string }> | null;
  } | null | undefined,
) {
  const singleAssetContext = getSingleAssetBuilderContext(parsed, backtestRequest);
  if (!singleAssetContext) return presentation;

  return {
    ...presentation,
    summaryItems: presentation.summaryItems.map((item) =>
      item.label === "유니버스"
        ? { ...item, value: singleAssetContext.label }
        : item,
    ),
  };
}

function buildSingleAssetBuilderPrompt(
  prompt: string,
  context: SingleAssetBuilderContext,
): string {
  const strategyBody = prompt.replace(
    /^(?:코스피·코스닥 전체|코스피200|코스피|코스닥|ETF)(?:\s+[^,]+?\s+업종)?\s+종목 중\s+/,
    "",
  );
  return `${context.label} 단일 종목에 적용하는 전략: ${strategyBody}`;
}

function mergeSingleAssetBuilderResult(
  data: {
    parsed: ParsedSummary;
    backtest_request: any;
    prompt?: string;
    notices?: string[];
  },
  context: SingleAssetBuilderContext,
  currentParsed: ParsedSummary,
  currentBacktestRequest: any,
) {
  const targetStock = currentBacktestRequest?.target_stocks?.find(
    (stock: { symbol: string }) => stock.symbol === context.symbol,
  );

  return {
    ...data,
    parsed: {
      ...data.parsed,
      description: data.prompt
        ? buildSingleAssetBuilderPrompt(data.prompt, context)
        : data.parsed.description,
      universe: currentParsed.universe,
      target_symbols: [context.symbol],
      max_positions: 1,
      rebalancing_period: "none",
    },
    backtest_request: {
      ...data.backtest_request,
      symbols: [context.symbol],
      universe_id: null,
      backtest_mode: "single_asset",
      target_stocks: targetStock ? [targetStock] : [{ symbol: context.symbol }],
      risk: {
        ...(data.backtest_request?.risk ?? {}),
        max_positions: 1,
        position_size_pct: 100,
        ranking_enabled: false,
      },
    },
  };
}

function formatElapsedTime(startedAt: number, now: number): string {
  const totalSeconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}분 ${seconds}초` : `${seconds}초`;
}

function MetricOptimizationProgressIndicator({
  progress,
}: {
  progress: MetricOptimizationProgressState;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const intervalId = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(intervalId);
  }, []);

  const elapsed = formatElapsedTime(progress.startedAt, now);
  return (
    <div className="space-y-2 pt-1" data-testid="metric-optimization-progress">
      <div className="flex items-center justify-between gap-4 text-[11px] font-bold text-gray-300">
        <span>{progress.totalTrials}개 조합 계산 중</span>
        <span className="tabular-nums text-[var(--text-label)]">경과 {elapsed}</span>
      </div>
      <div
        role="progressbar"
        aria-label="파라미터 조합 계산 진행 상황"
        aria-valuetext={`${progress.totalTrials}개 조합 계산 중, 경과 ${elapsed}`}
        className="h-1.5 overflow-hidden rounded-full bg-white/[0.08]"
      >
        <div className="metric-optimization-progress-bar h-full w-1/3 rounded-full bg-[var(--chat-accent)]" />
      </div>
    </div>
  );
}

type MetricOptimizationParameter = {
  path: string;
  label: string;
  min: number;
  max: number;
};

type MetricOptimizationDraft = {
  phase: "parameter" | "range";
  baseStrategy: StrategyBacktestRequest;
  parameters: MetricOptimizationParameter[];
  selectedRanges: Record<string, MetricOptimizationRange>;
  pendingPath?: string;
};

function formatOptimizationValue(value: unknown, suffix = ""): string {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric.toFixed(2)}${suffix}` : "-";
}

function buildMetricOptimizationResultText(
  response: OptimizationResponse,
  metric: ResearchMetric,
  labels: Record<string, string>
): string {
  const rows = (response.top_results ?? []).slice(0, 5);
  const metricLabel = getResearchMetricLabel(metric);
  const resultLines = rows.map((row, index) => {
    const parameters = Object.entries(row.parameters)
      .map(([path, value]) => `${labels[path] ?? path} ${value}`)
      .join(" · ");
    return [
      `조합 ${index + 1}`,
      parameters || "파라미터 정보 없음",
      `${metricLabel} ${formatOptimizationValue(row.target_value)} · CAGR ${formatOptimizationValue(row.metrics?.cagr, "%")} · MDD ${formatOptimizationValue(row.metrics?.maxDrawdown, "%")}`,
    ].join("\n");
  });

  return [
    `${metricLabel} 기준으로 ${response.total_iterations ?? rows.length}회 계산을 마쳤습니다.`,
    ...resultLines,
  ].join("\n\n");
}

function shouldShowMovingAverageHelp(message: ChatMessage) {
  const suggestions = message.infoSuggestions ?? [];
  return (
    message.infoText?.includes("어떤 이동평균") ||
    (suggestions.includes("단순(SMA)") && suggestions.includes("지수(EMA)"))
  );
}

function MovingAverageTypeHelp() {
  return (
    <div className="group relative inline-flex self-center">
      <button
        type="button"
        aria-label="SMA와 EMA 설명"
        className="flex h-7 w-7 items-center justify-center rounded-full border border-white/[0.14] bg-white/[0.05] text-gray-300 transition-colors duration-200 hover:border-[var(--chat-accent-line)] hover:bg-white/[0.09] hover:text-[var(--chat-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)]"
      >
        <Question size={14} weight="bold" />
      </button>
      <div
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-30 mt-2 w-[min(18rem,calc(100vw-3rem))] -translate-x-1/2 rounded-2xl border border-[var(--chat-hairline)] bg-[#101010] p-3 text-left opacity-0 shadow-2xl shadow-black/50 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 sm:left-auto sm:right-0 sm:translate-x-0"
      >
        <p className="text-[11px] font-black text-[var(--text-label)]">이동평균 종류</p>
        <div className="mt-2 space-y-1.5 text-xs font-bold leading-relaxed text-gray-300">
          <p>
            <span className="text-white">SMA</span>는 단순 이동평균으로, 최근 N일 가격을 같은 비중으로 평균낸 값입니다.
          </p>
          <p>
            <span className="text-white">EMA</span>는 지수 이동평균으로, 최근 가격에 더 큰 비중을 두어 변화에 더 민감하게 반응합니다.
          </p>
        </div>
      </div>
    </div>
  );
}

type CoachConversationMessage = {
  role: "user" | "assistant";
  content: string;
};

// ── 대화 표면 위계 ──
// 카드는 위계를 전달할 때만 쓴다. 이전에는 사용자 발화·어시스턴트 산문·전략 요약·
// 공지·되묻기·에러 여섯 종류가 모두 같은 글래스 카드여서 서로 구별되지 않았다.
//   맨 텍스트          = 흘러가는 대화. 카드가 없다는 것 자체가 구분이다(세로 레일 없음)
//   카드              = 남는 산출물(요약·검증·공지·되묻기)
// 응답이 필요한 블록은 강조 레일 대신 강조색 아이콘과 선택 칩으로 알린다.
const USER_CHAT_BUBBLE_CLASS = "rounded-2xl rounded-tr-md bg-[var(--chat-user-surface)]";
const ARTIFACT_CARD_CLASS =
  "rounded-2xl border border-[var(--chat-hairline)] bg-[var(--chat-artifact-surface)]";
// '돌아가기'는 되돌릴 길을 잃지 않게 해주는 컨트롤이라 반드시 클릭 가능해 보여야 한다.
// 회색 텍스트만 두면 정적 캡션으로 읽혀 사용자가 찾지 못한다(2026-07-25 제보).
// 강조색은 '사용자 차례'에 예약돼 있으므로 색이 아니라 테두리·면·눌림으로 알린다.
const BACK_CONTROL_CLASS =
  "flex flex-shrink-0 items-center gap-1 rounded-xl border border-white/[0.14] bg-white/[0.05] px-2.5 py-1 text-[11px] font-bold text-gray-200 transition-colors duration-200 hover:bg-white/[0.09] hover:text-white active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)] disabled:opacity-40";
// 선택 칩은 빌더 흐름의 주 경로라 3순위 컨트롤보다 무게를 올린다.
const CHOICE_CHIP_CLASS =
  "rounded-lg border border-white/[0.14] bg-white/[0.05] px-2.5 py-1.5 text-[12px] font-bold text-gray-200 text-left transition-colors duration-200 hover:border-[var(--chat-accent-line)] hover:bg-white/[0.09] hover:text-white active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)]";
// 진입 연출은 클래스로 둔다 — 인라인 animation은 prefers-reduced-motion으로 끌 수 없다.
const MESSAGE_ENTER_CLASS = "chat-card-enter";
const MESSAGE_ENTER_LATE_CLASS = "chat-card-enter-late";
const SURFACE_ENTER_CLASS = "chat-enter";
const SURFACE_ENTER_LATE_CLASS = "chat-enter-late";

// 전략 검증은 규칙 기반이라 즉시 응답하지만, 분석이 진행 중임을 사용자가 인지하도록
// 최소 노출 시간을 둔다. 응답이 더 오래 걸리면 추가 지연 없이 그대로 표시한다.
const MIN_VALIDATION_DELAY_MS = 2400;

// Choice-only prompts can reopen the shared chat input without sending another answer.
const FREE_INPUT_CHIP = "직접 입력";
const NO_REBALANCING_CHIP = "안 함";
const BUILDER_BACK_CHIP = "뒤로가기";
const CONFIRM_STRATEGY_CHIP = "이 전략으로 확정";
const CONFIRMATION_BACK_CHIP = "돌아가기";

function withFreeInputSuggestion(suggestions: string[] | undefined): string[] | undefined {
  if (!suggestions?.length || suggestions.includes(FREE_INPUT_CHIP)) return suggestions;
  return [...suggestions, FREE_INPUT_CHIP];
}

function isBuilderUniverseStep(state: Record<string, any>): boolean {
  return !hasBuilderSlotValue(state.universe);
}

function withBuilderNavigationSuggestions(
  suggestions: string[] | undefined,
  state: Record<string, any>,
  canGoBack: boolean,
): string[] | undefined {
  if (!suggestions?.length) return suggestions;

  const withoutNavigation = suggestions.filter(
    (suggestion) => suggestion !== FREE_INPUT_CHIP && suggestion !== BUILDER_BACK_CHIP,
  );
  if (isBuilderUniverseStep(state)) return withoutNavigation;

  return [
    ...withoutNavigation,
    FREE_INPUT_CHIP,
    ...(canGoBack ? [BUILDER_BACK_CHIP] : []),
  ];
}

const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));

async function enforceMinValidationDelay(startedAt: number) {
  const elapsed = Date.now() - startedAt;
  if (elapsed < MIN_VALIDATION_DELAY_MS) {
    await sleep(MIN_VALIDATION_DELAY_MS - elapsed);
  }
}

function ShimmerStatusText({
  children,
  className = "",
}: {
  children: string;
  className?: string;
}) {
  return (
    <>
      <span className={`loading-shimmer-text ${className}`}>{children}</span>
      <style jsx>{`
        .loading-shimmer-text {
          color: transparent;
          background-image: linear-gradient(
            90deg,
            rgba(255, 255, 255, 0.28) 0%,
            rgba(255, 255, 255, 0.28) 42%,
            rgba(255, 255, 255, 0.98) 50%,
            rgba(255, 255, 255, 0.28) 58%,
            rgba(255, 255, 255, 0.28) 100%
          );
          background-size: 260% 100%;
          background-position: 180% 0;
          -webkit-background-clip: text;
          background-clip: text;
          animation: loading-shine 1.5s linear infinite;
        }

        @keyframes loading-shine {
          0% {
            background-position: 180% 0;
          }
          100% {
            background-position: -180% 0;
          }
        }

        /* styled-jsx 스코프 클래스라 globals.css의 감속 규칙이 이기지 못한다.
           같은 스코프 안에서 직접 끈다. */
        @media (prefers-reduced-motion: reduce) {
          .loading-shimmer-text {
            animation: none;
            color: rgba(255, 255, 255, 0.82);
            background-image: none;
            -webkit-background-clip: border-box;
            background-clip: border-box;
          }
        }
      `}</style>
    </>
  );
}

// 분석 로딩 단계별 표시 문구. 미설정이면 기본 '분석 중...'.
// validating: 룰 파싱이 애매해 LLM 검증기를 호출하는 동안 표시(ShimmerStatusText 애니메이션).
// searching: 빌더 용어 그라운딩이 인터넷 검색으로 낯선 테마 용어를 학습하는 동안 표시.
// kg_lookup: 개념 해석 체인(지식그래프·어휘집·내부 LLM)에서 용어를 확인하는 동안 표시.
const ANALYSIS_STAGE_LABEL: Record<"parsing" | "thinking" | "validating" | "searching" | "kg_lookup", string> = {
  parsing: "파싱 중...",
  thinking: "생각 중...",
  validating: "검증 중...",
  searching: "검색 중...",
  kg_lookup: "개념 확인 중...",
};

// 빌더 스텝 호출 — 프록시가 SSE(text/event-stream)를 돌려주면 stage 이벤트('searching' =
// 인터넷 검색 그라운딩 진입, FR-STR-069)를 onStage로 알리고 최종 result 데이터를 반환한다.
// JSON 응답(테스트 mock 등)은 기존 계약대로 그대로 반환해 호출부 코드가 동일하게 동작한다.
async function requestBuilderStepData(
  payload: Record<string, any>,
  onStage?: (stage: string) => void,
): Promise<any> {
  const res = await fetch("/api/strategy/builder/step", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error();
  const contentType = res.headers?.get?.("content-type") ?? "";
  if (!contentType.includes("text/event-stream") || !res.body) {
    return res.json();
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: any = null;
  let errorDetail: string | null = null;

  const handlePayload = (raw: string) => {
    if (raw === "[DONE]") return;
    let evt: any;
    try {
      evt = JSON.parse(raw);
    } catch {
      return;
    }
    if (evt.type === "stage" && evt.stage) onStage?.(evt.stage);
    else if (evt.type === "result") result = evt.data;
    else if (evt.type === "error") errorDetail = evt.detail ?? "빌더 응답 실패";
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = done ? "" : blocks.pop() ?? "";
    for (const block of blocks) {
      const line = block.split(/\r?\n/).find(l => l.startsWith("data: "));
      if (line) handlePayload(line.slice(6).trim());
    }
    if (done) break;
  }

  if (errorDetail !== null) throw new Error(errorDetail);
  if (result === null) throw new Error();
  return result;
}

const SPINNER_DOT_COUNT = 12;
const SPINNER_CYCLE_S = 1.2;

function LoadingSpinner({ className = "" }: { className?: string }) {
  return (
    <span className={`relative inline-block h-4 w-4 flex-shrink-0 ${className}`}>
      {Array.from({ length: SPINNER_DOT_COUNT }, (_, i) => (
        <span
          key={i}
          className="absolute left-1/2 top-1/2 -ml-[1.5px] -mt-[1.5px] h-[3px] w-[3px] rounded-full bg-gray-600 animate-dot-fill"
          style={{
            transform: `rotate(${(i * 360) / SPINNER_DOT_COUNT}deg) translateY(-6.5px)`,
            animationDelay: `${(i * SPINNER_CYCLE_S) / SPINNER_DOT_COUNT}s`,
          }}
        />
      ))}
    </span>
  );
}

function AnalysisStatusBubble({
  title,
  stage,
}: {
  title?: string;
  stage?: "parsing" | "thinking" | "validating" | "searching" | "kg_lookup";
}) {
  const label = stage ? ANALYSIS_STAGE_LABEL[stage] : "분석 중...";
  return (
    <div
      className={`flex max-w-[88%] items-center gap-2 py-1 ${MESSAGE_ENTER_LATE_CLASS}`}
    >
      <LoadingSpinner />
      {title && <span className="text-sm font-black text-white">{title}</span>}
      <ShimmerStatusText className="text-sm font-bold">{label}</ShimmerStatusText>
    </div>
  );
}

type AuthState = "loading" | "authenticated" | "anonymous";

type CurrentUserResponse = {
  user?: {
    name?: string | null;
    email?: string | null;
    avatarUrl?: string | null;
  } | null;
};

type LoginResponse = {
  error?: string;
  user?: {
    name?: string | null;
    email?: string | null;
    avatarUrl?: string | null;
  } | null;
};

function isSupabaseConfigured() {
  return Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL &&
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  );
}

function getSupabaseBrowserClient() {
  if (!isSupabaseConfigured()) {
    throw new Error("Supabase client environment variables are not configured.");
  }

  if (!analyticsSupabaseClient) {
    analyticsSupabaseClient = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL as string,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY as string,
      {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
        },
      }
    );
  }

  return analyticsSupabaseClient;
}

function FilterBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded-md border border-white/[0.08] bg-white/[0.05] px-2.5 py-0.5 text-xs font-bold text-gray-200">
      {label}
    </span>
  );
}

// 백테스트 기간 배지 라벨. 명시적 연도 범위가 있으면 '백테스트 2002~2005'처럼,
// 없으면 상대 기간('백테스트 5년')으로 표시한다.
function backtestPeriodLabel(parsed: ParsedSummary): string {
  const startYear = parsed.backtest_start_date?.slice(0, 4);
  const endYear = parsed.backtest_end_date?.slice(0, 4);
  if (startYear || endYear) {
    const range =
      startYear && endYear
        ? startYear === endYear
          ? startYear
          : `${startYear}~${endYear}`
        : startYear
          ? `${startYear}~`
          : `~${endYear}`;
    return `백테스트 ${range}`;
  }
  return `백테스트 ${PERIOD_LABELS[parsed.backtest_period]}`;
}

// 글자별 진입 연출. 순서는 CSS animation-delay 캐스케이드가 만든다 —
// 이전 구현은 38ms마다 React 상태를 갱신해 글자 수만큼 전체 리렌더를 냈고,
// prefers-reduced-motion도 존중할 수 없었다(인라인 style 연출).
function buildAnimatedHeadline(lines: string[]) {
  let charOffset = 0;

  return lines.map((line, lineIndex) => {
    const startIndex = charOffset;
    charOffset += line.length;

    return (
      <span
        key={`${line}-${lineIndex}`}
        className="block min-h-[1em] whitespace-normal lg:whitespace-nowrap"
      >
        {line.split("").map((char, charIndex) => (
          <span
            key={`${line}-${lineIndex}-${charIndex}`}
            className="chat-headline-char"
            style={{ "--char-index": String(startIndex + charIndex) } as React.CSSProperties}
          >
            {char === " " ? "\u00A0" : char}
          </span>
        ))}
      </span>
    );
  });
}

const HEADLINE_LINES = ["투자 아이디어를 전략으로 만들고", "전략을 시뮬레이션 하세요"];

function AnimatedHeadline({ lines }: { lines: string[] }) {
  return <>{buildAnimatedHeadline(lines)}</>;
}

type ChatInputHandle = {
  focus: () => void;
  clear: () => void;
};

type ChatInputBoxProps = {
  variant: "inline" | "fixed";
  containerClassName?: string;
  running: boolean;
  canSend: boolean;
  isLlmWorking: boolean;
  isStrategyInput: boolean;
  onSend: (text: string) => void;
  onReset?: () => void;
};

// 채팅 입력창을 격리한 메모 컴포넌트 — 키 입력마다 페이지 전체(메시지 목록 포함)가
// 리렌더링되지 않도록 입력 상태를 내부에서만 관리한다(모바일 입력 버벅임의 핵심 원인).
const ChatInputBox = memo(
  forwardRef<ChatInputHandle, ChatInputBoxProps>(function ChatInputBox(
    { variant, containerClassName = "", running, canSend, isLlmWorking, isStrategyInput, onSend, onReset },
    ref,
  ) {
    const [value, setValue] = useState("");
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useImperativeHandle(
      ref,
      () => ({
        focus: () => textareaRef.current?.focus(),
        clear: () => setValue(""),
      }),
      [],
    );

    useEffect(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }, [value]);

    const trySend = () => {
      const text = value.trim();
      if (!text || !canSend) return;
      setValue("");
      onSend(text);
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        trySend();
      }
    };

    const hasTypedInput = value.length > 0;
    const canSubmitInput = !!value.trim() && canSend;

    const textarea = (
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={running}
        rows={2}
        placeholder="어떤 투자 아이디어를 테스트해볼까요?"
        className="w-full resize-none bg-transparent px-5 pt-4 pb-12 text-sm font-bold leading-relaxed text-white outline-none placeholder:text-[var(--text-placeholder)] focus:outline-none focus:ring-0"
      />
    );

    const sendButton = (
      <div className="absolute bottom-3 right-3 flex items-center gap-2">
        <button
          onClick={trySend}
          disabled={!canSubmitInput}
          aria-label={isLlmWorking ? (isStrategyInput ? "전략 생성 중" : "전송 중") : (isStrategyInput ? "전략 생성" : "전송")}
          title={isLlmWorking ? (isStrategyInput ? "전략 생성 중" : "전송 중") : (isStrategyInput ? "전략 생성" : "전송")}
          className={`flex h-8 w-8 items-center justify-center rounded-full transition-colors duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)] ${
            isLlmWorking
              ? "cursor-wait bg-[#f3f1ec]"
              : hasTypedInput
                ? "bg-[#f3f1ec] text-[#2b2b2b] hover:bg-white active:scale-[0.96] disabled:cursor-not-allowed"
                : "cursor-not-allowed bg-[#595959] text-[#bdbdbd]"
          }`}
        >
          {isLlmWorking ? (
            <span className="h-3 w-3 rounded-[3px] bg-[#3a3a3a]" aria-hidden="true" />
          ) : (
            <ArrowUp size={15} weight="bold" />
          )}
        </button>
      </div>
    );

    if (variant === "inline") {
      return (
        <div
          className={`relative w-full rounded-[28px] border border-[var(--glass-border)] bg-[#101010] ${containerClassName}`}
        >
          {textarea}
          {sendButton}
        </div>
      );
    }

    return (
      <div
        className={`fixed bottom-4 left-4 right-4 z-40 mx-auto max-w-4xl rounded-[28px] border border-[var(--glass-border)] bg-[#101010] ${containerClassName}`}
      >
        {textarea}
        <button
          type="button"
          onClick={onReset}
          className="absolute bottom-3 left-3 inline-flex items-center gap-1.5 rounded-full border border-white/[0.14] bg-white/[0.05] px-3 py-1.5 text-xs font-bold text-[var(--accent-blue)] transition-colors duration-200 hover:bg-white/[0.09] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)]"
        >
          <X size={12} weight="bold" />
          대화 종료
        </button>
        {sendButton}
      </div>
    );
  }),
);

function BacktestRunningStatus({ message }: { message: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`relative isolate w-full overflow-hidden px-4 py-3 ${ARTIFACT_CARD_CLASS}`}
    >
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-0">
        <span className="backtest-aurora" />
      </div>
      <div className="relative z-10 flex items-center gap-3">
        <ArrowsClockwise
          size={18}
          className="flex-shrink-0 animate-spin text-[var(--chat-accent)] motion-reduce:animate-none"
        />
        <div className="min-w-0">
          <p className="text-xs font-black text-[var(--text-label)]">백테스트 진행 중</p>
          <p className="mt-0.5 text-sm font-bold text-white">
            {message || "백테스트 준비 중..."}
          </p>
        </div>
      </div>
      <style jsx>{`
        /* 이전에는 blue·mint·gold 세 개의 블롭이 mix-blend-mode: screen으로 겹쳐
           한 카드 안에서 강조색이 세 개였고, 백테스트가 도는 동안 blur(26px)
           레이어 3장이 계속 합성됐다. 강조색 하나, 블롭 하나로 줄인다.
           역동성은 레이어를 늘리지 않고 궤적으로 만든다 — 제자리 흔들림(±5%)
           대신 카드를 가로지르는 스윕에 회전·크기·밝기 변화를 얹는다. */
        .backtest-aurora {
          position: absolute;
          display: block;
          left: -10%;
          top: -92%;
          width: 58%;
          height: 190%;
          border-radius: 999px;
          filter: blur(26px);
          opacity: 0.5;
          background: radial-gradient(
            ellipse at center,
            rgba(240, 180, 41, 0.5) 0%,
            rgba(240, 180, 41, 0.16) 38%,
            rgba(240, 180, 41, 0) 72%
          );
          animation: backtestAuroraSweep 6.5s ease-in-out infinite;
          will-change: transform, opacity;
        }

        /* 왕복 구간마다 정지점(%)을 불규칙하게 둬 시계추처럼 보이지 않게 한다. */
        @keyframes backtestAuroraSweep {
          0% {
            transform: translate3d(-18%, 5%, 0) rotate(-14deg) scale(0.9);
            opacity: 0.3;
          }
          18% {
            transform: translate3d(24%, -4%, 0) rotate(-4deg) scale(1.08);
            opacity: 0.58;
          }
          40% {
            transform: translate3d(70%, 6%, 0) rotate(7deg) scale(0.96);
            opacity: 0.4;
          }
          62% {
            transform: translate3d(114%, -5%, 0) rotate(15deg) scale(1.14);
            opacity: 0.62;
          }
          82% {
            transform: translate3d(52%, 4%, 0) rotate(3deg) scale(1);
            opacity: 0.36;
          }
          100% {
            transform: translate3d(-18%, 5%, 0) rotate(-14deg) scale(0.9);
            opacity: 0.3;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .backtest-aurora {
            animation: none;
          }
        }
      `}</style>
    </div>
  );
}

function ParsedSummaryBubble({
  parsed,
  backtestRequest,
}: {
  parsed: ParsedSummary;
  backtestRequest?: {
    symbols?: string[];
    target_stocks?: Array<{ symbol: string; name?: string }> | null;
  } | null;
}) {
  const universeLabels = getDisplayUniverseLabels(parsed, backtestRequest);
  const isSingleAsset = (parsed.target_symbols?.length ?? 0) > 0;
  const exitLabels = getDisplayExitLabels(parsed);
  const rankingLabel = getRankingLabel(parsed);
  // 종목 선정(모멘텀 랭킹)도 진입(종목 선정) 기준이므로 '진입 신호'로 통일해 함께 표시한다.
  const entryLabels = [
    ...parsed.fundamental_filters.map(formatFundamentalFilter),
    ...parsed.entry_signals.map((s) => getSignalLabel(s, "entry")),
    ...(rankingLabel ? [rankingLabel] : []),
  ];

  return (
    <div className={`space-y-3 p-4 ${ARTIFACT_CARD_CLASS} ${MESSAGE_ENTER_CLASS}`}>
      <div className="flex items-center gap-1.5 border-b border-[var(--chat-hairline)] pb-2">
        <CheckCircle size={13} className="text-[var(--text-label)]" weight="fill" />
        <span className="text-xs font-black text-white">전략 요약</span>
      </div>
      <div className="space-y-2">
        {(parsed.universe.length > 0 || isSingleAsset) && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="w-14 flex-shrink-0 text-[11px] font-bold text-[var(--text-label)]">{isSingleAsset ? "대상 종목" : "유니버스"}</span>
            <div className="flex flex-wrap gap-1">
              {universeLabels.map((label, i) => (
                <FilterBadge key={i} label={label} />
              ))}
            </div>
          </div>
        )}
        {entryLabels.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="w-14 flex-shrink-0 text-[11px] font-bold text-[var(--text-label)]">{FUNDAMENTAL_FILTER_SECTION_LABEL}</span>
            <div className="flex flex-wrap gap-1">
              {entryLabels.map((label, i) => (
                <FilterBadge key={i} label={label} />
              ))}
            </div>
          </div>
        )}
        {exitLabels.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="w-14 flex-shrink-0 text-[11px] font-bold text-[var(--text-label)]">청산 신호</span>
            <div className="flex flex-wrap gap-1">
              {exitLabels.map((label, i) => (
                <FilterBadge key={i} label={label} />
              ))}
            </div>
          </div>
        )}
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className="w-14 flex-shrink-0 text-[11px] font-bold text-[var(--text-label)]">포트폴리오</span>
          <div className="flex flex-wrap gap-1">
            <FilterBadge label={getPositionLabel(parsed)} />
            {parsed.hold_period_days && <FilterBadge label={`${parsed.hold_period_days}일 보유`} />}
            {parsed.rebalancing_period !== "none" && <FilterBadge label={`${REBAL_LABELS[parsed.rebalancing_period]} 리밸런싱`} />}
            <FilterBadge label={backtestPeriodLabel(parsed)} />
            <FilterBadge label={`초기자금 ${formatInitialCapital(parsed.initial_capital ?? 10000000)}`} />
          </div>
        </div>
        {(parsed.stop_loss_pct || parsed.take_profit_pct || parsed.trailing_stop_pct) && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="w-14 flex-shrink-0 text-[11px] font-bold text-[var(--text-label)]">리스크</span>
            <div className="flex flex-wrap gap-1">
              {parsed.stop_loss_pct && <FilterBadge label={`손절 ${parsed.stop_loss_pct}%`} />}
              {parsed.take_profit_pct && <FilterBadge label={`익절 ${parsed.take_profit_pct}%`} />}
              {parsed.trailing_stop_pct && <FilterBadge label={`트레일링 스탑 ${parsed.trailing_stop_pct}%`} />}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function BuilderStrategyOverview({
  presentation,
}: {
  presentation: NonNullable<ChatMessage["builderPresentation"]>;
}) {
  return (
    <div data-testid="builder-strategy-summary">
      <section aria-label="현재까지 이해한 전략입니다">
        <p className="text-sm font-black tracking-wide text-gray-400">
          현재까지 이해한 전략입니다
        </p>
        {presentation.summaryItems.length > 0 ? (
          <dl className="mt-2 space-y-1.5">
            {presentation.summaryItems.map((item) => (
              <div key={`${item.label}-${item.value}`} className="flex gap-2 text-xs leading-relaxed">
                <dt className="flex-shrink-0 break-keep font-bold text-[var(--text-label)]">
                  {item.label}
                </dt>
                <dd className="flex flex-wrap items-center gap-1.5 font-bold text-gray-200">
                  <span>{item.value}</span>
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="mt-1.5 text-xs font-bold text-gray-300">
            첫 조건부터 하나씩 함께 정해보겠습니다.
          </p>
        )}
      </section>
    </div>
  );
}

function StrategyProgressPanel({ items }: { items: BuilderProgressItem[] }) {
  const completedCount = items.filter((item) => item.complete).length;
  const displayItems = getDisplayBuilderProgressItems(items);

  return (
    <aside
      aria-label="전략 진행률"
      aria-live="polite"
      className="relative z-20 w-full max-w-4xl rounded-2xl border border-[var(--chat-hairline)] bg-[var(--chat-artifact-surface)] p-4 xl:fixed xl:right-4 xl:top-[calc(var(--top-menu-bar-height,76px)+5rem)] xl:w-40 xl:max-w-none 2xl:w-56"
      data-testid="strategy-progress-panel"
    >
      <div className="flex items-end justify-between gap-3">
        <h2 className="text-xs font-black text-white">
          전략 진행률
        </h2>
        <span className="font-outfit text-[11px] font-black tabular-nums text-[var(--text-label)]">
          {completedCount}/{items.length}
        </span>
      </div>
      <ol className="mt-3 flex flex-col gap-2" data-testid="strategy-progress-list">
        {displayItems.map((item) => (
          <li
            key={item.label}
            aria-label={`${item.label}: ${item.complete ? "완료" : "진행 전"}`}
            className={`flex items-center gap-2 text-xs font-bold transition-colors duration-200 ${
              item.complete ? "text-[var(--chat-accent)]" : "text-[var(--text-label)]"
            }`}
            data-complete={item.complete ? "true" : "false"}
            data-progress-label={item.label}
          >
            {item.complete ? (
              <CheckCircle
                aria-hidden="true"
                className="flex-shrink-0 text-[var(--chat-accent)]"
                size={15}
                weight="fill"
              />
            ) : (
              <span
                aria-hidden="true"
                className="h-[15px] w-[15px] flex-shrink-0 rounded-full border border-white/20"
              />
            )}
            <span>{item.label}</span>
          </li>
        ))}
      </ol>
    </aside>
  );
}

function StrategyLabContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isChatPage = pathname === "/analytics/chat" || searchParams.get("chat") === "1";
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [authState, setAuthState] = useState<AuthState>("loading");
  const [isStartingGoogleLogin, setIsStartingGoogleLogin] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [isStrategyPreviewModalOpen, setIsStrategyPreviewModalOpen] = useState(false);
  const [stage, setStage] = useState<Stage>("idle");
  // SSE 스트림 처리 중(오래된 클로저)에도 현재 stage를 읽기 위한 ref — 후행 검증 교정
  // (parsed_updated)이 백테스트 실행 시작 이후 도착하면 무시하는 판정에 쓴다.
  const stageRef = useRef<Stage>("idle");
  stageRef.current = stage;
  const [latestParsed, setLatestParsed] = useState<ParsedSummary | null>(null);
  const [backtestReq, setBacktestReq] = useState<any>(null);
  const [currentOptions, setCurrentOptions] = useState<any>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [metricOptimizationProgress, setMetricOptimizationProgress] =
    useState<MetricOptimizationProgressState | null>(null);
  // 현재 표시 중인 result를 만들어낸 '실행된 요청' 스냅샷. 화면 상태(backtestReq)는
  // 사용자가 계속 대화하면 갱신되므로, 결과 배지는 이 스냅샷에서 파생해 표시↔실행을 일치시킨다.
  const [executedReq, setExecutedReq] = useState<any>(null);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [modelStatus, setModelStatus] = useState<{ status: string; error: string | null } | null>(null);
  const chatInputRef = useRef<ChatInputHandle>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const resultScrollRef = useRef<HTMLDivElement>(null);
  // 대화를 복원하거나 결과 화면에서 돌아온 직후 대화 끝까지 스크롤을 올린다.
  const pendingScrollToEndRef = useRef(false);
  // 입력창 회피 자동 스크롤은 '새 메시지'용이다. 복원·복귀 화면에서는 사용자가 다음 메시지를
  // 보낼 때까지 꺼 두고, 위치는 위 pendingScrollToEnd(최대 스크롤)가 정한다.
  const chatAutoScrollEnabledRef = useRef(false);
  const latestParsedRef = useRef<ParsedSummary | null>(null);
  const backtestReqRef = useRef<any>(null);
  const coachSessionIdRef = useRef<string | null>(null);
  const coachConversationRef = useRef<CoachConversationMessage[]>([]);
  const pendingPromptConsumedRef = useRef(false);
  // 인증 하이드레이션(loading) 중에 보낸 전략 프롬프트 — 완료 후 자동 재전송/모달 분기.
  const pendingAuthGatePromptRef = useRef<string | null>(null);
  // 진행 중이던 채팅을 한 번만 복원하기 위한 가드.
  const chatRestoredRef = useRef(false);
  const handleSendRef = useRef<(overrideText?: string) => Promise<void>>();
  const handleResetRef = useRef<() => void>();
  // memo된 ChatInputBox에 넘길 안정 콜백 — 최신 구현은 ref로 참조한다.
  const handleSendFromInput = useCallback((text: string) => {
    void handleSendRef.current?.(text);
  }, []);
  const handleResetFromInput = useCallback(() => {
    handleResetRef.current?.();
  }, []);
  // 직전에 언급된 종목 — '이 종목 팔까?' 같은 anaphora 해석용(분류 요청에 전달).
  const lastAnalyzedSymbolRef = useRef<string | null>(null);
  // first user prompt — kept for advisor context
  const firstPromptRef = useRef<string>("");
  // [규제 안전] 열린 종목 추천(STOCK_PICK) 전환 직후 진입하는 전략 빌더 모드.
  // 짧은 답변을 전략 필드로 누적하는 동안 true. 상태는 백엔드 step에 그대로 재전송한다.
  const builderModeRef = useRef(false);
  const builderStateRef = useRef<Record<string, any>>({});
  const builderHistoryRef = useRef<Array<Record<string, any>>>([]);
  const applyBuilderConfirmedStrategyRef =
    useRef<(data: BuilderConfirmedData, currentPrompt?: string) => void>();
  const pendingHoldingPeriodPromptRef = useRef<string | null>(null);
  const pendingHoldingPeriodHorizonRef = useRef<HoldingPeriodHorizon | null>(null);
  const pendingMetricResearchPromptRef = useRef<string | null>(null);
  const researchMetricRef = useRef<ResearchMetric | null>(null);
  const metricOptimizationDraftRef = useRef<MetricOptimizationDraft | null>(null);
  const metricOptimizationAbortRef = useRef<AbortController | null>(null);
  const explicitNoRebalancingRef = useRef(false);
  // 직전 planner ask 컨텍스트(백엔드 pending_ask) — 다음 파스 요청에 그대로 에코해
  // 칩 클릭의 결정론 귀속 근거로 쓴다(previous_coach_text와 같은 무상태 에코 계약).
  // 매 파스 응답마다 덮어써 스테일 컨텍스트를 남기지 않는다.
  const pendingAskRef = useRef<{ topic?: string | null; question: string; chips: string[] } | null>(null);
  // 사용자가 실제로 말한 설정 필드(백엔드 provenance) — 다음 파스 요청에 에코해 누적한다.
  // ParsedStrategy 왕복은 기본값을 물질화해 이 정보를 지우므로 별도 채널이 필요하다.
  // 프론트가 원문 정규식으로 같은 판정을 하던 계약 위반(hasExplicit*)의 대체다.
  const explicitFieldsRef = useRef<string[]>([]);
  // 빌더 칩-only 단계에서 '직접 입력'을 눌러 채팅창을 다시 띄운 상태(빌더는 진행하지 않음).
  const [builderFreeTextRequested, setBuilderFreeTextRequested] = useState(false);
  const [explicitNoRebalancing, setExplicitNoRebalancing] = useState(false);

  useEffect(() => {
    fetch("/api/model/status")
      .then((r) => r.json())
      .then(setModelStatus)
      .catch(() => setModelStatus({ status: "failed", error: "서버에 연결할 수 없습니다" }));
  }, []);

  // 진행 중이던 채팅 복원 — 대시보드 등 다른 페이지로 갔다가 돌아와도 대화가 유지되도록.
  useEffect(() => {
    if (chatRestoredRef.current) return;
    chatRestoredRef.current = true;
    // 새 채팅을 막 시작하는 중(대기 프롬프트 존재)이면 옛 상태를 복원하지 않는다.
    if (sessionStorage.getItem(PENDING_STRATEGY_PROMPT_KEY)) return;
    try {
      const raw = sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY);
      if (!raw) return;
      const snapshot = JSON.parse(raw);
      if (!Array.isArray(snapshot.messages) || snapshot.messages.length === 0) return;
      pendingScrollToEndRef.current = true;
      chatAutoScrollEnabledRef.current = false;
      setMessages(snapshot.messages as ChatMessage[]);
      setLatestParsed(snapshot.latestParsed ?? null);
      setBacktestReq(snapshot.backtestReq ?? null);
      setCurrentOptions(snapshot.currentOptions ?? null);
      setStage(snapshot.stage ?? "idle");
      setResult(snapshot.result ?? null);
      // 복원 시 실행된 요청은 스냅샷의 backtestReq(= 저장 시점의 실행 요청)와 일치한다.
      setExecutedReq(snapshot.executedReq ?? snapshot.backtestReq ?? null);
      firstPromptRef.current = snapshot.firstPrompt ?? "";
      coachConversationRef.current = snapshot.coachConversation ?? [];
      coachSessionIdRef.current = snapshot.coachSessionId ?? null;
      lastAnalyzedSymbolRef.current = snapshot.lastAnalyzedSymbol ?? null;
      builderModeRef.current = snapshot.builderMode ?? false;
      builderStateRef.current = snapshot.builderState ?? {};
      builderHistoryRef.current = Array.isArray(snapshot.builderHistory)
        ? snapshot.builderHistory
        : [];
      const restoredNoRebalancing = snapshot.explicitNoRebalancing === true;
      explicitNoRebalancingRef.current = restoredNoRebalancing;
      setExplicitNoRebalancing(restoredNoRebalancing);
      explicitFieldsRef.current = Array.isArray(snapshot.explicitFields)
        ? snapshot.explicitFields.filter((f: unknown): f is string => typeof f === "string")
        : [];
      pendingHoldingPeriodPromptRef.current = snapshot.pendingHoldingPeriodPrompt ?? null;
      pendingHoldingPeriodHorizonRef.current = snapshot.pendingHoldingPeriodHorizon ?? null;
      pendingMetricResearchPromptRef.current = snapshot.pendingMetricResearchPrompt ?? null;
      researchMetricRef.current = snapshot.researchMetric ?? null;
      metricOptimizationDraftRef.current = snapshot.metricOptimizationDraft ?? null;
    } catch {
      // 손상된 스냅샷은 무시한다.
    }
  }, []);

  useEffect(() => {
    let isMounted = true;

    const hydrateAuthState = async () => {
      try {
        const response = await fetch("/api/user", {
          cache: "no-store",
          credentials: "same-origin",
        });
        const data = (await response.json()) as CurrentUserResponse;

        if (!isMounted) return;
        if (data.user) {
          setAuthState("authenticated");
          return;
        }
      } catch {
        // Fall through to Supabase session fallback below.
      }

      if (!isSupabaseConfigured()) {
        if (isMounted) setAuthState("anonymous");
        return;
      }

      try {
        const { data } = await getSupabaseBrowserClient().auth.getSession();
        const accessToken = data.session?.access_token;

        if (!accessToken) {
          if (isMounted) setAuthState("anonymous");
          return;
        }

        const loginResponse = await fetch("/api/login", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "same-origin",
          body: JSON.stringify({ supabaseAccessToken: accessToken }),
        });
        const loginData = (await loginResponse.json()) as LoginResponse;

        if (!isMounted) return;
        setAuthState(loginResponse.ok && loginData.user ? "authenticated" : "anonymous");
      } catch {
        if (isMounted) {
          setAuthState("anonymous");
        }
      }
    };

    void hydrateAuthState();

    return () => {
      isMounted = false;
    };
  }, []);

  // 채팅 상태를 세션에 저장해, 페이지를 떠났다가 돌아와도 복원할 수 있게 한다.
  useEffect(() => {
    if (messages.length === 0) return;
    try {
      const persistableMessages = selectPersistableChatMessages(messages);
      if (persistableMessages.length === 0) return;
      const snapshot = {
        messages: persistableMessages,
        latestParsed,
        backtestReq,
        currentOptions,
        // 진행 중이던 백테스트는 복원할 수 없으므로 ready로 강등한다.
        stage: stage === "running" ? "ready" : stage,
        result,
        executedReq,
        firstPrompt: firstPromptRef.current,
        coachConversation: coachConversationRef.current,
        coachSessionId: coachSessionIdRef.current,
        lastAnalyzedSymbol: lastAnalyzedSymbolRef.current,
        builderMode: builderModeRef.current,
        builderState: builderStateRef.current,
        builderHistory: builderHistoryRef.current,
        explicitNoRebalancing,
        // provenance는 대화 상태의 일부다 — 복원하지 않으면 이미 답한 조건을 다시 묻거나,
        // 답한 조건의 칩을 눌러도 게이트가 다른 조건을 기대해 결정적 적용이 빗나간다.
        explicitFields: explicitFieldsRef.current,
        pendingHoldingPeriodPrompt: pendingHoldingPeriodPromptRef.current,
        pendingHoldingPeriodHorizon: pendingHoldingPeriodHorizonRef.current,
        pendingMetricResearchPrompt: pendingMetricResearchPromptRef.current,
        researchMetric: researchMetricRef.current,
        metricOptimizationDraft: metricOptimizationDraftRef.current,
      };
      sessionStorage.setItem(STRATEGY_CHAT_STATE_KEY, JSON.stringify(snapshot));
    } catch {
      // 용량 초과 등은 무시한다 — 복원은 best-effort.
    }
  }, [
    messages,
    latestParsed,
    backtestReq,
    currentOptions,
    stage,
    result,
    executedReq,
    explicitNoRebalancing,
  ]);

  useEffect(() => {
    if (messages.length === 0) return;

    const animationFrame = window.requestAnimationFrame(() => {
      // 복원·복귀 화면은 대화 끝(최대 스크롤)에서 시작한다.
      if (pendingScrollToEndRef.current) {
        pendingScrollToEndRef.current = false;
        scrollChatViewToEnd();
        // 요약 카드·버튼이 한 박자 늦게 렌더돼 문서가 길어지면 방금 위치가 끝이 아니게 된다.
        // 레이아웃이 자리를 잡은 뒤 한 번 더 끝으로 맞춘다.
        window.setTimeout(scrollChatViewToEnd, 300);
        return;
      }
      // 사용자가 다음 메시지를 보내기 전까지는 입력창 회피 자동 스크롤을 돌리지 않는다
      // — 위치는 위 pendingScrollToEnd(최대 스크롤)가 정한다.
      if (!chatAutoScrollEnabledRef.current) return;
      if (!messagesEndRef.current) return;
      const main = document.querySelector("main");
      const endRect = messagesEndRef.current.getBoundingClientRect();

      // 메시지 끝이 고정 입력창에 가리면 그만큼만 아래로 스크롤한다(과스크롤로 상단이
      // 잘리지 않도록 현재 위치 기준 상대 스크롤).
      if (main && main.scrollHeight > main.clientHeight) {
        const delta = computeChatScrollDelta(endRect.bottom, main.getBoundingClientRect().bottom);
        if (delta > 0) {
          main.scrollTo({ top: main.scrollTop + delta, behavior: "smooth" });
        }
      } else {
        const delta = computeChatScrollDelta(endRect.bottom, window.innerHeight);
        if (delta > 0) {
          window.scrollTo({ top: window.scrollY + delta, behavior: "smooth" });
        }
      }
    });

    return () => window.cancelAnimationFrame(animationFrame);
    // messages 외의 의존성 — 마지막 버블 아래에 붙는 요소('백테스트 시작하기' 버튼 등)는
    // 메시지가 아니라 isSending/backtestReq/stage가 바뀔 때 뒤늦게 렌더된다. 그때 다시
    // 여유를 확인하지 않으면 새로 생긴 버튼이 고정 입력창 뒤에 걸린 채로 남는다.
  }, [messages, isSending, backtestReq, stage]);

  useEffect(() => {
    latestParsedRef.current = latestParsed;
  }, [latestParsed]);

  useEffect(() => {
    backtestReqRef.current = backtestReq;
  }, [backtestReq]);

  const isIdle = messages.length === 0 && !isSending;
  // 전략 빌더 옵션 칩(infoSuggestions)이나 되묻기(clarification) 칩을 보여주는 동안에는
  // 채팅창을 숨겨 사용자가 선택에 집중하게 한다 — 칩과 자유 입력창이 동시에 보이면
  // "직접 입력" 칩을 눌러야 하는 이유가 불분명해지고, 열린 입력창이 마치 선택을
  // 무시한 채 또 물어보는 것처럼 오인되기 쉽다. "직접 입력"을 고르면 입력창이 나타난다.
  const shouldShowChatInput = shouldShowChatInputBox(messages, isIdle, builderFreeTextRequested);

  useEffect(() => {
    if (!shouldShowChatInput || stage === "running" || result) return;

    const animationFrame = window.requestAnimationFrame(() => {
      chatInputRef.current?.focus();
    });

    return () => window.cancelAnimationFrame(animationFrame);
  }, [shouldShowChatInput, stage, result]);

  const handleSuggestionClick = (text: string) => {
    // 칩 답변도 사용자가 대화를 이어가는 행동 — 자동 스크롤을 다시 켠다.
    chatAutoScrollEnabledRef.current = true;
    if (text === BUILDER_BACK_CHIP) {
      void handleBuilderBack();
      return;
    }

    const latestAssistant = [...messages]
      .reverse()
      .find((message) => message.role === "assistant");
    if (latestAssistant?.strategyConfirmation && text === CONFIRM_STRATEGY_CHIP) {
      void confirmDeterministicStrategy();
      return;
    }

    const currentParsed = latestParsedRef.current ?? latestParsed;
    const promptContext = getStrategyPromptContext();
    const missingCondition = getNextMissingBacktestCondition(currentParsed, {
      allowNoRebalancing: explicitNoRebalancingRef.current,
      explicitFields: explicitFieldsRef.current,
      requireExplicitConfiguration: true,
    });
    const deterministicChoice = currentParsed && missingCondition &&
      latestAssistant?.clarificationSuggestions?.includes(text)
      ? applyDeterministicConditionChoice({
          parsed: currentParsed,
          condition: missingCondition,
          choice: text,
        })
      : null;

    if (!deterministicChoice || !missingCondition || !currentParsed) {
      handleSend(text);
      return;
    }

    const userChoice = missingCondition.field === "rebalancing" &&
      text === NO_REBALANCING_CHIP
      ? "리밸런싱 안 함"
      : text;
    const nextPromptContext = [promptContext, userChoice].filter(Boolean).join("\n");
    const previousAllowNoRebalancing = explicitNoRebalancingRef.current;
    const previousExplicitFields = [...explicitFieldsRef.current];
    const allowNoRebalancing = missingCondition.field === "rebalancing"
      ? deterministicChoice.allowNoRebalancing === true
      : previousAllowNoRebalancing;
    explicitNoRebalancingRef.current = allowNoRebalancing;
    setExplicitNoRebalancing(allowNoRebalancing);
    // 칩 답변은 백엔드 왕복 없이 여기서 State에 적용된다 — 사용자가 바로 그 질문에
    // 답했으므로 그 필드를 명시로 기록하지 않으면 게이트가 같은 질문을 무한 반복한다.
    // (자유 서술은 파스 응답의 explicit_fields가 담당한다.)
    if (EXPLICIT_GATE_FIELDS.includes(missingCondition.field)) {
      explicitFieldsRef.current = Array.from(
        new Set([...explicitFieldsRef.current, missingCondition.field]),
      );
    }
    latestParsedRef.current = deterministicChoice.parsed;
    setLatestParsed(deterministicChoice.parsed);

    const nextMissingCondition = getNextMissingBacktestCondition(
      deterministicChoice.parsed,
      {
        allowNoRebalancing,
        explicitFields: explicitFieldsRef.current,
        requireExplicitConfiguration: true,
      },
    );
    const nextQuestion = nextMissingCondition?.question ??
      "모든 조건을 정했습니다. 현재까지의 전략을 확인하고 확정해 주세요.";
    const nextPresentation = withSingleAssetSummaryLabel(
      buildBuilderTurnPresentation({
        state: {},
        reply: nextQuestion,
        parsed: deterministicChoice.parsed,
        explicitFields: explicitFieldsRef.current,
        backtestRequest: backtestReqRef.current ?? backtestReq,
      }),
      deterministicChoice.parsed,
      backtestReqRef.current ?? backtestReq,
    );

    setMessages((previousMessages) => [
      ...previousMessages,
      { role: "user", content: userChoice },
      {
        role: "assistant",
        parsed: deterministicChoice.parsed,
        clarification: nextPresentation.question,
        clarificationSuggestions: nextMissingCondition?.suggestions ??
          [CONFIRM_STRATEGY_CHIP],
        builderPresentation: {
          summaryItems: nextPresentation.summaryItems,
          progressItems: nextPresentation.progressItems,
        },
        strategyConfirmation: nextMissingCondition === null,
        // 이 블록에 진입했다는 것은 직전에 답한 조건 버블이 이미 존재한다는 뜻이다(유니버스
        // 질문은 이 경로로 생성되지 않으므로 자연히 제외된다) — 항상 되돌아갈 상태를 남긴다.
        previousStepState: {
          parsed: currentParsed,
          allowNoRebalancing: previousAllowNoRebalancing,
          explicitFields: previousExplicitFields,
        },
      },
    ]);
  };

  const focusFreeTextInput = () => {
    setBuilderFreeTextRequested(true);
    window.setTimeout(() => chatInputRef.current?.focus(), 0);
  };

  const updateLastAssistant = (patch: Partial<ChatMessage>) => {
    setMessages(prev => {
      const lastIdx = prev.map((m, i) => m.role === "assistant" ? i : -1).filter(i => i >= 0).at(-1);
      if (lastIdx === undefined) return prev;
      return prev.map((m, i) => i === lastIdx ? { ...m, ...patch } : m);
    });
  };

  // 사용자 입력 버블은 어떤 네트워크 호출(분류/파싱)보다 먼저, 즉시 그린다.
  const appendUserMessage = (userText: string) => {
    // 사용자가 대화를 이어가는 순간부터 새 메시지 자동 스크롤(입력창 회피)을 다시 켠다.
    chatAutoScrollEnabledRef.current = true;
    flushSync(() => {
      setMessages(prev => [...prev, { role: "user", content: userText }]);
    });
  };

  // 사용자 버블이 이미 그려진 뒤, assistant 자리표시자를 한 틱 늦게 추가한다(등장 스태거).
  const appendAssistant = async (assistant: ChatMessage) => {
    await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
    setMessages(prev => [...prev, assistant]);
  };

  const rememberCoachExchange = (userText: string, coachText: string) => {
    const next: CoachConversationMessage[] = [
      ...coachConversationRef.current,
      { role: "user", content: userText },
      { role: "assistant", content: coachText },
    ];
    coachConversationRef.current = next.slice(-8);
  };

  const lastCoachText = () => {
    for (let i = coachConversationRef.current.length - 1; i >= 0; i--) {
      const message = coachConversationRef.current[i];
      if (message.role === "assistant") return message.content;
    }
    return null;
  };

  const getStrategyPromptContext = (currentPrompt = "") => [
    ...messages
      .filter((message) => message.role === "user" && message.content)
      .map((message) => message.content as string),
    currentPrompt,
  ]
    .filter(Boolean)
    .join("\n");

  // Start the builder immediately. For a recognized single asset, prefill its
  // universe internally and move straight to the entry-condition question.
  const startStrategyBuilder = async (
    { reuseExisting = false, seedText, seedParsed, seedBacktestRequest, researchMetric }: {
      reuseExisting?: boolean;
      seedText?: string;
      seedParsed?: ParsedSummary | null;
      seedBacktestRequest?: any;
      researchMetric?: ResearchMetric | null;
    } = {},
  ) => {
    // reuseExisting=true면 이미 떠 있는 '분석 중...' 자리표시자를 그대로 빌더 첫 질문으로 바꾼다
    // (빈 전략 파싱에서 전환할 때 빈 버블이 추가되지 않도록).
    // seedText: 빌더 진입 시점의 사용자 원본 메시지. 백엔드가 이미 말한 조건을 미리 채워
    // 빠진 질문만 묻도록 한다(상태가 비어 있을 때만 적용).
    // seedParsed: 파싱 파이프라인(룰→LLM 검증→LLM 폴백)이 이미 해석한 결과. 결정적 시드가
    // 놓친 필드(sector 등)를 빌더가 이어받아, 긴 꼬리 표현마다 regex를 늘리지 않게 한다.
    if (!reuseExisting) {
      await appendAssistant({ role: "assistant", isLoading: true, builderQuestion: true });
    }
    const singleAssetContext = getSingleAssetBuilderContext(
      seedParsed,
      seedBacktestRequest ?? backtestReqRef.current,
    );
    try {
      // 시드에 낯선 테마 용어가 있으면 백엔드가 개념 확인(kg_lookup)·인터넷 검색
      // 그라운딩(searching)에 진입할 수 있다 — stage 이벤트로 로딩 버블 문구를 바꾼다.
      const onBuilderStage = (stage: string) => {
        if (stage === "searching" || stage === "kg_lookup") {
          updateLastAssistant({ isLoading: true, loadingStage: stage });
        }
      };
      const requestBuilderStep = (state: Record<string, any>) => requestBuilderStepData({
        state,
        input: "",
        seed: seedText,
        ...(seedParsed ? { seed_parsed: seedParsed } : {}),
      }, onBuilderStage);

      const initialState = builderStateRef.current;
      let data = await requestBuilderStep(initialState);
      let nextState = mergeBuilderState(initialState, data.state);

      const valueStrategyState = applyParsedValueStrategySeed(nextState, seedParsed);
      if (valueStrategyState !== nextState && data.status !== "confirmed") {
        data = await requestBuilderStep(valueStrategyState);
        nextState = mergeBuilderState(valueStrategyState, data.state);
      }

      if (singleAssetContext && data.status !== "confirmed") {
        const singleAssetState = {
          ...nextState,
          // 백엔드 빌더의 단일 종목 모드(FR-STR-068b): 횡단면 질문(보유 수·리밸런싱)을
          // 건너뛰고 종목 프로파일 근거의 진입 방식 질문을 생성한다.
          single_symbol: singleAssetContext.symbol,
          single_label: singleAssetContext.label,
          universe: nextState.universe ?? singleAssetContext.builderUniverse,
          holding_count: 1,
          rebalance_cycle: nextState.rebalance_cycle ?? "none",
        };
        data = await requestBuilderStep(singleAssetState);
        nextState = mergeBuilderState(singleAssetState, data.state);
      }

      builderStateRef.current = nextState;
      if (
        data.status === "confirmed" &&
        data.parsed &&
        data.backtest_request &&
        applyBuilderConfirmedStrategyRef.current
      ) {
        const confirmedData =
          singleAssetContext && seedParsed
            ? mergeSingleAssetBuilderResult(
                data,
                singleAssetContext,
                seedParsed,
                seedBacktestRequest ?? backtestReqRef.current,
              )
            : data;
        builderModeRef.current = false;
        builderStateRef.current = {};
        builderHistoryRef.current = [];
        updateLastAssistant({
          isLoading: false,
          infoText: undefined,
          infoSuggestions: undefined,
          builderQuestion: false,
          builderPresentation: undefined,
        });
        applyBuilderConfirmedStrategyRef.current(confirmedData, seedText);
        return;
      }
      const activeResearchMetric = researchMetric ?? researchMetricRef.current;
      const isChoosingSingleAssetEntry =
        Boolean(singleAssetContext) && !builderStateRef.current.strategy_type;
      // 백엔드가 종목 프로파일 근거의 진입 방식 질문(신호 발생 횟수 포함)을 생성한다 —
      // 응답이 비어 있을 때만 정적 문구로 폴백한다.
      const reply =
        isChoosingSingleAssetEntry && !data.reply
          ? `${singleAssetContext?.label} 단일 종목 전략으로 설정했습니다. 어떤 진입 조건을 사용할까요?`
          : data.reply;
      const suggestions = withBuilderNavigationSuggestions(
        isChoosingSingleAssetEntry && !data.suggestions?.length
          ? ["골든크로스", "MACD", "돌파", "거래량 급증", "과매도 반등", FREE_INPUT_CHIP]
          : data.suggestions,
        builderStateRef.current,
        builderHistoryRef.current.length > 0,
      );
      const {
        question,
        ...builderPresentation
      } = buildBuilderTurnPresentation({
        state: builderStateRef.current,
        reply,
        parsed: seedParsed ?? latestParsedRef.current,
        explicitFields: explicitFieldsRef.current,
        backtestRequest: seedBacktestRequest ?? backtestReqRef.current,
      });
      updateLastAssistant({
        isLoading: false,
        infoText: activeResearchMetric
          ? `${buildResearchMetricIntro(activeResearchMetric)}\n\n${question}`
          : question,
        infoSuggestions: suggestions?.length ? suggestions : undefined,
        builderQuestion: true,
        builderPresentation,
      });
    } catch {
      // 호출 실패 시 거절하지 않는다 — 빌더 모드는 유지되어 다음 입력부터 정상 진행된다.
      const activeResearchMetric = researchMetric ?? researchMetricRef.current;
      if (singleAssetContext) {
        builderStateRef.current = {
          ...builderStateRef.current,
          single_symbol: singleAssetContext.symbol,
          single_label: singleAssetContext.label,
          universe: singleAssetContext.builderUniverse,
          holding_count: 1,
          rebalance_cycle: "none",
        };
      }
      const fallbackQuestion = singleAssetContext
        ? `${singleAssetContext.label} 단일 종목 전략으로 설정했습니다. 어떤 진입 조건을 사용할까요?`
        : "어떤 시장을 대상으로 할까요?";
      const {
        question,
        ...builderPresentation
      } = buildBuilderTurnPresentation({
        state: builderStateRef.current,
        reply: fallbackQuestion,
        parsed: seedParsed ?? latestParsedRef.current,
        explicitFields: explicitFieldsRef.current,
        backtestRequest: seedBacktestRequest ?? backtestReqRef.current,
      });
      updateLastAssistant({
        isLoading: false,
        infoText: activeResearchMetric
          ? `${buildResearchMetricIntro(activeResearchMetric)}\n\n${question}`
          : question,
        infoSuggestions: singleAssetContext
          ? withBuilderNavigationSuggestions(
              ["골든크로스", "MACD", "돌파", "거래량 급증", "과매도 반등", FREE_INPUT_CHIP],
              builderStateRef.current,
              builderHistoryRef.current.length > 0,
            )
          : undefined,
        builderQuestion: true,
        builderPresentation,
      });
    }
  };

  const handleBuilderBack = async () => {
    if (isSending) return;
    const previousState = builderHistoryRef.current.pop();
    if (!previousState) return;

    setBuilderFreeTextRequested(false);
    setIsSending(true);
    appendUserMessage(BUILDER_BACK_CHIP);
    await appendAssistant({ role: "assistant", isLoading: true, builderQuestion: true });

    try {
      const data = await requestBuilderStepData(
        { state: previousState, input: "" },
        (stage) => {
          if (stage === "searching" || stage === "kg_lookup") {
            updateLastAssistant({ isLoading: true, loadingStage: stage });
          }
        },
      );
      builderStateRef.current = mergeBuilderState(previousState, data.state);
      if (data.status === "exited") {
        builderModeRef.current = false;
        builderStateRef.current = {};
        builderHistoryRef.current = [];
      }
      const {
        question,
        ...builderPresentation
      } = buildBuilderTurnPresentation({
        state: builderStateRef.current,
        reply: data.reply,
        parsed: latestParsedRef.current,
        explicitFields: explicitFieldsRef.current,
        backtestRequest: backtestReqRef.current ?? backtestReq,
      });
      updateLastAssistant({
        isLoading: false,
        infoText: question,
        infoSuggestions: withBuilderNavigationSuggestions(
          data.suggestions,
          builderStateRef.current,
          builderHistoryRef.current.length > 0,
        ),
        builderQuestion: data.status !== "exited",
        builderPresentation: data.status !== "exited" ? builderPresentation : undefined,
      });
    } catch {
      builderHistoryRef.current.push(previousState);
      updateLastAssistant({
        isLoading: false,
        error: "이전 조건으로 돌아가지 못했습니다. 다시 시도해 주세요.",
        builderQuestion: true,
      });
    } finally {
      setIsSending(false);
    }
  };

  const metricOptimizationSuggestions = (draft: MetricOptimizationDraft): string[] => {
    const selectedPaths = new Set(Object.keys(draft.selectedRanges));
    const remaining = draft.parameters
      .filter((parameter) => !selectedPaths.has(parameter.path))
      .map((parameter) => parameter.label);
    return Object.keys(draft.selectedRanges).length > 0
      ? [...remaining, RUN_METRIC_OPTIMIZATION_CHIP]
      : remaining;
  };

  const prepareMetricOptimization = (baseStrategy: StrategyBacktestRequest): MetricOptimizationDraft | null => {
    const ranges = buildWalkForwardParameterRanges(baseStrategy);
    const parameters = buildWalkForwardParameterDescriptors(baseStrategy, ranges)
      .map((descriptor) => {
        const bounds = walkForwardRangeBoundsForPath(ranges, descriptor.path);
        return bounds ? { ...descriptor, ...bounds } : null;
      })
      .filter((parameter): parameter is MetricOptimizationParameter => parameter !== null);
    if (parameters.length === 0) return null;

    const draft: MetricOptimizationDraft = {
      phase: "parameter",
      baseStrategy,
      parameters,
      selectedRanges: {},
    };
    metricOptimizationDraftRef.current = draft;
    return draft;
  };

  const runMetricOptimization = async (draft: MetricOptimizationDraft) => {
    const metric = researchMetricRef.current;
    if (!metric) return;

    const metricLabel = getResearchMetricLabel(metric);
    const controller = new AbortController();
    metricOptimizationAbortRef.current = controller;
    setMetricOptimizationProgress({ startedAt: Date.now(), totalTrials: 30 });
    await appendAssistant({
      role: "assistant",
      infoText: `${metricLabel} 기준으로 30개 파라미터 조합을 계산하고 있습니다.`,
      infoSuggestions: [CANCEL_METRIC_OPTIMIZATION_CHIP],
    });

    try {
      const response = await fetch(`${OPTIMIZATION_BACKEND_URL.replace(/\/$/, "")}/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_strategy: {
            ...draft.baseStrategy,
            symbols: draft.baseStrategy.symbols ?? [],
          },
          user_prompt: firstPromptRef.current,
          target_metric: metric,
          n_trials: 30,
          ranges: draft.selectedRanges,
        }),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({})) as OptimizationResponse & { detail?: string };
      if (!response.ok) throw new Error(data.detail ?? data.message ?? "파라미터 계산에 실패했습니다.");
      if (!data.top_results?.length) throw new Error("계산된 파라미터 조합이 없습니다.");

      const labels = Object.fromEntries(draft.parameters.map((parameter) => [parameter.path, parameter.label]));
      metricOptimizationDraftRef.current = null;
      updateLastAssistant({
        infoText: buildMetricOptimizationResultText(data, metric, labels),
        infoSuggestions: undefined,
      });
    } catch (error) {
      const cancelled = error instanceof Error && error.name === "AbortError";
      updateLastAssistant({
        infoText: cancelled
          ? "파라미터 계산을 취소했습니다."
          : `파라미터 계산을 완료하지 못했습니다: ${error instanceof Error ? error.message : "알 수 없는 오류"}`,
        infoSuggestions: [RUN_METRIC_OPTIMIZATION_CHIP],
      });
    } finally {
      metricOptimizationAbortRef.current = null;
      setMetricOptimizationProgress(null);
    }
  };

  const handleMetricOptimizationInput = async (userText: string) => {
    const draft = metricOptimizationDraftRef.current;
    if (!draft) return;

    if (draft.phase === "parameter") {
      if (userText === RUN_METRIC_OPTIMIZATION_CHIP) {
        if (Object.keys(draft.selectedRanges).length === 0) {
          await appendAssistant({
            role: "assistant",
            infoText: "계산할 파라미터를 먼저 선택해 주세요.",
            infoSuggestions: metricOptimizationSuggestions(draft),
          });
          return;
        }
        await runMetricOptimization(draft);
        return;
      }

      const parameter = draft.parameters.find((candidate) => candidate.label === userText);
      if (!parameter) {
        await appendAssistant({
          role: "assistant",
          infoText: "계산할 파라미터를 아래에서 선택해 주세요.",
          infoSuggestions: metricOptimizationSuggestions(draft),
        });
        return;
      }

      draft.phase = "range";
      draft.pendingPath = parameter.path;
      await appendAssistant({
        role: "assistant",
        infoText: `${parameter.label}의 계산 범위를 최소값 ~ 최대값 형식으로 입력해 주세요.`,
        infoSuggestions: [`${parameter.min} ~ ${parameter.max}`, FREE_INPUT_CHIP],
      });
      return;
    }

    const parameter = draft.parameters.find((candidate) => candidate.path === draft.pendingPath);
    const range = parseMetricOptimizationRange(userText);
    if (!parameter || !range || range.min < parameter.min || range.max > parameter.max) {
      await appendAssistant({
        role: "assistant",
        infoText: parameter
          ? `${parameter.label} 범위는 ${parameter.min} ~ ${parameter.max} 안에서 최소값보다 최대값이 크게 입력되어야 합니다.`
          : "파라미터 범위를 다시 선택해 주세요.",
        infoSuggestions: parameter
          ? [`${parameter.min} ~ ${parameter.max}`, FREE_INPUT_CHIP]
          : metricOptimizationSuggestions(draft),
      });
      return;
    }

    draft.selectedRanges[parameter.path] = range;
    draft.phase = "parameter";
    draft.pendingPath = undefined;
    const selectedCount = Object.keys(draft.selectedRanges).length;
    const canAddMore = selectedCount < MAX_METRIC_OPTIMIZATION_PARAMETERS;
    await appendAssistant({
      role: "assistant",
      infoText: canAddMore
        ? `${parameter.label} 범위를 ${range.min} ~ ${range.max}로 설정했습니다. 다른 파라미터를 추가하거나 계산을 시작해 주세요.`
        : `${MAX_METRIC_OPTIMIZATION_PARAMETERS}개 파라미터 범위를 설정했습니다. 계산을 시작해 주세요.`,
      infoSuggestions: canAddMore
        ? metricOptimizationSuggestions(draft)
        : [RUN_METRIC_OPTIMIZATION_CHIP],
    });
  };

  const classifyConversationPrompt = async (userText: string) => {
    const history = selectClassifierHistory(messages);
    try {
      const res = await fetch("/api/query/classify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: userText,
          last_symbol: lastAnalyzedSymbolRef.current,
          history,
        }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      const classification: SemanticClassification = {
        intent: data.intent,
        symbol: data.symbols?.[0]?.symbol ?? null,
        suggestedReply: data.suggested_reply ?? null,
      };
      return { classification, history };
    } catch {
      return {
        classification: { intent: "STRATEGY_ADVICE" as const },
        history,
      };
    }
  };

  // 전략 프롬프트를 파싱→백테스트 준비→코치까지 스트리밍 처리한다. 일반 입력과
  // 전략 빌더 확정(합성 프롬프트) 양쪽에서 공유한다. isSending은 호출 측이 관리한다.
  const runStrategyParseFlow = async (
    promptText: string,
    currentParsed: ParsedSummary | null,
    currentBacktestReq: any,
    strategyAssumptions: StrategyAssumptions = {},
  ) => {
    // NL 파서 규칙 파싱 단계 — 'parsing...' 표시. LLM 폴백 시 'thinking...'으로 전환된다.
    updateLastAssistant({ isLoading: true, loadingStage: "parsing" });
    const res = await fetch("/api/strategy/parse/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: promptText,
        backend: "ollama",
        ...(currentParsed ? { previous_parsed: currentParsed } : {}),
        // 코치 맥락 리스크 해석을 백엔드가 하도록 직전 코치 문장을 넘긴다(수정 모드).
        // "익절 추천" 뒤 "10%" 같은 필드 없는 답을 백엔드가 코치 맥락으로 귀속한다(FR-STR-019e).
        ...(currentParsed ? { previous_coach_text: lastCoachText() } : {}),
        // 직전 planner ask 컨텍스트 에코 — 입력이 이 칩과 정확히 일치하면 백엔드가
        // 결정론 칩 답변 레인(LLM 생략)으로 State에 반영한다(Phase 4 후속 ①).
        ...(currentParsed && pendingAskRef.current ? { pending_ask: pendingAskRef.current } : {}),
        previous_explicit_fields: explicitFieldsRef.current,
      }),
    });
    if (!res.ok || !res.body) {
      const err = await res.json();
      throw new Error(err.detail ?? "파싱 실패");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let parsedPayload: any = null;
    let finalizedParsed: ParsedSummary | null = null;
    let finalizedBacktestRequest: any = null;
    let parseClarification: string | null = null;
    let shouldRouteSingleAssetToBuilder = false;

    // 요약 카드 메시지를 인덱스로 고정한다. 후행 검증 교정(parsed_updated)이 도착할 때는
    // 이미 코치 버블이 뒤에 추가돼 있으므로, updateLastAssistant로는 코치 버블을 덮어쓴다.
    // 캡처한 인덱스로 갱신해 요약 카드만 조용히 갱신되도록 한다.
    let summaryMessageIndex: number | null = null;
    const applySummaryPatch = (patch: Partial<ChatMessage>) => {
      setMessages(prev => {
        if (summaryMessageIndex === null) {
          summaryMessageIndex =
            prev.map((m, i) => (m.role === "assistant" ? i : -1)).filter(i => i >= 0).at(-1) ?? null;
        }
        if (summaryMessageIndex === null) return prev;
        return prev.map((m, i) => (i === summaryMessageIndex ? { ...m, ...patch } : m));
      });
    };

    // 파싱 결과가 확정되면(요약 카드 표시 직후) 코치 검증을 곧바로 착수한다. 후행 LLM
    // 검증이 스트림을 붙잡고 있어도 '전략 검증'이 몇 초씩 늦게 뜨지 않도록, 스트림 종료
    // ([DONE])를 기다리지 않는다.
    let coachStarted = false;
    const maybeStartCoachValidation = () => {
      if (
        coachStarted ||
        !finalizedParsed ||
        parseClarification ||
        shouldRouteSingleAssetToBuilder ||
        researchMetricRef.current
      ) return;
      coachStarted = true;
      setMessages(prev => [...prev, { role: "assistant", coachLoading: true, coachText: "" }]);
      generateCoachResponse({ userText: promptText, parsed: finalizedParsed });
    };

    const finalizeParse = (backtestRequest: any, symbolCount?: number | null) => {
      if (!parsedPayload) return;
      const assumedHoldingPeriod = strategyAssumptions.holdingPeriodDays;
      const nextBacktestRequest = backtestRequest
        ? {
            ...backtestRequest,
            symbol_count: symbolCount ?? backtestRequest.symbol_count,
            ...(assumedHoldingPeriod
              ? {
                  risk: {
                    ...(backtestRequest.risk ?? {}),
                    max_holding_days: assumedHoldingPeriod,
                  },
                }
              : {}),
          }
        : backtestRequest;
      const nextParsedPayload = assumedHoldingPeriod
        ? { ...parsedPayload.parsed, hold_period_days: assumedHoldingPeriod }
        : parsedPayload.parsed;
      const mergedResponse = mergeStrategyModification({
        previousParsed: currentParsed,
        nextParsed: nextParsedPayload,
        previousBacktestRequest: currentBacktestReq,
        nextBacktestRequest,
        userPrompt: promptText,
        riskOverrides: parsedPayload.risk_overrides ?? null,
      });

      const nextParsed = mergedResponse.parsed;
      const nextBacktestReq = mergedResponse.backtestRequest;

      coachSessionIdRef.current = null;
      // 전략을 수정해도 코치 대화 기록은 유지한다 — 이미 설명한 전문용어를 다시 설명하지 않도록.
      finalizedParsed = nextParsed;
      finalizedBacktestRequest = nextBacktestReq;
      setLatestParsed(nextParsed);
      setBacktestReq(nextBacktestReq);
      setCurrentOptions({
        period: nextBacktestReq?.period ?? "5y",
        initialCapital: nextBacktestReq?.risk?.init_cash ?? 10000000,
        commissionPct: 0.015,
        slippagePct: 0.05,
      });
      setStage("ready");

      // provenance 누적을 되묻기 게이트 계산보다 **먼저** 갱신한다 — 순서가 뒤바뀌면
      // 게이트가 이전 턴(빈) 목록을 보고 이미 답한 설정을 다시 묻는다.
      explicitFieldsRef.current = parsedPayload.explicit_fields ?? explicitFieldsRef.current;

      const promptContext = getStrategyPromptContext(promptText);
      const explicitMissingCondition = getNextMissingBacktestCondition(nextParsed, {
        explicitFields: explicitFieldsRef.current,
        requireExplicitConfiguration: true,
      });
      // 우선순위 마커(clarification_priority)가 실린 백엔드 질문 — 테마 유니버스(FR-STR-071/072)·
      // 미해결 업종/테마(sector_unresolved: 되묻기 또는 검색 후 '관련주를 찾을 수 없음' 종결
      // 안내) — 은 유니버스 범위를 정하는 선행 결정이라 explicit 설정 게이트의 시장 질문보다
      // 먼저 보여준다. 게이트가 삼키면 '리센즈 관련주'처럼 검색으로도 못 찾은 테마가 조용히
      // 일반 시장 질문으로 강등된다(2026-07-26 회귀).
      // planner ask 컨텍스트 저장 — 다음 파스 요청이 그대로 에코한다. 없으면 null로
      // 덮어써 이전 턴의 스테일 컨텍스트가 다음 칩 판정에 쓰이지 않게 한다.
      pendingAskRef.current = parsedPayload.pending_ask ?? null;
      const priorityClarification =
        parsedPayload.clarification_priority &&
        parsedPayload.clarification_question
          ? {
              question: parsedPayload.clarification_question as string,
              suggestions: (parsedPayload.clarification_suggestions ?? []) as string[],
              missingCondition: null,
            }
          : null;
      let presentedClarification = priorityClarification ?? (explicitMissingCondition
        ? {
            question: explicitMissingCondition.question,
            suggestions: explicitMissingCondition.suggestions,
            missingCondition: explicitMissingCondition,
          }
        : presentStrategyClarification({
            prompt: promptContext,
            parsed: nextParsed,
            backendQuestion: parsedPayload.clarification_question,
            backendSuggestions: parsedPayload.clarification_suggestions,
          }));
      if (
        explicitNoRebalancingRef.current &&
        presentedClarification?.missingCondition?.field === "rebalancing"
      ) {
        const nextMissingCondition = getNextMissingBacktestCondition(nextParsed, {
          allowNoRebalancing: true,
          explicitFields: explicitFieldsRef.current,
          requireExplicitConfiguration: true,
        });
        presentedClarification = nextMissingCondition
          ? {
              question: nextMissingCondition.question,
              suggestions: nextMissingCondition.suggestions,
              missingCondition: nextMissingCondition,
            }
          : null;
      }
      const clarificationTurn = presentedClarification
        ? buildBuilderTurnPresentation({
            state: {},
            reply: presentedClarification.question,
            parsed: nextParsed,
            explicitFields: explicitFieldsRef.current,
            backtestRequest: nextBacktestReq,
          })
        : null;
      const clarificationText = clarificationTurn?.question ?? null;
      const clarificationSuggestions = presentedClarification?.suggestions;
      parseClarification = clarificationText;
      shouldRouteSingleAssetToBuilder = shouldContinueWithSingleAssetBuilder(
        nextParsed,
      );
      const optimizationDraft = researchMetricRef.current && !clarificationText && nextBacktestReq
        ? prepareMetricOptimization(nextBacktestReq)
        : null;
      if (shouldRouteSingleAssetToBuilder) {
        return;
      }
      // 첫 문장으로 사용자의 자연어를 전략 개념으로 재정리해 되돌려준다("…전략이군요.").
      // 지표 연구 질문(researchMetric)은 전략 선언이 아니므로 제외한다.
      const restatement = researchMetricRef.current
        ? null
        : buildStrategyRestatement(nextParsed, explicitFieldsRef.current);
      applySummaryPatch({
        isLoading: false,
        restatement: restatement ?? undefined,
        infoText: researchMetricRef.current
          ? `${buildResearchMetricSummary(researchMetricRef.current)}${
              optimizationDraft
                ? "\n\n실제로 비교할 파라미터를 선택해 주세요. 최대 3개까지 설정할 수 있습니다."
                : ""
            }`
          : undefined,
        infoSuggestions: optimizationDraft
          ? metricOptimizationSuggestions(optimizationDraft)
          : undefined,
        parsed: nextParsed,
        clarification: clarificationText ?? undefined,
        clarificationSuggestions: clarificationText ? clarificationSuggestions : undefined,
        builderPresentation: clarificationTurn
          ? {
              summaryItems: clarificationTurn.summaryItems,
              progressItems: clarificationTurn.progressItems,
            }
          : undefined,
        notices: parsedPayload.notices?.length ? parsedPayload.notices : undefined,
      });
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const chunk of parts) {
        const line = chunk.split("\n").find(l => l.startsWith("data: "));
        if (!line) continue;
        const payload = line.slice(6).trim();
        if (payload === "[DONE]") continue;
        const evt = JSON.parse(payload);

        if (evt.type === "skeleton") {
          // 구조 분석 스켈레톤은 표시하지 않는다 — 파싱이 끝날 때까지 단계 문구만 노출한다.
        } else if (evt.type === "stage") {
          // 백엔드 진행 단계: 'parsing'(규칙 파싱) → 'kg_lookup'(개념 확인) →
          // 'searching'(용어 그라운딩 인터넷 검색) → 'thinking'(LLM 처리) → 'validating'(LLM 검증).
          if (evt.stage === "parsing" || evt.stage === "kg_lookup" || evt.stage === "searching" || evt.stage === "thinking" || evt.stage === "validating") {
            updateLastAssistant({ isLoading: true, loadingStage: evt.stage });
          }
        } else if (evt.type === "parsed_final") {
          parsedPayload = evt;
        } else if (evt.type === "dsl_ready") {
          finalizeParse(evt.backtest_request, evt.symbol_count);
          // 요약 카드 표시 직후 코치 검증 착수 — 후행 검증이 스트림을 붙잡아도 지연 없이.
          maybeStartCoachValidation();
        } else if (evt.type === "parsed_updated") {
          // 후행 LLM 검증 교정본 — 룰 파스 결과를 이미 표시한 뒤 도착한다. 사용자가 이미
          // 백테스트를 실행했으면 무시(실행 스냅샷 일관성), 아니면 parsed_final과 동일한
          // 파이프라인으로 전략·요청을 조용히 갱신한다.
          if (stageRef.current !== "running" && stageRef.current !== "done") {
            parsedPayload = evt;
            finalizeParse(evt.backtest_request, evt.symbol_count);
          }
        } else if (evt.type === "error") {
          throw new Error(evt.detail ?? "파싱 실패");
        }
      }
    }

    // 결과(parsed_final) 없이 스트림이 끝났다 = 프록시/서버 타임아웃으로 끊긴 것
    // (LLM 콜드스타트 ~101s vs 프록시 스트림 예산 120s). 조용히 로딩 상태로 방치하지
    // 않고 오류로 승격해 '다시 시도' 버튼이 뜨게 한다 — 재시도 시점엔 웜 상태라 빠르다.
    if (!parsedPayload) {
      throw new Error(
        "분석 서버 응답이 시간 안에 도착하지 않았어요. 서버가 준비 중일 수 있으니 잠시 후 다시 시도해 주세요.",
      );
    }

    if (shouldRouteSingleAssetToBuilder && finalizedParsed) {
      builderModeRef.current = true;
      await startStrategyBuilder({
        reuseExisting: true,
        seedText: promptText,
        seedParsed: finalizedParsed,
        seedBacktestRequest: finalizedBacktestRequest,
      });
      return;
    }

    // 스트림이 끝난 시점에도 아직 코치가 시작되지 않았으면(예: dsl_ready 없이 종료) 착수한다.
    maybeStartCoachValidation();
  };

  const confirmDeterministicStrategy = async () => {
    if (isSending || stage === "running") return;

    const completedPrompt = getStrategyPromptContext();
    const confirmedParsed = latestParsedRef.current ?? latestParsed;
    setBuilderFreeTextRequested(false);
    setIsSending(true);
    appendUserMessage(CONFIRM_STRATEGY_CHIP);
    await appendAssistant({ role: "assistant", isLoading: true });

    try {
      // 확정 시 대화 전체를 LLM에 재파싱시키지 않는다 — 재해석은 규칙 파서가 표현 못 하는
      // 조건(예: '영업이익 흑자' 필터)을 비결정적으로 잃어 완성 전략의 매수 조건을 다시
      // 되묻는 사고로 이어진다. 누적 parsed를 진실로 삼아 컴파일만 요청한다(특화 빌더의
      // '재파싱 왕복 없이 그대로 적용'과 같은 계약).
      if (confirmedParsed) {
        const res = await fetch("/api/strategy/compile", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ parsed: confirmedParsed }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({} as { detail?: string }));
          throw new Error(err.detail ?? "전략 확정에 실패했습니다.");
        }
        const data = await res.json();
        applyBuilderConfirmedStrategy({
          parsed: data.parsed,
          backtest_request: data.backtest_request,
          notices: data.notices,
          prompt: completedPrompt,
        });
      } else {
        await runStrategyParseFlow(completedPrompt, null, null);
      }
    } catch (error) {
      updateLastAssistant({
        isLoading: false,
        error: error instanceof Error ? error.message : "전략 확정에 실패했습니다.",
      });
    } finally {
      setIsSending(false);
    }
  };

  const returnToPreviousCondition = (message: ChatMessage) => {
    if (isSending) return;
    const previous = message.previousStepState;
    if (!previous) return;

    setBuilderFreeTextRequested(false);
    latestParsedRef.current = previous.parsed;
    setLatestParsed(previous.parsed);
    explicitNoRebalancingRef.current = previous.allowNoRebalancing;
    setExplicitNoRebalancing(previous.allowNoRebalancing);
    explicitFieldsRef.current = [...previous.explicitFields];
    setMessages((previousMessages) => {
      const currentIndex = previousMessages.length - 1;
      const selectedConditionIndex = previousMessages
        .slice(0, currentIndex)
        .map((m, index) => (m.role === "user" ? index : -1))
        .filter((index) => index >= 0)
        .at(-1);

      return previousMessages.filter(
        (_, index) => index !== currentIndex && index !== selectedConditionIndex,
      );
    });
  };

  // [전략별 특화 빌더] 빌더가 DSL을 직접 구성해 내려준 완성 전략을 한국어 재파싱 왕복 없이
  // 그대로 적용한다(파라미터 유실 방지). parsed는 ParsedStrategy dump = ParsedSummary와 동형,
  // backtest_request는 엔진 요청. runStrategyParseFlow.finalizeParse의 적용부와 동일한 효과.
  const applyBuilderConfirmedStrategy = (
    data: BuilderConfirmedData,
    currentPrompt = "",
  ) => {
    coachSessionIdRef.current = null;
    setLatestParsed(data.parsed);
    setBacktestReq(data.backtest_request);
    setCurrentOptions({
      period: data.backtest_request?.period ?? "5y",
      initialCapital: data.backtest_request?.risk?.init_cash ?? 10000000,
      commissionPct: 0.015,
      slippagePct: 0.05,
    });
    setStage("ready");
    explicitFieldsRef.current = Array.from(
      new Set([
        ...explicitFieldsRef.current,
        ...builderStateExplicitFields(builderStateRef.current),
      ]),
    );
    const promptContext = getStrategyPromptContext(currentPrompt);
    const missingCondition = getNextMissingBacktestCondition(data.parsed, {
      allowNoRebalancing: explicitNoRebalancingRef.current,
      explicitFields: explicitFieldsRef.current,
      requireExplicitConfiguration: true,
    });
    if (missingCondition) {
      const {
        question,
        ...builderPresentation
      } = buildBuilderTurnPresentation({
        state: {},
        reply: missingCondition.question,
        parsed: data.parsed,
        explicitFields: explicitFieldsRef.current,
        backtestRequest: data.backtest_request,
      });
      updateLastAssistant({
        isLoading: false,
        infoText: undefined,
        infoSuggestions: undefined,
        parsed: data.parsed,
        clarification: question,
        clarificationSuggestions: missingCondition.suggestions,
        builderPresentation,
        notices: data.notices?.length ? data.notices : undefined,
      });
      return;
    }
    const optimizationDraft = researchMetricRef.current
      ? prepareMetricOptimization(data.backtest_request)
      : null;
    updateLastAssistant({
      isLoading: false,
      infoText: researchMetricRef.current
        ? `${buildResearchMetricSummary(researchMetricRef.current)}\n\n${
            optimizationDraft
              ? "실제로 비교할 파라미터를 선택해 주세요. 최대 3개까지 설정할 수 있습니다."
              : "계산 범위를 만들 수 있는 숫자 파라미터가 없습니다. 기간·임계값·손절·익절처럼 숫자가 있는 조건을 추가해 주세요."
          }`
        : undefined,
      infoSuggestions: optimizationDraft
        ? metricOptimizationSuggestions(optimizationDraft)
        : undefined,
      parsed: data.parsed,
      notices: data.notices?.length ? data.notices : undefined,
    });
    if (researchMetricRef.current) return;
    setMessages(prev => [...prev, { role: "assistant", coachLoading: true, coachText: "" }]);
    generateCoachResponse({ userText: data.prompt ?? data.parsed.description, parsed: data.parsed });
  };
  applyBuilderConfirmedStrategyRef.current = applyBuilderConfirmedStrategy;

  const handleSend = async (overrideText?: string) => {
    const userText = overrideText ?? "";
    if (!userText || isSending || stage === "running") return;
    // 메시지를 보내는 순간 '직접 입력' 노출 토글을 해제한다(다음 빌더 단계는 다시 칩 집중).
    setBuilderFreeTextRequested(false);

    if (authState !== "authenticated" && isStrategyInput) {
      // 리로드 직후에는 /api/user 왕복이 끝날 때까지 authState가 "loading"이라
      // 로그인 여부를 아직 모른다. 이때 모달을 띄우면 로그인된 사용자에게도
      // 재로그인을 요구하게 되므로, 프롬프트를 보관했다가 하이드레이션 완료 후 처리한다.
      if (authState === "loading") {
        pendingAuthGatePromptRef.current = userText;
        return;
      }
      sessionStorage.setItem(PENDING_STRATEGY_PROMPT_KEY, userText);
      setIsAuthModalOpen(true);
      return;
    }

    if (shouldBeginStrategyChatNavigation(isChatPage, messages.length)) {
      beginStrategyChatNavigation(userText, (url) => router.push(url));
      return;
    }

    if (!firstPromptRef.current) firstPromptRef.current = userText;
    const currentParsed = latestParsedRef.current ?? latestParsed;
    const currentBacktestReq = backtestReqRef.current ?? backtestReq;
    setIsSending(true);
    // 분류/파싱 호출이 시작되기 전에 사용자 입력을 화면에 즉시 반영한다.
    appendUserMessage(userText);

    if (metricOptimizationDraftRef.current) {
      await handleMetricOptimizationInput(userText);
      setIsSending(false);
      return;
    }

    // Phase 5: 직전 planner ask 칩과 정확히 일치하는 입력은 시스템 생성 열거형 선택지의
    // '답'이다 — 새 발화가 아니므로 의도 분류를 거치지 않고 곧장 파스 레인으로 보낸다.
    // 분류를 거치면 금융 단서가 없는 카탈로그 테마명 칩("보안주(정보)")이 OFF_TOPIC
    // 거절로 빠진다(2026-07-28 실측). 백엔드 결정론 칩 귀속(run_chip_answer)이
    // pending_ask 에코로 이 입력을 처리한다(미일치·자유 서술은 기존 분류 흐름 그대로).
    if (
      !builderModeRef.current &&
      currentParsed &&
      pendingAskRef.current?.chips?.includes(userText.trim())
    ) {
      await appendAssistant({ role: "assistant", isLoading: true });
      try {
        await runStrategyParseFlow(userText, currentParsed, currentBacktestReq);
      } catch (e: any) {
        updateLastAssistant({
          isLoading: false,
          error: e.message ?? "알 수 없는 오류",
          retryPrompt: userText,
        });
      } finally {
        setIsSending(false);
      }
      return;
    }

    const restoredBuilderQuestion = hasActiveBuilderQuestion(messages);
    const restoredBuilderProgress = hasBuilderProgress(builderStateRef.current);
    if (restoredBuilderQuestion || restoredBuilderProgress) {
      builderModeRef.current = true;
    }
    const conversationContext = {
      stage,
      hasBacktestRequest: Boolean(currentBacktestReq),
      hasCurrentStrategy: Boolean(currentParsed),
      builderMode:
        builderModeRef.current ||
        restoredBuilderQuestion ||
        restoredBuilderProgress,
      lastCoachText: lastCoachText(),
      pendingHoldingPeriodPrompt: pendingHoldingPeriodPromptRef.current,
      pendingHoldingPeriodHorizon: pendingHoldingPeriodHorizonRef.current,
      pendingResearchMetricPrompt: pendingMetricResearchPromptRef.current,
    };
    let turnDecision = decideConversationTurn(userText, conversationContext);

    // 결정론 즉답(respond)에도 현재 전략이 있으면 '현재까지 이해한 전략입니다' 요약 카드를
    // 항상 함께 보여준다(사용자 결정 2026-07-26 — 종목 변경 의향 안내 등이 전략 맥락 없이
    // 답변만 떠 있지 않도록).
    const currentStrategyPresentation = () => {
      const parsed = latestParsedRef.current;
      if (!parsed) return undefined;
      const { summaryItems, progressItems } = buildBuilderTurnPresentation({
        state: {},
        reply: "",
        parsed,
        explicitFields: explicitFieldsRef.current,
        backtestRequest: backtestReqRef.current ?? backtestReq,
      });
      return { summaryItems, progressItems };
    };

    if (turnDecision.action === "respond") {
      await appendAssistant({
        role: "assistant",
        infoText: turnDecision.message,
        infoSuggestions: turnDecision.suggestions,
        builderPresentation: currentStrategyPresentation(),
      });
      setIsSending(false);
      return;
    }

    if (turnDecision.action === "ask_research_metric") {
      pendingMetricResearchPromptRef.current = turnDecision.strategyPrompt;
      await appendAssistant({
        role: "assistant",
        infoText: turnDecision.message,
        infoSuggestions: turnDecision.suggestions,
      });
      setIsSending(false);
      return;
    }

    if (turnDecision.action === "run_backtest") {
      setIsSending(false);
      await handleRunBacktest();
      return;
    }

    if (turnDecision.action === "ask_holding_period") {
      pendingHoldingPeriodPromptRef.current = turnDecision.strategyPrompt;
      pendingHoldingPeriodHorizonRef.current = turnDecision.holdingHorizon;
      await appendAssistant({
        role: "assistant",
        infoText: turnDecision.message,
        infoSuggestions: turnDecision.suggestions,
      });
      setIsSending(false);
      return;
    }

    if (turnDecision.action === "start_builder") {
      const holdingPeriodDays = turnDecision.strategyAssumptions?.holdingPeriodDays;
      const researchMetric = turnDecision.researchMetric ?? null;
      pendingHoldingPeriodPromptRef.current = null;
      pendingHoldingPeriodHorizonRef.current = null;
      pendingMetricResearchPromptRef.current = null;
      researchMetricRef.current = researchMetric;
      metricOptimizationDraftRef.current = null;
      if (researchMetric) firstPromptRef.current = turnDecision.seedPrompt;
      builderModeRef.current = true;
      builderStateRef.current = holdingPeriodDays
        ? { hold_period_days: holdingPeriodDays, risk_done: true }
        : {};
      builderHistoryRef.current = [];
      await startStrategyBuilder({ seedText: turnDecision.seedPrompt, researchMetric });
      setIsSending(false);
      return;
    }

    // 분류/파싱 호출 전에 '분석 중...' 로딩을 즉시 보여준다 (딜레이 동안 사용자 피드백 제공).
    // 이후 분기들은 이 버블을 updateLastAssistant로 변형해 재사용한다(새 버블 생성 금지).
    await appendAssistant({
      role: "assistant",
      isLoading: true,
      builderQuestion: turnDecision.action === "continue_builder",
    });

    // 전략 빌더 모드: 짧은 답변을 전략 필드로 누적한다(분류/거절보다 먼저 실행).
    if (turnDecision.action === "continue_builder") {
      try {
        const requestState = builderStateRef.current;
        // 답변에 낯선 테마 용어가 있으면(업종 되묻기 답 등) 개념 확인(kg_lookup)·검색
        // 그라운딩(searching)에 진입할 수 있다 — stage 수신 시 진행 문구 표시.
        const data = await requestBuilderStepData(
          { state: requestState, input: userText },
          (stage) => {
            if (stage === "searching" || stage === "kg_lookup") {
              updateLastAssistant({ isLoading: true, loadingStage: stage });
            }
          },
        );
        builderStateRef.current =
          data.status === "reset" || data.status === "exited"
            ? data.state ?? {}
            : mergeBuilderState(requestState, data.state);

        if (data.status === "confirmed") {
          // 전략 완성 → 빌더 종료. 특화 빌더가 DSL(parsed+backtest_request)을 직접 내려주면
          // 재파싱 없이 그대로 적용하고, custom(자유 서술)만 프롬프트 재파싱 경로로 폴백한다.
          const confirmedBuilderState = builderStateRef.current;
          builderModeRef.current = false;
          updateLastAssistant({
            isLoading: true,
            infoText: undefined,
            infoSuggestions: undefined,
            builderQuestion: false,
            builderPresentation: undefined,
          });
          try {
            const singleAssetContext = getSingleAssetBuilderContext(
              currentParsed,
              currentBacktestReq,
            );
            if (data.parsed && data.backtest_request) {
              applyBuilderConfirmedStrategy(
                singleAssetContext && currentParsed
                  ? mergeSingleAssetBuilderResult(
                      data,
                      singleAssetContext,
                      currentParsed,
                      currentBacktestReq,
                    )
                  : data,
                userText,
              );
              builderStateRef.current = {};
              builderHistoryRef.current = [];
            } else if (data.prompt) {
              await runStrategyParseFlow(
                singleAssetContext
                  ? buildSingleAssetBuilderPrompt(data.prompt, singleAssetContext)
                  : data.prompt,
                singleAssetContext ? currentParsed : null,
                singleAssetContext ? currentBacktestReq : null,
              );
              if (!builderModeRef.current) {
                builderStateRef.current = {};
                builderHistoryRef.current = [];
              }
            } else {
              builderModeRef.current = true;
              builderStateRef.current = confirmedBuilderState;
              throw new Error("완성된 전략 결과가 비어 있습니다.");
            }
          } catch (e: any) {
            if (!hasBuilderProgress(builderStateRef.current)) {
              builderStateRef.current = confirmedBuilderState;
            }
            builderModeRef.current = true;
            updateLastAssistant({ isLoading: false, error: e.message ?? "알 수 없는 오류" });
          }
          setIsSending(false);
          return;
        }
        if (data.status === "reset" || data.status === "exited") {
          builderHistoryRef.current = [];
        }
        if (data.status === "exited") {
          builderModeRef.current = false;
          builderStateRef.current = {};
          pendingMetricResearchPromptRef.current = null;
          researchMetricRef.current = null;
          metricOptimizationDraftRef.current = null;
        }
        if (data.status !== "reset" && data.status !== "exited") {
          builderHistoryRef.current.push({ ...requestState });
        }
        const {
          question,
          ...builderPresentation
        } = buildBuilderTurnPresentation({
          state: builderStateRef.current,
          reply: data.reply,
          parsed: currentParsed,
          explicitFields: explicitFieldsRef.current,
          backtestRequest: backtestReqRef.current ?? backtestReq,
        });
        updateLastAssistant({
          isLoading: false,
          infoText: question,
          infoSuggestions: withBuilderNavigationSuggestions(
            data.suggestions,
            builderStateRef.current,
            builderHistoryRef.current.length > 0,
          ),
          builderQuestion: data.status !== "exited",
          builderPresentation: data.status !== "exited" ? builderPresentation : undefined,
        });
      } catch {
        // 빌더 호출 실패 시 거절하지 않고 자연스럽게 다시 묻는다.
        updateLastAssistant({
          isLoading: false,
          infoText: "조건을 한 번 더 말씀해 주시겠어요?",
          builderQuestion: true,
        });
      }
      setIsSending(false);
      return;
    }

    if (turnDecision.action === "answer_follow_up" && currentParsed) {
      updateLastAssistant({
        isLoading: false,
        parsed: currentParsed,
        coachLoading: true,
        coachText: "",
      });
      try {
        await generateFollowUpCoachResponse({
          userText,
          parsed: currentParsed,
        });
      } finally {
        setIsSending(false);
      }
      return;
    }

    if (turnDecision.action === "parse_strategy") {
      pendingHoldingPeriodPromptRef.current = null;
      pendingHoldingPeriodHorizonRef.current = null;
      try {
        await runStrategyParseFlow(
          turnDecision.strategyPrompt,
          currentParsed,
          currentBacktestReq,
          turnDecision.strategyAssumptions,
        );
      } catch (e: any) {
        updateLastAssistant({
          isLoading: false,
          error: e.message ?? "알 수 없는 오류",
          retryPrompt: turnDecision.strategyPrompt,
          retryAssumptions: turnDecision.strategyAssumptions,
        });
      } finally {
        setIsSending(false);
      }
      return;
    }

    const { classification, history } = await classifyConversationPrompt(userText);
    turnDecision = decideConversationTurn(userText, conversationContext, classification);

    if (turnDecision.action === "respond") {
      updateLastAssistant({
        isLoading: false,
        infoText: turnDecision.message,
        infoSuggestions: turnDecision.suggestions,
        builderPresentation: currentStrategyPresentation(),
      });
      setIsSending(false);
      return;
    }

    if (turnDecision.action === "ask_holding_period") {
      pendingHoldingPeriodPromptRef.current = turnDecision.strategyPrompt;
      pendingHoldingPeriodHorizonRef.current = turnDecision.holdingHorizon;
      updateLastAssistant({
        isLoading: false,
        infoText: turnDecision.message,
        infoSuggestions: turnDecision.suggestions,
      });
      setIsSending(false);
      return;
    }

    if (turnDecision.action === "start_builder") {
      updateLastAssistant({ isLoading: false, infoText: turnDecision.message });
      pendingMetricResearchPromptRef.current = null;
      researchMetricRef.current = null;
      metricOptimizationDraftRef.current = null;
      builderModeRef.current = true;
      builderStateRef.current = {};
      builderHistoryRef.current = [];
      await startStrategyBuilder({ seedText: turnDecision.seedPrompt });
      setIsSending(false);
      return;
    }

    if (turnDecision.action === "answer_general") {
      try {
        const res = await fetch("/api/query/general", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: userText, history }),
        });
        if (!res.ok) throw new Error();
        const data = await res.json();
        updateLastAssistant({ isLoading: false, infoText: data.answer });
      } catch {
        updateLastAssistant({
          isLoading: false,
          error:
            classification.intent === "UNKNOWN"
              ? "요청을 이해하지 못했습니다. 연구하려는 시장, 조건 또는 기간을 조금 더 구체적으로 입력해 주세요."
              : "답변을 가져오지 못했습니다.",
        });
      }
      setIsSending(false);
      return;
    }

    if (turnDecision.action === "respond_stock") {
      if (turnDecision.symbol) lastAnalyzedSymbolRef.current = turnDecision.symbol;
      updateLastAssistant({ isLoading: false, infoText: turnDecision.message });
      setIsSending(false);
      return;
    }

    try {
      if (turnDecision.action === "parse_strategy") {
        pendingHoldingPeriodPromptRef.current = null;
        pendingHoldingPeriodHorizonRef.current = null;
        await runStrategyParseFlow(
          turnDecision.strategyPrompt,
          currentParsed,
          currentBacktestReq,
          turnDecision.strategyAssumptions,
        );
      }
    } catch (e: any) {
      setMessages(prev => prev.map((m, i) =>
        i === prev.length - 1
          ? {
              role: "assistant",
              error: e.message ?? "알 수 없는 오류",
              ...(turnDecision.action === "parse_strategy"
                ? {
                    retryPrompt: turnDecision.strategyPrompt,
                    retryAssumptions: turnDecision.strategyAssumptions,
                  }
                : {}),
            }
          : m
      ));
    } finally {
      setIsSending(false);
    }
  };

  handleSendRef.current = handleSend;

  // 파싱 실패(주로 LLM 콜드스타트 타임아웃)의 '다시 시도' — 사용자 버블을 중복 추가하지
  // 않고 오류 버블을 로딩 버블로 되돌린 뒤 같은 턴을 재실행한다. 분류는 건너뛴다(실패한
  // 턴이 이미 parse_strategy로 판정된 상태의 재실행이므로).
  const handleRetryParse = async (message: ChatMessage) => {
    const retryPrompt = message.retryPrompt;
    if (!retryPrompt || isSending || stage === "running") return;
    const currentParsed = latestParsedRef.current ?? latestParsed;
    const currentBacktestReq = backtestReqRef.current ?? backtestReq;
    setIsSending(true);
    // 오류 버블이 마지막이면 그 자리를 로딩 버블로 되돌리고, 아니면(뒤에 대화가 이어진
    // 경우) 새 로딩 버블을 추가한다 — runStrategyParseFlow는 항상 마지막 assistant
    // 버블을 갱신하므로 로딩 버블이 마지막임을 보장해야 한다.
    setMessages(prev => {
      const last = prev[prev.length - 1];
      const loading: ChatMessage = { role: "assistant", isLoading: true, loadingStage: "parsing" };
      if (last?.role === "assistant" && last.error) {
        return prev.map((m, i) => (i === prev.length - 1 ? loading : m));
      }
      return [...prev, loading];
    });
    try {
      await runStrategyParseFlow(
        retryPrompt,
        currentParsed,
        currentBacktestReq,
        message.retryAssumptions,
      );
    } catch (e: any) {
      setMessages(prev => prev.map((m, i) =>
        i === prev.length - 1
          ? {
              role: "assistant",
              error: e.message ?? "알 수 없는 오류",
              retryPrompt,
              retryAssumptions: message.retryAssumptions,
            }
          : m
      ));
    } finally {
      setIsSending(false);
    }
  };

  const handleGoogleStart = async () => {
    if (isStartingGoogleLogin || !isSupabaseConfigured()) return;

    setIsStartingGoogleLogin(true);
    try {
      const supabase = getSupabaseBrowserClient();
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: window.location.href,
          queryParams: OAUTH_QUERY_PARAMS,
        },
      });

      if (error) {
        throw error;
      }
    } finally {
      setIsAuthModalOpen(false);
      setIsStartingGoogleLogin(false);
    }
  };

  // 인증 하이드레이션 중(loading)에 막혔던 전략 프롬프트를 완료 후 처리한다 —
  // 로그인 확인 시 자동 재전송, 비로그인 확정 시에만 로그인 모달.
  useEffect(() => {
    if (authState === "loading") return;
    const blockedPrompt = pendingAuthGatePromptRef.current;
    if (!blockedPrompt) return;
    pendingAuthGatePromptRef.current = null;
    if (authState === "authenticated") {
      void handleSendRef.current?.(blockedPrompt);
      return;
    }
    sessionStorage.setItem(PENDING_STRATEGY_PROMPT_KEY, blockedPrompt);
    setIsAuthModalOpen(true);
  }, [authState]);

  useEffect(() => {
    if (
      !isChatPage ||
      authState !== "authenticated" ||
      pendingPromptConsumedRef.current ||
      messages.length > 0 ||
      isSending
    ) {
      return;
    }

    const pendingPrompt = sessionStorage.getItem(PENDING_STRATEGY_PROMPT_KEY);
    if (!pendingPrompt) return;

    pendingPromptConsumedRef.current = true;
    sessionStorage.removeItem(PENDING_STRATEGY_PROMPT_KEY);
    chatInputRef.current?.clear();
    void handleSendRef.current?.(pendingPrompt);
  }, [authState, isChatPage, messages.length, isSending]);

  const generateCoachResponse = async ({
    userText,
    parsed,
  }: {
    userText: string;
    parsed: ParsedSummary;
  }) => {
    const updateLastAssistant = (patch: Partial<ChatMessage>) => {
      setMessages(prev => {
        const lastIdx = prev.map((m, i) => m.role === "assistant" ? i : -1).filter(i => i >= 0).at(-1);
        if (lastIdx === undefined) return prev;
        return prev.map((m, i) => i === lastIdx ? { ...m, ...patch } : m);
      });
    };

    const startedAt = Date.now();
    try {
      const coachRes = await fetch("/api/strategy/coach", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "create_session",
          user_prompt: userText,
          parsed_strategy: parsed as unknown as Record<string, unknown>,
          // 직전까지의 코치 대화를 넘겨 이미 설명한 전문용어를 다시 설명하지 않도록 한다.
          ...(coachConversationRef.current.length > 0
            ? { conversation_context: coachConversationRef.current }
            : {}),
        }),
      });

      await enforceMinValidationDelay(startedAt);

      if (!coachRes.ok) {
        updateLastAssistant({
          coachLoading: false,
          coachText: "전략 검증 결과를 가져오지 못했습니다. 전략 요약은 준비되어 있으니 백테스트는 계속 실행할 수 있습니다.",
        });
        return;
      }

      coachSessionIdRef.current = coachRes.headers.get("X-Coach-Session-Id");
      const result: { message?: string } = await coachRes.json();
      const message = normalizeCoachMessage(
        result.message,
        "현재 전략을 검증하지 못했습니다."
      );
      rememberCoachExchange(userText, message);
      updateLastAssistant({
        coachLoading: false,
        coachText: message,
      });
    } catch {
      await enforceMinValidationDelay(startedAt);
      updateLastAssistant({
        coachLoading: false,
        coachText: "전략 검증 중 오류가 발생했습니다. 전략 요약은 준비되어 있으니 백테스트는 계속 실행할 수 있습니다.",
      });
    }
  };

  const generateFollowUpCoachResponse = async ({
    userText,
    parsed,
  }: {
    userText: string;
    parsed: ParsedSummary;
  }) => {
    const updateLastAssistant = (patch: Partial<ChatMessage>) => {
      setMessages(prev => {
        const lastIdx = prev.map((m, i) => m.role === "assistant" ? i : -1).filter(i => i >= 0).at(-1);
        if (lastIdx === undefined) return prev;
        return prev.map((m, i) => i === lastIdx ? { ...m, ...patch } : m);
      });
    };

    const startedAt = Date.now();
    try {
      const sessionId = coachSessionIdRef.current;
      const coachRes = await fetch("/api/strategy/coach", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sessionId
          ? {
              action: "follow_up",
              session_id: sessionId,
              user_prompt: userText,
            }
          : {
              action: "create_session",
              user_prompt: userText,
              parsed_strategy: parsed as unknown as Record<string, unknown>,
            }),
      });

      await enforceMinValidationDelay(startedAt);

      if (!coachRes.ok) {
        updateLastAssistant({
          coachLoading: false,
          coachText: "전략 검증 결과를 가져오지 못했습니다. 전략 요약은 준비되어 있으니 백테스트는 계속 실행할 수 있습니다.",
        });
        return;
      }

      if (!sessionId) {
        coachSessionIdRef.current = coachRes.headers.get("X-Coach-Session-Id");
      }
      const result: { message?: string } = await coachRes.json();
      const message = normalizeCoachMessage(
        result.message,
        "현재 전략을 검증하지 못했습니다."
      );
      rememberCoachExchange(userText, message);
      updateLastAssistant({
        coachLoading: false,
        coachText: message,
      });
    } catch {
      await enforceMinValidationDelay(startedAt);
      updateLastAssistant({
        coachLoading: false,
        coachText: "전략 검증 중 오류가 발생했습니다. 전략 요약은 준비되어 있으니 백테스트는 계속 실행할 수 있습니다.",
      });
    }
  };

  const handleRunBacktest = async (options?: any) => {
    if (!backtestReq) return;

    // 매수 기준이 없는 전략은 0매매로 끝나므로 실행을 막고 전략 빌더로 전환한다(버튼은 이미
    // 숨겨지지만, 확인 응답 등 다른 경로로 도달하는 경우를 위한 최종 방어선).
    const currentParsed = latestParsedRef.current ?? latestParsed;
    if (!hasBuyCriteria(currentParsed)) {
      builderModeRef.current = true;
      builderStateRef.current = {};
      builderHistoryRef.current = [];
      await startStrategyBuilder();
      return;
    }

    const effectiveReq = options ? {
      ...backtestReq,
      engine_version: BACKTEST_ENGINE_VERSION,
      period: options.period ?? backtestReq.period,
      risk: { ...backtestReq.risk, init_cash: options.initialCapital ?? backtestReq.risk?.init_cash },
      options: {
        fee_rate: (options.commissionPct ?? 0.015) / 100,
        slippage_rate: (options.slippagePct ?? 0.05) / 100,
      },
    } : {
      ...backtestReq,
      engine_version: BACKTEST_ENGINE_VERSION,
    };

    if (options) {
      setCurrentOptions(options);
      setBacktestReq(effectiveReq);
    }

    // 결과 화면을 닫아도 직전 result는 state에 남는다(대화 복귀 후 결과 유지). 그래서 채팅에서
    // 새 백테스트를 시작하면 이전 결과 화면이 진행 바와 함께 되살아났다 — 결과 화면 밖에서
    // 시작한 실행은 이전 결과를 비워 채팅의 진행 표시만 보이게 한다.
    // 결과 화면 안에서의 재실행(옵션 변경)은 이전 결과를 그대로 두고 진행 바를 얹는다.
    const isRerunFromResultView = (stage === "done" || stage === "running") && !!result;
    if (!isRerunFromResultView) {
      setResult(null);
    }

    setStage("running");
    setStatusMessage("백테스트 준비 중...");

    try {
      const res = await fetch("/api/strategy/backtest-stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(effectiveReq),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? "백테스트 실패");
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let streamDone = false;
      // result 이전에 도착하는 meta 이벤트의 dedup 키. 자동저장/명시저장이
      // 같은 히스토리 행으로 수렴하도록 result에 실어준다.
      let nlCacheKey: string | undefined;

      const processPayload = (payload: string) => {
        if (payload === "[DONE]") {
          streamDone = true;
          return;
        }

        const event = JSON.parse(payload);
        if (event.type === "status") {
          setStatusMessage(event.message);
        } else if (event.type === "meta") {
          nlCacheKey = event.cacheKey ?? undefined;
        } else if (event.type === "result") {
          setResult(mapRawBacktestResult(event.data, `nl_${Date.now()}`, nlCacheKey));
          setExecutedReq(effectiveReq);
          setStage("done");
        } else if (event.type === "error") {
          throw new Error(event.message);
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          const parsed = parseSseBlocks(buffer + decoder.decode(), true);
          for (const event of parsed.events) processPayload(event.payload);
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const parsed = parseSseBlocks(buffer);
        buffer = parsed.remaining;

        for (const event of parsed.events) {
          processPayload(event.payload);
        }

        if (streamDone) {
          break;
        }
      }
    } catch (e: any) {
      setStage("ready");
      setMessages(prev => [
        ...prev,
        { role: "assistant", error: e.message ?? "백테스트 오류" },
      ]);
    }
  };

  const handleWalkForward = async (
    settings: AdvisorWalkForwardSettings,
    signal?: AbortSignal,
    onProgress?: WalkForwardProgressHandler
  ) => {
    if (!backtestReq) {
      throw new Error("워크포워드 분석을 실행할 백테스트 요청이 없습니다.");
    }

    const ranges = buildWalkForwardParameterRanges(backtestReq);
    if (!hasWalkForwardParameterRanges(ranges)) {
      throw new Error(
        "워크포워드 최적화에 사용할 숫자 파라미터가 없습니다. 손절/익절, 지표 기간, 임계값처럼 조정 가능한 조건이 포함된 전략에서 실행해 주세요."
      );
    }

    return runWalkForwardStream(buildWalkForwardRequest(backtestReq, settings, ranges), {
      signal,
      onProgress,
    });
  };

  const handleReset = () => {
    setStage("idle");
    setMessages([]);
    setLatestParsed(null);
    setBacktestReq(null);
    setCurrentOptions(null);
    setResult(null);
    setExecutedReq(null);
    setIsSending(false);
    chatInputRef.current?.clear();
    setBuilderFreeTextRequested(false);
    latestParsedRef.current = null;
    backtestReqRef.current = null;
    coachSessionIdRef.current = null;
    coachConversationRef.current = [];
    firstPromptRef.current = "";
    lastAnalyzedSymbolRef.current = null;
    builderModeRef.current = false;
    builderStateRef.current = {};
    builderHistoryRef.current = [];
    explicitNoRebalancingRef.current = false;
    setExplicitNoRebalancing(false);
    explicitFieldsRef.current = [];
    pendingHoldingPeriodPromptRef.current = null;
    pendingHoldingPeriodHorizonRef.current = null;
    pendingMetricResearchPromptRef.current = null;
    researchMetricRef.current = null;
    pendingPromptConsumedRef.current = false;
    metricOptimizationDraftRef.current = null;
    metricOptimizationAbortRef.current?.abort();
    metricOptimizationAbortRef.current = null;
    setMetricOptimizationProgress(null);
    try {
      sessionStorage.removeItem(PENDING_STRATEGY_PROMPT_KEY);
      sessionStorage.removeItem(STRATEGY_CHAT_STATE_KEY);
    } catch {
      // 무시
    }
    if (isChatPage) {
      router.push("/analytics");
    }
    setTimeout(() => chatInputRef.current?.focus(), 100);
  };
  handleResetRef.current = handleReset;

  const shouldShowIntro = isIdle && !isChatPage;
  const strategyPreviewBackgroundClass = isStrategyPreviewModalOpen
    ? "pointer-events-none select-none blur-[6px] transition-[filter,opacity] duration-200"
    : "transition-[filter,opacity] duration-200";
  const softEnterClass = SURFACE_ENTER_CLASS;
  const softEnterLateClass = SURFACE_ENTER_LATE_CLASS;

  // ── 결과 화면
  const isRunning = stage === "running";
  const showingBacktestResult = (stage === "done" || isRunning) && !!result;

  // 탑메뉴 '전략연구소' 클릭 → 결과 화면을 내리고 대화 화면으로 복귀(결과·대화 유지).
  // 결과 화면은 같은 라우트의 상태라서 router.push만으로는 화면이 바뀌지 않는다.
  // 이미 대화 화면이면 화면은 그대로고 스크롤만 대화 끝까지 올린다.
  useEffect(() => {
    const showChatView = () => {
      setStage((prev) => (prev === "done" ? "ready" : prev));
      pendingScrollToEndRef.current = true;
      chatAutoScrollEnabledRef.current = false;
      scrollChatViewToEnd();
    };
    window.addEventListener(STRATEGY_LAB_CHAT_VIEW_EVENT, showChatView);
    return () => window.removeEventListener(STRATEGY_LAB_CHAT_VIEW_EVENT, showChatView);
  }, []);

  // 결과 화면에서 브라우저 뒤로가기 → 페이지 이탈 대신 대화창으로 복귀(결과·대화 유지).
  // showingBacktestResult(boolean) 변화에만 반응하므로 running↔done 전환 시 중복 push가 없다.
  useEffect(() => {
    if (!showingBacktestResult) return;
    return installBacktestResultBackHandler(() => setStage("ready"));
  }, [showingBacktestResult]);

  // 결과 화면 진입 시(또는 재실행 완료 시) 채팅 화면에서 내려가 있던 스크롤 위치가 그대로
  // 남아 결과가 아래쪽부터 보이는 문제를 막기 위해 항상 맨 위로 스크롤한다.
  // 반대로 대화 화면으로 돌아올 때(탑메뉴 '전략연구소'·뒤로가기)는 대화 끝까지 올려
  // 마지막 버블이 고정 입력창 뒤에 걸린 채로 남지 않게 한다.
  const wasShowingBacktestResultRef = useRef(false);
  useEffect(() => {
    const enteringResultView = showingBacktestResult && !wasShowingBacktestResultRef.current;
    const leavingResultView = !showingBacktestResult && wasShowingBacktestResultRef.current;
    wasShowingBacktestResultRef.current = showingBacktestResult;
    if (!enteringResultView && !leavingResultView && stage !== "done") return;

    if (leavingResultView) {
      pendingScrollToEndRef.current = true;
      chatAutoScrollEnabledRef.current = false;
      scrollChatViewToEnd();
      return;
    }
    document.querySelector("main")?.scrollTo({ top: 0, behavior: "auto" });
    resultScrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [showingBacktestResult, stage]);

  if (showingBacktestResult) {
    return (
      <DashboardLayout userName="">
        <div
          className="flex flex-col"
          style={{ minHeight: "calc(100dvh - var(--top-menu-bar-height, 76px))" }}
        >
          <div ref={resultScrollRef} className="flex flex-1 flex-col overflow-auto">
            {isRunning && (
              <div className="sticky top-0 z-30 mx-4 mt-4 max-w-4xl">
                <BacktestRunningStatus message={statusMessage} />
              </div>
            )}
            <BacktestDashboard
              result={result}
              onRestart={() => router.back()}
              onRun={handleRunBacktest}
              currentOptions={currentOptions}
              isRunning={isRunning}
              backtestDsl={backtestReq}
              onWalkForward={handleWalkForward}
              promptText={firstPromptRef.current || undefined}
              strategySummary={buildStrategySummaryFromRequest(executedReq ?? backtestReq)}
              parsedStrategy={latestParsed as unknown as Record<string, unknown>}
            />
          </div>
        </div>
      </DashboardLayout>
    );
  }

  // 전략 작성 맥락(시작 화면 또는 전략 요약 존재)에서만 '전략 생성', 그 외(안내 대화)는 '전송'.
  const isStrategyInput = isIdle || messages.some((m) => m.parsed);
  const isLlmWorking = isSending;
  const canSendInput = !isSending && stage !== "running";
  const hasChatStarted = messages.length > 0;
  const isLastAssistant = (i: number) => i === messages.length - 1 && messages[i].role === "assistant";
  const latestAssistantMessage = [...messages]
    .reverse()
    .find((message) => message.role === "assistant");
  const latestBuilderPresentation = [...messages]
    .reverse()
    .find((message) => message.builderPresentation)?.builderPresentation;
  const activeStrategyProgressItems =
    latestBuilderPresentation &&
    (latestAssistantMessage?.builderQuestion === true ||
      Boolean(latestAssistantMessage?.builderPresentation))
      ? latestBuilderPresentation.progressItems
      : null;

  // ── 메인 채팅 화면
  return (
    <DashboardLayout userName="">
      {/* 대화 진입 연출(chat-enter / chat-card-enter)은 globals.css에 있다 —
          prefers-reduced-motion으로 끌 수 있어야 하므로 인라인 style을 쓰지 않는다. */}
      <style>{`
        @keyframes metricOptimizationSweep {
          from { transform: translateX(-120%); }
          to { transform: translateX(320%); }
        }

        .metric-optimization-progress-bar {
          animation: metricOptimizationSweep 1.4s ease-in-out infinite;
        }

        @media (prefers-reduced-motion: reduce) {
          .metric-optimization-progress-bar {
            animation: none;
          }
        }
      `}</style>
      <div
        className={`relative flex flex-col items-center gap-4 overflow-x-hidden px-4 pt-10 sm:pt-14 lg:pt-20 ${hasChatStarted ? "pb-56" : "pb-12"} ${strategyPreviewBackgroundClass}`}
        data-testid="strategy-lab-background"
        style={{ minHeight: "calc(100dvh - var(--top-menu-bar-height, 76px))" }}
      >
        {shouldShowIntro && <StrategyWaveBackground />}

        {activeStrategyProgressItems && (
          <StrategyProgressPanel items={activeStrategyProgressItems} />
        )}

        {/* ── 채팅 영역 ── */}
        <div
          key={isChatPage ? "strategy-chat-page" : "strategy-intro-page"}
          className={`relative z-10 flex min-h-[calc(100dvh-var(--top-menu-bar-height,76px)-5rem)] w-full flex-col items-center justify-start transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] ${softEnterClass}`}
        >
        <div className={`w-full max-w-4xl flex flex-col items-center gap-6 ${
          hasChatStarted
            ? "min-h-[calc(100dvh-var(--top-menu-bar-height,76px)-5rem)]"
            : "min-h-[calc(100dvh-var(--top-menu-bar-height,76px)-5rem)] justify-end pb-10"
        }`}>

          {/* 헤더 */}
          {shouldShowIntro && (
          <div className="w-full max-w-3xl">
            <div className="flex flex-col items-center gap-3 text-center">
              <div
                className="w-full space-y-4 lg:w-auto"
                data-testid="strategy-lab-headline-stack"
              >
                <p
                  data-testid="strategy-lab-headline"
                  className="max-w-5xl text-[27px] leading-none tracking-tight text-[#fcfdff] sm:text-5xl lg:text-7xl [font-weight:950]"
                >
                  <AnimatedHeadline lines={HEADLINE_LINES} />
                </p>
                <p className="text-sm font-bold leading-relaxed text-gray-400 sm:text-base">
                  AI와 함께 전략을 설계하고, 바로 백테스트 하세요
                </p>
              </div>
            </div>
            {modelStatus?.status === "failed" && (
              <div className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-[var(--error-red-line)] bg-[var(--chat-artifact-surface)] px-3 py-1 text-xs font-bold text-[var(--error-red)]">
                <Warning size={12} weight="fill" />
                AI 모델 로드 실패 — 전략 생성을 사용할 수 없습니다
              </div>
            )}
          </div>
          )}

          {/* 채팅창 */}
          <div className="w-full flex flex-col gap-2.5">

            {/* 대화 히스토리 */}
            {messages.length > 0 && (
              <div className={`w-full space-y-4 px-1 py-2 ${softEnterClass}`}>
                {messages.map((msg, i) => (
                  <div key={i}>
                    {msg.role === "user" && (
                      <div className={`flex justify-end ${MESSAGE_ENTER_CLASS}`}>
                        <div className={`max-w-[80%] px-4 py-2.5 ${USER_CHAT_BUBBLE_CLASS}`}>
                          <p className="text-sm font-bold text-white leading-relaxed">{msg.content}</p>
                        </div>
                      </div>
                    )}
                    {msg.role === "assistant" && (
                      <div className="space-y-3">
                        {msg.isLoading && (
                          <AnalysisStatusBubble stage={msg.loadingStage} />
                        )}
                        {msg.infoText && (
                          <>
                            {msg.builderPresentation && (
                              <div
                                className={`max-w-[88%] p-4 ${ARTIFACT_CARD_CLASS} ${MESSAGE_ENTER_CLASS}`}
                              >
                                <BuilderStrategyOverview presentation={msg.builderPresentation} />
                              </div>
                            )}
                            <div
                              className={`max-w-[88%] space-y-2 py-0.5 ${MESSAGE_ENTER_CLASS}`}
                            >
                              <p className="text-sm font-bold text-white leading-relaxed whitespace-pre-line">
                                {msg.infoText}
                              </p>
                              {isLastAssistant(i) && metricOptimizationProgress && (
                                <MetricOptimizationProgressIndicator progress={metricOptimizationProgress} />
                              )}
                              {isLastAssistant(i) && msg.infoSuggestions && msg.infoSuggestions.length > 0 && (
                                <div className="space-y-1.5 pt-1">
                                  {msg.builderPresentation && (
                                    <p className="text-[11px] font-black text-[var(--text-label)]">
                                      선택 예시
                                    </p>
                                  )}
                                  <div className="flex flex-wrap gap-2">
                                    {msg.infoSuggestions.map((suggestion) => (
                                      <button
                                        key={suggestion}
                                        onClick={() => {
                                          if (suggestion === CANCEL_METRIC_OPTIMIZATION_CHIP) {
                                            metricOptimizationAbortRef.current?.abort();
                                            return;
                                          }
                                          // '직접 입력'은 빌더 답변이 아니라 입력창을 다시 띄우는 토글이다.
                                          if (suggestion === FREE_INPUT_CHIP) {
                                            focusFreeTextInput();
                                            return;
                                          }
                                          handleSuggestionClick(suggestion);
                                        }}
                                        className={CHOICE_CHIP_CLASS}
                                      >
                                        {suggestion}
                                      </button>
                                    ))}
                                    {shouldShowMovingAverageHelp(msg) && <MovingAverageTypeHelp />}
                                  </div>
                                </div>
                              )}
                            </div>
                          </>
                        )}
                        {msg.parsed && (
                          <>
                            {/* 사용자의 자연어를 전략 개념으로 재정리한 첫 문장 — 요약 카드·되묻기보다 먼저 보여준다. */}
                            {msg.restatement && (
                              <div
                                className={`flex max-w-[88%] items-start gap-2.5 py-0.5 ${MESSAGE_ENTER_CLASS}`}
                              >
                                {/* 산문은 카드도 레일도 없으므로 닷이 블록 시작점을 표시한다.
                                    강조색은 '사용자 차례'에 예약돼 있어 중립 톤을 쓴다. */}
                                <span
                                  aria-hidden="true"
                                  data-testid="strategy-restatement-dot"
                                  className="mt-[7px] h-1.5 w-1.5 flex-shrink-0 rounded-full bg-[var(--text-label)]"
                                />
                                <p
                                  data-testid="strategy-restatement"
                                  className="text-sm font-bold text-white leading-relaxed"
                                >
                                  {msg.restatement}
                                </p>
                              </div>
                            )}
                            {/* 백테스트 최소 조건을 채우는 중(clarification 대기)에는 전략 요약을
                                미리 보여주지 않는다 — 모든 조건에 답한 뒤 한 번에 요약을 만든다. */}
                            {!msg.clarification && (
                              <>
                                <ParsedSummaryBubble parsed={msg.parsed} backtestRequest={backtestReq} />
                                {msg.notices && msg.notices.length > 0 && (
                                  <div className={`flex flex-col gap-1.5 ${MESSAGE_ENTER_LATE_CLASS}`}>
                                    {msg.notices.map((notice, ni) => (
                                      <div
                                        key={ni}
                                        className={`flex items-start gap-2.5 p-3 ${ARTIFACT_CARD_CLASS}`}
                                      >
                                        <Info size={13} className="mt-0.5 flex-shrink-0 text-[var(--text-label)]" weight="fill" />
                                        <p className="text-xs font-bold text-gray-300 leading-relaxed whitespace-pre-line">
                                          {notice}
                                        </p>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </>
                            )}
                            {isLastAssistant(i) && !msg.coachLoading && msg.clarification && (
                              <>
                                {msg.builderPresentation && (
                                  <div
                                    className={`flex flex-col gap-2.5 p-4 ${ARTIFACT_CARD_CLASS} ${MESSAGE_ENTER_CLASS}`}
                                  >
                                    <BuilderStrategyOverview presentation={msg.builderPresentation} />
                                  </div>
                                )}
                                <div
                                  className={`flex flex-col gap-2.5 p-4 ${ARTIFACT_CARD_CLASS} ${MESSAGE_ENTER_LATE_CLASS}`}
                                >
                                  <div className="flex items-start justify-between gap-2.5">
                                    <div className="flex items-start gap-2.5">
                                      <Question size={13} className="mt-0.5 flex-shrink-0 text-[var(--chat-accent)]" weight="fill" />
                                      <p className="text-[13px] font-bold leading-relaxed text-gray-200 whitespace-pre-line">
                                        {msg.clarification.replace(/\*\*(.*?)\*\*/g, "$1")}
                                      </p>
                                    </div>
                                    {msg.previousStepState && (
                                      <button
                                        type="button"
                                        onClick={() => returnToPreviousCondition(msg)}
                                        disabled={isSending}
                                        className={BACK_CONTROL_CLASS}
                                      >
                                        <ArrowLeft size={11} />
                                        {CONFIRMATION_BACK_CHIP}
                                      </button>
                                    )}
                                  </div>
                                  {msg.clarificationSuggestions && msg.clarificationSuggestions.length > 0 && (
                                    <div className="space-y-1.5 pl-6">
                                      <p className="text-[11px] font-black text-[var(--text-label)]">
                                        {msg.strategyConfirmation ? "전략 확인" : "선택 예시"}
                                      </p>
                                      <div className="flex flex-wrap gap-2">
                                        {msg.clarificationSuggestions.map((suggestion) => (
                                          <button
                                            key={suggestion}
                                            onClick={() => handleSuggestionClick(suggestion)}
                                            className={CHOICE_CHIP_CLASS}
                                          >
                                            {suggestion}
                                          </button>
                                        ))}
                                        {!msg.strategyConfirmation &&
                                          !msg.clarificationSuggestions.includes(FREE_INPUT_CHIP) && (
                                          <button
                                            type="button"
                                            onClick={focusFreeTextInput}
                                            className={CHOICE_CHIP_CLASS}
                                          >
                                            {FREE_INPUT_CHIP}
                                          </button>
                                        )}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </>
                            )}
                            {isLastAssistant(i) && stage === "running" && (
                              <div className="flex items-center gap-2 px-1">
                                <ArrowsClockwise size={13} className="flex-shrink-0 animate-spin text-[var(--chat-accent)] motion-reduce:animate-none" />
                                <span className="text-xs font-bold text-[var(--text-label)] transition-colors duration-300">{statusMessage}</span>
                              </div>
                            )}
                          </>
                        )}
                        {(msg.coachLoading || msg.coachText) && (
                          <div
                            className={`max-w-[88%] space-y-2 p-4 ${ARTIFACT_CARD_CLASS} ${MESSAGE_ENTER_LATE_CLASS}`}
                            data-testid="strategy-coach-bubble"
                          >
                            <div className="flex items-center gap-2">
                              {msg.coachLoading && <LoadingSpinner />}
                              <span className="text-xs font-black text-white">
                                전략 검증
                              </span>
                              {msg.coachLoading && (
                                <ShimmerStatusText className="text-sm font-bold">검증 중...</ShimmerStatusText>
                              )}
                            </div>
                            {msg.coachText && (
                              <p className="text-sm font-bold text-white leading-relaxed whitespace-pre-line">
                                {parseCoachSegments(msg.coachText).map((seg, segIdx) =>
                                  seg.type === "link" ? (
                                    <a
                                      key={segIdx}
                                      href={seg.href}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-[var(--chat-accent)] underline decoration-[var(--chat-accent-underline)] underline-offset-2 transition-colors hover:decoration-[var(--chat-accent)]"
                                    >
                                      {seg.value}
                                    </a>
                                  ) : (
                                    <span key={segIdx}>{seg.value}</span>
                                  )
                                )}
                              </p>
                            )}
                          </div>
                        )}
                        {isLastAssistant(i) &&
                          backtestReq &&
                          stage !== "running" &&
                          !isSending &&
                          !msg.isLoading &&
                          !msg.clarification &&
                          runButtonPlacement(msg) !== null &&
                          isBacktestReady(msg.parsed ?? latestParsed, {
                            allowNoRebalancing: explicitNoRebalancing,
                            explicitFields: explicitFieldsRef.current,
                            requireExplicitConfiguration: true,
                          }) && (
                            <div
                              className={`flex max-w-[88%] px-1 ${MESSAGE_ENTER_LATE_CLASS}`}
                              data-testid="backtest-action"
                            >
                              <button
                                onClick={() => handleRunBacktest()}
                                className="flex items-center gap-2 rounded-xl bg-[var(--chat-accent)] px-5 py-2.5 text-xs font-black text-[var(--chat-accent-ink)] transition-colors duration-200 hover:brightness-110 active:translate-y-[1px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)]"
                              >
                                <ChartLineUp size={13} weight="fill" />
                                백테스트 시작하기
                                <ArrowRight size={11} />
                              </button>
                            </div>
                          )}
                        {msg.error && (
                          <div
                            className={`flex items-start gap-2.5 rounded-2xl border border-[var(--error-red-line)] bg-[var(--chat-artifact-surface)] p-4 ${MESSAGE_ENTER_CLASS}`}
                          >
                            <Warning size={13} className="mt-0.5 flex-shrink-0 text-[var(--error-red)]" weight="fill" />
                            <div className="flex-1 space-y-1">
                              <p className="text-xs font-black text-[var(--error-red)]">오류 발생</p>
                              <p className="text-xs font-bold text-[var(--text-label)]">{msg.error}</p>
                              {msg.retryPrompt && (
                                <button
                                  onClick={() => void handleRetryParse(msg)}
                                  disabled={isSending}
                                  data-testid="parse-retry"
                                  className="mt-2 flex items-center gap-1.5 rounded-lg border border-[var(--chat-line)] bg-[var(--chat-surface)] px-3 py-1.5 text-xs font-black text-[var(--text-strong)] transition-colors duration-200 hover:brightness-110 active:translate-y-[1px] disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)]"
                                >
                                  <ArrowsClockwise size={12} weight="bold" />
                                  다시 시도
                                </button>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}

            {stage === "running" && (
              <BacktestRunningStatus message={statusMessage} />
            )}

            {/* 입력 영역 — 시작 화면, 전략 요약 출력 후, 또는 안내 대화 중 표시 */}
            {shouldShowChatInput && !hasChatStarted && (
              <ChatInputBox
                key={shouldShowIntro ? "intro-chat-input" : "active-chat-input"}
                ref={chatInputRef}
                variant="inline"
                containerClassName={softEnterLateClass}
                running={stage === "running"}
                canSend={canSendInput}
                isLlmWorking={isLlmWorking}
                isStrategyInput={isStrategyInput}
                onSend={handleSendFromInput}
              />
            )}
          </div>

          {/* 예시 프롬프트 */}
          {shouldShowIntro && (
            <div className="w-[min(calc(100vw_-_2rem),80rem)]">
              <StrategyExampleTabs
                onSelectExample={(prompt) => void handleSend(prompt)}
                onPreviewOpenChange={setIsStrategyPreviewModalOpen}
              />
            </div>
          )}
        </div>
        </div>{/* end 채팅 영역 */}

        {shouldShowChatInput && hasChatStarted && (
          <ChatInputBox
            key="fixed-chat-input"
            ref={chatInputRef}
            variant="fixed"
            containerClassName={softEnterLateClass}
            running={stage === "running"}
            canSend={canSendInput}
            isLlmWorking={isLlmWorking}
            isStrategyInput={isStrategyInput}
            onSend={handleSendFromInput}
            onReset={handleResetFromInput}
          />
        )}

        {/* 입력창이 숨겨지는 상태(에러/로딩 등 예상 못 한 상태 포함)에서도 항상 빠져나갈 수 있도록,
            입력 바가 안 보일 때는 '대화 종료' 버튼만이라도 독립적으로 띄운다. */}
        {hasChatStarted && !shouldShowChatInput && (
          <div
            key="fixed-chat-escape"
            className="fixed bottom-4 left-4 right-4 z-40 mx-auto flex max-w-4xl justify-center"
          >
            <button
              type="button"
              onClick={handleReset}
              className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.14] bg-white/[0.05] px-4 py-2 text-xs font-bold text-[var(--accent-blue)] shadow-lg transition-colors duration-200 hover:bg-white/[0.09] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)]"
            >
              <X size={12} weight="bold" />
              대화 종료
            </button>
          </div>
        )}

      </div>

      {isAuthModalOpen && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm animate-fade-in"
          role="dialog"
          aria-modal="true"
          aria-labelledby="strategy-auth-modal-title"
        >
          <div
            className={`w-full max-w-md rounded-2xl border border-[var(--chat-hairline)] bg-[#0b0b0b] p-6 text-center shadow-2xl shadow-black/50 ${softEnterClass}`}
          >
            <div className="space-y-3">
              <p
                id="strategy-auth-modal-title"
                className="text-2xl font-black tracking-tight text-white"
              >
                아이디어를 전략으로 만들어 드립니다
              </p>
              <p className="text-sm font-bold leading-relaxed text-gray-400">
                Google로 3초만에 시작하세요
              </p>
            </div>
            <div className="mt-6 flex flex-col items-center gap-3">
              <p className="text-xs font-black text-[#ff6b6b]">
                카드 등록 불필요
              </p>
              <button
                type="button"
                onClick={() => void handleGoogleStart()}
                disabled={isStartingGoogleLogin}
                className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white px-4 py-2 text-sm font-black text-black transition-colors duration-200 hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <GoogleLogo size={18} weight="fill" />
                <span>{isStartingGoogleLogin ? "로그인 준비 중..." : "Google로 시작하기"}</span>
              </button>
              <button
                type="button"
                onClick={() => setIsAuthModalOpen(false)}
                className="text-sm font-black text-gray-400 transition-colors hover:text-white"
              >
                취소
              </button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}

export default function StrategyLabPage() {
  return (
    <Suspense>
      <StrategyLabContent />
    </Suspense>
  );
}
