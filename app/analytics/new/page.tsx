"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import dynamic from "next/dynamic";
import { createClient } from "@supabase/supabase-js";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { StrategyExampleTabs } from "@/components/strategy/StrategyExampleTabs";
import { StrategyWaveBackground } from "@/components/strategy/StrategyWaveBackground";
import { PENDING_STRATEGY_PROMPT_KEY } from "@/components/strategy/strategyTemplateSession";
import { BacktestResult } from "@/types/strategy";
import { mapRawBacktestResult } from "./backtestResultMapper";
import {
  Sparkle,
  ArrowRight,
  ArrowsClockwise,
  CheckCircle,
  Warning,
  ChartLineUp,
  Question,
  GoogleLogo,
} from "phosphor-react";
import {
  buildStrategySummary,
  FUNDAMENTAL_FILTER_SECTION_LABEL,
  formatFundamentalFilter,
  formatInitialCapital,
  getDisplayExitLabels,
  getDisplayUniverseLabels,
  getRankingLabel,
  INDICATOR_LABELS,
  PERIOD_LABELS,
  REBAL_LABELS,
  type ParsedSummary,
} from "./strategySummary";
import {
  buildWalkForwardRequest,
  isAdvisorFollowUpPrompt,
  mergeStrategyModification,
  type AdvisorWalkForwardSettings,
} from "./parsedStrategyMerge";
import { normalizeCoachMessage } from "./coachMessage";
import { parseCoachSegments } from "./coachText";
import { parseSseBlocks } from "./sseEvents";
import StockAnalysisPanel, { type StockAnalysisResult } from "@/components/strategy/StockAnalysisPanel";

const BacktestDashboard = dynamic(
  () => import("@/components/strategy/backtest/BacktestDashboard"),
  { ssr: false }
);

type Stage = "idle" | "ready" | "running" | "done";
const BACKTEST_ENGINE_VERSION = "benchmark-etf-v2";
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
  parseSkeleton?: ParseSkeleton;
  coachText?: string;
  clarification?: string;
  clarificationSuggestions?: string[];
  coachLoading?: boolean;  // coach response is being generated
  isLoading?: boolean;
  error?: string;
  // 개별 종목 질문 / 일반 투자 질문 응답
  stockAnalysis?: StockAnalysisResult;
  stockLoading?: boolean;
  infoText?: string;  // 일반 투자 답변 또는 종목 명확화 안내
}

