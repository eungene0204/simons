"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
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
import {
  buildAdvisorEvaluationContextFromWalkForward,
  buildCandidateBacktestRequest,
  buildWalkForwardRequest,
  mergeStrategyModification,
  type AdvisorWalkForwardResult,
  type AdvisorWalkForwardSettings,
} from "./parsedStrategyMerge";
import {
  StrategyAdvisorPanel,
  type AdvisorResult,
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
  parseSkeleton?: ParseSkeleton;
  clarification?: string;
  clarificationSuggestions?: string[];
  coachLoading?: boolean;  // coach response is being generated
  isLoading?: boolean;
  error?: string;
}

interface ParseSkeleton {
  description: string;
  universe: string[];
  max_positions: number | null;
  recognized_terms: string[];
  confidence: "partial" | "low";
}

interface RuntimeStageMetrics {
  count: number;
  cache_hits?: number;
  cache_misses?: number;
  avg_total_ms?: number;
  p50_total_ms?: number;
  p95_total_ms?: number;
  last_total_ms?: number;
}

interface RuntimeMetricsSnapshot {
  stages?: Record<string, RuntimeStageMetrics>;
  recent?: Array<{
    stage: string;
    timestamp: number;
    runtime: Record<string, unknown>;
  }>;
}

interface WalkForwardEvidence {
  settings: AdvisorWalkForwardSettings;
  result: AdvisorWalkForwardResult;
  ranges: Record<string, unknown>;
  requestKey: string;
  completedAt: number;
}

function toAdvisorBacktestSummary(value: any) {
  if (!value) return null;
  return {
    cagr: value.cagr ?? null,
    mdd: value.mdd ?? value.maxDrawdown ?? null,
    sharpe: value.sharpe ?? null,
    sortino: value.sortino ?? null,
    calmar: value.calmar ?? null,
    profit_factor: value.profit_factor ?? value.profitFactor ?? null,
    trade_count: value.trade_count ?? value.trades ?? null,
    win_rate: value.win_rate ?? value.winRate ?? null,
    avg_trade_return: value.avg_trade_return ?? value.avgProfit ?? null,
    max_losing_streak: value.max_losing_streak ?? value.maxConsecutiveLosses ?? null,
  };
}

async function readBacktestStreamResult(response: Response) {
  if (!response.ok || !response.body) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail ?? "후보 백테스트 실패");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: any = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6).trim();
      if (payload === "[DONE]") continue;
      const event = JSON.parse(payload);
      if (event.type === "result") result = event.data;
      if (event.type === "error") throw new Error(event.message ?? "후보 백테스트 실패");
    }
  }

  if (!result) throw new Error("후보 백테스트 결과가 없습니다.");
  return result;
}

function backtestRequestKey(value: unknown): string {
  return JSON.stringify(value ?? null);
}

function FilterBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-md bg-white/[0.05] border border-white/[0.08] text-white text-xs font-bold">
      {label}
    </span>
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
    <div className="bg-white/[0.025] border border-white/[0.07] rounded-2xl rounded-tl-sm p-4 space-y-3">
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

const RUNTIME_STAGE_LABELS: Record<string, string> = {
  parse: "Parse",
  summary: "Summary",
  coach: "Coach",
  coach_stream: "Coach Stream",
};

function RuntimeMetricValue({ label, value }: { label: string; value?: number }) {
  return (
    <div>
      <p className="text-[9px] font-black uppercase tracking-widest text-gray-600">{label}</p>
      <p className="text-xs font-black text-white">{typeof value === "number" ? `${value.toFixed(0)}ms` : "--"}</p>
    </div>
  );
}

