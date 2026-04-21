"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { StrategyExampleTabs } from "@/components/strategy/StrategyExampleTabs";
import { BacktestResult } from "@/types/strategy";
import {
  Sparkle,
  ArrowRight,
  ArrowsClockwise,
  CheckCircle,
  Warning,
  ChartLineUp,
  Question,
} from "phosphor-react";
import {
  buildStrategySummary,
  getDisplayExitLabels,
  getDisplayUniverseLabels,
  INDICATOR_LABELS,
  METRIC_LABELS,
  PERIOD_LABELS,
  REBAL_LABELS,
  type ParsedSummary,
} from "./strategySummary";
import { mergeStrategyModification } from "./parsedStrategyMerge";

const BacktestDashboard = dynamic(
  () => import("@/components/strategy/backtest/BacktestDashboard"),
  { ssr: false }
);

type Stage = "idle" | "ready" | "running" | "done";
type LabMode = "builder" | "research";

interface ResearchTemplateResponse {
  templates: string[];
  universes: string[][];
}

interface ResearchAccessState {
  status: "loading" | "ready" | "unauthorized" | "locked" | "offline";
  message: string;
  userId: number | null;
  templates: string[];
  universes: string[][];
}

interface ChatMessage {
  role: "user" | "assistant";
  content?: string;       // user text
  parsed?: ParsedSummary; // assistant parsed result
  clarification?: string; // follow-up question when factors are missing
  clarificationSuggestions?: string[]; // quick reply options
  isLoading?: boolean;
  error?: string;
}

function FilterBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-md bg-white/[0.05] border border-white/[0.08] text-white text-xs font-bold">
      {label}
    </span>
  );
}

