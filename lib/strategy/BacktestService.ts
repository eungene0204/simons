import { StrategyDSL, BacktestResult } from "@/types/strategy";
import { UniverseResolver } from "./pipeline/UniverseResolver";
import { BacktestConfigOptions } from "@/components/strategy/backtest/BacktestConfig";

export class BacktestService {

  async run(strategy: StrategyDSL, options: BacktestConfigOptions): Promise<BacktestResult> {
    console.error("[DEBUG] BacktestService: run method START");
    // 1. Identify required symbols (For now, just one from Universe)
    const symbols = UniverseResolver.getSymbols(
      strategy.universe.id, 
      strategy.universe.filters
    );

    if (symbols.length === 0) {
      throw new Error("No symbols found in selected universe");
    }

    const symbol = symbols[0]; // Single-stock proof of concept

    const requestBody = {
          symbol,
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
            execution_type: "next_open" // Default
          }
        };

    console.error("[DEBUG] BacktestService: Fetching http://localhost:8000/backtest with body:", JSON.stringify(requestBody, null, 2));

    // 2. Call Python Microservice
    try {
      const response = await fetch("http://localhost:8000/backtest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to run backtest in Python engine");
      }

      console.error("[DEBUG] BacktestService: HTTP response received, status:", response.status);
      const pythonResult = await response.json();
      console.error("[DEBUG] BacktestService: Final result data keys:", Object.keys(pythonResult));
      console.error("[DEBUG] BacktestService: Sample signal:", pythonResult.signals?.[0]);

      // 3. Map Python Result to TS BacktestResult interface
      return {
        strategyId: strategy.id,
        symbol: pythonResult.symbol,
        totalReturn: pythonResult.totalReturn,
        cagr: pythonResult.cagr,
        buyAndHoldReturn: pythonResult.buyAndHoldReturn,
        maxDrawdown: pythonResult.maxDrawdown,
        winRate: pythonResult.winRate,
        profitFactor: pythonResult.profitFactor || 0,
        sharpe: pythonResult.sharpe || 0,
        sortino: pythonResult.sortino || 0,
        volatility: pythonResult.volatility || 0,
        kelly: 0,
        trades: pythonResult.signals.length / 2,
        finalEquity: pythonResult.equity[pythonResult.equity.length - 1],
        initialCapital: pythonResult.equity[0],
        equity: pythonResult.equity,
        benchmarkEquity: pythonResult.benchmark_equity,
        dates: pythonResult.dates,
        tradesList: pythonResult.signals.map((s: any) => ({
          date: s.date,
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
          type: s.type === 'buy' ? 'entry' : 'exit',
          condition: s.condition,
          price: Number(s.price),
          quantity: Number(s.quantity),
          amount: Number(s.amount)
        })),
        warnings: pythonResult.warnings,
      };
    } catch (error: any) {
      console.error("Backtest integration error:", error);
      const errorMessage = error instanceof Error ? error.message : "알 수 없는 에러가 발생했습니다.";
      throw new Error(`백테스트 엔진 오류: ${errorMessage}`);
    }
  }
}
