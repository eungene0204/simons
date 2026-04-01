"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import dynamic from "next/dynamic";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { BacktestResult } from "@/types/strategy";

const BacktestDashboard = dynamic(
  () => import("@/components/strategy/backtest/BacktestDashboard"),
  { ssr: false }
);
import {
  Sparkle,
  ArrowRight,
  ArrowsClockwise,
  CheckCircle,
  Warning,
  ChartLineUp,
  Question,
} from "phosphor-react";

type ExampleCategory = "가치투자" | "기술분석" | "모멘텀" | "복합전략" | "AI 전략";

interface Example {
  category: ExampleCategory;
  title: string;
  prompt: string;
}

const EXAMPLES: Example[] = [
  // 가치투자
  {
    category: "가치투자",
    title: "저PBR·저PER 스크리닝",
    prompt: "PBR 1 이하, PER 7 이하 종목 10개를 1년간 보유",
  },
  {
    category: "가치투자",
    title: "우량 성장주 분기 리밸런싱",
    prompt: "ROE 15% 이상, 부채비율 100% 이하인 우량주 20개 분기 리밸런싱",
  },
  {
    category: "가치투자",
    title: "소형 저PBR 가치주",
    prompt: "시가총액 1000억 이상 5000억 이하, PBR 0.5 이하인 소형 가치주 10개 6개월 보유",
  },
  {
    category: "가치투자",
    title: "고ROE 저부채 장기보유",
    prompt: "ROE 20% 이상, 부채비율 50% 이하, PER 15 이하인 종목 15개를 1년 보유 후 연간 리밸런싱",
  },
  // 기술분석
  {
    category: "기술분석",
    title: "골든크로스 + RSI 매도",
    prompt: "골든크로스 발생 시 매수, RSI 70 이상이면 매도, 최대 15종목",
  },
  {
    category: "기술분석",
    title: "MACD 크로스 + 손익절",
    prompt: "MACD 골든크로스 매수, 데드크로스 매도, 손절 10%, 익절 25%",
  },
  {
    category: "기술분석",
    title: "RSI 과매도 반등 전략",
    prompt: "RSI 30 이하 과매도 구간에서 매수, RSI 65 이상에서 매도, 최대 10종목, 손절 8%",
  },
  {
    category: "기술분석",
    title: "볼린저밴드 역추세",
    prompt: "볼린저밴드 하단 이탈 후 회복 시 매수, 상단 터치 시 매도, 손절 7%, 최대 12종목",
  },
  // 모멘텀
  {
    category: "모멘텀",
    title: "거래량 급증 브레이크아웃",
    prompt: "거래량 급증과 52주 신고가 브레이크아웃이 동시에 발생한 종목 매수, 20일 보유 후 청산, 최대 10종목",
  },
  {
    category: "모멘텀",
    title: "스토캐스틱 모멘텀",
    prompt: "스토캐스틱 %K가 20 이하에서 %D 상향 돌파 시 매수, 80 이상에서 하향 이탈 시 매도, 손절 12%",
  },
  {
    category: "모멘텀",
    title: "거래대금 상위 EMA",
    prompt: "일 거래대금 50억 이상인 종목 중 EMA 단기 장기 골든크로스 발생 시 매수, 익절 20%, 손절 10%",
  },
  {
    category: "모멘텀",
    title: "CCI 과매도 반등",
    prompt: "CCI -100 이하 과매도 후 반등 시 매수, CCI +100 이상에서 매도, 손절 10%, 최대 10종목",
  },
  // 복합전략
  {
    category: "복합전략",
    title: "가치 + 기술 결합",
    prompt: "PER 10 이하 저평가 종목 중 MA 골든크로스 발생 시 매수, 데드크로스 또는 손절 15% 시 청산, 20종목",
  },
  {
    category: "복합전략",
    title: "ROE + MACD 월 리밸런싱",
    prompt: "ROE 10% 이상이고 부채비율 150% 이하인 종목 중 MACD 크로스 매수, 15종목 월간 리밸런싱, 손절 10%",
  },
  {
    category: "복합전략",
    title: "퀄리티 + 모멘텀 혼합",
    prompt: "PBR 2 이하, ROE 12% 이상인 종목 중 거래량 급증과 RSI 50 돌파 동시 발생 시 매수, 30일 보유, 10종목",
  },
  {
    category: "복합전략",
    title: "소형가치 + 볼린저",
    prompt: "시총 2000억 이하, PBR 1 이하 소형 가치주 중 볼린저밴드 하단 반등 시 매수, 상단 도달 시 매도, 손절 8%",
  },
  // AI 전략
  {
    category: "AI 전략",
    title: "AI 단독 매수 예측",
    prompt: "AI 모델이 상승 예측한 종목에 매수, AI 하락 예측 시 매도, 최대 15종목, 손절 10%",
  },
  {
    category: "AI 전략",
    title: "AI + RSI 복합 필터",
    prompt: "AI 모델 상승 신호와 RSI 50 이상 동시 조건 충족 시 매수, RSI 70 초과 또는 AI 하락 예측 시 매도, 10종목",
  },
  {
    category: "AI 전략",
    title: "AI + 가치 스크리닝",
    prompt: "PBR 1.5 이하, ROE 10% 이상인 종목 중 AI 모델이 상승 예측한 종목 매수, AI 하락 예측 시 즉시 청산, 손절 12%",
  },
  {
    category: "AI 전략",
    title: "AI + 골든크로스 확인",
    prompt: "AI 상승 예측과 MA 골든크로스가 동시에 발생한 종목 매수, 데드크로스 또는 AI 하락 신호 시 매도, 최대 10종목",
  },
];

