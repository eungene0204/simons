// @ts-nocheck
import { StrategyDSL, BacktestResult } from "@/types/strategy";
import { generateCandleData } from "@/lib/mock-stock-data";

/**
 * Technical Indicator Calculation Functions
 */

// Calculate Simple Moving Average
function calculateMA(prices: number[], period: number): number[] {
  const ma: number[] = [];
  for (let i = 0; i < prices.length; i++) {
    if (i < period - 1) {
      ma.push(NaN);
    } else {
      const sum = prices.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
      ma.push(sum / period);
    }
  }
  return ma;
}

// Calculate Exponential Moving Average
function calculateEMA(prices: number[], period: number): number[] {
  const ema: number[] = [];
  const multiplier = 2 / (period + 1);
  
  for (let i = 0; i < prices.length; i++) {
    if (i === 0) {
      ema.push(prices[i]);
    } else if (i < period - 1) {
      // Use SMA for initial values
      const sum = prices.slice(0, i + 1).reduce((a, b) => a + b, 0);
      ema.push(sum / (i + 1));
    } else {
      ema.push((prices[i] - ema[i - 1]) * multiplier + ema[i - 1]);
    }
  }
  return ema;
}

// Calculate RSI
function calculateRSI(prices: number[], period: number): number[] {
  const rsi: number[] = [];
  const gains: number[] = [];
  const losses: number[] = [];

  for (let i = 1; i < prices.length; i++) {
    const change = prices[i] - prices[i - 1];
    gains.push(change > 0 ? change : 0);
    losses.push(change < 0 ? -change : 0);
  }

  for (let i = 0; i < prices.length; i++) {
    if (i < period) {
      rsi.push(NaN);
    } else {
      const avgGain = gains.slice(i - period, i).reduce((a, b) => a + b, 0) / period;
      const avgLoss = losses.slice(i - period, i).reduce((a, b) => a + b, 0) / period;
      if (avgLoss === 0) {
        rsi.push(100);
      } else {
        const rs = avgGain / avgLoss;
        rsi.push(100 - 100 / (1 + rs));
      }
    }
  }
  return rsi;
}

// Calculate MACD
function calculateMACD(
  prices: number[],
  fastPeriod: number = 12,
  slowPeriod: number = 26,
  signalPeriod: number = 9
): { macd: number[]; signal: number[]; histogram: number[] } {
  const fastEMA = calculateEMA(prices, fastPeriod);
  const slowEMA = calculateEMA(prices, slowPeriod);
  const macd: number[] = [];
  
  for (let i = 0; i < prices.length; i++) {
    if (isNaN(fastEMA[i]) || isNaN(slowEMA[i])) {
      macd.push(NaN);
    } else {
      macd.push(fastEMA[i] - slowEMA[i]);
    }
  }
  
  // Calculate signal line (EMA of MACD line)
  const signal: number[] = [];
  const multiplier = 2 / (signalPeriod + 1);
  
  for (let i = 0; i < macd.length; i++) {
    if (isNaN(macd[i])) {
      signal.push(NaN);
    } else {
      // Find first valid MACD value for initialization
      let firstValidIndex = i;
      while (firstValidIndex < macd.length && isNaN(macd[firstValidIndex])) {
        firstValidIndex++;
      }
      
      if (i === firstValidIndex) {
        signal.push(macd[i]);
      } else if (i < firstValidIndex + signalPeriod - 1) {
        // Use SMA for initial values
        const validMacdValues = macd.slice(firstValidIndex, i + 1).filter(v => !isNaN(v));
        if (validMacdValues.length > 0) {
          const sum = validMacdValues.reduce((a, b) => a + b, 0);
          signal.push(sum / validMacdValues.length);
        } else {
          signal.push(NaN);
        }
      } else {
        signal.push((macd[i] - signal[i - 1]) * multiplier + signal[i - 1]);
      }
    }
  }
  
  const histogram: number[] = [];
  
  for (let i = 0; i < macd.length; i++) {
    if (isNaN(macd[i]) || isNaN(signal[i])) {
      histogram.push(NaN);
    } else {
      histogram.push(macd[i] - signal[i]);
    }
  }
  
  return { macd, signal, histogram };
}