function RuntimeMetricsPanel({
  snapshot,
  onReset,
  isResetting,
}: {
  snapshot: RuntimeMetricsSnapshot | null;
  onReset: () => void;
  isResetting: boolean;
}) {
  const stages = Object.entries(snapshot?.stages ?? {});

  return (
    <div className="w-full max-w-3xl rounded-2xl border border-white/[0.08] bg-white/[0.025] p-3.5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[10px] font-black uppercase tracking-[0.2em] text-sky-300">AI Runtime</p>
          <p className="text-[11px] font-bold text-gray-500">같은 모델 기준 단계별 latency 집계</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-white/[0.08] px-2 py-0.5 text-[10px] font-black text-gray-500">
            최근 {snapshot?.recent?.length ?? 0}건
          </span>
          <button
            type="button"
            onClick={onReset}
            disabled={isResetting}
            className="rounded-full border border-white/[0.08] px-2 py-0.5 text-[10px] font-black text-gray-500 transition-colors hover:border-sky-400/40 hover:text-sky-300 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isResetting ? "초기화 중" : "초기화"}
          </button>
        </div>
      </div>
      {stages.length === 0 ? (
        <p className="mt-3 text-[11px] font-bold text-gray-600">아직 수집된 런타임 샘플이 없습니다.</p>
      ) : (
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {stages.map(([stage, metrics]) => (
            <div key={stage} className="rounded-xl border border-white/[0.07] bg-black/20 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-black text-white">{RUNTIME_STAGE_LABELS[stage] ?? stage}</p>
                <p className="text-[10px] font-black text-gray-500">
                  {metrics.count} calls · cache {metrics.cache_hits ?? 0}/{metrics.count}
                </p>
              </div>
              <div className="grid grid-cols-4 gap-2">
                <RuntimeMetricValue label="avg" value={metrics.avg_total_ms} />
                <RuntimeMetricValue label="p50" value={metrics.p50_total_ms} />
                <RuntimeMetricValue label="p95" value={metrics.p95_total_ms} />
                <RuntimeMetricValue label="last" value={metrics.last_total_ms} />
              </div>
            </div>
          ))}
        </div>
      )}
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
  const [runtimeMetrics, setRuntimeMetrics] = useState<RuntimeMetricsSnapshot | null>(null);
  const [isResettingRuntimeMetrics, setIsResettingRuntimeMetrics] = useState(false);
  const [advisorRequest, setAdvisorRequest] = useState<AdvisorRequest | null>(null);
  const [walkForwardEvidence, setWalkForwardEvidence] = useState<WalkForwardEvidence | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // first user prompt — kept for advisor context
  const firstPromptRef = useRef<string>("");
  const candidateEvaluationKeyRef = useRef<string | null>(null);

  useEffect(() => {
    fetch("/api/model/status")
      .then((r) => r.json())
      .then(setModelStatus)
      .catch(() => setModelStatus({ status: "failed", error: "서버에 연결할 수 없습니다" }));
  }, []);

  useEffect(() => {
    let cancelled = false;

    const refreshRuntimeMetrics = () => {
      fetch("/api/ai/runtime/metrics", { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (!cancelled && data) setRuntimeMetrics(data);
        })
        .catch(() => {
          if (!cancelled) setRuntimeMetrics(null);
        });
    };

    refreshRuntimeMetrics();
    const timer = window.setInterval(refreshRuntimeMetrics, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const resetRuntimeMetrics = async () => {
    if (isResettingRuntimeMetrics) return;
    setIsResettingRuntimeMetrics(true);
    try {
      const res = await fetch("/api/ai/runtime/metrics/reset", {
        method: "POST",
        cache: "no-store",
      });
      if (res.ok) {
        setRuntimeMetrics({ stages: {}, recent: [] });
      }
    } finally {
      setIsResettingRuntimeMetrics(false);
    }
  };

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
      backtest_result: toAdvisorBacktestSummary(result),
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestParsed, result]);

  // After the baseline backtest, verify the advisor candidate in the background.
  useEffect(() => {
    if (stage !== "done" || !latestParsed || !backtestReq || !result) return;

    const beforeBacktest = toAdvisorBacktestSummary(result);
    if (!beforeBacktest) return;

    const key = JSON.stringify({
      parsed: latestParsed,
      result: (result as any).cacheKey ?? result.executionId ?? result.finalEquity,
      walkForwardCompletedAt: walkForwardEvidence?.completedAt ?? null,
    });
    if (candidateEvaluationKeyRef.current === key) return;
    candidateEvaluationKeyRef.current = key;

    let cancelled = false;
    void (async () => {
      try {
        const reviewRes = await fetch("/api/advisor/review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_prompt: firstPromptRef.current,
            parsed_strategy: latestParsed as unknown as Record<string, unknown>,
            backtest_result: beforeBacktest,
          }),
        });
        if (!reviewRes.ok || cancelled) return;

        const review: AdvisorResult = await reviewRes.json();
        if (!review.candidate_strategy || cancelled) return;

        const candidateReq = buildCandidateBacktestRequest(backtestReq, review.candidate_strategy as any);
        const candidateRes = await fetch("/api/strategy/backtest-stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(candidateReq),
        });
        const candidateRaw = await readBacktestStreamResult(candidateRes);
        const candidateBacktest = toAdvisorBacktestSummary(candidateRaw);
        if (!candidateBacktest || cancelled) return;

        let evaluationContext = { oos_available: false };
        if (
          walkForwardEvidence &&
          walkForwardEvidence.requestKey === backtestRequestKey(backtestReq)
        ) {
          const candidateWalkForwardRes = await fetch("/api/backtest/walk-forward", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(buildWalkForwardRequest(
              candidateReq,
              walkForwardEvidence.settings,
              walkForwardEvidence.ranges,
            )),
          });
          const candidateWalkForward = candidateWalkForwardRes.ok
            ? await candidateWalkForwardRes.json()
            : null;

          evaluationContext = buildAdvisorEvaluationContextFromWalkForward(
            walkForwardEvidence.result,
            candidateWalkForward,
          );
        }

        await fetch("/api/advisor/review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_prompt: firstPromptRef.current,
            parsed_strategy: latestParsed as unknown as Record<string, unknown>,
            backtest_result: beforeBacktest,
            candidate_backtest_result: candidateBacktest,
            evaluation_context: evaluationContext,
          }),
        });
      } catch (error) {
        console.warn("advisor candidate retest skipped", error);
      }
    })();

    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, latestParsed, backtestReq, result, walkForwardEvidence]);

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

  const handleSend = async (overrideText?: string) => {
    const userText = overrideText ?? inputValue.trim();
    if (!userText || isSending || stage === "running") return;
    if (!overrideText) setInputValue("");
    if (!firstPromptRef.current) firstPromptRef.current = userText;
    setIsSending(true);

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
          backend: "mlx",
          ...(latestParsed ? { previous_parsed: latestParsed } : {}),
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

      const finalizeParse = (backtestRequest: any, symbolCount?: number | null) => {
        if (!parsedPayload) return;
        const nextBacktestRequest = backtestRequest
          ? {
              ...backtestRequest,
              symbol_count: symbolCount ?? backtestRequest.symbol_count,
            }
          : backtestRequest;
        const mergedResponse = mergeStrategyModification({
          previousParsed: latestParsed,
          nextParsed: parsedPayload.parsed,
          previousBacktestRequest: backtestReq,
          nextBacktestRequest,
          userPrompt: userText,
          clarificationQuestion: parsedPayload.clarification_question,
        });

        const nextParsed = mergedResponse.parsed;
        const nextBacktestReq = mergedResponse.backtestRequest;

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

        updateLastAssistant({
          isLoading: false,
          parseSkeleton: undefined,
          parsed: nextParsed,
          clarification: undefined,
          clarificationSuggestions: undefined,
          coachLoading: true,
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

      if (finalizedParsed) {
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
    setWalkForwardEvidence(null);

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
    setWalkForwardEvidence({
      settings,
      result: data,
      ranges,
      requestKey: backtestRequestKey(backtestReq),
      completedAt: Date.now(),
    });
    return data;
  };

  const handleReset = () => {
    setStage("idle");
    setMessages([]);
    setLatestParsed(null);
    setBacktestReq(null);
    setResult(null);
    setWalkForwardEvidence(null);
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
              onWalkForward={handleWalkForward}
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

          <RuntimeMetricsPanel
            snapshot={runtimeMetrics}
            onReset={resetRuntimeMetrics}
            isResetting={isResettingRuntimeMetrics}
          />

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
                        {msg.parseSkeleton && !msg.parsed && (
                          <ParseSkeletonBubble skeleton={msg.parseSkeleton} />
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
