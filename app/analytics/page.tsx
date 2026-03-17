"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import BacktestDashboard from "@/components/strategy/backtest/BacktestDashboard";
import { BacktestResult } from "@/types/strategy";
import {
  Sparkle,
  ArrowRight,
  ArrowsClockwise,
  CheckCircle,
  Warning,
  ChartLineUp,
} from "phosphor-react";

const EXAMPLES = [
  "PBR 1 이하, PER 7 이하 종목 10개를 1년간 보유",
  "ROE 15% 이상, 부채비율 100% 이하인 우량주 20개 분기 리밸런싱",
  "골든크로스 발생 시 매수, RSI 70 이상이면 매도, 최대 15종목",
  "시가총액 1000억 이상, PBR 0.5 이하 소형 가치주 10개 6개월 보유",
  "MACD 크로스 매수, 데드크로스 매도, 손절 10%, 익절 25%",
];

type Stage = "idle" | "parsing" | "ready" | "running" | "done" | "error";

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
};

function FilterBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center px-2.5 py-1 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-300 text-xs font-bold">
      {label}
    </span>
  );
}

function ParsedSummaryCard({ parsed }: { parsed: ParsedSummary }) {
  return (
    <div className="w-full max-w-2xl bg-white/[0.03] border border-white/10 rounded-2xl p-5 space-y-4">
      <div className="flex items-center gap-2">
        <CheckCircle size={16} className="text-green-400" weight="fill" />
        <span className="text-xs font-bold text-green-400">전략 파싱 완료</span>
      </div>

      <div className="space-y-3">
        {/* Filters */}
        {parsed.fundamental_filters.length > 0 && (
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-xs text-gray-500 w-16 flex-shrink-0">재무 필터</span>
            <div className="flex flex-wrap gap-1.5">
              {parsed.fundamental_filters.map((f, i) => (
                <FilterBadge key={i} label={`${METRIC_LABELS[f.metric] ?? f.metric} ${f.operator} ${f.value}`} />
              ))}
            </div>
          </div>
        )}

        {/* Entry signals */}
        {parsed.entry_signals.length > 0 && (
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-xs text-gray-500 w-16 flex-shrink-0">진입 신호</span>
            <div className="flex flex-wrap gap-1.5">
              {parsed.entry_signals.map((s, i) => (
                <FilterBadge key={i} label={INDICATOR_LABELS[s.indicator] ?? s.indicator} />
              ))}
            </div>
          </div>
        )}

        {/* Exit signals */}
        {parsed.exit_signals.length > 0 && (
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-xs text-gray-500 w-16 flex-shrink-0">청산 신호</span>
            <div className="flex flex-wrap gap-1.5">
              {parsed.exit_signals.map((s, i) => (
                <FilterBadge key={i} label={INDICATOR_LABELS[s.indicator] ?? s.indicator} />
              ))}
            </div>
          </div>
        )}

        {/* Portfolio settings */}
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-gray-500 w-16 flex-shrink-0">포트폴리오</span>
          <div className="flex flex-wrap gap-1.5">
            <FilterBadge label={`최대 ${parsed.max_positions}종목`} />
            {parsed.hold_period_days && (
              <FilterBadge label={`${parsed.hold_period_days}일 보유`} />
            )}
            {parsed.rebalancing_period !== "none" && (
              <FilterBadge label={`${REBAL_LABELS[parsed.rebalancing_period]} 리밸런싱`} />
            )}
            <FilterBadge label={`백테스트 ${PERIOD_LABELS[parsed.backtest_period]}`} />
            <FilterBadge label={`초기자금 ${(parsed.initial_capital ?? 10000000).toLocaleString("ko-KR")}원`} />
          </div>
        </div>

        {/* Risk */}
        {(parsed.stop_loss_pct || parsed.take_profit_pct) && (
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-xs text-gray-500 w-16 flex-shrink-0">리스크</span>
            <div className="flex flex-wrap gap-1.5">
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
  const [prompt, setPrompt] = useState("");
  const [stage, setStage] = useState<Stage>("idle");
  const [parsed, setParsed] = useState<ParsedSummary | null>(null);
  const [backtestReq, setBacktestReq] = useState<any>(null);
  const [currentOptions, setCurrentOptions] = useState<any>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [prompt]);

  const handleParse = async () => {
    if (!prompt.trim() || stage === "parsing") return;
    setStage("parsing");
    setError(null);
    setParsed(null);
    setResult(null);

    try {
      const res = await fetch("http://localhost:8000/strategy/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt.trim(), backend: "mlx" }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? "파싱 실패");
      }
      const data = await res.json();
      setParsed(data.parsed);
      setBacktestReq(data.backtest_request);
      setCurrentOptions({
        period: data.backtest_request?.period ?? "5y",
        initialCapital: data.backtest_request?.risk?.init_cash ?? 10000000,
        commissionPct: 0.015,
        slippagePct: 0.05,
      });
      setStage("ready");
    } catch (e: any) {
      setError(e.message ?? "알 수 없는 오류");
      setStage("error");
    }
  };

  const handleRunBacktest = async (options?: any) => {
    if (!backtestReq) return;

    // 옵션이 있으면 즉시 적용한 요청 객체를 빌드 (state 비동기 문제 방지)
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
    setError(null);

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
        // 청크를 버퍼에 누적 (한 줄이 여러 청크에 걸쳐 올 수 있음)
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        // 마지막 미완성 줄은 버퍼에 남겨둠
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
      setError(e.message ?? "알 수 없는 오류");
      setStage("error");
    }
  };

  const handleReset = () => {
    setStage("idle");
    setParsed(null);
    setBacktestReq(null);
    setResult(null);
    setError(null);
    setTimeout(() => textareaRef.current?.focus(), 100);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleParse();
    }
  };

  // ── 결과 화면
  const isRunning = stage === "running";
  if ((stage === "done" || isRunning) && result) {
    return (
      <DashboardLayout userName="">
        <div className="h-full flex flex-col">
          {/* 상단 바 */}
          <div className="flex items-center justify-between px-6 py-3 border-b border-white/5">
            <div className="flex items-center gap-3">
              <ChartLineUp size={18} className="text-blue-400" weight="fill" />
              <span className="text-sm font-black text-white">전략연구소</span>
              <span className="text-xs text-gray-500 font-bold truncate max-w-xs">"{parsed?.description}"</span>
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
            />
          </div>
        </div>
      </DashboardLayout>
    );
  }

  // ── 메인 프롬프트 화면
  return (
    <DashboardLayout userName="">
      <div className="h-full flex flex-col items-center justify-center px-4 pt-24">
        <div className="w-full max-w-2xl flex flex-col items-center gap-8">

          {/* 헤더 */}
          <div className="text-center space-y-2">
            <h1 className="text-2xl font-black text-white tracking-tight">전략연구소</h1>
            <p className="text-sm text-gray-500">
              원하는 투자 전략을 말로 설명하면 자동으로 백테스트해드립니다
            </p>
          </div>

          {/* 입력창 */}
          <div className="w-full space-y-3">
            <div className={`relative w-full rounded-2xl border transition-all duration-200 ${
              stage === "parsing" || stage === "running"
                ? "border-blue-500/40 bg-blue-500/5"
                : "border-white/10 bg-white/[0.03] hover:border-white/20 focus-within:border-blue-500/40 focus-within:bg-white/[0.05]"
            }`}>
              <textarea
                ref={textareaRef}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="예) PBR 1 이하, PER 7 이하 종목 10개를 1년간 보유하는 전략"
                disabled={stage === "parsing" || stage === "running"}
                rows={2}
                className="w-full bg-transparent text-white placeholder-gray-600 text-sm font-medium resize-none outline-none px-5 pt-4 pb-12 leading-relaxed"
              />
              <div className="absolute bottom-3 right-3 flex items-center gap-2">
                <span className="text-[10px] text-gray-600 font-bold">⌘ Enter</span>
                <button
                  onClick={handleParse}
                  disabled={!prompt.trim() || stage === "parsing" || stage === "running"}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-white/5 disabled:text-gray-600 text-white text-xs font-bold transition-all"
                >
                  {stage === "parsing" ? (
                    <>
                      <ArrowsClockwise size={12} className="animate-spin" />
                      분석 중...
                    </>
                  ) : (
                    <>
                      <Sparkle size={12} weight="fill" />
                      전략 생성
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* 예시 프롬프트 */}
            {stage === "idle" && (
              <div className="flex flex-wrap gap-2">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    onClick={() => setPrompt(ex)}
                    className="text-xs text-gray-500 hover:text-gray-300 bg-white/[0.02] hover:bg-white/5 border border-white/5 hover:border-white/10 rounded-lg px-3 py-1.5 transition-all font-medium text-left"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 파싱 결과 카드 */}
          {stage === "ready" && parsed && (
            <div className="w-full flex flex-col items-center gap-4">
              <ParsedSummaryCard parsed={parsed} />
              <button
                onClick={handleRunBacktest}
                className="flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-sm font-black shadow-[0_0_20px_rgba(59,130,246,0.3)] hover:shadow-[0_0_30px_rgba(59,130,246,0.5)] transition-all"
              >
                <ChartLineUp size={16} weight="fill" />
                백테스트 실행
                <ArrowRight size={14} />
              </button>
            </div>
          )}

          {/* 백테스트 실행 중 */}
          {stage === "running" && (
            <div className="flex flex-col items-center gap-4 text-center">
              {parsed && <ParsedSummaryCard parsed={parsed} />}
              <div className="flex items-center gap-3 mt-1">
                <ArrowsClockwise size={15} className="text-blue-400 animate-spin flex-shrink-0" />
                <span className="text-sm text-gray-300 font-bold transition-all duration-300">
                  {statusMessage}
                </span>
              </div>
            </div>
          )}

          {/* 에러 */}
          {stage === "error" && error && (
            <div className="w-full max-w-2xl flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20">
              <Warning size={16} className="text-red-400 flex-shrink-0 mt-0.5" weight="fill" />
              <div className="space-y-1 flex-1">
                <p className="text-xs font-bold text-red-400">오류 발생</p>
                <p className="text-xs text-red-300/70">{error}</p>
              </div>
              <button
                onClick={handleReset}
                className="text-xs text-gray-500 hover:text-white font-bold transition-colors"
              >
                다시 시도
              </button>
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
