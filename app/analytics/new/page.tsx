"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import RunAllTestsModal from "@/components/strategy/RunAllTestsModal";
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
import {
  StrategyAdvisorPanel,
  type AdvisorRequest,
} from "@/components/strategy/StrategyAdvisorPanel";

const BacktestDashboard = dynamic(
  () => import("@/components/strategy/backtest/BacktestDashboard"),
  { ssr: false }
);

type Stage = "idle" | "ready" | "running" | "done";

interface ChatMessage {
  role: "user" | "assistant";
  content?: string;
  parsed?: ParsedSummary;
  clarification?: string;
  clarificationSuggestions?: string[];
  coachLoading?: boolean;  // coach response is being generated
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
  const [inputValue, setInputValue] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [stage, setStage] = useState<Stage>("idle");
  const [latestParsed, setLatestParsed] = useState<ParsedSummary | null>(null);
  const [backtestReq, setBacktestReq] = useState<any>(null);
  const [currentOptions, setCurrentOptions] = useState<any>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [modelStatus, setModelStatus] = useState<{ status: string; error: string | null } | null>(null);
  const [isRunAllTestsOpen, setIsRunAllTestsOpen] = useState(false);
  const [advisorRequest, setAdvisorRequest] = useState<AdvisorRequest | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // first user prompt — kept for advisor context
  const firstPromptRef = useRef<string>("");