interface ParseSkeleton {
  description: string;
  universe: string[];
  max_positions: number | null;
  recognized_terms: string[];
  confidence: "partial" | "low";
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

function AnalysisStatusBubble({ title }: { title: string }) {
  return (
    <div
      className={`max-w-[88%] rounded-tl-sm p-3.5 space-y-2 ${COACH_CHAT_BUBBLE_CLASS}`}
      style={SOFT_MESSAGE_ENTER_LATE_STYLE}
    >
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-black uppercase tracking-widest text-white">
          {title}
        </span>
        <ShimmerStatusText className="text-sm font-bold">분석 중...</ShimmerStatusText>
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

const SKELETON_TERM_LABELS: Record<string, string> = {
  pbr: "PBR",
  per: "PER",
  roe: "ROE",
  ma_crossover: "이동평균 크로스",
  rsi: "RSI",
  macd: "MACD",
  bollinger_bands: "볼린저밴드",
  breakout: "신고가 돌파",
  stop_loss: "손절",
  take_profit: "익절",
  hold_period: "보유 기간",
};

function ParseSkeletonBubble({ skeleton }: { skeleton: ParseSkeleton }) {
  return (
    <div
      className="bg-[#111111] border border-white/[0.07] rounded-2xl rounded-tl-sm p-4 space-y-3"
      style={SOFT_MESSAGE_ENTER_STYLE}
    >
      <div className="flex items-center gap-1.5">
        <ArrowsClockwise size={13} className="text-sky-400 animate-spin" />
        <span className="text-xs font-black uppercase tracking-widest text-white">전략 구조 분석 중</span>
      </div>
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest w-14 flex-shrink-0">유니버스</span>
          <div className="flex flex-wrap gap-1">
            {skeleton.universe.map((item) => (
              <FilterBadge key={item} label={item} />
            ))}
          </div>
        </div>
        {skeleton.max_positions !== null && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest w-14 flex-shrink-0">포트폴리오</span>
            <FilterBadge label={`최대 ${skeleton.max_positions}종목`} />
          </div>
        )}
        {skeleton.recognized_terms.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest w-14 flex-shrink-0">인식 조건</span>
            <div className="flex flex-wrap gap-1">
              {skeleton.recognized_terms.map((term) => (
                <FilterBadge key={term} label={SKELETON_TERM_LABELS[term] ?? term} />
              ))}
            </div>
          </div>
        )}
      </div>
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
  const entryLabels = [
    ...parsed.fundamental_filters.map(formatFundamentalFilter),
    ...parsed.entry_signals.map((s) => INDICATOR_LABELS[s.indicator] ?? s.indicator),
  ];

  return (
    <div
      className="space-y-3 rounded-2xl border border-amber-300/50 bg-[#101010] p-4"
      style={SOFT_MESSAGE_ENTER_STYLE}
    >
      <div className="flex items-center gap-1.5 border-b border-amber-300/20 pb-2">
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
        {rankingLabel && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-300 uppercase tracking-widest w-14 flex-shrink-0">선정</span>
            <div className="flex flex-wrap gap-1">
              <FilterBadge label={rankingLabel} />
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
            <FilterBadge label={`백테스트 ${PERIOD_LABELS[parsed.backtest_period]}`} />
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
  const [latestParsed, setLatestParsed] = useState<ParsedSummary | null>(null);
  const [backtestReq, setBacktestReq] = useState<any>(null);
  const [currentOptions, setCurrentOptions] = useState<any>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [modelStatus, setModelStatus] = useState<{ status: string; error: string | null } | null>(null);
  const [visibleHeadlineChars, setVisibleHeadlineChars] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const latestParsedRef = useRef<ParsedSummary | null>(null);
  const backtestReqRef = useRef<any>(null);
  const coachSessionIdRef = useRef<string | null>(null);
  const coachConversationRef = useRef<CoachConversationMessage[]>([]);
  const pendingPromptConsumedRef = useRef(false);
  const handleSendRef = useRef<(overrideText?: string) => Promise<void>>();
  // 직전 분석 종목 — '이 종목 팔까?' 같은 anaphora 해석용
  const lastAnalyzedSymbolRef = useRef<string | null>(null);
  // '다른 종목 분석' 버튼으로 종목명을 묻는 중 — 다음 입력을 분석으로 받는다.
  const awaitingStockAnalysisRef = useRef(false);
  // first user prompt — kept for advisor context
  const firstPromptRef = useRef<string>("");

  useEffect(() => {
    fetch("/api/model/status")
      .then((r) => r.json())
      .then(setModelStatus)
      .catch(() => setModelStatus({ status: "failed", error: "서버에 연결할 수 없습니다" }));
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

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [inputValue]);

  useEffect(() => {
    const animationFrame = window.requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    });

    return () => window.cancelAnimationFrame(animationFrame);
  }, [messages]);

  useEffect(() => {
    latestParsedRef.current = latestParsed;
  }, [latestParsed]);

  useEffect(() => {
    backtestReqRef.current = backtestReq;
  }, [backtestReq]);

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

  const updateLastAssistant = (patch: Partial<ChatMessage>) => {
    setMessages(prev => {
      const lastIdx = prev.map((m, i) => m.role === "assistant" ? i : -1).filter(i => i >= 0).at(-1);
      if (lastIdx === undefined) return prev;
      return prev.map((m, i) => i === lastIdx ? { ...m, ...patch } : m);
    });
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

  // 종목 분석 요청을 보내고 마지막 assistant 메시지에 결과/에러를 렌더한다(분류 경로·
  // '다른 종목 분석' 경로 공용). symbol 없이 query만 주면 백엔드가 종목명을 해석한다.
  const renderStockAnalysisResult = async (
    body: { symbol?: string; query: string; last_symbol?: string | null },
  ): Promise<void> => {
    try {
      const res = await fetch("/api/stock/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.status === 422) {
        // 종목을 특정하지 못함 → 다시 묻고 다음 입력을 분석으로 받는다.
        awaitingStockAnalysisRef.current = true;
        updateLastAssistant({
          stockLoading: false,
          infoText: "종목을 찾지 못했어요. 정확한 종목명이나 코드를 알려주세요.",
        });
        setTimeout(() => textareaRef.current?.focus(), 100);
        return;
      }
      if (!res.ok) throw new Error();
      const result: StockAnalysisResult = await res.json();
      lastAnalyzedSymbolRef.current = result.symbol;
      updateLastAssistant({ stockLoading: false, stockAnalysis: result });
    } catch {
      updateLastAssistant({
        stockLoading: false,
        error: "종목 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
      });
    }
  };

  // '다른 종목 분석' 버튼 — 종목명을 묻고, 다음 사용자 입력을 종목 분석으로 받는다.
  const handleAnalyzeAnotherStock = () => {
    awaitingStockAnalysisRef.current = true;
    setMessages(prev => [
      ...prev,
      { role: "assistant", infoText: "어떤 종목을 분석해 드릴까요? 종목명을 입력해 주세요." },
    ]);
    setTimeout(() => textareaRef.current?.focus(), 100);
  };

  // 개별 종목 질문 / 일반 투자 질문을 전략 흐름과 분리해 처리한다.
  // 처리했으면 true(전략 파싱으로 넘어가지 않음), 아니면 false(기존 전략 흐름).
  const maybeRouteNonStrategyQuery = async (
    userText: string,
    currentParsed: ParsedSummary | null,
  ): Promise<boolean> => {
    let intent = "STRATEGY_ADVICE";
    let symbol: string | null = null;
    let suggestedReply: string | null = null;
    try {
      const res = await fetch("/api/query/classify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: userText, last_symbol: lastAnalyzedSymbolRef.current }),
      });
      if (!res.ok) return false;  // 분류 실패 시 기존 전략 흐름으로 폴백
      const data = await res.json();
      intent = data.intent;
      symbol = data.symbols?.[0]?.symbol ?? null;
      suggestedReply = data.suggested_reply ?? null;
    } catch {
      return false;
    }

    // 인사 / 역할 밖 질문 → 전략으로 파싱하지 않고 정해진 안내를 바로 보여준다.
    if (intent === "GREETING" || intent === "OFF_TOPIC") {
      const fallback =
        intent === "GREETING"
          ? "안녕하세요. 오늘은 어떤 전략을 연구해 볼까요?"
          : "저는 투자 전략 및 투자 분석 전용 모델입니다. 현재 질문에는 도움을 드릴 수 없습니다. 대신 투자 전략, 백테스트, 종목 분석과 관련된 질문은 도와드릴 수 있습니다.";
      setMessages(prev => [
        ...prev,
        { role: "user", content: userText },
        { role: "assistant", infoText: suggestedReply ?? fallback },
      ]);
      return true;
    }

    // 개별 종목 질문 → Stock Analysis Agent
    if (intent === "STOCK_ANALYSIS") {
      // 전략 작성 중인데 종목이 특정되지 않은 STOCK_ANALYSIS는 대개 오분류다
      // (예: "PBR 1 이하 종목"). "어떤 종목을 분석할까요?" 막다른 길 대신
      // 전략 다듬기 흐름으로 흘려보낸다.
      if (!symbol && currentParsed) return false;
      setMessages(prev => [
        ...prev,
        { role: "user", content: userText },
        { role: "assistant", stockLoading: true },
      ]);
      if (!symbol) {
        updateLastAssistant({
          stockLoading: false,
          infoText: "어떤 종목을 분석할까요? 종목명을 알려주시면 분석해 드리겠습니다.",
        });
        return true;
      }
      await renderStockAnalysisResult({ symbol, query: userText });
      return true;
    }

    // 일반 투자 지식 질문 → 전략 작성 중이 아닐 때만 가로챈다.
    if (intent === "GENERAL_INVESTMENT" && !currentParsed) {
      setMessages(prev => [
        ...prev,
        { role: "user", content: userText },
        { role: "assistant", isLoading: true },
      ]);
      try {
        const res = await fetch("/api/query/general", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: userText }),
        });
        if (!res.ok) throw new Error();
        const data = await res.json();
        updateLastAssistant({ isLoading: false, infoText: data.answer });
      } catch {
        updateLastAssistant({ isLoading: false, error: "답변을 가져오지 못했습니다." });
      }
      return true;
    }

    return false;
  };

