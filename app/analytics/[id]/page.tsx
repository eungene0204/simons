"use client";

import { useState, useEffect, Suspense } from "react";
import { useParams, useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import BacktestDashboard from "@/components/strategy/backtest/BacktestDashboard";
import { BacktestResult } from "@/types/strategy";
import { ChartLineUp, ArrowLeft, Spinner, Warning } from "phosphor-react";
import { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";
import {
  inferBacktestOptionsFromResult,
  normalizeLegacyBreakoutStrategy,
} from "@/components/strategy/legacyBreakout";
import { buildStrategySummaryFromDsl, resolveStrategyPrompt } from "@/lib/strategy-summary";
import {
  buildWalkForwardParameterRanges,
  buildWalkForwardRequest,
  hasWalkForwardParameterRanges,
  type AdvisorWalkForwardSettings,
} from "../new/parsedStrategyMerge";

function mapBacktestResponse(raw: any): BacktestResult {
  const equity: number[] = raw.equity ?? [];

  return {
    executionId: `rerun_${Date.now()}`,
    strategyId: "saved_strategy",
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
    calmar: raw.calmar ?? 0,
    avgHoldingDays: raw.avgHoldingDays ?? 0,
    exposure: raw.exposure ?? 0,
    maxDrawdownDuration: raw.maxDrawdownDuration ?? 0,
    expectancy: raw.expectancy ?? 0,
    recoveryFactor: raw.recoveryFactor ?? 0,
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
    tradesList: (raw.signals ?? []).map((signal: any) => ({
      date: signal.date,
      symbol: signal.symbol,
      type: signal.type as "buy" | "sell",
      price: signal.price,
      quantity: signal.quantity ?? 0,
      amount: signal.amount ?? 0,
      reason: signal.condition,
    })),
    monthlyReturns: {},
    yearlyReturns: {},
    signals: (raw.signals ?? []).map((signal: any) => ({
      date: signal.date,
      symbol: signal.symbol,
      type: signal.type === "buy" ? "entry" : "exit",
      condition: signal.condition,
      price: Number(signal.price),
      quantity: Number(signal.quantity),
      amount: Number(signal.amount),
    })),
    perAssetStats: raw.perAssetStats,
    benchmarkLabel: raw.benchmark_label,
    universeId: raw.universe_id,
    warnings: raw.warnings,
    executionTime: raw.executionTime,
    fromCache: raw.fromCache ?? false,
    cachedAt: raw.cachedAt,
    cacheKey: raw.cacheKey,
    vbtResult: raw.vbtResult ?? undefined,
    aiSummary: raw.aiSummary ?? undefined,
    aiScore: raw.aiScore ?? undefined,
    aiStrengths: raw.aiStrengths ?? undefined,
    aiWeaknesses: raw.aiWeaknesses ?? undefined,
    aiImprovements: raw.aiImprovements ?? undefined,
    advisorScore: raw.advisorScore ?? null,
    riskScore: raw.riskScore ?? null,
    overfitRisk: raw.overfitRisk ?? null,
  };
}

function StrategyResultContent() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [strategyName, setStrategyName] = useState("");
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [backtestDsl, setBacktestDsl] = useState<any>(null);
  const [currentOptions, setCurrentOptions] = useState<BacktestConfigOptions | undefined>();
  const [isRunning, setIsRunning] = useState(false);
  const [legacyNotice, setLegacyNotice] = useState<string | null>(null);
  const [strategyPrompt, setStrategyPrompt] = useState("");
  const [strategySummary, setStrategySummary] = useState<any>(null);
  const [aiSummary, setAiSummary] = useState<string | undefined>();
  const [aiScore, setAiScore] = useState<number | undefined>();
  const [aiStrengths, setAiStrengths] = useState<string[]>([]);
  const [aiWeaknesses, setAiWeaknesses] = useState<string[]>([]);
  const [aiImprovements, setAiImprovements] = useState<string[]>([]);
  const [advisorScore, setAdvisorScore] = useState<number | null>(null);
  const [riskScore, setRiskScore] = useState<number | null>(null);
  const [overfitRisk, setOverfitRisk] = useState<string | null>(null);

  useEffect(() => {
    const loadStrategy = async () => {
      try {
        const response = await fetch(`/api/strategy/${id}`);
        const data = await response.json();
        if (data.error) throw new Error(data.error);
        setStrategyName(data.name ?? "전략");
        if (!data.backtestResult) {
          setError("저장된 백테스트 결과가 없습니다.");
          return;
        }

        const rawSettings = data.settings;
        const normalizedSettings = rawSettings ? normalizeLegacyBreakoutStrategy(rawSettings) : null;
        const options = inferBacktestOptionsFromResult(data.backtestResult);
        const sourcePrompt = resolveStrategyPrompt(normalizedSettings, data.description);

        setBacktestDsl(normalizedSettings);
        setCurrentOptions(options);
        setStrategyPrompt(sourcePrompt);

        if (data.backtestResult.aiSummary) setAiSummary(data.backtestResult.aiSummary);
        if (data.backtestResult.aiScore != null) setAiScore(data.backtestResult.aiScore);
        setAiStrengths(data.backtestResult.aiStrengths ?? []);
        setAiWeaknesses(data.backtestResult.aiWeaknesses ?? []);
        setAiImprovements(data.backtestResult.aiImprovements ?? []);
        setAdvisorScore(data.backtestResult.advisorScore ?? null);
        setRiskScore(data.backtestResult.riskScore ?? null);
        setOverfitRisk(data.backtestResult.overfitRisk ?? null);

        if (data.historySummary) {
          setStrategySummary(data.historySummary);
        } else if (normalizedSettings) {
          setStrategySummary(buildStrategySummaryFromDsl({
            ...normalizedSettings,
            name: data.name,
            description: sourcePrompt,
          }));
        }

        if (normalizedSettings !== rawSettings) {
          setLegacyNotice("기존 52일 breakout 버그가 감지되었습니다. 필요하면 재실행 버튼으로 252일 기준 결과를 다시 계산해 주세요.");
        }

        setResult(data.backtestResult);
      } catch (e: any) {
        setError(e.message ?? "불러오기 실패");
      } finally {
        setLoading(false);
      }
    };

    loadStrategy();
  }, [id]);

  const buildEffectiveBacktestRequest = (options?: BacktestConfigOptions) => {
    return {
      ...backtestDsl,
      period: options?.period ?? backtestDsl.period,
      risk: {
        ...backtestDsl.risk,
        init_cash: options?.initialCapital ?? backtestDsl.risk?.init_cash,
      },
      options: {
        ...backtestDsl.options,
        fee_rate: (options?.commissionPct ?? 0.015) / 100,
        slippage_rate: (options?.slippagePct ?? 0.05) / 100,
      },
    };
  };

  const handleRun = async (options: BacktestConfigOptions) => {
    if (!backtestDsl) return;

    setIsRunning(true);
    setCurrentOptions(options);
    try {
      const rerunRequest = buildEffectiveBacktestRequest(options);
      const rerunResponse = await fetch("/api/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(rerunRequest),
        cache: "no-store",
      });
      const rerunData = await rerunResponse.json();
      if (!rerunResponse.ok) {
        throw new Error(rerunData.detail ?? rerunData.error ?? "재실행 실패");
      }
      setResult(mapBacktestResponse(rerunData));
      setLegacyNotice(null);
      setError(null);
    } catch (e: any) {
      setError(e.message ?? "재실행 실패");
    } finally {
      setIsRunning(false);
    }
  };

  const handleWalkForward = async (settings: AdvisorWalkForwardSettings) => {
    if (!backtestDsl) {
      throw new Error("워크포워드 분석을 실행할 백테스트 요청이 없습니다.");
    }

    const baseRequest = buildEffectiveBacktestRequest(currentOptions);
    const ranges = buildWalkForwardParameterRanges(baseRequest);
    if (!hasWalkForwardParameterRanges(ranges)) {
      throw new Error(
        "워크포워드 최적화에 사용할 숫자 파라미터가 없습니다. 손절/익절, 지표 기간, 임계값처럼 조정 가능한 조건이 포함된 전략에서 실행해 주세요."
      );
    }

    const res = await fetch("/api/backtest/walk-forward", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildWalkForwardRequest(baseRequest, settings, ranges)),
    });

    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail ?? "워크포워드 분석 실패");
    }

    return res.json();
  };

  if (loading) {
    return (
      <DashboardLayout userName="">
        <div
          role="status"
          aria-label="전략 결과 불러오는 중"
          className="flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] items-center justify-center"
        >
          <Spinner size={32} className="animate-spin text-gray-500" aria-hidden="true" />
        </div>
      </DashboardLayout>
    );
  }

  if (error || !result) {
    return (
      <DashboardLayout userName="">
        <div className="flex flex-col items-center justify-center h-full gap-4">
          <Warning size={32} className="text-[var(--main-blue)]" weight="fill" />
          <p className="text-sm font-bold text-[var(--main-blue)]">{error ?? "결과를 불러올 수 없습니다."}</p>
          <button
            onClick={() => router.push("/analytics")}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/[0.05] hover:bg-white/10 text-gray-400 hover:text-white text-xs font-bold transition-all duration-200"
          >
            <ArrowLeft size={13} />
            전략 목록으로
          </button>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout userName="">
      <div className="h-full flex flex-col">
        {legacyNotice && (
          <div className="px-5 pt-3">
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-xs font-bold text-amber-300">
              {legacyNotice}
            </div>
          </div>
        )}
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.05]">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/analytics")}
              className="flex items-center gap-1.5 text-gray-500 hover:text-gray-300 transition-colors duration-200"
            >
              <ArrowLeft size={14} />
            </button>
            <ChartLineUp size={16} className="text-sky-400" weight="fill" />
            <span className="text-sm font-black text-white">{strategyName}</span>
          </div>
        </div>
        <div className="flex-1 overflow-auto">
          <BacktestDashboard
            result={result}
            onRestart={() => router.push("/analytics")}
            onRun={handleRun}
            currentOptions={currentOptions}
            isRunning={isRunning}
            backtestDsl={backtestDsl}
            onWalkForward={handleWalkForward}
            strategySummary={strategySummary}
            promptText={strategyPrompt || undefined}
            aiSummary={aiSummary}
            aiScore={aiScore}
            aiStrengths={aiStrengths}
            aiWeaknesses={aiWeaknesses}
            aiImprovements={aiImprovements}
            advisorScore={advisorScore}
            riskScore={riskScore}
            overfitRisk={overfitRisk}
            disableHistorySave={true}
          />
        </div>
      </div>
    </DashboardLayout>
  );
}

export default function StrategyResultPage() {
  return (
    <Suspense>
      <StrategyResultContent />
    </Suspense>
  );
}
