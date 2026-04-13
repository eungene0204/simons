"use client";

import { useState, useEffect, Suspense } from "react";
import { useParams, useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import BacktestDashboard from "@/components/strategy/backtest/BacktestDashboard";
import { BacktestResult } from "@/types/strategy";
import { ChartLineUp, ArrowLeft, ArrowsClockwise, Warning } from "phosphor-react";
import { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";
import {
  inferBacktestOptionsFromResult,
  normalizeLegacyBreakoutStrategy,
} from "@/components/strategy/legacyBreakout";

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
  const [strategySummary, setStrategySummary] = useState<any>(null);
  const [aiSummary, setAiSummary] = useState<string | undefined>();
  const [aiScore, setAiScore] = useState<number | undefined>();
  const [aiStrengths, setAiStrengths] = useState<string[]>([]);
  const [aiWeaknesses, setAiWeaknesses] = useState<string[]>([]);
  const [aiImprovements, setAiImprovements] = useState<string[]>([]);

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

        setBacktestDsl(normalizedSettings);
        setCurrentOptions(options);

        if (data.backtestResult.aiSummary) setAiSummary(data.backtestResult.aiSummary);
        if (data.backtestResult.aiScore != null) setAiScore(data.backtestResult.aiScore);
        setAiStrengths(data.backtestResult.aiStrengths ?? []);
        setAiWeaknesses(data.backtestResult.aiWeaknesses ?? []);
        setAiImprovements(data.backtestResult.aiImprovements ?? []);

        // strategySummary 구성
        if (normalizedSettings) {
          // universe는 V2: { id: "kospi", filters: {...} } 또는 NL: 없음
          const universeId = normalizedSettings.universe?.id ?? normalizedSettings.universe;
          const UNIVERSE_NAMES: Record<string, string> = {
            kospi: "KOSPI", kosdaq: "KOSDAQ", kospi200: "KOSPI 200",
            KOR_KOSPI200: "KOSPI 200", KOR_KOSDAQ150: "KOSDAQ 150",
            US_TECH_TOP10: "미국 테크 Top 10", CRYPTO_TOP10: "크립토 Top 10",
          };
          const universeName = (typeof universeId === "string" && universeId)
            ? (UNIVERSE_NAMES[universeId] ?? universeId)
            : "";
          setStrategySummary({
            strategyName: data.name,
            universeName: universeName || "—",
            blockNames: [],
            positionText: normalizedSettings.risk?.max_positions ? `최대 ${normalizedSettings.risk.max_positions}종목` : undefined,
            riskText: [
              normalizedSettings.risk?.stop_loss_pct ? `손절 ${normalizedSettings.risk.stop_loss_pct}%` : "",
              normalizedSettings.risk?.take_profit_pct ? `익절 ${normalizedSettings.risk.take_profit_pct}%` : "",
            ].filter(Boolean).join(", ") || undefined,
          });
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

  const handleRun = async (options: BacktestConfigOptions) => {
    if (!backtestDsl) return;

    setIsRunning(true);
    setCurrentOptions(options);
    try {
      const rerunRequest = {
        ...backtestDsl,
        period: options.period ?? backtestDsl.period,
        risk: {
          ...backtestDsl.risk,
          init_cash: options.initialCapital ?? backtestDsl.risk?.init_cash,
        },
        options: {
          ...backtestDsl.options,
          fee_rate: (options.commissionPct ?? 0.015) / 100,
          slippage_rate: (options.slippagePct ?? 0.05) / 100,
        },
      };
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

  if (loading) {
    return (
      <DashboardLayout userName="">
        <div className="flex items-center justify-center h-full gap-2 text-gray-500">
          <ArrowsClockwise size={16} className="animate-spin" />
          <span className="text-sm font-bold">불러오는 중...</span>
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
            strategySummary={strategySummary}
            aiSummary={aiSummary}
            aiScore={aiScore}
            aiStrengths={aiStrengths}
            aiWeaknesses={aiWeaknesses}
            aiImprovements={aiImprovements}
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