const CATEGORY_STYLE: Record<ExampleCategory, { label: string; color: string; bg: string; border: string }> = {
  가치투자: { label: "가치투자", color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  기술분석: { label: "기술분석", color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20" },
  모멘텀: { label: "모멘텀", color: "text-violet-400", bg: "bg-violet-500/10", border: "border-violet-500/20" },
  복합전략: { label: "복합전략", color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  "AI 전략": { label: "AI 전략", color: "text-pink-400", bg: "bg-pink-500/10", border: "border-pink-500/20" },
};

type Stage = "idle" | "ready" | "running" | "done";

interface ChatMessage {
  role: "user" | "assistant";
  content?: string;       // user text
  parsed?: ParsedSummary; // assistant parsed result
  clarification?: string; // follow-up question when factors are missing
  clarificationSuggestions?: string[]; // quick reply options
  isLoading?: boolean;
  error?: string;
}

interface ParsedSummary {
  description: string;
  universe: string[];
  fundamental_filters: Array<{ metric: string; operator: string; value: number }>;
  entry_signals: Array<{ indicator: string }>;
  exit_signals: Array<{ indicator: string }>;
  max_positions: number;
  hold_period_days: number | null;
  rebalancing_period: string;
  stop_loss_pct: number | null;
  take_profit_pct: number | null;
  backtest_period: string;
  initial_capital: number;
}

const UNIVERSE_LABELS: Record<string, string> = {
  kospi: "KOSPI", kosdaq: "KOSDAQ", kospi200: "KOSPI 200",
  KOR_KOSPI200: "KOSPI 200", KOR_KOSDAQ150: "KOSDAQ 150",
  US_TECH_TOP10: "미국 테크 Top 10", CRYPTO_TOP10: "크립토 Top 10",
};

const METRIC_LABELS: Record<string, string> = {
  per: "PER", pbr: "PBR", roe_or_gpa: "ROE",
  debt_ratio: "부채비율", market_cap: "시총", trading_value: "거래대금",
};
const PERIOD_LABELS: Record<string, string> = {
  "1y": "1년", "3y": "3년", "5y": "5년", "full": "전체",
};
const REBAL_LABELS: Record<string, string> = {
  none: "없음", monthly: "매월", quarterly: "분기", yearly: "매년",
};
const INDICATOR_LABELS: Record<string, string> = {
  ma_crossover: "MA 크로스", rsi: "RSI", ema: "EMA 크로스",
  macd: "MACD", bollinger_bands: "볼린저밴드", breakout: "브레이크아웃",
  volume_spike: "거래량 급증", stochastic: "스토캐스틱", cci: "CCI", adx: "ADX",
  ai_model: "AI 매수 예측", ai_drop_model: "AI 하락 예측",
};

function FilterBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center px-2.5 py-1 rounded-lg bg-white/[0.05] border border-white/10 text-white text-xs font-bold">
      {label}
    </span>
  );
}


function ParsedSummaryBubble({ parsed }: { parsed: ParsedSummary }) {
  return (
    <div className="bg-white/[0.03] border border-white/8 rounded-2xl rounded-tl-sm p-4 space-y-3">
      <div className="flex items-center gap-1.5">
        <CheckCircle size={14} className="text-white/50" weight="fill" />
        <span className="text-xs font-bold text-white">전략 요약</span>
      </div>
      <div className="space-y-2.5">
        {parsed.universe.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-xs text-gray-500 w-16 flex-shrink-0">유니버스</span>
            <div className="flex flex-wrap gap-1">
              {parsed.universe.map((u, i) => (
                <FilterBadge key={i} label={UNIVERSE_LABELS[u] ?? u} />
              ))}
            </div>
          </div>
        )}
        {parsed.fundamental_filters.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-xs text-gray-500 w-16 flex-shrink-0">재무 필터</span>
            <div className="flex flex-wrap gap-1">
              {parsed.fundamental_filters.map((f, i) => (
                <FilterBadge key={i} label={`${METRIC_LABELS[f.metric] ?? f.metric} ${f.operator} ${f.value}`} />
              ))}
            </div>
          </div>
        )}
        {parsed.entry_signals.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-xs text-gray-500 w-16 flex-shrink-0">진입 신호</span>
            <div className="flex flex-wrap gap-1">
              {parsed.entry_signals.map((s, i) => (
                <FilterBadge key={i} label={INDICATOR_LABELS[s.indicator] ?? s.indicator} />
              ))}
            </div>
          </div>
        )}
        {parsed.exit_signals.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-xs text-gray-500 w-16 flex-shrink-0">청산 신호</span>
            <div className="flex flex-wrap gap-1">
              {parsed.exit_signals.map((s, i) => (
                <FilterBadge key={i} label={INDICATOR_LABELS[s.indicator] ?? s.indicator} />
              ))}
            </div>
          </div>
        )}
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className="text-xs text-gray-500 w-16 flex-shrink-0">포트폴리오</span>
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
            <span className="text-xs text-gray-500 w-16 flex-shrink-0">리스크</span>
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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("http://localhost:8000/model/status")
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

  const handleSend = async (overrideText?: string) => {
    const userText = overrideText ?? inputValue.trim();
    if (!userText || isSending || stage === "running") return;
    if (!overrideText) setInputValue("");
    setIsSending(true);

    setMessages(prev => [
      ...prev,
      { role: "user", content: userText },
      { role: "assistant", isLoading: true },
    ]);

    try {
      const res = await fetch("http://localhost:8000/strategy/parse", {
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
      setLatestParsed(data.parsed);
      setBacktestReq(data.backtest_request);
      setCurrentOptions({
        period: data.backtest_request?.period ?? "5y",
        initialCapital: data.backtest_request?.risk?.init_cash ?? 10000000,
        commissionPct: 0.015,
        slippagePct: 0.05,
      });
      setStage("ready");
      setMessages(prev => prev.map((m, i) =>
        i === prev.length - 1 ? {
          role: "assistant",
          parsed: data.parsed,
          clarification: data.clarification_question ?? undefined,
          clarificationSuggestions: data.clarification_suggestions ?? undefined,
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
      const res = await fetch("http://localhost:8000/strategy/backtest-stream", {
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
              warnings: raw.warnings,
              executionTime: raw.executionTime,
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
          <div className="flex items-center justify-between px-6 py-3 border-b border-white/5">
            <div className="flex items-center gap-3">
              <ChartLineUp size={18} className="text-blue-400" weight="fill" />
              <span className="text-sm font-black text-white">전략연구소</span>
              <span className="text-xs text-gray-500 font-bold truncate max-w-xs">"{latestParsed?.description}"</span>
            </div>
            <button
              onClick={handleReset}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-xs font-bold text-gray-400 hover:text-white"
            >
              <ArrowsClockwise size={14} />
              새 전략
            </button>
          </div>
          <div className="flex-1 overflow-auto">
            <BacktestDashboard
              result={result}
              onRestart={handleReset}
              onRun={handleRunBacktest}
              currentOptions={currentOptions}
              isRunning={isRunning}
              backtestDsl={backtestReq}
              strategySummary={latestParsed ? {
                strategyName: latestParsed.description,
                universeName: latestParsed.universe.map(u => UNIVERSE_LABELS[u] ?? u).join(", "),
                blockNames: [
                  ...latestParsed.fundamental_filters.map(f => `${METRIC_LABELS[f.metric] ?? f.metric} ${f.operator} ${f.value}`),
                  ...latestParsed.entry_signals.map(s => INDICATOR_LABELS[s.indicator] ?? s.indicator),
                  ...latestParsed.exit_signals.map(s => INDICATOR_LABELS[s.indicator] ?? s.indicator),
                ],
                entryBlocks: latestParsed.entry_signals.map(s => INDICATOR_LABELS[s.indicator] ?? s.indicator),
                exitBlocks: latestParsed.exit_signals.map(s => INDICATOR_LABELS[s.indicator] ?? s.indicator),
                positionText: `최대 ${latestParsed.max_positions}종목${latestParsed.hold_period_days ? ` · ${latestParsed.hold_period_days}일 보유` : ""}`,
                riskText: [
                  latestParsed.stop_loss_pct ? `손절 ${latestParsed.stop_loss_pct}%` : "",
                  latestParsed.take_profit_pct ? `익절 ${latestParsed.take_profit_pct}%` : "",
                ].filter(Boolean).join(", ") || undefined,
              } : undefined}
            />
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
      <div className="h-full flex flex-col items-center justify-center px-4 pt-24 pb-16">
        <div className="w-full max-w-5xl flex flex-col items-center gap-8">

          {/* 헤더 */}
          <div className="text-center space-y-2">
            <h1 className="text-2xl font-black text-white tracking-tight">전략연구소</h1>
            <p className="text-sm text-gray-500">
              원하는 투자 전략을 말로 설명하면 자동으로 백테스트해드립니다
            </p>
            {modelStatus?.status === "failed" && (
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-bold">
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
          <div className="w-full flex flex-col gap-3">

            {/* 대화 히스토리 */}
            {messages.length > 0 && (
              <div className="w-full rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-5 space-y-4 max-h-[60vh] overflow-y-auto">
                {messages.map((msg, i) => (
                  <div key={i}>
                    {msg.role === "user" && (
                      <div className="flex justify-end">
                        <div className="max-w-[80%] bg-blue-600/20 border border-blue-500/20 rounded-2xl rounded-tr-sm px-4 py-2.5">
                          <p className="text-xs text-white font-medium leading-relaxed">{msg.content}</p>
                        </div>
                      </div>
                    )}
                    {msg.role === "assistant" && (
                      <div className="space-y-3">
                        {msg.isLoading && (
                          <div className="flex items-center gap-2 px-1">
                            <ArrowsClockwise size={14} className="text-blue-400 animate-spin flex-shrink-0" />
                            <span className="text-xs text-gray-400 font-bold">전략 분석 중...</span>
                          </div>
                        )}
                        {msg.parsed && (
                          <>
                            <ParsedSummaryBubble parsed={msg.parsed} />
                            {msg.clarification && (
                              <div className="space-y-2.5">
                                <div className="flex items-start gap-2.5 p-3.5 rounded-xl bg-white/[0.03] border border-yellow-400/60">
                                  <Question size={14} className="text-yellow-400 flex-shrink-0 mt-0.5" weight="fill" />
                                  <p className="text-xs text-white leading-relaxed whitespace-pre-line">{msg.clarification.replace(/\*\*(.*?)\*\*/g, "$1")}</p>
                                </div>
                                {msg.clarificationSuggestions && (
                                  <div className="flex flex-wrap gap-1.5 pl-1">
                                    {msg.clarificationSuggestions.map((s, si) => (
                                      <button
                                        key={si}
                                        onClick={() => handleSend(s)}
                                        className="px-3 py-1.5 rounded-lg bg-white/[0.03] border border-yellow-400/30 hover:border-yellow-400 text-xs text-white/70 hover:text-white transition-all"
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
                                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-black shadow-[0_0_16px_rgba(59,130,246,0.25)] hover:shadow-[0_0_24px_rgba(59,130,246,0.4)] transition-all"
                              >
                                <ChartLineUp size={14} weight="fill" />
                                백테스트 실행
                                <ArrowRight size={12} />
                              </button>
                            )}
                            {isLastAssistant(i) && stage === "running" && (
                              <div className="flex items-center gap-2 px-1">
                                <ArrowsClockwise size={14} className="text-blue-400 animate-spin flex-shrink-0" />
                                <span className="text-xs text-gray-400 font-bold transition-all duration-300">{statusMessage}</span>
                              </div>
                            )}
                          </>
                        )}
                        {msg.error && (
                          <div className="flex items-start gap-2.5 p-3.5 rounded-xl bg-red-500/10 border border-red-500/20">
                            <Warning size={14} className="text-red-400 flex-shrink-0 mt-0.5" weight="fill" />
                            <div className="space-y-1 flex-1">
                              <p className="text-xs font-bold text-red-400">오류 발생</p>
                              <p className="text-xs text-red-300/70">{msg.error}</p>
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
            <div className="relative w-full rounded-2xl border border-white/20 bg-white/[0.03]">
              <textarea
                ref={textareaRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={isIdle ? "예) PBR 1 이하, PER 7 이하 종목 10개를 1년간 보유하는 전략" : "수정하고 싶은 내용을 입력하세요..."}
                disabled={stage === "running"}
                rows={2}
                className="w-full bg-transparent text-white placeholder-gray-600 text-sm font-medium resize-none outline-none focus:outline-none focus:ring-0 px-5 pt-4 pb-12 leading-relaxed"
              />
              <div className="absolute bottom-3 right-3 flex items-center gap-2">
                <button
                  onClick={() => handleSend()}
                  disabled={!inputValue.trim() || isSending || stage === "running"}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-white/5 disabled:text-gray-600 text-white text-xs font-bold transition-all"
                >
                  <>
                    <Sparkle size={12} weight="fill" />
                    전략 생성
                  </>
                </button>
              </div>
            </div>
            )}
          </div>

          {/* 예시 프롬프트 */}
          {isIdle && (
            <div className="w-full space-y-2">
              <p className="text-[13px] text-gray-600 font-bold text-center tracking-wider uppercase">전략 예시</p>
              <div className="grid grid-cols-4 gap-2">
                {EXAMPLES.map((ex) => {
                  const style = CATEGORY_STYLE[ex.category];
                  return (
                    <button
                      key={ex.title}
                      onClick={() => setInputValue(ex.prompt)}
                      className="group text-left rounded-xl border border-white/5 hover:border-white/10 bg-white/[0.02] hover:bg-white/[0.05] px-3.5 py-3 transition-all space-y-1.5"
                    >
                      <span className={`inline-block text-[9px] font-black px-1.5 py-0.5 rounded-full ${style.bg} ${style.border} border ${style.color}`}>
                        {style.label}
                      </span>
                      <p className="text-[12px] font-black text-white/80 group-hover:text-white leading-snug">{ex.title}</p>
                      <p className="text-[11px] text-gray-500 group-hover:text-gray-400 leading-relaxed line-clamp-2">{ex.prompt}</p>
                    </button>
                  );
                })}
              </div>
            </div>
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
