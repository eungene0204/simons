import { StrategyDSL, BacktestResult } from "@/types/strategy";
import { UniverseResolver } from "./pipeline/UniverseResolver";

export class BacktestService {

  async run(strategy: StrategyDSL, period: string = "full"): Promise<BacktestResult> {
    // 1. Identify required symbols (For now, just one from Universe)
    const symbols = UniverseResolver.getSymbols(
      strategy.universe.id, 
      strategy.universe.filters
    );

    if (symbols.length === 0) {
      throw new Error("No symbols found in selected universe");
    }

    const symbol = symbols[0]; // Single-stock proof of concept

    // 2. Call Python Microservice
    try {
      const response = await fetch("http://localhost:8000/backtest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          symbol,
          entry: strategy.entry,
          exit: strategy.exit,
          risk: strategy.risk,
          period: period
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to run backtest in Python engine");
      }

      const pythonResult = await response.json();

      // 3. Map Python Result to TS BacktestResult interface
      return {
        strategyId: strategy.id,
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
        dates: pythonResult.dates,
        tradesList: pythonResult.signals.map((s: any) => ({
          date: s.date,
          type: s.type,
          price: s.price,
          quantity: 0, // Placeholder
          reason: s.condition
        })),
        monthlyReturns: {},
        yearlyReturns: {},
        signals: pythonResult.signals.map((s: any) => ({
          date: s.date,
          type: s.type,
          condition: s.condition,
          price: s.price
        })),
      };
    } catch (error: any) {
      console.error("Backtest integration error:", error);
      throw error;
    }
  }
}
