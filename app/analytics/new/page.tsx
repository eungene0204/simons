"use client";

import { useState, useRef, useEffect, Suspense } from "react";
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
} from "@/components/strategy/strategyTemplateSession";
import { BacktestResult, type OptimizationResponse } from "@/types/strategy";
import { mapRawBacktestResult } from "./backtestResultMapper";
import {
  ArrowUp,
  ArrowRight,
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
import { computeChatScrollDelta } from "./chatScroll";
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
  // 미설정이면 기본 '분석 중...'을 표시한다(빌더/분류 등 비파싱 로딩).
  loadingStage?: "parsing" | "thinking" | "validating";
  error?: string;
  infoText?: string;  // 일반 투자 답변 또는 전략 전환 안내
  infoSuggestions?: string[];  // 전략 빌더 옵션 칩(클릭 시 그 답으로 전송)
  // 전략 요약을 막지 않는 보정 안내(예: 초기자금 하한선 보정). 요약 카드와 함께 표시된다.
  notices?: string[];
}

type MetricOptimizationProgressState = {
  startedAt: number;
  totalTrials: number;
};

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
      <div className="flex items-center justify-between gap-4 text-[11px] font-bold text-gray-400">
        <span>{progress.totalTrials}개 조합 계산 중</span>
        <span className="tabular-nums text-gray-500">경과 {elapsed}</span>
      </div>
      <div
        role="progressbar"
        aria-label="파라미터 조합 계산 진행 상황"
        aria-valuetext={`${progress.totalTrials}개 조합 계산 중, 경과 ${elapsed}`}
        className="h-1.5 overflow-hidden rounded-full bg-white/[0.08]"
      >
        <div className="metric-optimization-progress-bar h-full w-1/3 rounded-full bg-sky-400/80" />
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
        className="flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-[#171717] text-gray-400 transition-all duration-200 hover:border-yellow-400/50 hover:bg-[#202020] hover:text-yellow-300 focus:outline-none focus:ring-2 focus:ring-yellow-400/40"
      >
        <Question size={14} weight="bold" />
      </button>
      <div
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-30 mt-2 w-[min(18rem,calc(100vw-3rem))] -translate-x-1/2 rounded-xl border border-white/10 bg-[#101010] p-3 text-left opacity-0 shadow-2xl shadow-black/50 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 sm:left-auto sm:right-0 sm:translate-x-0"
      >
        <p className="text-[11px] font-black uppercase tracking-widest text-gray-500">이동평균 종류</p>
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

const USER_CHAT_BUBBLE_CLASS = "rounded-2xl bg-[#171717]";
const COACH_CHAT_BUBBLE_CLASS = "rounded-2xl bg-[#171717]";
const SOFT_MESSAGE_ENTER_STYLE = {
  animation: "softChatCardEnter 780ms cubic-bezier(0.19, 1, 0.22, 1) both",
};
const SOFT_MESSAGE_ENTER_LATE_STYLE = {
  animation: "softChatCardEnter 860ms cubic-bezier(0.19, 1, 0.22, 1) 140ms both",
};

// 전략 검증은 규칙 기반이라 즉시 응답하지만, 분석이 진행 중임을 사용자가 인지하도록
// 최소 노출 시간을 둔다. 응답이 더 오래 걸리면 추가 지연 없이 그대로 표시한다.
const MIN_VALIDATION_DELAY_MS = 2400;

// Choice-only prompts can reopen the shared chat input without sending another answer.
const FREE_INPUT_CHIP = "직접 입력";

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
      `}</style>
    </>
  );
}

// 분석 로딩 단계별 표시 문구. 미설정이면 기본 '분석 중...'.
// validating: 룰 파싱이 애매해 LLM 검증기를 호출하는 동안 표시(ShimmerStatusText 애니메이션).
const ANALYSIS_STAGE_LABEL: Record<"parsing" | "thinking" | "validating", string> = {
  parsing: "파싱 중...",
  thinking: "생각 중...",
  validating: "검증 중...",
};

function AnalysisStatusBubble({
  title,
  stage,
}: {
  title?: string;
  stage?: "parsing" | "thinking" | "validating";
}) {
  const label = stage ? ANALYSIS_STAGE_LABEL[stage] : "분석 중...";
  return (
    <div
      className={`max-w-[88%] rounded-tl-sm p-3.5 space-y-2 ${COACH_CHAT_BUBBLE_CLASS}`}
      style={SOFT_MESSAGE_ENTER_LATE_STYLE}
    >
      <div className="flex items-center gap-2">
        {title && (
          <span className="text-[11px] font-black uppercase tracking-widest text-white">
            {title}
          </span>
        )}
        <ShimmerStatusText className="text-sm font-bold">{label}</ShimmerStatusText>
      </div>
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
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-md bg-[#171717] border border-white/[0.08] text-white text-xs font-bold">
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

function buildAnimatedHeadline(lines: string[], visibleCount: number) {
  let remaining = visibleCount;

  return lines.map((line, lineIndex) => {
    const visibleChars = Math.max(0, Math.min(line.length, remaining));
    remaining -= visibleChars;

    return (
      <span key={`${line}-${lineIndex}`} className="block min-h-[1em] whitespace-nowrap">
        {line.split("").map((char, charIndex) => {
          const isVisible = charIndex < visibleChars;

          return (
            <span
              key={`${line}-${lineIndex}-${charIndex}`}
              className="inline-block transition-all duration-300 ease-out"
              style={{
                opacity: isVisible ? 1 : 0,
                transform: isVisible ? "translateY(0)" : "translateY(8px)",
                filter: isVisible ? "blur(0)" : "blur(6px)",
              }}
            >
              {char === " " ? "\u00A0" : char}
            </span>
          );
        })}
      </span>
    );
  });
}

function BacktestRunningStatus({ message }: { message: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`relative isolate w-full overflow-hidden rounded-2xl border border-white/[0.08] px-4 py-3 ${COACH_CHAT_BUBBLE_CLASS}`}
    >
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-0">
        <span className="backtest-aurora backtest-aurora-blue" />
        <span className="backtest-aurora backtest-aurora-mint" />
        <span className="backtest-aurora backtest-aurora-gold" />
        <span className="absolute inset-0 bg-[#171717]/45" />
      </div>
      <div className="relative z-10 flex items-center gap-3">
        <ArrowsClockwise size={18} className="flex-shrink-0 animate-spin text-white" />
        <div className="min-w-0">
          <p className="text-xs font-black uppercase tracking-widest text-white">백테스트 진행 중</p>
          <p className="mt-0.5 text-sm font-bold text-white">
            {message || "백테스트 준비 중..."}
          </p>
        </div>
      </div>
      <style jsx>{`
        .backtest-aurora {
          position: absolute;
          display: block;
          width: 58%;
          height: 190%;
          border-radius: 999px;
          filter: blur(26px);
          mix-blend-mode: screen;
          opacity: 0.68;
          animation: backtestAuroraDrift 7s ease-in-out infinite;
        }

        .backtest-aurora-blue {
          left: -10%;
          top: -92%;
          background: radial-gradient(
            ellipse at center,
            rgba(125, 211, 252, 0.72) 0%,
            rgba(59, 130, 246, 0.3) 38%,
            rgba(59, 130, 246, 0) 72%
          );
        }

        .backtest-aurora-mint {
          right: 14%;
          bottom: -118%;
          background: radial-gradient(
            ellipse at center,
            rgba(167, 243, 208, 0.58) 0%,
            rgba(34, 197, 94, 0.22) 36%,
            rgba(34, 197, 94, 0) 74%
          );
          animation-delay: -2.4s;
        }

        .backtest-aurora-gold {
          right: -12%;
          top: -96%;
          background: radial-gradient(
            ellipse at center,
            rgba(253, 224, 71, 0.45) 0%,
            rgba(245, 158, 11, 0.18) 34%,
            rgba(245, 158, 11, 0) 74%
          );
          animation-delay: -4.8s;
        }

        @keyframes backtestAuroraDrift {
          0%,
          100% {
            transform: translate3d(-2%, 0, 0) rotate(-8deg) scale(1);
          }
          50% {
            transform: translate3d(5%, 6%, 0) rotate(8deg) scale(1.08);
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
  backtestRequest?: { symbols?: string[] } | null;
}) {
  const universeLabels = getDisplayUniverseLabels(parsed, backtestRequest);
  const exitLabels = getDisplayExitLabels(parsed);
  const rankingLabel = getRankingLabel(parsed);
  // 종목 선정(모멘텀 랭킹)도 진입(종목 선정) 기준이므로 '진입 신호'로 통일해 함께 표시한다.
  const entryLabels = [
    ...parsed.fundamental_filters.map(formatFundamentalFilter),
    ...parsed.entry_signals.map((s) => getSignalLabel(s, "entry")),
    ...(rankingLabel ? [rankingLabel] : []),
  ];

  return (
    <div
      className="space-y-3 rounded-2xl border border-gray-300/30 bg-[#101010] p-4"
      style={SOFT_MESSAGE_ENTER_STYLE}
    >
      <div className="flex items-center gap-1.5 border-b border-gray-300/20 pb-2">
        <CheckCircle size={13} className="text-amber-300" weight="fill" />
        <span className="text-xs font-black uppercase tracking-widest text-amber-100">전략 요약</span>
      </div>
      <div className="space-y-2">
        {parsed.universe.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-300 uppercase tracking-widest w-14 flex-shrink-0">유니버스</span>
            <div className="flex flex-wrap gap-1">
              {universeLabels.map((label, i) => (
                <FilterBadge key={i} label={label} />
              ))}
            </div>
          </div>
        )}
        {entryLabels.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-300 uppercase tracking-widest w-14 flex-shrink-0">{FUNDAMENTAL_FILTER_SECTION_LABEL}</span>
            <div className="flex flex-wrap gap-1">
              {entryLabels.map((label, i) => (
                <FilterBadge key={i} label={label} />
              ))}
            </div>
          </div>
        )}
        {exitLabels.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-300 uppercase tracking-widest w-14 flex-shrink-0">청산 신호</span>
            <div className="flex flex-wrap gap-1">
              {exitLabels.map((label, i) => (
                <FilterBadge key={i} label={label} />
              ))}
            </div>
          </div>
        )}
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className="text-[10px] font-bold text-gray-300 uppercase tracking-widest w-14 flex-shrink-0">포트폴리오</span>
          <div className="flex flex-wrap gap-1">
            <FilterBadge label={`최대 ${parsed.max_positions}종목`} />
            {parsed.hold_period_days && <FilterBadge label={`${parsed.hold_period_days}일 보유`} />}
            {parsed.rebalancing_period !== "none" && <FilterBadge label={`${REBAL_LABELS[parsed.rebalancing_period]} 리밸런싱`} />}
            <FilterBadge label={backtestPeriodLabel(parsed)} />
            <FilterBadge label={`초기자금 ${formatInitialCapital(parsed.initial_capital ?? 10000000)}`} />
          </div>
        </div>
        {(parsed.stop_loss_pct || parsed.take_profit_pct || parsed.trailing_stop_pct) && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-300 uppercase tracking-widest w-14 flex-shrink-0">리스크</span>
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

function StrategyLabContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isChatPage = pathname === "/analytics/chat" || searchParams.get("chat") === "1";
  const [inputValue, setInputValue] = useState("");
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
  const [visibleHeadlineChars, setVisibleHeadlineChars] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const resultScrollRef = useRef<HTMLDivElement>(null);
  const latestParsedRef = useRef<ParsedSummary | null>(null);
  const backtestReqRef = useRef<any>(null);
  const coachSessionIdRef = useRef<string | null>(null);
  const coachConversationRef = useRef<CoachConversationMessage[]>([]);
  const pendingPromptConsumedRef = useRef(false);
  // 진행 중이던 채팅을 한 번만 복원하기 위한 가드.
  const chatRestoredRef = useRef(false);
  const handleSendRef = useRef<(overrideText?: string) => Promise<void>>();
  // 직전에 언급된 종목 — '이 종목 팔까?' 같은 anaphora 해석용(분류 요청에 전달).
  const lastAnalyzedSymbolRef = useRef<string | null>(null);
  // first user prompt — kept for advisor context
  const firstPromptRef = useRef<string>("");
  // [규제 안전] 열린 종목 추천(STOCK_PICK) 전환 직후 진입하는 전략 빌더 모드.
  // 짧은 답변을 전략 필드로 누적하는 동안 true. 상태는 백엔드 step에 그대로 재전송한다.
  const builderModeRef = useRef(false);
  const builderStateRef = useRef<Record<string, any>>({});
  const pendingHoldingPeriodPromptRef = useRef<string | null>(null);
  const pendingHoldingPeriodHorizonRef = useRef<HoldingPeriodHorizon | null>(null);
  const pendingMetricResearchPromptRef = useRef<string | null>(null);
  const researchMetricRef = useRef<ResearchMetric | null>(null);
  const metricOptimizationDraftRef = useRef<MetricOptimizationDraft | null>(null);
  const metricOptimizationAbortRef = useRef<AbortController | null>(null);
  // 빌더 칩-only 단계에서 '직접 입력'을 눌러 채팅창을 다시 띄운 상태(빌더는 진행하지 않음).
  const [builderFreeTextRequested, setBuilderFreeTextRequested] = useState(false);

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
  }, [messages, latestParsed, backtestReq, currentOptions, stage, result, executedReq]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [inputValue]);

  useEffect(() => {
    const animationFrame = window.requestAnimationFrame(() => {
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
  }, [messages]);

  useEffect(() => {
    latestParsedRef.current = latestParsed;
  }, [latestParsed]);

  useEffect(() => {
    backtestReqRef.current = backtestReq;
  }, [backtestReq]);

  const isIdle = messages.length === 0 && !isSending;
  // 전략 빌더가 옵션 칩을 보여주는 동안에는 채팅창을 숨겨 사용자가 선택에 집중하게 한다.
  // 칩(infoSuggestions)은 빌더만 사용하므로, 마지막 어시스턴트 메시지에 칩이 있으면 입력창을 가린다.
  // '직접 설명하기'를 고르면 진입 조건(자유 입력) 질문은 칩이 없어 입력창이 다시 나타난다.
  const shouldShowChatInput = shouldShowChatInputBox(messages, isIdle, builderFreeTextRequested);

  useEffect(() => {
    if (!shouldShowChatInput || stage === "running" || result) return;

    const animationFrame = window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
    });

    return () => window.cancelAnimationFrame(animationFrame);
  }, [shouldShowChatInput, stage, result]);

  // period 제안 텍스트 → { parsed: backtest_period 값, options: currentOptions.period 값 }
  // 매칭되지 않으면 null 반환 (AI 파싱 필요)
  const resolvePeriodSuggestion = (text: string): { parsed: string; options: string } | "keep" | null => {
    if (/\d+년.*그대로 진행/.test(text)) return "keep";        // 현재 기간 유지
    if (/^1년/.test(text))   return { parsed: "1y",   options: "1Y"  };
    if (/^3년/.test(text))   return { parsed: "3y",   options: "3Y"  };
    if (/^5년/.test(text))   return { parsed: "5y",   options: "5Y"  };
    if (text === "전체 데이터") return { parsed: "full", options: "ALL" };
    return null;
  };

  const handleSuggestionClick = (text: string) => {
    const periodResult = resolvePeriodSuggestion(text);

    if (periodResult === null) {
      // period 제안이 아님 → 기존 AI 파싱 경로
      handleSend(text);
      return;
    }

    // period 제안: AI 없이 직접 적용
    const updatedParsed = latestParsed
      ? {
          ...latestParsed,
          backtest_period: periodResult === "keep"
            ? latestParsed.backtest_period
            : periodResult.parsed,
        }
      : latestParsed;

    if (updatedParsed) setLatestParsed(updatedParsed);

    if (periodResult !== "keep") {
      setCurrentOptions((prev: any) => ({ ...prev, period: periodResult.options }));
      if (backtestReq) setBacktestReq((prev: any) => ({ ...prev, period: periodResult.options }));
    }

    // 메시지: 사용자 선택 버블 추가 + 마지막 assistant 메시지의 parsed 업데이트 + clarification 제거
    setMessages(prev => {
      const msgs = [...prev];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant" && msgs[i].parsed) {
          msgs[i] = {
            ...msgs[i],
            parsed: updatedParsed ?? msgs[i].parsed,
            clarification: undefined,
            clarificationSuggestions: undefined,
          };
          break;
        }
      }
      return [...msgs, { role: "user", content: text }];
    });
  };

  const focusFreeTextInput = () => {
    setBuilderFreeTextRequested(true);
    window.setTimeout(() => textareaRef.current?.focus(), 0);
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

  // 열린 종목 추천(STOCK_PICK) 전환 직후, 사용자의 후속 입력을 기다리지 않고 곧바로
  // 전략 빌더의 첫 질문(시장 선택)을 띄운다. 질문·옵션 칩은 백엔드 빌더가 단일 출처로
  // 결정하므로(빈 입력 step = 현재 질문 조회) 프론트에서 하드코딩하지 않는다.
  const startStrategyBuilder = async (
    { reuseExisting = false, seedText, seedParsed, researchMetric }: {
      reuseExisting?: boolean;
      seedText?: string;
      seedParsed?: ParsedSummary | null;
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
      await appendAssistant({ role: "assistant", isLoading: true });
    }
    try {
      const res = await fetch("/api/strategy/builder/step", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          state: builderStateRef.current,
          input: "",
          seed: seedText,
          ...(seedParsed ? { seed_parsed: seedParsed } : {}),
        }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      builderStateRef.current = data.state ?? {};
      const activeResearchMetric = researchMetric ?? researchMetricRef.current;
      updateLastAssistant({
        isLoading: false,
        infoText: activeResearchMetric
          ? `${buildResearchMetricIntro(activeResearchMetric)}\n\n${data.reply}`
          : data.reply,
        infoSuggestions: data.suggestions?.length ? data.suggestions : undefined,
      });
    } catch {
      // 호출 실패 시 거절하지 않는다 — 빌더 모드는 유지되어 다음 입력부터 정상 진행된다.
      const activeResearchMetric = researchMetric ?? researchMetricRef.current;
      updateLastAssistant({
        isLoading: false,
        infoText: activeResearchMetric
          ? `${buildResearchMetricIntro(activeResearchMetric)}\n\n어떤 시장을 대상으로 할까요?`
          : "어떤 시장을 대상으로 할까요?",
      });
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
    // 최초 파싱에서 진입 규칙을 못 잡아 되묻는 경우. 이때는 코치를 돌리지 않는다
    // (불완전한 전략을 평가하면 안내 박스와 모순됨).
    let parseClarification: string | null = null;

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
        clarificationQuestion: parsedPayload.clarification_question,
        previousCoachText: lastCoachText(),
        riskOverrides: parsedPayload.risk_overrides ?? null,
      });

      const nextParsed = mergedResponse.parsed;
      const nextBacktestReq = mergedResponse.backtestRequest;

      coachSessionIdRef.current = null;
      // 전략을 수정해도 코치 대화 기록은 유지한다 — 이미 설명한 전문용어를 다시 설명하지 않도록.
      finalizedParsed = nextParsed;
      setLatestParsed(nextParsed);
      setBacktestReq(nextBacktestReq);
      setCurrentOptions({
        period: nextBacktestReq?.period ?? "5y",
        initialCapital: nextBacktestReq?.risk?.init_cash ?? 10000000,
        commissionPct: 0.015,
        slippagePct: 0.05,
      });
      setStage("ready");

      // The backend owns clarification decisions; the UI only renders the returned payload.
      const clarificationText = parsedPayload.clarification_question ?? null;
      const clarificationSuggestions = clarificationText
        ? parsedPayload.clarification_suggestions
        : undefined;
      parseClarification = clarificationText;
      const optimizationDraft = researchMetricRef.current && !clarificationText
        ? prepareMetricOptimization(nextBacktestReq)
        : null;
      updateLastAssistant({
        isLoading: false,
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
          // 백엔드 진행 단계: 'parsing'(규칙 파싱) → 'thinking'(LLM 처리) → 'validating'(LLM 검증).
          if (evt.stage === "parsing" || evt.stage === "thinking" || evt.stage === "validating") {
            updateLastAssistant({ isLoading: true, loadingStage: evt.stage });
          }
        } else if (evt.type === "parsed_final") {
          parsedPayload = evt;
        } else if (evt.type === "dsl_ready") {
          finalizeParse(evt.backtest_request, evt.symbol_count);
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

    if (finalizedParsed && !parseClarification && !researchMetricRef.current) {
      setMessages(prev => [
        ...prev,
        { role: "assistant", coachLoading: true, coachText: "" },
      ]);
      generateCoachResponse({
        userText: promptText,
        parsed: finalizedParsed,
      });
    }
  };

  // [전략별 특화 빌더] 빌더가 DSL을 직접 구성해 내려준 완성 전략을 한국어 재파싱 왕복 없이
  // 그대로 적용한다(파라미터 유실 방지). parsed는 ParsedStrategy dump = ParsedSummary와 동형,
  // backtest_request는 엔진 요청. runStrategyParseFlow.finalizeParse의 적용부와 동일한 효과.
  const applyBuilderConfirmedStrategy = (data: {
    parsed: ParsedSummary;
    backtest_request: any;
    prompt?: string;
    notices?: string[];
  }) => {
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

  const handleSend = async (overrideText?: string) => {
    const userText = overrideText ?? inputValue.trim();
    if (!userText || isSending || stage === "running") return;
    // 메시지를 보내는 순간 '직접 입력' 노출 토글을 해제한다(다음 빌더 단계는 다시 칩 집중).
    setBuilderFreeTextRequested(false);

    if (authState !== "authenticated" && isStrategyInput) {
      sessionStorage.setItem(PENDING_STRATEGY_PROMPT_KEY, userText);
      if (!overrideText) setInputValue("");
      setIsAuthModalOpen(true);
      return;
    }

    if (shouldBeginStrategyChatNavigation(isChatPage, messages.length)) {
      if (!overrideText) setInputValue("");
      beginStrategyChatNavigation(userText, (url) => router.push(url));
      return;
    }

    if (!overrideText) setInputValue("");
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

    const conversationContext = {
      stage,
      hasBacktestRequest: Boolean(currentBacktestReq),
      hasCurrentStrategy: Boolean(currentParsed),
      builderMode: builderModeRef.current,
      lastCoachText: lastCoachText(),
      pendingHoldingPeriodPrompt: pendingHoldingPeriodPromptRef.current,
      pendingHoldingPeriodHorizon: pendingHoldingPeriodHorizonRef.current,
      pendingResearchMetricPrompt: pendingMetricResearchPromptRef.current,
    };
    let turnDecision = decideConversationTurn(userText, conversationContext);

    if (turnDecision.action === "respond") {
      await appendAssistant({
        role: "assistant",
        infoText: turnDecision.message,
        infoSuggestions: turnDecision.suggestions,
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
      await startStrategyBuilder({ seedText: turnDecision.seedPrompt, researchMetric });
      setIsSending(false);
      return;
    }

    // 분류/파싱 호출 전에 '분석 중...' 로딩을 즉시 보여준다 (딜레이 동안 사용자 피드백 제공).
    // 이후 분기들은 이 버블을 updateLastAssistant로 변형해 재사용한다(새 버블 생성 금지).
    await appendAssistant({ role: "assistant", isLoading: true });

    // 전략 빌더 모드: 짧은 답변을 전략 필드로 누적한다(분류/거절보다 먼저 실행).
    if (turnDecision.action === "continue_builder") {
      try {
        const res = await fetch("/api/strategy/builder/step", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state: builderStateRef.current, input: userText }),
        });
        if (!res.ok) throw new Error();
        const data = await res.json();
        builderStateRef.current = data.state ?? {};

        if (data.status === "confirmed") {
          // 전략 완성 → 빌더 종료. 특화 빌더가 DSL(parsed+backtest_request)을 직접 내려주면
          // 재파싱 없이 그대로 적용하고, custom(자유 서술)만 프롬프트 재파싱 경로로 폴백한다.
          builderModeRef.current = false;
          builderStateRef.current = {};
          updateLastAssistant({ isLoading: true, infoText: undefined });
          try {
            if (data.parsed && data.backtest_request) {
              applyBuilderConfirmedStrategy(data);
            } else if (data.prompt) {
              await runStrategyParseFlow(data.prompt, null, null);
            }
          } catch (e: any) {
            updateLastAssistant({ isLoading: false, error: e.message ?? "알 수 없는 오류" });
          }
          setIsSending(false);
          return;
        }
        if (data.status === "exited") {
          builderModeRef.current = false;
          builderStateRef.current = {};
          pendingMetricResearchPromptRef.current = null;
          researchMetricRef.current = null;
          metricOptimizationDraftRef.current = null;
        }
        updateLastAssistant({
          isLoading: false,
          infoText: data.reply,
          infoSuggestions: data.suggestions?.length ? data.suggestions : undefined,
        });
      } catch {
        // 빌더 호출 실패 시 거절하지 않고 자연스럽게 다시 묻는다.
        updateLastAssistant({
          isLoading: false,
          infoText: "조건을 한 번 더 말씀해 주시겠어요?",
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
        updateLastAssistant({ isLoading: false, error: e.message ?? "알 수 없는 오류" });
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
        i === prev.length - 1 ? { role: "assistant", error: e.message ?? "알 수 없는 오류" } : m
      ));
    } finally {
      setIsSending(false);
    }
  };

  handleSendRef.current = handleSend;

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
    setInputValue("");
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
    setResult(null);
    setExecutedReq(null);
    setIsSending(false);
    coachSessionIdRef.current = null;
    coachConversationRef.current = [];
    firstPromptRef.current = "";
    pendingPromptConsumedRef.current = false;
    metricOptimizationDraftRef.current = null;
    metricOptimizationAbortRef.current?.abort();
    metricOptimizationAbortRef.current = null;
    setMetricOptimizationProgress(null);
    try {
      sessionStorage.removeItem(STRATEGY_CHAT_STATE_KEY);
    } catch {
      // 무시
    }
    if (isChatPage) {
      router.push("/analytics");
    }
    setTimeout(() => textareaRef.current?.focus(), 100);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  const shouldShowIntro = isIdle && !isChatPage;
  const headlineLines = ["투자 아이디어를 전략으로 만들고", "전략을 시뮬레이션 하세요"];
  const totalHeadlineChars = headlineLines.reduce((sum, line) => sum + line.length, 0);
  const strategyPreviewBackgroundClass = isStrategyPreviewModalOpen
    ? "pointer-events-none select-none blur-[6px] transition-[filter,opacity] duration-200"
    : "transition-[filter,opacity] duration-200";
  const softEnterStyle = {
    animation: "softChatSurfaceEnter 720ms cubic-bezier(0.19, 1, 0.22, 1) both",
  };
  const softEnterLateStyle = {
    animation: "softChatSurfaceEnter 820ms cubic-bezier(0.19, 1, 0.22, 1) 120ms both",
  };

  // 훅은 early return 위에 있어야 한다 — 결과 화면으로 early return 시 훅 개수가
  // 줄어들어 "Rendered fewer hooks than expected" 에러가 나기 때문.
  useEffect(() => {
    if (!shouldShowIntro) {
      setVisibleHeadlineChars(0);
      return;
    }

    setVisibleHeadlineChars(0);
    const timer = window.setInterval(() => {
      setVisibleHeadlineChars((current) => {
        if (current >= totalHeadlineChars) {
          window.clearInterval(timer);
          return current;
        }

        return current + 1;
      });
    }, 38);

    return () => window.clearInterval(timer);
  }, [shouldShowIntro, totalHeadlineChars]);

  // ── 결과 화면
  const isRunning = stage === "running";
  const showingBacktestResult = (stage === "done" || isRunning) && !!result;

  // 결과 화면에서 브라우저 뒤로가기 → 페이지 이탈 대신 대화창으로 복귀(결과·대화 유지).
  // showingBacktestResult(boolean) 변화에만 반응하므로 running↔done 전환 시 중복 push가 없다.
  useEffect(() => {
    if (!showingBacktestResult) return;
    return installBacktestResultBackHandler(() => setStage("ready"));
  }, [showingBacktestResult]);

  // 결과 화면 진입 시(또는 재실행 완료 시) 채팅 화면에서 내려가 있던 스크롤 위치가 그대로
  // 남아 결과가 아래쪽부터 보이는 문제를 막기 위해 항상 맨 위로 스크롤한다.
  const wasShowingBacktestResultRef = useRef(false);
  useEffect(() => {
    const enteringResultView = showingBacktestResult && !wasShowingBacktestResultRef.current;
    wasShowingBacktestResultRef.current = showingBacktestResult;
    if (!enteringResultView && stage !== "done") return;

    document.querySelector("main")?.scrollTo({ top: 0, behavior: "auto" });
    resultScrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [showingBacktestResult, stage]);

  if (showingBacktestResult) {
    return (
      <DashboardLayout userName="">
        <div
          className="flex flex-col"
          style={{ minHeight: "calc(100vh - var(--top-menu-bar-height, 76px))" }}
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
  const hasTypedInput = inputValue.length > 0;
  const canSubmitInput = !!inputValue.trim() && !isSending && stage !== "running";
  const isLlmWorking = isSending;
  const hasChatStarted = messages.length > 0;
  const isLastAssistant = (i: number) => i === messages.length - 1 && messages[i].role === "assistant";

  // ── 메인 채팅 화면
  return (
    <DashboardLayout userName="">
      <style>{`
        @keyframes softChatSurfaceEnter {
          from {
            opacity: 0;
            transform: translate3d(0, 6px, 0);
          }
          to {
            opacity: 1;
            transform: translate3d(0, 0, 0);
          }
        }

        @keyframes softChatCardEnter {
          from {
            opacity: 0;
            transform: translate3d(0, 5px, 0) scale(0.995);
          }
          to {
            opacity: 1;
            transform: translate3d(0, 0, 0) scale(1);
          }
        }

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
        className={`relative flex flex-col items-center gap-4 overflow-x-hidden px-4 pt-20 ${hasChatStarted ? "pb-56" : "pb-12"} ${strategyPreviewBackgroundClass}`}
        data-testid="strategy-lab-background"
        style={{ minHeight: "calc(100vh - var(--top-menu-bar-height, 76px))" }}
      >
        {shouldShowIntro && <StrategyWaveBackground />}

        {/* ── 채팅 영역 ── */}
        <div
          key={isChatPage ? "strategy-chat-page" : "strategy-intro-page"}
          className="relative z-10 flex min-h-[calc(100vh-var(--top-menu-bar-height,76px)-5rem)] w-full flex-col items-center justify-start transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
          style={softEnterStyle}
        >
        <div className={`w-full max-w-4xl flex flex-col items-center gap-6 ${
          hasChatStarted
            ? "min-h-[calc(100vh-var(--top-menu-bar-height,76px)-5rem)]"
            : "min-h-[calc(100vh-var(--top-menu-bar-height,76px)-5rem)] justify-end pb-10"
        }`}>

          {/* 헤더 */}
          {shouldShowIntro && (
          <div className="w-full max-w-3xl">
            <div className="flex flex-col items-center gap-3 text-center">
              <div className="space-y-4">
                <p
                  data-testid="strategy-lab-headline"
                  className="max-w-5xl text-6xl leading-none tracking-tight text-[#fcfdff] md:text-7xl [font-weight:950]"
                  style={{ textShadow: "0 0 24px rgba(255, 255, 255, 0.18)" }}
                >
                  {buildAnimatedHeadline(headlineLines, visibleHeadlineChars)}
                </p>
                <p className="text-base font-bold leading-relaxed text-gray-400">
                  AI와 함께 전략을 설계하고, 바로 백테스트 하세요
                </p>
              </div>
            </div>
            {modelStatus?.status === "failed" && (
              <div className="mt-2 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--main-blue)]/10 border border-[var(--main-blue)]/20 text-[var(--main-blue)] text-xs font-bold">
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
              <div
                className="w-full space-y-4 px-1 py-2"
                style={softEnterStyle}
              >
                {messages.map((msg, i) => (
                  <div key={i}>
                    {msg.role === "user" && (
                      <div className="flex justify-end" style={SOFT_MESSAGE_ENTER_STYLE}>
                        <div className={`max-w-[80%] rounded-tr-sm px-4 py-2.5 ${USER_CHAT_BUBBLE_CLASS}`}>
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
                          <div
                            className={`max-w-[88%] rounded-tl-sm p-3.5 space-y-2 ${COACH_CHAT_BUBBLE_CLASS}`}
                            style={SOFT_MESSAGE_ENTER_STYLE}
                          >
                            <p className="text-sm font-bold text-white leading-relaxed whitespace-pre-line">
                              {msg.infoText}
                            </p>
                            {isLastAssistant(i) && metricOptimizationProgress && (
                              <MetricOptimizationProgressIndicator progress={metricOptimizationProgress} />
                            )}
                            {isLastAssistant(i) && msg.infoSuggestions && msg.infoSuggestions.length > 0 && (
                              <div className="flex flex-wrap gap-2 pt-1">
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
                                      void handleSend(suggestion);
                                    }}
                                    className="px-3 py-1.5 rounded-lg bg-[#171717] border border-white/10 hover:border-yellow-400/50 hover:bg-[#202020] text-xs font-bold text-gray-300 transition-all duration-200 text-left"
                                  >
                                    {suggestion}
                                  </button>
                                ))}
                                {shouldShowMovingAverageHelp(msg) && <MovingAverageTypeHelp />}
                              </div>
                            )}
                          </div>
                        )}
                        {msg.parsed && (
                          <>
                            <ParsedSummaryBubble parsed={msg.parsed} backtestRequest={backtestReq} />
                            {msg.notices && msg.notices.length > 0 && (
                              <div className="flex flex-col gap-1.5" style={SOFT_MESSAGE_ENTER_LATE_STYLE}>
                                {msg.notices.map((notice, ni) => (
                                  <div
                                    key={ni}
                                    className="flex items-start gap-2.5 p-3 rounded-xl bg-[#111111] border border-white/10"
                                  >
                                    <Info size={13} className="text-yellow-400 flex-shrink-0 mt-0.5" weight="fill" />
                                    <p className="text-xs font-bold text-gray-300 leading-relaxed whitespace-pre-line">
                                      {notice}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            )}
                            {isLastAssistant(i) && !msg.coachLoading && msg.clarification && (
                              <div
                                className="flex flex-col gap-2.5 p-3.5 rounded-xl bg-[#111111] border border-yellow-400/40"
                                style={SOFT_MESSAGE_ENTER_LATE_STYLE}
                              >
                                <div className="flex items-start gap-2.5">
                                  <Question size={13} className="text-yellow-400 flex-shrink-0 mt-0.5" weight="fill" />
                                  <p className="text-xs font-bold text-gray-300 leading-relaxed whitespace-pre-line">
                                    {msg.clarification.replace(/\*\*(.*?)\*\*/g, "$1")}
                                  </p>
                                </div>
                                {msg.clarificationSuggestions && msg.clarificationSuggestions.length > 0 && (
                                  <div className="flex flex-wrap gap-2 pl-6">
                                    {msg.clarificationSuggestions.map((suggestion) => (
                                      <button
                                        key={suggestion}
                                        onClick={() => handleSuggestionClick(suggestion)}
                                        className="px-3 py-1.5 rounded-lg bg-[#171717] border border-white/10 hover:border-yellow-400/50 hover:bg-[#202020] text-xs font-bold text-gray-300 transition-all duration-200 text-left"
                                      >
                                        {suggestion}
                                      </button>
                                    ))}
                                    {!msg.clarificationSuggestions.includes(FREE_INPUT_CHIP) && (
                                      <button
                                        type="button"
                                        onClick={focusFreeTextInput}
                                        className="px-3 py-1.5 rounded-lg bg-[#171717] border border-white/10 hover:border-yellow-400/50 hover:bg-[#202020] text-xs font-bold text-gray-300 transition-all duration-200 text-left"
                                      >
                                        {FREE_INPUT_CHIP}
                                      </button>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}
                            {isLastAssistant(i) && stage === "ready" && runButtonPlacement(msg) === "summary" && (
                              <button
                                onClick={() => handleRunBacktest()}
                                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-black transition-all duration-300 hover:shadow-[0_0_24px_rgba(59,130,246,0.4)]"
                              >
                                <ChartLineUp size={13} weight="fill" />
                                백테스트 실행
                                <ArrowRight size={11} />
                              </button>
                            )}
                            {isLastAssistant(i) && stage === "running" && (
                              <div className="flex items-center gap-2 px-1">
                                <ArrowsClockwise size={13} className="text-sky-400 animate-spin flex-shrink-0" />
                                <span className="text-xs font-bold text-gray-500 transition-all duration-300">{statusMessage}</span>
                              </div>
                            )}
                          </>
                        )}
                        {(msg.coachLoading || msg.coachText) && (
                          <div
                            className={`max-w-[88%] rounded-tl-sm p-3.5 space-y-2 ${COACH_CHAT_BUBBLE_CLASS}`}
                            style={SOFT_MESSAGE_ENTER_LATE_STYLE}
                          >
                            <div className="flex items-center gap-2">
                              <span className="text-[11px] font-black uppercase tracking-widest text-white">
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
                                      className="underline text-sky-300 hover:text-sky-200"
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
                        {isLastAssistant(i) && stage === "ready" && runButtonPlacement(msg) === "coach" && (
                          <button
                            onClick={() => handleRunBacktest()}
                            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-black transition-all duration-300 hover:shadow-[0_0_24px_rgba(59,130,246,0.4)]"
                          >
                            <ChartLineUp size={13} weight="fill" />
                            백테스트 실행
                            <ArrowRight size={11} />
                          </button>
                        )}
                        {msg.error && (
                          <div
                            className="flex items-start gap-2.5 p-3.5 rounded-xl bg-[var(--error-red)]/10 border border-[var(--error-red)]/20"
                            style={SOFT_MESSAGE_ENTER_STYLE}
                          >
                            <Warning size={13} className="text-[var(--error-red)] flex-shrink-0 mt-0.5" weight="fill" />
                            <div className="space-y-1 flex-1">
                              <p className="text-xs font-black text-[var(--error-red)]">오류 발생</p>
                              <p className="text-xs font-bold text-gray-500">{msg.error}</p>
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
            <div
              key={shouldShowIntro ? "intro-chat-input" : "active-chat-input"}
              className="relative w-full rounded-[28px] border border-[var(--glass-border)] bg-[#101010]"
              style={softEnterLateStyle}
            >
              <textarea
                ref={textareaRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={stage === "running"}
                rows={2}
                placeholder="어떤 투자 아이디어를 테스트해볼까요?"
                className="w-full resize-none bg-transparent px-5 pt-4 pb-12 text-sm font-bold leading-relaxed text-white outline-none placeholder-gray-600 focus:outline-none focus:ring-0"
              />
              <div className="absolute bottom-3 right-3 flex items-center gap-2">
                <button
                  onClick={() => handleSend()}
                  disabled={!canSubmitInput}
                  aria-label={isLlmWorking ? (isStrategyInput ? "전략 생성 중" : "전송 중") : (isStrategyInput ? "전략 생성" : "전송")}
                  title={isLlmWorking ? (isStrategyInput ? "전략 생성 중" : "전송 중") : (isStrategyInput ? "전략 생성" : "전송")}
                  className={`flex h-8 w-8 items-center justify-center rounded-full transition-colors duration-300 ${
                    isLlmWorking
                      ? "cursor-wait bg-[#f3f1ec]"
                      : hasTypedInput
                        ? "bg-[#f3f1ec] text-[#2b2b2b] hover:bg-white disabled:cursor-not-allowed"
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
            </div>
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
          <div
            key="fixed-chat-input"
            className="fixed bottom-4 left-4 right-4 z-40 mx-auto max-w-4xl rounded-[28px] border border-[var(--glass-border)] bg-[#101010]"
            style={softEnterLateStyle}
          >
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={stage === "running"}
              rows={2}
              placeholder="어떤 투자 아이디어를 테스트해볼까요?"
              className="w-full resize-none bg-transparent px-5 pt-4 pb-12 text-sm font-bold leading-relaxed text-white outline-none placeholder-gray-600 focus:outline-none focus:ring-0"
            />
            <button
              type="button"
              onClick={handleReset}
              className="absolute bottom-3 left-3 inline-flex items-center gap-1.5 rounded-full border border-[var(--accent-blue)] bg-[#171717] px-3 py-1.5 text-xs font-bold text-gray-400 transition-all duration-200 hover:bg-[#202020] hover:text-white"
            >
              <X size={12} weight="bold" />
              대화 종료
            </button>
            <div className="absolute bottom-3 right-3 flex items-center gap-2">
              <button
                onClick={() => handleSend()}
                disabled={!canSubmitInput}
                aria-label={isLlmWorking ? (isStrategyInput ? "전략 생성 중" : "전송 중") : (isStrategyInput ? "전략 생성" : "전송")}
                title={isLlmWorking ? (isStrategyInput ? "전략 생성 중" : "전송 중") : (isStrategyInput ? "전략 생성" : "전송")}
                className={`flex h-8 w-8 items-center justify-center rounded-full transition-colors duration-300 ${
                  isLlmWorking
                    ? "cursor-wait bg-[#f3f1ec]"
                    : hasTypedInput
                      ? "bg-[#f3f1ec] text-[#2b2b2b] hover:bg-white disabled:cursor-not-allowed"
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
          </div>
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
              className="inline-flex items-center gap-1.5 rounded-full border border-[var(--accent-blue)] bg-[#171717] px-4 py-2 text-xs font-bold text-gray-300 shadow-lg transition-all duration-200 hover:bg-[#202020] hover:text-white"
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
            className="w-full max-w-md rounded-3xl border border-white/[0.08] bg-[#0b0b0b] p-6 text-center shadow-2xl shadow-black/50"
            style={softEnterStyle}
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