// Calculate Bollinger Bands
function calculateBollingerBands(
  prices: number[],
  period: number = 20,
  stdDev: number = 2
): { upper: number[]; middle: number[]; lower: number[] } {
  const ma = calculateMA(prices, period);
  const upper: number[] = [];
  const lower: number[] = [];
  
  for (let i = 0; i < prices.length; i++) {
    if (isNaN(ma[i])) {
      upper.push(NaN);
      lower.push(NaN);
    } else {
      // Calculate standard deviation
      const slice = prices.slice(i - period + 1, i + 1);
      const mean = ma[i];
      const variance = slice.reduce((sum, price) => sum + Math.pow(price - mean, 2), 0) / period;
      const standardDeviation = Math.sqrt(variance);
      
      upper.push(mean + stdDev * standardDeviation);
      lower.push(mean - stdDev * standardDeviation);
    }
  }
  
  return { upper, middle: ma, lower };
}

// Calculate volume average
function calculateVolumeMA(volumes: number[], period: number): number[] {
  const ma: number[] = new Array(volumes.length).fill(NaN);
  for (let i = period - 1; i < volumes.length; i++) {
    const window = volumes.slice(i - period + 1, i + 1);
    ma[i] = window.reduce((a, b) => a + b, 0) / period;
  }
  return ma;
}

function calculateOBV(prices: number[], volumes: number[], signalPeriod: number): { obv: number[], signal: number[] } {
  const obv: number[] = new Array(prices.length).fill(0);
  if (prices.length > 0) {
    obv[0] = volumes[0];
  }
  
  for (let i = 1; i < prices.length; i++) {
    if (prices[i] > prices[i - 1]) {
      obv[i] = obv[i - 1] + volumes[i];
    } else if (prices[i] < prices[i - 1]) {
      obv[i] = obv[i - 1] - volumes[i];
    } else {
      obv[i] = obv[i - 1];
    }
  }
  
  const signal = calculateMA(obv, signalPeriod);
  return { obv, signal };
}

/**
 * Backtest Engine - Executes strategy DSL and returns results
 */
