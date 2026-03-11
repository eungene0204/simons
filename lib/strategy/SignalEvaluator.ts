import { Condition, ConditionGroup, StrategyDSL, StrategyDataset } from "@/types/strategy";

export class SignalEvaluator {
  static evaluateGroup(
    group: ConditionGroup,
    index: number,
    dataset: StrategyDataset,
    portfolioState: any // To check risk/position related conditions
  ): boolean {
    if (group.conditions.length === 0) return false;

    // Implicitly evaluate as OR for indicators (any condition met)
    // Filter conditions will be evaluated outside if needed, 
    // but within a condition group, we treat it as OR based on the new spec.
    return group.conditions.some((c) => this.evaluateCondition(c, index, dataset, portfolioState));
  }

  private static evaluateCondition(
    condition: Condition,
    index: number,
    dataset: StrategyDataset,
    portfolioState: any
  ): boolean {
    const { type, id, params } = condition;

    if (type === "indicator") {
      return this.evaluateIndicator(id, params, index, dataset);
    }

    if (type === "risk") {
      return this.evaluateRiskCondition(id, params, index, dataset, portfolioState);
    }

    // Add other types like 'flow', 'ml', 'filter' as needed
    return false;
  }

  private static evaluateIndicator(
    id: string,
    params: any,
    index: number,
    dataset: StrategyDataset
  ): boolean {
    const features = dataset.features;

    switch (id) {
      case "ma_crossover": {
        const short = params.shortMA || 5;
        const long = params.longMA || 20;
        const shortMA = features[`sma_${short}`];
        const longMA = features[`sma_${long}`];
        
        if (index < 1 || isNaN(shortMA[index]) || isNaN(longMA[index])) return false;
        
        const isUp = params.signalType !== "sell";
        if (isUp) {
          return shortMA[index - 1] <= longMA[index - 1] && shortMA[index] > longMA[index];
        } else {
          return shortMA[index - 1] >= longMA[index - 1] && shortMA[index] < longMA[index];
        }
      }

      case "rsi": {
        const period = params.period || 14;
        const rsi = features[`rsi_${period}`];
        if (isNaN(rsi[index])) return false;
        
        const operator = params.operator || "<";
        const threshold = params.value || 30;
        return this.compare(rsi[index], operator, threshold);
      }

      case "macd": {
        const key = `macd_${params.fastPeriod || 12}_${params.slowPeriod || 26}_${params.signalPeriod || 9}`;
        const { macd, signal } = features[key] || {};
        if (!macd || isNaN(macd[index]) || isNaN(signal[index])) return false;

        const isUp = params.signalType !== "sell";
        if (isUp) {
          return macd[index - 1] <= signal[index - 1] && macd[index] > signal[index];
        } else {
          return macd[index - 1] >= signal[index - 1] && macd[index] < signal[index];
        }
      }
      
      // More cases can be added here
    }
    return false;
  }

  private static evaluateRiskCondition(
    id: string,
    params: any,
    index: number,
    dataset: StrategyDataset,
    portfolioState: any
  ): boolean {
    const currentPrice = dataset.prices.close[index];
    const { entryPrice, entryIndex } = portfolioState;

    if (!entryPrice) return false;

    switch (id) {
      case "stop_loss_pct": {
        const stopLoss = params.value || 0;
        const change = ((currentPrice - entryPrice) / entryPrice) * 100;
        return change <= -stopLoss;
      }
      case "take_profit_pct": {
        const takeProfit = params.value || 0;
        const change = ((currentPrice - entryPrice) / entryPrice) * 100;
        return change >= takeProfit;
      }
      case "max_holding_days": {
        const maxDays = params.value || 0;
        return (index - entryIndex) >= maxDays;
      }
      case "trailing_stop": {
        const trailPct = params.percentage || 0;
        const peakPrice = Math.max(...dataset.prices.high.slice(entryIndex, index + 1));
        const decline = ((peakPrice - currentPrice) / peakPrice) * 100;
        return decline >= trailPct;
      }
    }
    return false;
  }

  private static compare(val: number, operator: string, threshold: number): boolean {
    switch (operator) {
      case "<": return val < threshold;
      case ">": return val > threshold;
      case "<=": return val <= threshold;
      case ">=": return val >= threshold;
      case "==": return val === threshold;
      default: return false;
    }
  }
}