function getResearchBaseUrl() {
  if (typeof window === "undefined") {
    return "http://localhost:8000";
  }
  return `${window.location.protocol}//${window.location.hostname}:8000`;
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

  return (
    <div className="bg-white/[0.03] border border-white/[0.08] rounded-2xl rounded-tl-sm p-4 space-y-3">
      <div className="flex items-center gap-1.5">
        <CheckCircle size={13} className="text-gray-400" weight="fill" />
        <span className="text-xs font-black uppercase tracking-widest text-white">전략 요약</span>
      </div>
      <div className="space-y-2">
        {parsed.universe.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest w-14 flex-shrink-0">유니버스</span>
            <div className="flex flex-wrap gap-1">
              {universeLabels.map((label, i) => (
                <FilterBadge key={i} label={label} />
              ))}
            </div>
          </div>
        )}
        {parsed.fundamental_filters.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest w-14 flex-shrink-0">재무 필터</span>
            <div className="flex flex-wrap gap-1">
              {parsed.fundamental_filters.map((f, i) => (
                <FilterBadge key={i} label={`${METRIC_LABELS[f.metric] ?? f.metric} ${f.operator} ${f.value}`} />
              ))}
            </div>
          </div>
        )}
        {parsed.entry_signals.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest w-14 flex-shrink-0">진입 신호</span>
            <div className="flex flex-wrap gap-1">
              {parsed.entry_signals.map((s, i) => (
                <FilterBadge key={i} label={INDICATOR_LABELS[s.indicator] ?? s.indicator} />
              ))}
            </div>
          </div>
        )}
        {exitLabels.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest w-14 flex-shrink-0">청산 신호</span>
            <div className="flex flex-wrap gap-1">
              {exitLabels.map((label, i) => (
                <FilterBadge key={i} label={label} />
              ))}
            </div>
          </div>
        )}
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest w-14 flex-shrink-0">포트폴리오</span>
          <div className="flex flex-wrap gap-1">
            <FilterBadge label={`최대 ${parsed.max_positions}종목`} />
            {parsed.hold_period_days && <FilterBadge label={`${parsed.hold_period_days}일 보유`} />}
            {parsed.rebalancing_period !== "none" && <FilterBadge label={`${REBAL_LABELS[parsed.rebalancing_period]} 리밸런싱`} />}
            <FilterBadge label={`백테스트 ${PERIOD_LABELS[parsed.backtest_period]}`} />
            <FilterBadge label={`초기자금 ${(parsed.initial_capital ?? 10000000).toLocaleString("ko-KR")}원`} />
          </div>
        </div>
        {(parsed.stop_loss_pct || parsed.take_profit_pct) && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest w-14 flex-shrink-0">리스크</span>
            <div className="flex flex-wrap gap-1">
              {parsed.stop_loss_pct && <FilterBadge label={`손절 ${parsed.stop_loss_pct}%`} />}
              {parsed.take_profit_pct && <FilterBadge label={`익절 ${parsed.take_profit_pct}%`} />}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StrategyLabContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [inputValue, setInputValue] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [stage, setStage] = useState<Stage>("idle");
  const [labMode, setLabMode] = useState<LabMode>("builder");
  const [latestParsed, setLatestParsed] = useState<ParsedSummary | null>(null);
  const [backtestReq, setBacktestReq] = useState<any>(null);
  const [currentOptions, setCurrentOptions] = useState<any>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [modelStatus, setModelStatus] = useState<{ status: string; error: string | null } | null>(null);
  const [researchAccess, setResearchAccess] = useState<ResearchAccessState>({
    status: "loading",
    message: "연구 에이전트 권한을 확인하는 중입니다.",
    userId: null,
    templates: [],
    universes: [],
  });
  const [researchGoal, setResearchGoal] = useState("");
  const [researchTemplates, setResearchTemplates] = useState<string[]>(["momentum", "mean_reversion"]);
  const [researchUniverse, setResearchUniverse] = useState<string[]>(["KOSPI200"]);
  const [researchMaxCandidates, setResearchMaxCandidates] = useState(120);
  const [researchTrials, setResearchTrials] = useState(50);
  const [researchSplits, setResearchSplits] = useState(5);
  const [isStartingResearch, setIsStartingResearch] = useState(false);
  const [researchError, setResearchError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mode = searchParams.get("mode");
    setLabMode(mode === "research" ? "research" : "builder");
  }, [searchParams]);

  useEffect(() => {
    fetch("/api/model/status")
      .then((r) => r.json())
      .then(setModelStatus)
      .catch(() => setModelStatus({ status: "failed", error: "서버에 연결할 수 없습니다" }));
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadResearchAccess() {
      try {
        const userResponse = await fetch("/api/user", { cache: "no-store" });
        const userData = await userResponse.json();
        const userId = userData?.user?.id ?? null;

        if (!userId) {
          if (!cancelled) {
            setResearchAccess({
              status: "unauthorized",
              message: "로그인 후 Premium 플랜에서 연구 에이전트를 사용할 수 있습니다.",
              userId: null,
              templates: [],
              universes: [],
            });
          }
          return;
        }

        const templateResponse = await fetch(`${getResearchBaseUrl()}/research/templates`, {
          headers: { "X-User-Id": String(userId) },
        });

        if (templateResponse.status === 402) {
          if (!cancelled) {
            setResearchAccess({
              status: "locked",
              message: "연구 에이전트는 Premium 플랜에서만 사용할 수 있습니다.",
              userId,
              templates: [],
              universes: [],
            });
          }
          return;
        }

        if (!templateResponse.ok) {
          throw new Error("research templates unavailable");
        }

        const data = (await templateResponse.json()) as ResearchTemplateResponse;
        if (!cancelled) {
          setResearchAccess({
            status: "ready",
            message: "연구 에이전트를 실행할 수 있습니다.",
            userId,
            templates: data.templates ?? [],
            universes: data.universes ?? [],
          });
          setResearchTemplates((prev) =>
            prev.filter((item) => (data.templates ?? []).includes(item)).length > 0
              ? prev.filter((item) => (data.templates ?? []).includes(item))
              : (data.templates ?? []).slice(0, 2)
          );
          if ((data.universes ?? []).length > 0) {
            setResearchUniverse((prev) => {
              const matched = (data.universes ?? []).find(
                (item) => item.join("|") === prev.join("|")
              );
              return matched ?? data.universes[0];
            });
          }
        }
      } catch {
        if (!cancelled) {
          setResearchAccess({
            status: "offline",
            message: "연구 백엔드에 연결할 수 없습니다. 백엔드 서버와 CORS 설정을 확인하세요.",
            userId: null,
            templates: [],
            universes: [],
          });
        }
      }
    }

    loadResearchAccess();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [inputValue]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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

  const handleSend = async (overrideText?: string) => {
    const userText = overrideText ?? inputValue.trim();
    if (!userText || isSending || stage === "running") return;
    if (!overrideText) setInputValue("");
    setIsSending(true);
    const previousAssistantMessage = [...messages]
      .reverse()
      .find((message) => message.role === "assistant" && message.parsed);

    setMessages(prev => [
      ...prev,
      { role: "user", content: userText },
      { role: "assistant", isLoading: true },
    ]);

    try {
      const res = await fetch("/api/strategy/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: userText,
          backend: "mlx",
          ...(latestParsed ? { previous_parsed: latestParsed } : {}),
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? "파싱 실패");
      }
      const data = await res.json();
      const mergedResponse = mergeStrategyModification({
        previousParsed: latestParsed,
        nextParsed: data.parsed,
        previousBacktestRequest: backtestReq,
        nextBacktestRequest: data.backtest_request,
        userPrompt: userText,
        clarificationQuestion: data.clarification_question,
      });

      const nextParsed = mergedResponse.parsed;
      const nextBacktestReq = mergedResponse.backtestRequest;
      const clarification = mergedResponse.shouldReusePreviousClarification
        ? previousAssistantMessage?.clarification
        : data.clarification_question;
      const clarificationSuggestions = mergedResponse.shouldReusePreviousClarification
        ? previousAssistantMessage?.clarificationSuggestions
        : data.clarification_suggestions;

      setLatestParsed(nextParsed);
      setBacktestReq(nextBacktestReq);
      setCurrentOptions({
        period: nextBacktestReq?.period ?? "5y",
        initialCapital: nextBacktestReq?.risk?.init_cash ?? 10000000,
        commissionPct: 0.015,
        slippagePct: 0.05,
      });
      setStage("ready");
      setMessages(prev => prev.map((m, i) =>
        i === prev.length - 1 ? {
          role: "assistant",
          parsed: nextParsed,
          clarification: clarification ?? undefined,
          clarificationSuggestions: clarificationSuggestions ?? undefined,
        } : m
      ));
    } catch (e: any) {
      setMessages(prev => prev.map((m, i) =>
        i === prev.length - 1 ? { role: "assistant", error: e.message ?? "알 수 없는 오류" } : m
      ));
    } finally {
      setIsSending(false);
    }
  };

  const handleRunBacktest = async (options?: any) => {
    if (!backtestReq) return;

    const effectiveReq = options ? {
      ...backtestReq,
      period: options.period ?? backtestReq.period,
      risk: { ...backtestReq.risk, init_cash: options.initialCapital ?? backtestReq.risk?.init_cash },
      options: {
        fee_rate: (options.commissionPct ?? 0.015) / 100,
        slippage_rate: (options.slippagePct ?? 0.05) / 100,
      },
    } : backtestReq;

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

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") break;
          const event = JSON.parse(payload);
          if (event.type === "status") {
            setStatusMessage(event.message);
          } else if (event.type === "result") {
            const raw = event.data;
            const equity: number[] = raw.equity ?? [];
            setResult({
              executionId: `nl_${Date.now()}`,
              strategyId: "nl_strategy",
              symbols: raw.symbols,
              totalReturn: raw.totalReturn ?? 0,
              cagr: raw.cagr ?? 0,
              buyAndHoldReturn: raw.buyAndHoldReturn ?? 0,
              maxDrawdown: raw.maxDrawdown ?? 0,
              winRate: raw.winRate ?? 0,
              profitFactor: raw.profitFactor ?? 0,
              sharpe: raw.sharpe ?? 0,
              sortino: raw.sortino ?? 0,
              kelly: raw.kelly ?? 0,
              volatility: raw.volatility ?? 0,
              trades: raw.trades ?? 0,
              avgProfit: raw.avgProfit ?? 0,
              avgLoss: raw.avgLoss ?? 0,
              maxConsecutiveWins: raw.maxConsecutiveWins ?? 0,
              maxConsecutiveLosses: raw.maxConsecutiveLosses ?? 0,
              finalEquity: equity[equity.length - 1] ?? 0,
              initialCapital: equity[0] ?? 0,
              equity,
              benchmarkEquity: raw.benchmark_equity,
              benchmarkLabel: raw.benchmark_label,
              dates: raw.dates ?? [],
              tradesList: (raw.signals ?? []).map((s: any) => ({
                date: s.date,
                symbol: s.symbol,
                type: s.type as "buy" | "sell",
                price: s.price,
                quantity: s.quantity ?? 0,
                amount: s.amount ?? 0,
                reason: s.condition,
              })),
              monthlyReturns: {},
              yearlyReturns: {},
              signals: (raw.signals ?? []).map((s: any) => ({
                date: s.date,
                symbol: s.symbol,
                type: s.type === "buy" ? "entry" : "exit",
                condition: s.condition,
                price: Number(s.price),
                quantity: Number(s.quantity),
                amount: Number(s.amount),
              })),
              perAssetStats: raw.perAssetStats,
              universeId: raw.universe_id,
              warnings: raw.warnings,
              executionTime: raw.executionTime,
              vbtResult: raw.vbtResult ?? undefined,
            });
            setStage("done");
          } else if (event.type === "error") {
            throw new Error(event.message);
          }
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

  const handleReset = () => {
    setStage("idle");
    setMessages([]);
    setLatestParsed(null);
    setBacktestReq(null);
    setResult(null);
    setIsSending(false);
    setTimeout(() => textareaRef.current?.focus(), 100);
  };

  const handleStartResearch = async () => {
    if (researchAccess.status !== "ready" || !researchAccess.userId || researchTemplates.length === 0) {
      return;
    }

    setIsStartingResearch(true);
    setResearchError(null);
    try {
      const response = await fetch(`${getResearchBaseUrl()}/research/runs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": String(researchAccess.userId),
        },
        body: JSON.stringify({
          goal: researchGoal.trim() || null,
          templates: researchTemplates,
          universes: [researchUniverse],
          max_candidates: researchMaxCandidates,
          optuna_trials: researchTrials,
          wfa_splits: researchSplits,
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data?.detail ?? "연구 실행에 실패했습니다.");
      }
      router.push(`/analytics/research/${data.runId}`);
    } catch (error: any) {
      setResearchError(error?.message ?? "연구 실행에 실패했습니다.");
    } finally {
      setIsStartingResearch(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── 결과 화면
  const isRunning = stage === "running";
  if ((stage === "done" || isRunning) && result) {
    return (
      <DashboardLayout userName="">
        <div className="h-full flex flex-col">
          <div className="flex-1 overflow-auto">
            <BacktestDashboard
              result={result}
              onRestart={handleReset}
              onRun={handleRunBacktest}
              currentOptions={currentOptions}
              isRunning={isRunning}
              backtestDsl={backtestReq}
              strategySummary={buildStrategySummary(latestParsed, backtestReq)}
            />
          </div>
        </div>
      </DashboardLayout>
    );
  }

  if (labMode === "research") {
    const canStartResearch = researchAccess.status === "ready" && researchTemplates.length > 0 && !isStartingResearch;

    return (
      <DashboardLayout userName="">
        <div className="min-h-full px-4 py-6 md:px-6">
          <div className="mx-auto max-w-6xl space-y-6">
            <div className="flex flex-col gap-4 rounded-3xl border border-emerald-500/20 bg-[linear-gradient(135deg,rgba(16,185,129,0.12),rgba(255,255,255,0.02))] p-6 md:flex-row md:items-end md:justify-between">
              <div className="space-y-3">
                <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1">
                  <Sparkle size={12} className="text-emerald-300" weight="fill" />
                  <span className="text-[11px] font-black uppercase tracking-[0.2em] text-emerald-200">Research Agent</span>
                </div>
                <div className="space-y-1">
                  <h1 className="text-2xl font-black text-white">전략 연구 워크벤치</h1>
                  <p className="max-w-2xl text-sm font-bold leading-relaxed text-gray-300">
                    목표와 탐색 범위를 지정하면 후보 생성, 프리스크린, 견고성 검증, 최종 승격 후보 선별까지 연구 런 단위로 진행합니다.
                  </p>
                </div>
              </div>
              <div className="inline-flex rounded-2xl border border-white/[0.08] bg-black/20 p-1">
                <button
                  onClick={() => {
                    setLabMode("builder");
                    router.replace("/analytics/new");
                  }}
                  className="rounded-xl px-4 py-2 text-xs font-black text-gray-400 transition-colors duration-200 hover:text-white"
                >
                  직접 설계
                </button>
                <button
                  className="rounded-xl bg-white/[0.08] px-4 py-2 text-xs font-black text-white"
                >
                  연구 에이전트
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-3xl border border-white/[0.08] bg-white/[0.03] p-5 space-y-5">
                <div className="space-y-1">
                  <p className="text-[11px] font-black uppercase tracking-[0.2em] text-gray-500">Task</p>
                  <h2 className="text-lg font-black text-white">연구 목표 정의</h2>
                </div>

                <label className="block space-y-2">
                  <span className="text-xs font-black text-gray-300">찾고 싶은 전략</span>
                  <textarea
                    value={researchGoal}
                    onChange={(e) => setResearchGoal(e.target.value)}
                    rows={4}
                    placeholder="예: KOSPI200에서 낙폭을 제한하면서 거래 수가 너무 적지 않은 모멘텀 전략"
                    className="w-full rounded-2xl border border-white/[0.08] bg-black/20 px-4 py-3 text-sm font-bold text-white outline-none placeholder:text-gray-600"
                  />
                </label>

                <div className="space-y-3">
                  <span className="text-xs font-black text-gray-300">탐색 템플릿</span>
                  <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
                    {(researchAccess.templates.length > 0 ? researchAccess.templates : ["momentum", "mean_reversion"]).map((template) => {
                      const checked = researchTemplates.includes(template);
                      return (
                        <button
                          key={template}
                          type="button"
                          disabled={researchAccess.status !== "ready"}
                          onClick={() =>
                            setResearchTemplates((prev) => {
                              if (prev.includes(template)) {
                                return prev.length === 1 ? prev : prev.filter((item) => item !== template);
                              }
                              return [...prev, template];
                            })
                          }
                          className={`rounded-2xl border px-3 py-3 text-left text-xs font-black transition-colors duration-200 ${
                            checked
                              ? "border-emerald-400/40 bg-emerald-400/10 text-white"
                              : "border-white/[0.08] bg-white/[0.02] text-gray-400 hover:text-white"
                          }`}
                        >
                          {template}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-3">
                  <span className="text-xs font-black text-gray-300">유니버스</span>
                  <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                    {(researchAccess.universes.length > 0 ? researchAccess.universes : [["KOSPI200"], ["KOSPI"], ["KOSDAQ"]]).map((universe) => {
                      const selected = universe.join("|") === researchUniverse.join("|");
                      return (
                        <button
                          key={universe.join("|")}
                          type="button"
                          disabled={researchAccess.status !== "ready"}
                          onClick={() => setResearchUniverse(universe)}
                          className={`rounded-2xl border px-4 py-3 text-left transition-colors duration-200 ${
                            selected
                              ? "border-sky-400/40 bg-sky-400/10"
                              : "border-white/[0.08] bg-white/[0.02]"
                          }`}
                        >
                          <p className="text-sm font-black text-white">{universe.join(" + ")}</p>
                          <p className="mt-1 text-[11px] font-bold text-gray-500">탐색 단위를 이 유니버스로 제한합니다.</p>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  <label className="space-y-2">
                    <span className="text-xs font-black text-gray-300">후보 수</span>
                    <input
                      type="number"
                      min={10}
                      max={500}
                      value={researchMaxCandidates}
                      onChange={(e) => setResearchMaxCandidates(Number(e.target.value))}
                      className="w-full rounded-2xl border border-white/[0.08] bg-black/20 px-4 py-3 text-sm font-black text-white outline-none"
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-xs font-black text-gray-300">Optuna Trials</span>
                    <input
                      type="number"
                      min={10}
                      max={200}
                      value={researchTrials}
                      onChange={(e) => setResearchTrials(Number(e.target.value))}
                      className="w-full rounded-2xl border border-white/[0.08] bg-black/20 px-4 py-3 text-sm font-black text-white outline-none"
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-xs font-black text-gray-300">WFA Splits</span>
                    <input
                      type="number"
                      min={3}
                      max={10}
                      value={researchSplits}
                      onChange={(e) => setResearchSplits(Number(e.target.value))}
                      className="w-full rounded-2xl border border-white/[0.08] bg-black/20 px-4 py-3 text-sm font-black text-white outline-none"
                    />
                  </label>
                </div>

                {researchError && (
                  <div className="rounded-2xl border border-[var(--error-red)]/20 bg-[var(--error-red)]/10 px-4 py-3 text-xs font-bold text-[var(--error-red)]">
                    {researchError}
                  </div>
                )}

                <div className="flex flex-col gap-3 border-t border-white/[0.06] pt-4 md:flex-row md:items-center md:justify-between">
                  <p className="text-xs font-bold text-gray-500">
                    실행 후 연구 런 상세 화면으로 이동해 후보, 탈락 사유, 승격 상태를 확인합니다.
                  </p>
                  <button
                    onClick={handleStartResearch}
                    disabled={!canStartResearch}
                    className="inline-flex items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-emerald-500 to-sky-500 px-5 py-3 text-sm font-black text-white transition-opacity duration-200 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {isStartingResearch ? <ArrowsClockwise size={14} className="animate-spin" /> : <ChartLineUp size={14} weight="fill" />}
                    연구 시작
                  </button>
                </div>
              </div>

              <div className="space-y-4">
                <div className="rounded-3xl border border-white/[0.08] bg-white/[0.03] p-5 space-y-4">
                  <div className="space-y-1">
                    <p className="text-[11px] font-black uppercase tracking-[0.2em] text-gray-500">Status</p>
                    <h2 className="text-lg font-black text-white">실행 가능 상태</h2>
                  </div>
                  <div className={`rounded-2xl border px-4 py-4 ${
                    researchAccess.status === "ready"
                      ? "border-emerald-400/20 bg-emerald-400/10"
                      : "border-white/[0.08] bg-black/20"
                  }`}>
                    <p className="text-sm font-black text-white">
                      {researchAccess.status === "ready" ? "연구 에이전트 사용 가능" : "사전 조건 확인 필요"}
                    </p>
                    <p className="mt-1 text-xs font-bold leading-relaxed text-gray-400">{researchAccess.message}</p>
                  </div>
                  <div className="grid grid-cols-1 gap-2">
                    <div className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-3">
                      <p className="text-[11px] font-black uppercase tracking-[0.2em] text-gray-600">Pipeline</p>
                      <p className="mt-1 text-xs font-bold text-gray-300">Generate → Prescreen → Robustness → Optimize → Holdout → Finalize</p>
                    </div>
                    <div className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-3">
                      <p className="text-[11px] font-black uppercase tracking-[0.2em] text-gray-600">Output</p>
                      <p className="mt-1 text-xs font-bold text-gray-300">후보 비교, 탈락 사유 검토, 가상계좌 승격 후보 선별</p>
                    </div>
                  </div>
                </div>

                <div className="rounded-3xl border border-white/[0.08] bg-white/[0.03] p-5 space-y-3">
                  <div className="space-y-1">
                    <p className="text-[11px] font-black uppercase tracking-[0.2em] text-gray-500">Tips</p>
                    <h2 className="text-lg font-black text-white">좋은 입력 예시</h2>
                  </div>
                  <div className="space-y-2">
                    {[
                      "KOSPI200에서 낙폭이 작은 모멘텀 전략",
                      "거래 수가 너무 적지 않은 평균회귀 전략",
                      "홀드아웃에서도 유지되는 가치+거래대금 필터 전략",
                    ].map((example) => (
                      <button
                        key={example}
                        onClick={() => setResearchGoal(example)}
                        className="w-full rounded-2xl border border-white/[0.08] bg-black/20 px-4 py-3 text-left text-xs font-bold text-gray-300 transition-colors duration-200 hover:border-white/[0.14] hover:text-white"
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  const isIdle = messages.length === 0 && !isSending;
  const isLastAssistant = (i: number) => i === messages.length - 1 && messages[i].role === "assistant";

  // ── 메인 채팅 화면
  return (
    <DashboardLayout userName="">
      <div className="h-full flex flex-col items-center justify-center px-4 pt-20 pb-12">
        <div className="w-full max-w-4xl flex flex-col items-center gap-6">

          {/* 헤더 */}
          <div className="text-center space-y-2">
            <h1 className="text-2xl font-black text-white">전략 만들기</h1>
            <p className="text-sm font-bold text-gray-400 max-w-md leading-relaxed">
              투자 아이디어를 말씀해주시면,<br /> AI가 전략으로 설계하고 바로 백테스트해드립니다.
            </p>
            {modelStatus?.status === "failed" && (
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--main-blue)]/10 border border-[var(--main-blue)]/20 text-[var(--main-blue)] text-xs font-bold">
                <Warning size={12} weight="fill" />
                AI 모델 로드 실패 — 전략 생성을 사용할 수 없습니다
              </div>
            )}
            {modelStatus?.status === "loading" && (
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-xs font-bold">
                <ArrowsClockwise size={12} className="animate-spin" />
                AI 모델 로딩 중...
              </div>
            )}
          </div>

          {/* 채팅창 */}
          <div className="w-full flex flex-col gap-2.5">

            {/* 대화 히스토리 */}
            {messages.length > 0 && (
              <div className="w-full rounded-2xl border border-white/[0.08] bg-white/[0.02] px-5 py-5 space-y-4 max-h-[60vh] overflow-y-auto scrollbar-hide">
                {messages.map((msg, i) => (
                  <div key={i}>
                    {msg.role === "user" && (
                      <div className="flex justify-end">
                        <div className="max-w-[80%] bg-sky-500/15 border border-sky-500/20 rounded-2xl rounded-tr-sm px-4 py-2.5">
                          <p className="text-xs font-bold text-white leading-relaxed">{msg.content}</p>
                        </div>
                      </div>
                    )}
                    {msg.role === "assistant" && (
                      <div className="space-y-3">
                        {msg.isLoading && (
                          <div className="flex items-center gap-2 px-1">
                            <ArrowsClockwise size={13} className="text-sky-400 animate-spin flex-shrink-0" />
                            <span className="text-xs font-bold text-gray-500">전략 분석 중...</span>
                          </div>
                        )}
                        {msg.parsed && (
                          <>
                            <ParsedSummaryBubble parsed={msg.parsed} backtestRequest={backtestReq} />
                            {msg.clarification && (
                              <div className="space-y-2">
                                <div className="flex items-start gap-2.5 p-3.5 rounded-xl bg-white/[0.02] border border-yellow-400/40">
                                  <Question size={13} className="text-yellow-400 flex-shrink-0 mt-0.5" weight="fill" />
                                  <p className="text-xs font-bold text-gray-300 leading-relaxed whitespace-pre-line">{msg.clarification.replace(/\*\*(.*?)\*\*/g, "$1")}</p>
                                </div>
                                {msg.clarificationSuggestions && (
                                  <div className="flex flex-wrap gap-1.5 pl-1">
                                    {msg.clarificationSuggestions.map((s, si) => (
                                      <button
                                        key={si}
                                        onClick={() => handleSuggestionClick(s)}
                                        className="px-3 py-1.5 rounded-md bg-white/[0.03] border border-yellow-400/20 hover:border-yellow-400/50 text-xs font-bold text-gray-400 hover:text-white transition-all duration-200"
                                      >
                                        {s}
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}
                            {isLastAssistant(i) && stage === "ready" && (
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
                        {msg.error && (
                          <div className="flex items-start gap-2.5 p-3.5 rounded-xl bg-[var(--error-red)]/10 border border-[var(--error-red)]/20">
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

            {/* 입력 영역 — 전략 요약이 출력된 이후에만 표시 */}
            {(isIdle || messages.some((m) => m.parsed)) && (
            <div className="relative w-full rounded-2xl border border-[var(--glass-border)] bg-white/[0.02]">
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
                  전략 생성
                </button>
              </div>
            </div>
            )}
          </div>

          {/* 예시 프롬프트 */}
          {isIdle && (
            <StrategyExampleTabs onSelectExample={setInputValue} />
          )}
        </div>
      </div>
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