export async function runBacktest(
  strategy: StrategyDSL,
  period: "1Y" | "3Y" | "5Y" | "Max"
): Promise<BacktestResult> {
  // Simulate processing time
  await new Promise((resolve) => setTimeout(resolve, 1000));

  // Generate mock historical data
  const candleData = generateCandleData("KOSPI", 3000, period === "1Y" ? 252 : period === "3Y" ? 756 : period === "5Y" ? 1260 : 2520);
  const prices = candleData.map((c) => c.close);
  const highs = candleData.map((c) => c.high);
  const lows = candleData.map((c) => c.low);
  const opens = candleData.map((c) => c.open);
  const volumes = candleData.map((c) => c.volume);
  const dates = candleData.map((c) => c.date);

  const initialCapital = 10000000; // 1천만원
  let capital = initialCapital;
  let shares = 0;
  let position: "long" | "none" = "none";
  let entryPrice = 0;
  let peakEquity = initialCapital;

  const equity: number[] = [initialCapital];
  const trades: Array<{
    date: string;
    type: "buy" | "sell";
    price: number;
    quantity: number;
    reason: string;
  }> = [];
  const signals: Array<{
    date: string;
    type: "entry" | "exit";
    condition: string;
    price: number;
  }> = [];

  // Evaluate entry conditions
  const evaluateEntryConditions = (index: number): boolean => {
    if (strategy.entry.conditions.length === 0) return false;

    if (strategy.entry.logic === "AND") {
      return strategy.entry.conditions.every((condition) =>
        evaluateCondition(condition, index, "entry")
      );
    } else if (strategy.entry.logic === "OR") {
      return strategy.entry.conditions.some((condition) =>
        evaluateCondition(condition, index, "entry")
      );
    } else if (strategy.entry.logic === "WEIGHTED_SUM") {
      const sum = strategy.entry.conditions.reduce((acc, condition) => {
        const weight = condition.weight || 1;
        return acc + (evaluateCondition(condition, index, "entry") ? weight : 0);
      }, 0);
      const totalWeight = strategy.entry.conditions.reduce(
        (acc, condition) => acc + (condition.weight || 1),
        0
      );
      return sum / totalWeight >= 0.5; // Threshold for weighted sum
    }

    return false;
  };

  // Evaluate exit conditions
  const evaluateExitConditions = (index: number): boolean => {
    if (strategy.exit.conditions.length === 0) return false;

    if (strategy.exit.logic === "AND") {
      return strategy.exit.conditions.every((condition) =>
        evaluateCondition(condition, index, "exit")
      );
    } else {
      return strategy.exit.conditions.some((condition) =>
        evaluateCondition(condition, index, "exit")
      );
    }
  };

  // Track entry date for max_holding_days
  let entryDateIndex = 0;

  // Pre-calculate all indicators for efficiency
  const indicators: {
    ma: Record<number, number[]>;
    ema: Record<number, number[]>;
    rsi: Record<number, number[]>;
    macd: Record<string, { macd: number[]; signal: number[]; histogram: number[] }>;
    bollinger: Record<string, { upper: number[]; middle: number[]; lower: number[] }>;
    volumeMA: Record<number, number[]>;
    obv: Record<number, { obv: number[]; signal: number[] }>;
  } = {
    ma: {},
    ema: {},
    rsi: {},
    macd: {},
    bollinger: {},
    volumeMA: {},
    obv: {},
  };

  // Evaluate individual condition
  const evaluateCondition = (
    condition: any,
    index: number,
    type: "entry" | "exit"
  ): boolean => {
    if (index < 0 || index >= prices.length) return false;

    // Risk management conditions
    if (condition.type === "risk") {
      if (condition.id === "price_limit_exit" && position === "long" && entryPrice > 0) {
        const change = ((prices[index] - entryPrice) / entryPrice) * 100;
        const stopLoss = condition.params.stopLossPct;
        const takeProfit = condition.params.takeProfitPct;
        const isStopLossHit = stopLoss > 0 && change <= -stopLoss;
        const isTakeProfitHit = takeProfit > 0 && change >= takeProfit;
        return isStopLossHit || isTakeProfitHit;
      }
      if (condition.id === "max_holding_days" && position === "long") {
        const holdingDays = index - entryDateIndex;
        return holdingDays >= condition.params.value;
      }
      if (condition.id === "trailing_stop" && position === "long" && entryPrice > 0) {
        // Track peak price since entry
        let peakPrice = entryPrice;
        for (let i = entryDateIndex; i <= index; i++) {
          peakPrice = Math.max(peakPrice, prices[i]);
        }
        const decline = ((peakPrice - prices[index]) / peakPrice) * 100;
        return decline >= condition.params.percentage;
      }
      return false;
    }

    // Indicator conditions
    if (condition.type === "indicator") {
      // MA Crossover
      if (condition.id === "ma_crossover") {
        const shortPeriod = condition.params.shortMA || 5;
        const longPeriod = condition.params.longMA || 20;
        
        if (!indicators.ma[shortPeriod]) {
          indicators.ma[shortPeriod] = calculateMA(prices, shortPeriod);
        }
        if (!indicators.ma[longPeriod]) {
          indicators.ma[longPeriod] = calculateMA(prices, longPeriod);
        }
        
        const shortMA = indicators.ma[shortPeriod];
        const longMA = indicators.ma[longPeriod];
        
        if (index < 1 || isNaN(shortMA[index]) || isNaN(longMA[index]) || 
            isNaN(shortMA[index - 1]) || isNaN(longMA[index - 1])) {
          return false;
        }
        
        const direction = condition.params.signalType === "sell" ? "down" : "up";
        if (direction === "up") {
          // Golden cross: short MA crosses above long MA
          return shortMA[index - 1] <= longMA[index - 1] && shortMA[index] > longMA[index];
        } else {
          // Death cross: short MA crosses below long MA
          return shortMA[index - 1] >= longMA[index - 1] && shortMA[index] < longMA[index];
        }
      }

      // RSI
      if (condition.id === "rsi") {
        const period = condition.params.period || 14;
        if (!indicators.rsi[period]) {
          indicators.rsi[period] = calculateRSI(prices, period);
        }
        const rsi = indicators.rsi[period];
        
        if (isNaN(rsi[index])) return false;
        
        const operator = condition.params.operator || "<";
        const value = condition.params.value || 30;
        
        switch (operator) {
          case "<":
            return rsi[index] < value;
          case ">":
            return rsi[index] > value;
          case "<=":
            return rsi[index] <= value;
          case ">=":
            return rsi[index] >= value;
          default:
            return false;
        }
      }

      // MACD
      if (condition.id === "macd") {
        const fastPeriod = condition.params.fastPeriod || 12;
        const slowPeriod = condition.params.slowPeriod || 26;
        const signalPeriod = condition.params.signalPeriod || 9;
        const key = `${fastPeriod}_${slowPeriod}_${signalPeriod}`;
        
        if (!indicators.macd[key]) {
          indicators.macd[key] = calculateMACD(prices, fastPeriod, slowPeriod, signalPeriod);
        }
        const { macd, signal } = indicators.macd[key];
        
        if (index < 1 || isNaN(macd[index]) || isNaN(signal[index]) ||
            isNaN(macd[index - 1]) || isNaN(signal[index - 1])) {
          return false;
        }
        
        const direction = condition.params.signalType === "sell" ? "down" : "up";
        if (direction === "up") {
          // MACD crosses above signal
          return macd[index - 1] <= signal[index - 1] && macd[index] > signal[index];
        } else {
          // MACD crosses below signal
          return macd[index - 1] >= signal[index - 1] && macd[index] < signal[index];
        }
      }

      // Bollinger Bands
      if (condition.id === "bollinger_bands") {
        const period = condition.params.period || 20;
        const stdDev = condition.params.stdDev || 2;
        const key = `${period}_${stdDev}`;
        
        if (!indicators.bollinger[key]) {
          indicators.bollinger[key] = calculateBollingerBands(prices, period, stdDev);
        }
        const { upper, lower } = indicators.bollinger[key];
        
        if (isNaN(upper[index]) || isNaN(lower[index])) return false;
        
        const position = condition.params.signalType === "sell" ? "upper" : "lower";
        if (position === "upper") {
          // Price crosses above upper band
          return index > 0 && prices[index - 1] <= upper[index - 1] && prices[index] > upper[index];
        } else {
          // Price crosses below lower band
          return index > 0 && prices[index - 1] >= lower[index - 1] && prices[index] < lower[index];
        }
      }
      
      // Volume Signal (OBV Signal Cross)
      if (condition.id === "volume_spike") { // Renamed from volume_spike to volume_signal in instruction, but keeping original ID for now
        const period = condition.params.period || 20;
        
        if (!indicators.obv[period]) {
          indicators.obv[period] = calculateOBV(prices, volumes, period);
        }
        const { obv, signal } = indicators.obv[period];
        
        if (index < 1 || isNaN(obv[index]) || isNaN(signal[index]) ||
            isNaN(obv[index - 1]) || isNaN(signal[index - 1])) {
          return false;
        }
        
        const direction = condition.params.signalType === "sell" ? "down" : "up";
        if (direction === "up") {
          // OBV crosses above signal
          return obv[index - 1] <= signal[index - 1] && obv[index] > signal[index];
        } else {
          // OBV crosses below signal
          return obv[index - 1] >= signal[index - 1] && obv[index] < signal[index];
        }
      }

      // Breakout
      if (condition.id === "breakout") {
        const lookbackPeriod = condition.params.lookbackPeriod || 20;
        
        if (index < lookbackPeriod) return false;
        
        const direction = condition.params.signalType === "sell" ? "down" : "up";
        if (direction === "up") { // Upward breakout (highest high) is buy signal by convention here
          // Breakout above high
          const highestHigh = Math.max(...highs.slice(index - lookbackPeriod, index));
          return prices[index] > highestHigh;
        } else {
          // Breakout below low
          const lowestLow = Math.min(...lows.slice(index - lookbackPeriod, index));
          return prices[index] < lowestLow;
        }
      }
    }

    // Flow conditions (mock for now - would need actual flow data)
    if (condition.type === "flow") {
      // These would require actual institutional/foreign/individual flow data
      // For now, return false as we don't have this data
      return false;
    }

    // Unified Quantitative Factors Evaluation (for blocks marked as hidden in strategy-blocks.ts)
    const quantFactorIds = [
      "per", "pbr", "dividend_yield", "psr", "revenue_growth", 
      "ev_ebitda", "pcf", "roic", "operating_margin", 
      "debt_to_equity", "operating_profit_growth", "beta", 
      "market_cap", "foreigner_ownership"
    ];

    if (quantFactorIds.includes(condition.id)) {
      // For mock purposes, we generate semi-stable factor values for each stock.
      // In a real system, these would be fetched from a fundamental data API.
      const factorSeed = (condition.id.length * 7) % 31;
      const getFactorValue = (idx: number) => {
        // Create some pseudo-random but somewhat consistent factor values
        const noise = Math.sin(idx * 0.1) * 2;
        switch (condition.id) {
          case "per": return 15 + factorSeed + noise; 
          case "pbr": return 1.5 + (factorSeed / 10) + (noise / 5);
          case "dividend_yield": return 2.5 + (factorSeed / 15) + (noise / 2);
          case "psr": return 0.8 + (factorSeed / 20) + (noise / 10);
          case "revenue_growth": return 12 + factorSeed + (noise * 5);
          case "ev_ebitda": return 7 + (factorSeed / 5) + (noise / 2);
          case "pcf": return 9 + (factorSeed / 4) + (noise / 3);
          case "roic": return 14 + (factorSeed / 2) + (noise * 2);
          case "operating_margin": return 18 + (factorSeed / 3) + (noise * 3);
          case "debt_to_equity": return 80 + (factorSeed * 5) + (noise * 10);
          case "operating_profit_growth": return 15 + factorSeed + (noise * 6);
          case "beta": return 1.0 + (factorSeed / 50) + (noise / 100);
          case "market_cap": return (5000 + factorSeed * 1000 + idx * 10) * 1000000; // Mock in millions
          case "foreigner_ownership": return 15 + (factorSeed / 2) + noise;
          default: return 0;
        }
      };

      const factorValue = getFactorValue(index);
      const operator = condition.params.operator || "<";
      const threshold = condition.params.value || 0;

      switch (operator) {
        case "<": return factorValue < threshold;
        case ">": return factorValue > threshold;
        case "<=": return factorValue <= threshold;
        case ">=": return factorValue >= threshold;
        default: return false;
      }
    }

    return false;
  };

  // Main backtest loop
  for (let i = 1; i < prices.length; i++) {
    const currentPrice = prices[i];
    const currentDate = dates[i];

    // Check exit conditions first (if in position)
    if (position === "long") {
      if (evaluateExitConditions(i)) {
        const sellPrice = currentPrice;
        const sellAmount = shares * sellPrice;
        capital += sellAmount;
        const profit = sellAmount - shares * entryPrice;
        const profitPct = ((sellPrice - entryPrice) / entryPrice) * 100;

        trades.push({
          date: currentDate,
          type: "sell",
          price: sellPrice,
          quantity: shares,
          reason: "Exit condition met",
        });

        signals.push({
          date: currentDate,
          type: "exit",
          condition: "Exit condition",
          price: sellPrice,
        });

        shares = 0;
        position = "none";
        entryPrice = 0;
        entryDateIndex = 0;
      }
    }

    // Check entry conditions (if not in position)
    if (position === "none" && evaluateEntryConditions(i)) {
      const positionSize = (capital * strategy.risk.position_size_pct) / 100;
      shares = Math.floor(positionSize / currentPrice);

      if (shares > 0) {
        const buyAmount = shares * currentPrice;
        capital -= buyAmount;
        entryPrice = currentPrice;
        entryDateIndex = i;
        position = "long";

        trades.push({
          date: currentDate,
          type: "buy",
          price: currentPrice,
          quantity: shares,
          reason: "Entry condition met",
        });

        signals.push({
          date: currentDate,
          type: "entry",
          condition: "Entry condition",
          price: currentPrice,
        });
      }
    }

    // Update equity
    const currentEquity = capital + shares * currentPrice;
    equity.push(currentEquity);
    peakEquity = Math.max(peakEquity, currentEquity);
  }

  // Close final position
  if (position === "long" && prices.length > 0) {
    const finalPrice = prices[prices.length - 1];
    capital += shares * finalPrice;
    trades.push({
      date: dates[dates.length - 1],
      type: "sell",
      price: finalPrice,
      quantity: shares,
      reason: "End of period",
    });
  }

  // Calculate metrics
  const finalEquity = equity[equity.length - 1] || initialCapital;
  const totalReturn = ((finalEquity - initialCapital) / initialCapital) * 100;
  const days = dates.length;
  const cagr =
    days > 0
      ? (Math.pow(finalEquity / initialCapital, 365 / days) - 1) * 100
      : 0;
  const buyAndHoldReturn =
    ((prices[prices.length - 1] - prices[0]) / prices[0]) * 100;

  // Calculate max drawdown
  let maxDrawdown = 0;
  for (let i = 0; i < equity.length; i++) {
    const peak = Math.max(...equity.slice(0, i + 1));
    const drawdown = ((peak - equity[i]) / peak) * 100;
    maxDrawdown = Math.max(maxDrawdown, drawdown);
  }

  // Calculate win rate
  let wins = 0;
  let totalTrades = 0;
  for (let i = 0; i < trades.length - 1; i += 2) {
    if (i + 1 < trades.length) {
      totalTrades++;
      const buyPrice = trades[i].price;
      const sellPrice = trades[i + 1].price;
      if (sellPrice > buyPrice) wins++;
    }
  }
  const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;

  // Calculate profit factor
  let totalProfit = 0;
  let totalLoss = 0;
  for (let i = 0; i < trades.length - 1; i += 2) {
    if (i + 1 < trades.length) {
      const profit = trades[i + 1].price - trades[i].price;
      if (profit > 0) totalProfit += profit;
      else totalLoss += Math.abs(profit);
    }
  }
  const profitFactor = totalLoss > 0 ? totalProfit / totalLoss : 0;

  // Calculate Sharpe and Sortino
  const returns = equity
    .slice(1)
    .map((val, i) => (val - equity[i]) / equity[i]);
  const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
  const stdDev = Math.sqrt(
    returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) /
      returns.length
  );
  const sharpe = stdDev > 0 ? (avgReturn / stdDev) * Math.sqrt(252) : 0;

  const negativeReturns = returns.filter((r) => r < 0);
  const downsideStdDev = Math.sqrt(
    negativeReturns.reduce((sum, r) => sum + Math.pow(r, 2), 0) /
      negativeReturns.length
  );
  const sortino =
    downsideStdDev > 0 ? (avgReturn / downsideStdDev) * Math.sqrt(252) : 0;

  // Calculate Kelly %
  const kelly =
    winRate > 0 && profitFactor > 0
      ? ((winRate / 100 - (1 - winRate / 100) / profitFactor) * 100)
      : 0;

  // Calculate monthly/yearly returns
  const monthlyReturns: Record<string, number> = {};
  const yearlyReturns: Record<string, number> = {};
  let lastEquity = initialCapital;
  dates.forEach((date, i) => {
    if (i > 0 && equity[i] > 0) {
      const dateObj = new Date(date);
      const monthKey = `${dateObj.getFullYear()}-${String(
        dateObj.getMonth() + 1
      ).padStart(2, "0")}`;
      const yearKey = String(dateObj.getFullYear());
      const returnPct = ((equity[i] - lastEquity) / lastEquity) * 100;
      monthlyReturns[monthKey] =
        (monthlyReturns[monthKey] || 0) + returnPct;
      yearlyReturns[yearKey] = (yearlyReturns[yearKey] || 0) + returnPct;
      lastEquity = equity[i];
    }
  });

  return {
    strategyId: strategy.id,
    totalReturn,
    cagr,
    buyAndHoldReturn,
    maxDrawdown,
    winRate,
    profitFactor,
    sharpe,
    sortino,
    kelly,
    trades: Math.floor(trades.length / 2),
    finalEquity,
    initialCapital,
    equity,
    dates,
    tradesList: trades,
    monthlyReturns,
    yearlyReturns,
    signals,
  };
}