  useEffect(() => {
    fetch("/api/model/status")
      .then((r) => r.json())
      .then(setModelStatus)
      .catch(() => setModelStatus({ status: "failed", error: "서버에 연결할 수 없습니다" }));
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

  // auto-trigger advisor whenever parsed strategy changes
  useEffect(() => {
    if (!latestParsed) return;
    setAdvisorRequest({
      user_prompt: firstPromptRef.current,
      parsed_strategy: latestParsed as unknown as Record<string, unknown>,
      backtest_result: result
        ? {
            cagr: (result as any).cagr ?? null,
            mdd: (result as any).mdd ?? null,
            sharpe: (result as any).sharpe ?? null,
            profit_factor: (result as any).profit_factor ?? null,
            trade_count: (result as any).trade_count ?? null,
            win_rate: (result as any).win_rate ?? null,
          }
        : null,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestParsed, result]);

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
    if (!firstPromptRef.current) firstPromptRef.current = userText;
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

      setLatestParsed(nextParsed);
      setBacktestReq(nextBacktestReq);
      setCurrentOptions({
        period: nextBacktestReq?.period ?? "5y",
        initialCapital: nextBacktestReq?.risk?.init_cash ?? 10000000,
        commissionPct: 0.015,
        slippagePct: 0.05,
      });
      setStage("ready");

      // Show parsed strategy card only; coach response is the sole source of clarification text
      setMessages(prev => prev.map((m, i) =>
        i === prev.length - 1 ? {
          role: "assistant",
          parsed: nextParsed,
          clarification: undefined,
          clarificationSuggestions: undefined,
          coachLoading: true,
        } : m
      ));

      generateCoachResponse({
        userText,
        parsed: nextParsed,
      });
    } catch (e: any) {
      setMessages(prev => prev.map((m, i) =>
        i === prev.length - 1 ? { role: "assistant", error: e.message ?? "알 수 없는 오류" } : m
      ));
    } finally {
      setIsSending(false);
    }
  };

  const generateCoachResponse = async ({
    userText,
    parsed,
    newsAgentInsight,
  }: {
    userText: string;
    parsed: ParsedSummary;
    newsAgentInsight?: Record<string, unknown> | null;
  }) => {
    const updateLastAssistant = (patch: Partial<ChatMessage>) => {
      setMessages(prev => {
        const lastIdx = prev.map((m, i) => m.role === "assistant" ? i : -1).filter(i => i >= 0).at(-1);
        if (lastIdx === undefined) return prev;
        return prev.map((m, i) => i === lastIdx ? { ...m, ...patch } : m);
      });
    };

    try {
      // Step 1: get advisor insight (fast, rule-based ~14ms)
      const advisorRes = await fetch("/api/advisor/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_prompt: firstPromptRef.current || userText,
          parsed_strategy: parsed as unknown as Record<string, unknown>,
        }),
      });
      const advisorInsight = advisorRes.ok ? await advisorRes.json() : null;

      // Step 2: stream coaching response (local Qwen MLX)
      const coachRes = await fetch("/api/strategy/coach/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_prompt: userText,
          parsed_strategy: parsed,
          advisor_insight: advisorInsight,
          news_agent_insight: newsAgentInsight ?? null,
        }),
      });
      if (!coachRes.ok || !coachRes.body) {
        updateLastAssistant({ coachLoading: false });
        return;
      }

      const reader = coachRes.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let firstDelta = true;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const chunk of parts) {
          const line = chunk.split("\n").find(l => l.startsWith("data: "));
          if (!line) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === "delta" && evt.message) {
              if (firstDelta) {
                firstDelta = false;
                updateLastAssistant({ coachLoading: false, clarification: evt.message });
              } else {
                updateLastAssistant({ clarification: evt.message });
              }
            } else if (evt.type === "done") {
              updateLastAssistant({
                coachLoading: false,
                clarification: evt.message || undefined,
                clarificationSuggestions: evt.suggestions?.length ? evt.suggestions : undefined,
              });
            } else if (evt.type === "error") {
              updateLastAssistant({ coachLoading: false });
            }
          } catch {
            // ignore malformed chunk
          }
        }
      }
    } catch {
      updateLastAssistant({ coachLoading: false });
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

  const isIdle = messages.length === 0 && !isSending;
  const isLastAssistant = (i: number) => i === messages.length - 1 && messages[i].role === "assistant";
  const showAdvisor = !!advisorRequest;

  // ── 메인 채팅 화면
  return (
    <DashboardLayout userName="">
      <div className="h-full flex gap-4 px-4 pt-20 pb-12 overflow-hidden">

        {/* ── 왼쪽: 채팅 영역 ── */}
        <div className={`flex flex-col items-center justify-center transition-all duration-300 ${showAdvisor ? "flex-1 min-w-0" : "w-full items-center justify-center"}`}>
        <div className={`w-full flex flex-col items-center gap-6 ${showAdvisor ? "" : "max-w-4xl"}`}>

          {/* 헤더 */}
          <div className="w-full max-w-3xl">
            <div className="flex flex-col items-center gap-3 text-center md:flex-row md:items-start md:justify-between md:text-left">
              <div className="space-y-2">
                <h1 className="text-2xl font-black text-white">전략 만들기</h1>
                <p className="text-sm font-bold text-gray-400 max-w-md leading-relaxed">
                  투자 아이디어를 말씀해주시면,<br /> AI가 전략으로 설계하고 바로 백테스트해드립니다.
                </p>
              </div>
              <button
                onClick={() => setIsRunAllTestsOpen(true)}
                className="inline-flex items-center gap-2 rounded-xl bg-[var(--main-blue)] px-4 py-2.5 text-xs font-black text-white transition-opacity duration-200 hover:opacity-90"
              >
                <Sparkle size={13} weight="fill" />
                모두 테스트
              </button>
            </div>
            {modelStatus?.status === "failed" && (
              <div className="mt-2 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--main-blue)]/10 border border-[var(--main-blue)]/20 text-[var(--main-blue)] text-xs font-bold">
                <Warning size={12} weight="fill" />
                AI 모델 로드 실패 — 전략 생성을 사용할 수 없습니다
              </div>
            )}
            {modelStatus?.status === "loading" && (
              <div className="mt-2 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-xs font-bold">
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
                            {isLastAssistant(i) && msg.coachLoading && (
                              <div className="flex items-center gap-2 px-1">
                                <ArrowsClockwise size={11} className="text-indigo-400 animate-spin flex-shrink-0" />
                                <span className="text-[11px] font-bold text-gray-600">코치 분석 중...</span>
                              </div>
                            )}
                            {isLastAssistant(i) && !msg.coachLoading && msg.clarification && (
                              <div className="flex items-start gap-2.5 p-3.5 rounded-xl bg-white/[0.02] border border-yellow-400/40">
                                <Question size={13} className="text-yellow-400 flex-shrink-0 mt-0.5" weight="fill" />
                                <p className="text-xs font-bold text-gray-300 leading-relaxed whitespace-pre-line">
                                  {msg.clarification.replace(/\*\*(.*?)\*\*/g, "$1")}
                                </p>
                              </div>
                            )}
                            {isLastAssistant(i) && stage === "ready" && !msg.coachLoading && (
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
        </div>{/* end 채팅 영역 */}

        {/* ── 오른쪽: 전략 코치 패널 ── */}
        {showAdvisor && (
          <div className="w-80 flex-shrink-0 pt-0 pb-0 flex flex-col">
            <StrategyAdvisorPanel
              request={advisorRequest}
              onDismiss={() => setAdvisorRequest(null)}
            />
          </div>
        )}

      </div>
      <RunAllTestsModal
        isOpen={isRunAllTestsOpen}
        onClose={() => setIsRunAllTestsOpen(false)}
        currentPrompt={inputValue}
      />
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