  const handleSend = async (overrideText?: string) => {
    const userText = overrideText ?? inputValue.trim();
    if (!userText || isSending || stage === "running") return;

    if (authState !== "authenticated" && isStrategyInput) {
      sessionStorage.setItem(PENDING_STRATEGY_PROMPT_KEY, userText);
      if (!overrideText) setInputValue("");
      setIsAuthModalOpen(true);
      return;
    }

    if (!overrideText && !isChatPage && messages.length === 0) {
      sessionStorage.setItem(PENDING_STRATEGY_PROMPT_KEY, userText);
      setInputValue("");
      router.push("/analytics/chat");
      return;
    }

    if (!overrideText) setInputValue("");
    if (!firstPromptRef.current) firstPromptRef.current = userText;
    const currentParsed = latestParsedRef.current ?? latestParsed;
    const currentBacktestReq = backtestReqRef.current ?? backtestReq;
    setIsSending(true);

    // '다른 종목 분석'으로 종목명을 묻는 중이면, 다음 입력은 분류 없이 바로 분석한다.
    if (awaitingStockAnalysisRef.current) {
      awaitingStockAnalysisRef.current = false;
      setMessages(prev => [
        ...prev,
        { role: "user", content: userText },
        { role: "assistant", stockLoading: true },
      ]);
      await renderStockAnalysisResult({ query: userText, last_symbol: lastAnalyzedSymbolRef.current });
      setIsSending(false);
      return;
    }

    const routed = await maybeRouteNonStrategyQuery(userText, currentParsed);
    if (routed) {
      setIsSending(false);
      return;
    }

    if (currentParsed && isAdvisorFollowUpPrompt(userText)) {
      setMessages(prev => [
        ...prev,
        { role: "user", content: userText },
        { role: "assistant", parsed: currentParsed, coachLoading: true, coachText: "" },
      ]);
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

    setMessages(prev => [
      ...prev,
      { role: "user", content: userText },
      { role: "assistant", isLoading: true },
    ]);

    try {
      const res = await fetch("/api/strategy/parse/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: userText,
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
        const nextBacktestRequest = backtestRequest
          ? {
              ...backtestRequest,
              symbol_count: symbolCount ?? backtestRequest.symbol_count,
            }
          : backtestRequest;
        const mergedResponse = mergeStrategyModification({
          previousParsed: currentParsed,
          nextParsed: parsedPayload.parsed,
          previousBacktestRequest: currentBacktestReq,
          nextBacktestRequest,
          userPrompt: userText,
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

        // 최초 파싱에서 진입(종목 선정) 규칙을 통째로 못 잡았으면, 조용히 넘기지 않고
        // 백엔드가 보낸 안내를 노란 박스로 드러낸다(상대강도 랭킹 등 미지원 유형 포함).
        const isFirstParse = !currentParsed;
        parseClarification = isFirstParse ? (parsedPayload.clarification_question ?? null) : null;
        updateLastAssistant({
          isLoading: false,
          parseSkeleton: undefined,
          parsed: nextParsed,
          clarification: isFirstParse ? (parsedPayload.clarification_question ?? undefined) : undefined,
          clarificationSuggestions: isFirstParse
            ? (parsedPayload.clarification_suggestions ?? undefined)
            : undefined,
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

          if (evt.type === "skeleton" && evt.data) {
            updateLastAssistant({ isLoading: true, parseSkeleton: evt.data });
          } else if (evt.type === "parsed_final") {
            parsedPayload = evt;
          } else if (evt.type === "dsl_ready") {
            finalizeParse(evt.backtest_request, evt.symbol_count);
          } else if (evt.type === "error") {
            throw new Error(evt.detail ?? "파싱 실패");
          }
        }
      }

      if (finalizedParsed && !parseClarification) {
        setMessages(prev => [
          ...prev,
          { role: "assistant", coachLoading: true, coachText: "" },
        ]);
        generateCoachResponse({
          userText,
          parsed: finalizedParsed,
        });
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

      if (!coachRes.ok) {
        updateLastAssistant({
          coachLoading: false,
          coachText: "전략 코칭 응답을 가져오지 못했습니다. 전략 요약은 준비되어 있으니 백테스트는 계속 실행할 수 있습니다.",
        });
        return;
      }

      coachSessionIdRef.current = coachRes.headers.get("X-Coach-Session-Id");
      const result: { message?: string } = await coachRes.json();
      const message = normalizeCoachMessage(
        result.message,
        "현재 전략에 대한 코칭 응답을 생성하지 못했습니다."
      );
      rememberCoachExchange(userText, message);
      updateLastAssistant({
        coachLoading: false,
        coachText: message,
      });
    } catch {
      updateLastAssistant({
        coachLoading: false,
        coachText: "전략 코칭 중 오류가 발생했습니다. 전략 요약은 준비되어 있으니 백테스트는 계속 실행할 수 있습니다.",
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

      if (!coachRes.ok) {
        updateLastAssistant({
          coachLoading: false,
          coachText: "전략 코칭 응답을 가져오지 못했습니다. 전략 요약은 준비되어 있으니 백테스트는 계속 실행할 수 있습니다.",
        });
        return;
      }

      if (!sessionId) {
        coachSessionIdRef.current = coachRes.headers.get("X-Coach-Session-Id");
      }
      const result: { message?: string } = await coachRes.json();
      const message = normalizeCoachMessage(
        result.message,
        "현재 질문에 대한 코칭 응답을 생성하지 못했습니다."
      );
      rememberCoachExchange(userText, message);
      updateLastAssistant({
        coachLoading: false,
        coachText: message,
      });
    } catch {
      updateLastAssistant({
        coachLoading: false,
        coachText: "전략 코칭 중 오류가 발생했습니다. 전략 요약은 준비되어 있으니 백테스트는 계속 실행할 수 있습니다.",
      });
    }
  };

  const handleRunBacktest = async (options?: any) => {
    if (!backtestReq) return;

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

      const processPayload = (payload: string) => {
        if (payload === "[DONE]") {
          streamDone = true;
          return;
        }

        const event = JSON.parse(payload);
        if (event.type === "status") {
          setStatusMessage(event.message);
        } else if (event.type === "result") {
          setResult(mapRawBacktestResult(event.data, `nl_${Date.now()}`));
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

  const handleWalkForward = async (settings: AdvisorWalkForwardSettings) => {
    if (!backtestReq) {
      throw new Error("워크포워드 분석을 실행할 백테스트 요청이 없습니다.");
    }

    const ranges: Record<string, unknown> = {};
    const res = await fetch("/api/backtest/walk-forward", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildWalkForwardRequest(backtestReq, settings, ranges)),
    });

    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail ?? "워크포워드 분석 실패");
    }

    const data = await res.json();
    return data;
  };

  const handleReset = () => {
    setStage("idle");
    setMessages([]);
    setLatestParsed(null);
    setBacktestReq(null);
    setResult(null);
    setIsSending(false);
    coachSessionIdRef.current = null;
    coachConversationRef.current = [];
    firstPromptRef.current = "";
    pendingPromptConsumedRef.current = false;
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

  const isIdle = messages.length === 0 && !isSending;
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
  if ((stage === "done" || isRunning) && result) {
    return (
      <DashboardLayout userName="">
        <div
          className="flex flex-col"
          style={{ minHeight: "calc(100vh - var(--top-menu-bar-height, 76px))" }}
        >
          <div className="flex-1 overflow-auto">
            {isRunning && (
              <div className="sticky top-0 z-30 mx-4 mt-4 max-w-4xl">
                <BacktestRunningStatus message={statusMessage} />
              </div>
            )}
            <BacktestDashboard
              result={result}
              onRestart={handleReset}
              onRun={handleRunBacktest}
              currentOptions={currentOptions}
              isRunning={isRunning}
              backtestDsl={backtestReq}
              onWalkForward={handleWalkForward}
              promptText={firstPromptRef.current || undefined}
              strategySummary={buildStrategySummary(latestParsed, backtestReq)}
              parsedStrategy={latestParsed as unknown as Record<string, unknown>}
            />
          </div>
        </div>
      </DashboardLayout>
    );
  }

  // 전략 작성 맥락(시작 화면 또는 전략 요약 존재)에서만 '전략 생성', 그 외(종목 분석·안내)는 '전송'.
  const isStrategyInput = isIdle || messages.some((m) => m.parsed);
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
      `}</style>
      <div
        className={`relative flex gap-4 overflow-hidden px-4 pt-20 pb-12 ${strategyPreviewBackgroundClass}`}
        data-testid="strategy-lab-background"
        style={{ minHeight: "calc(100vh - var(--top-menu-bar-height, 76px))" }}
      >
        {shouldShowIntro && <StrategyWaveBackground />}

        {/* ── 채팅 영역 ── */}
        <div
          key={isChatPage ? "strategy-chat-page" : "strategy-intro-page"}
          className={`relative z-10 flex w-full flex-col items-center transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] ${shouldShowIntro ? "justify-center" : "justify-start"}`}
          style={softEnterStyle}
        >
        <div className="w-full max-w-4xl flex flex-col items-center gap-6">

          {/* 헤더 */}
          {shouldShowIntro && (
          <div className="w-full max-w-3xl">
            <div className="flex flex-col items-center gap-3 text-center">
              <div className="space-y-4">
                <p
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
                className="w-full rounded-2xl border border-white/[0.08] bg-[#101010] px-5 py-5 space-y-4 max-h-[60vh] overflow-y-auto scrollbar-hide"
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
                        {msg.isLoading && !msg.parseSkeleton && (
                          <AnalysisStatusBubble title="전략 분석" />
                        )}
                        {msg.stockLoading && <AnalysisStatusBubble title="종목 분석" />}
                        {msg.stockAnalysis && (
                          <div className="space-y-3" style={SOFT_MESSAGE_ENTER_STYLE}>
                            <div className={`max-w-[88%] rounded-tl-sm p-3.5 space-y-2 ${COACH_CHAT_BUBBLE_CLASS}`}>
                              <span className="text-[11px] font-black uppercase tracking-widest text-white">
                                종목 분석
                              </span>
                              <p className="text-sm font-bold text-white leading-relaxed whitespace-pre-line">
                                {parseCoachSegments(msg.stockAnalysis.explanation).map((seg, segIdx) =>
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
                            </div>
                            <StockAnalysisPanel result={msg.stockAnalysis} />
                            {isLastAssistant(i) && (
                              <div className="flex flex-wrap gap-2 pt-1">
                                <button
                                  onClick={handleReset}
                                  className="px-4 py-2 rounded-xl bg-[#171717] border border-white/10 hover:border-white/30 hover:bg-[#202020] text-xs font-bold text-gray-300 transition-all duration-200"
                                >
                                  돌아가기
                                </button>
                                <button
                                  onClick={handleAnalyzeAnotherStock}
                                  className="px-4 py-2 rounded-xl bg-[#171717] border border-white/10 hover:border-yellow-400/50 hover:bg-[#202020] text-xs font-bold text-gray-200 transition-all duration-200"
                                >
                                  다른 종목 분석
                                </button>
                              </div>
                            )}
                          </div>
                        )}
                        {msg.infoText && (
                          <div
                            className={`max-w-[88%] rounded-tl-sm p-3.5 space-y-2 ${COACH_CHAT_BUBBLE_CLASS}`}
                            style={SOFT_MESSAGE_ENTER_STYLE}
                          >
                            <p className="text-sm font-bold text-white leading-relaxed whitespace-pre-line">
                              {msg.infoText}
                            </p>
                          </div>
                        )}
                        {msg.parseSkeleton && !msg.parsed && (
                          <ParseSkeletonBubble skeleton={msg.parseSkeleton} />
                        )}
                        {msg.parsed && (
                          <>
                            <ParsedSummaryBubble parsed={msg.parsed} backtestRequest={backtestReq} />
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
                                  </div>
                                )}
                              </div>
                            )}
                            {isLastAssistant(i) && stage === "ready" && !msg.coachLoading && !msg.clarification && (
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
                                전략 코치
                              </span>
                              {msg.coachLoading && (
                                <ShimmerStatusText className="text-sm font-bold">분석 중...</ShimmerStatusText>
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
                        {isLastAssistant(i) && msg.coachText && stage === "ready" && !msg.coachLoading && (
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

            {/* 입력 영역 — 시작 화면, 전략 요약 출력 후, 또는 종목 분석·안내 대화 중 표시 */}
            {(isIdle || messages.some((m) => m.parsed || m.stockAnalysis || m.infoText)) && (
            <div
              key={shouldShowIntro ? "intro-chat-input" : "active-chat-input"}
              className="relative w-full rounded-2xl border border-[var(--glass-border)] bg-[#101010]"
              style={softEnterLateStyle}
            >
              <textarea
                ref={textareaRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={stage === "running"}
                rows={2}
                className="w-full bg-transparent text-white placeholder-gray-600 text-sm font-bold resize-none outline-none focus:outline-none focus:ring-0 px-5 pt-4 pb-12 leading-relaxed"
              />
              <div className="absolute bottom-3 right-3 flex items-center gap-2">
                <button
                  onClick={() => handleSend()}
                  disabled={!inputValue.trim() || isSending || stage === "running"}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed text-white text-xs font-black transition-all duration-300 hover:shadow-[0_0_15px_rgba(59,130,246,0.4)]"
                >
                  <Sparkle size={12} weight="fill" />
                  {isStrategyInput ? "전략 생성" : "전송"}
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
