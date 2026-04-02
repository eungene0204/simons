import { StrategyDSL, BacktestResult } from "@/types/strategy";
import { UniverseResolver } from "./pipeline/UniverseResolver";
import { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";

export class BacktestService {

  async run(strategy: StrategyDSL, options: BacktestConfigOptions): Promise<BacktestResult> {
    const serviceId = Math.random().toString(36).substr(2, 5);

    // 1. Identify required symbols
    const symbols = await UniverseResolver.getSymbols(
      strategy.universe.id,
      strategy.universe.filters
    );

    if (symbols.length === 0) {
      throw new Error("No symbols found in selected universe");
    }

    const requestBody = {
      symbols,
      entry: strategy.entry,
      exit: strategy.exit,
      risk: {
        ...strategy.risk,
        init_cash: options.initialCapital
      },
      period: options.period,
      options: {
        fee_rate: options.commissionPct / 100,
        slippage_rate: options.slippagePct / 100,
        execution_type: strategy.risk?.execution_timing || "next_open"
      }
    };

    // 2. Call caching proxy (deduplicates identical backtests across users)
    try {
      const response = await fetch("/api/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
        cache: "no-store",
      });

      if (!response.ok) {
        const errorData = await response.json();
        const detail = errorData.detail;
        let errorMessage = "Failed to run backtest in Python engine";
        
        if (typeof detail === "string") {
          errorMessage = detail;
        } else if (Array.isArray(detail)) {
          // FastAPI validation error format
          errorMessage = detail.map((err: any) => `${err.loc.join('.')}: ${err.msg}`).join(', ');
        } else if (detail && typeof detail === "object") {
          errorMessage = JSON.stringify(detail);
        }
        
        throw new Error(errorMessage);
      }

      const pythonResult = await response.json();

      // 3. Map Python Result to TS BacktestResult interface
      return {
        executionId: `run_${Date.now()}_${serviceId}`,
        strategyId: strategy.id,
        symbols: pythonResult.symbols,
        totalReturn: pythonResult.totalReturn,
        cagr: pythonResult.cagr,
        buyAndHoldReturn: pythonResult.buyAndHoldReturn,
        maxDrawdown: pythonResult.maxDrawdown,
        winRate: pythonResult.winRate,
        profitFactor: pythonResult.profitFactor || 0,
        sharpe: pythonResult.sharpe || 0,
        sortino: Number(pythonResult.sortino),
        kelly: Number(pythonResult.kelly || 0),
        volatility: Number(pythonResult.volatility),
        trades: Number(pythonResult.trades),
        finalEquity: pythonResult.equity[pythonResult.equity.length - 1],
        initialCapital: pythonResult.equity[0],
        equity: pythonResult.equity,
        benchmarkEquity: pythonResult.benchmark_equity,
        dates: pythonResult.dates,
        tradesList: pythonResult.signals.map((s: any) => ({
          date: s.date,
          symbol: s.symbol,
          type: s.type,
          price: s.price,
          quantity: s.quantity || 0,
          amount: s.amount || 0,
          reason: s.condition
        })),
        monthlyReturns: {},
        yearlyReturns: {},
        signals: pythonResult.signals.map((s: any) => ({
          date: s.date,
          symbol: s.symbol,
          type: s.type === 'buy' ? 'entry' : 'exit',
          condition: s.condition,
          price: Number(s.price),
          quantity: Number(s.quantity),
          amount: Number(s.amount)
        })),
        perAssetStats: pythonResult.perAssetStats,
        warnings: pythonResult.warnings,
        avgProfit: pythonResult.avgProfit,
        avgLoss: pythonResult.avgLoss,
        maxConsecutiveWins: pythonResult.maxConsecutiveWins,
        maxConsecutiveLosses: pythonResult.maxConsecutiveLosses,
        executionTime: pythonResult.executionTime,
        fromCache: pythonResult.fromCache ?? false,
        cachedAt: pythonResult.cachedAt,
        cacheKey: pythonResult.cacheKey,
      };
    } catch (error: any) {
      console.error("Backtest integration error:", error);
      const errorMessage = error instanceof Error ? error.message : "알 수 없는 에러가 발생했습니다.";
      throw new Error(`백테스트 엔진 오류: ${errorMessage}`);
    }
  }

  async walkForward(strategy: StrategyDSL, options: BacktestConfigOptions, ranges: Record<string, any>, wfaSettings: { n_splits: number; train_pct: number; anchor: boolean; target_metric: string; n_trials: number }): Promise<any> {
    const symbols = await UniverseResolver.getSymbols(
      strategy.universe.id,
      strategy.universe.filters
    );

    if (symbols.length === 0) {
      throw new Error("No symbols found in selected universe");
    }

    const baseStrategy = {
      symbols,
      entry: strategy.entry,
      exit: strategy.exit,
      risk: { ...strategy.risk, init_cash: options.initialCapital },
      period: options.period,
      options: {
        fee_rate: options.commissionPct / 100,
        slippage_rate: options.slippagePct / 100,
        execution_type: strategy.risk?.execution_timing || "next_open",
      },
    };

    const requestBody = {
      base_strategy: baseStrategy,
      ranges,
      ...wfaSettings,
    };

    try {
      const response = await fetch("/api/backtest/walk-forward", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
        cache: "no-store",
      });

      if (!response.ok) {
        const errorData = await response.json();
        const detail = errorData.detail;
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }

      return await response.json();
    } catch (error: any) {
      const msg = error instanceof Error ? error.message : "알 수 없는 에러";
      throw new Error(`워크포워드 분석 오류: ${msg}`);
    }
  }

  async optimize(strategy: StrategyDSL, options: BacktestConfigOptions, userPrompt: string, targetMetric: string = "cagr", ranges: Record<string, any>, nTrials: number = 50, signal?: AbortSignal): Promise<any> {
    // 1. Identify required symbols
    const symbols = await UniverseResolver.getSymbols(
      strategy.universe.id, 
      strategy.universe.filters
    );

    if (symbols.length === 0) {
      throw new Error("No symbols found in selected universe");
    }

    const baseStrategy = {
      symbols,
      entry: strategy.entry,
      exit: strategy.exit,
      risk: {
        ...strategy.risk,
        init_cash: options.initialCapital
      },
      period: options.period,
      options: {
        fee_rate: options.commissionPct / 100,
        slippage_rate: options.slippagePct / 100,
        execution_type: strategy.risk?.execution_timing || "next_open"
      }
    };

    const requestBody = {
      base_strategy: baseStrategy,
      user_prompt: userPrompt,
      target_metric: targetMetric,
      n_trials: nTrials,
      ranges: ranges
    };

    try {
      const response = await fetch("http://localhost:8000/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
        cache: "no-store",
        signal,
      });

      if (!response.ok) {
        const errorData = await response.json();
        const detail = errorData.detail;
        let errorMessage = "Failed to run optimization in Python engine";
        if (typeof detail === "string") {
          errorMessage = detail;
        } else if (detail && typeof detail === "object") {
          errorMessage = JSON.stringify(detail);
        }
        throw new Error(errorMessage);
      }

      const result = await response.json();
      return result;
    } catch (error: any) {
      console.error("Optimization integration error:", error);
      const errorMessage = error instanceof Error ? error.message : "알 수 없는 에러가 발생했습니다.";
      throw new Error(`최적화 엔진 오류: ${errorMessage}`);
    }
  }
}
