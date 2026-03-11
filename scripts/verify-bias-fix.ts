import { BacktestService } from "../lib/strategy/BacktestService";
import { StrategyDSL } from "../types/strategy";

async function verifyTPlusOne() {
  const engine = new BacktestService();
  
  // Strategy: Buy if RSI < 30 (which will happen on first day)
  const mockStrategy: StrategyDSL = {
    id: "test-bias-fix",
    name: "Bias Fix Test",
    description: "Test",
    version: "1.0.0",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    universe: { id: "US_TECH_TOP10", filters: {} },
    entry: {
      conditions: [
        { type: "indicator", id: "ma_crossover", params: { shortMA: 1, longMA: 2, signalType: "buy" } }
      ]
    },
    exit: {
      conditions: [
        { type: "indicator", id: "ma_crossover", params: { shortMA: 1, longMA: 2, signalType: "sell" } }
      ]
    },
    risk: { position_size_pct: 100, max_positions: 1 }
  };

  try {
    const result = await engine.run(mockStrategy, {} as any);
    console.log("Backtest run successful!");
    console.log("Symbol:", result.initialCapital === 10000000 ? "Capital Matched" : "Capital Mismatch");
    console.log("Return:", result.totalReturn, "%");
    console.log("Signals found:", result.signals.length);
    
    if (result.signals.length > 0) {
      console.log("First Signal Details:", result.signals[0]);
    }
  } catch (e) {
    console.error("Verification failed:", e);
  }
}

verifyTPlusOne();
