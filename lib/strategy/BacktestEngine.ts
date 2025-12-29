import { StrategyDSL, BacktestResult } from "@/types/strategy";
import { DataPipeline, StrategyDataset } from "./pipeline/DataPipeline";
import { SignalEvaluator } from "./SignalEvaluator";
import { TradeSimulator } from "./TradeSimulator";

export class BacktestEngine {
  private pipeline = new DataPipeline();

  async run(strategy: StrategyDSL, period: string = "full"): Promise<BacktestResult> {
    // 1. Get Data
    const datasets = await this.pipeline.getDatasetForStrategy(strategy, period);
    if (datasets.length === 0) {
      throw new Error("No data available for backtest");
    }

    // For now, support single-stock backtest (first in dataset)
    const dataset = datasets[0];
    const { dates, prices } = dataset;
    const simulator = new TradeSimulator();

    // 2. Main Loop
    for (let i = 0; i < dates.length; i++) {
      const currentPrice = prices.close[i];
      const currentDate = dates[i];
      const portfolioState = simulator.getState();

      // Check Exit Conditions
      if (portfolioState.shares > 0) {
        const shouldExit = SignalEvaluator.evaluateGroup(strategy.exit, i, dataset, portfolioState);
        if (shouldExit) {
          simulator.executeExit(currentDate, currentPrice);
        }
      }

      // Check Entry Conditions
      if (portfolioState.shares === 0) {
        const shouldEntry = SignalEvaluator.evaluateGroup(strategy.entry, i, dataset, portfolioState);
        if (shouldEntry) {
          simulator.executeEntry(currentDate, i, currentPrice, strategy.risk);
        }
      }

      // Update Daily Equity
      simulator.updateEquity(currentPrice);
    }

    // 3. Finalize
    const lastPrice = prices.close[prices.close.length - 1];
    const lastDate = dates[dates.length - 1];
    simulator.finalize(lastPrice, lastDate);

    // 4. Calculate Metrics & Return Results
    return this.calculateResults(strategy, simulator.getState(), dataset);
  }

  private calculateResults(strategy: StrategyDSL, state: any, dataset: StrategyDataset): BacktestResult {
    const initialCapital = state.equity[0];
    const finalEquity = state.equity[state.equity.length - 1];
    const totalReturn = ((finalEquity - initialCapital) / initialCapital) * 100;
    
    // Simple CAGR calculation
    const years = dataset.dates.length / 252;
    const cagr = (Math.pow(finalEquity / initialCapital, 1 / years) - 1) * 100;

    // MDD calculation
    let maxDrawdown = 0;
    let peak = initialCapital;
    for (const eq of state.equity) {
      if (eq > peak) peak = eq;
      const dd = ((peak - eq) / peak) * 100;
      if (dd > maxDrawdown) maxDrawdown = dd;
    }

    const metrics = this.calculateMetrics(state.equity, dataset.dates);

    return {
      strategyId: strategy.id,
      totalReturn,
      cagr: isNaN(cagr) ? 0 : cagr,
      buyAndHoldReturn: ((dataset.prices.close[dataset.prices.close.length - 1] - dataset.prices.close[0]) / dataset.prices.close[0]) * 100,
      maxDrawdown,
      winRate: this.calculateWinRate(state.trades),
      profitFactor: this.calculateProfitFactor(state.trades),
      sharpe: metrics.sharpe,
      sortino: metrics.sortino,
      kelly: metrics.kelly,
      trades: state.trades.length / 2,
      finalEquity,
      initialCapital,
      equity: state.equity,
      dates: dataset.dates,
      tradesList: state.trades.map((t: any) => ({
        ...t,
        quantity: t.shares,
      })),
      monthlyReturns: {},
      yearlyReturns: {},
      signals: state.trades.map((t: any) => ({
        date: t.date,
        type: t.type === "buy" ? "entry" : "exit",
        condition: t.reason,
        price: t.price,
      })),
    };
  }

  private calculateMetrics(equity: number[], dates: string[]) {
    if (equity.length < 2) return { sharpe: 0, sortino: 0, kelly: 0 };

    const returns = [];
    for (let i = 1; i < equity.length; i++) {
      returns.push((equity[i] - equity[i - 1]) / equity[i - 1]);
    }

    const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
    const stdDev = Math.sqrt(returns.reduce((s, r) => s + Math.pow(r - avgReturn, 2), 0) / returns.length);
    
    // Annualized Sharpe (assuming daily data)
    const sharpe = stdDev > 0 ? (avgReturn / stdDev) * Math.sqrt(252) : 0;

    const negReturns = returns.filter(r => r < 0);
    const downsideStdDev = Math.sqrt(negReturns.reduce((s, r) => s + Math.pow(r, 2), 0) / (negReturns.length || 1));
    const sortino = downsideStdDev > 0 ? (avgReturn / downsideStdDev) * Math.sqrt(252) : 0;

    return { sharpe, sortino, kelly: 0 };
  }

  private calculateProfitFactor(trades: any[]) {
    let grossProfit = 0;
    let grossLoss = 0;
    for (let i = 0; i < trades.length; i += 2) {
      if (i + 1 < trades.length) {
        const pnl = (trades[i + 1].price - trades[i].price) * trades[i].shares;
        if (pnl > 0) grossProfit += pnl;
        else grossLoss += Math.abs(pnl);
      }
    }
    return grossLoss > 0 ? grossProfit / grossLoss : 0;
  }

  private calculateWinRate(trades: any[]): number {
    let wins = 0;
    let total = 0;
    for (let i = 0; i < trades.length; i += 2) {
      if (i + 1 < trades.length) {
        total++;
        if (trades[i + 1].price > trades[i].price) wins++;
      }
    }
    return total > 0 ? (wins / total) * 100 : 0;
  }
}
