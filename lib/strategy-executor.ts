/**
 * Strategy Executor - Executes individual strategies from strategy groups
 */

import { StrategyDefinition } from "./strategy-groups";
import { generateCandleData, getBasePrice } from "./mock-stock-data";

// Technical indicator functions (reuse from backtest-engine)
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

function calculateEMA(prices: number[], period: number): number[] {
  const ema: number[] = [];
  const multiplier = 2 / (period + 1);
  
  for (let i = 0; i < prices.length; i++) {
    if (i === 0) {
      ema.push(prices[i]);
    } else if (i < period - 1) {
      const sum = prices.slice(0, i + 1).reduce((a, b) => a + b, 0);
      ema.push(sum / (i + 1));
    } else {
      ema.push((prices[i] - ema[i - 1]) * multiplier + ema[i - 1]);
    }
  }
  return ema;
}

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
  
  const signal: number[] = [];
  const multiplier = 2 / (signalPeriod + 1);
  
  for (let i = 0; i < macd.length; i++) {
    if (isNaN(macd[i])) {
      signal.push(NaN);
    } else {
      let firstValidIndex = i;
      while (firstValidIndex < macd.length && isNaN(macd[firstValidIndex])) {
        firstValidIndex++;
      }
      
      if (i === firstValidIndex) {
        signal.push(macd[i]);
      } else if (i < firstValidIndex + signalPeriod - 1) {
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

// Calculate ATR (Average True Range)
function calculateATR(
  highs: number[],
  lows: number[],
  closes: number[],
  period: number = 14
): number[] {
  const tr: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    const hl = highs[i] - lows[i];
    const hc = Math.abs(highs[i] - closes[i - 1]);
    const lc = Math.abs(lows[i] - closes[i - 1]);
    tr.push(Math.max(hl, hc, lc));
  }
  
  const atr: number[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period) {
      atr.push(NaN);
    } else {
      const sum = tr.slice(i - period, i).reduce((a, b) => a + b, 0);
      atr.push(sum / period);
    }
  }
  return atr;
}

// Calculate Stochastic Oscillator
function calculateStochastic(
  highs: number[],
  lows: number[],
  closes: number[],
  kPeriod: number = 14,
  dPeriod: number = 3
): { k: number[]; d: number[] } {
  const k: number[] = [];
  
  for (let i = 0; i < closes.length; i++) {
    if (i < kPeriod - 1) {
      k.push(NaN);
    } else {
      const highSlice = highs.slice(i - kPeriod + 1, i + 1);
      const lowSlice = lows.slice(i - kPeriod + 1, i + 1);
      const highestHigh = Math.max(...highSlice);
      const lowestLow = Math.min(...lowSlice);
      
      if (highestHigh === lowestLow) {
        k.push(50);
      } else {
        k.push(((closes[i] - lowestLow) / (highestHigh - lowestLow)) * 100);
      }
    }
  }
  
  const d = calculateMA(k, dPeriod);
  
  return { k, d };
}

// Calculate VWAP (Volume Weighted Average Price)
function calculateVWAP(
  prices: number[],
  volumes: number[],
  period: number = 20
): number[] {
  const vwap: number[] = [];
  
  for (let i = 0; i < prices.length; i++) {
    if (i < period - 1) {
      vwap.push(NaN);
    } else {
      let totalPV = 0;
      let totalVolume = 0;
      for (let j = i - period + 1; j <= i; j++) {
        totalPV += prices[j] * volumes[j];
        totalVolume += volumes[j];
      }
      vwap.push(totalVolume > 0 ? totalPV / totalVolume : NaN);
    }
  }
  
  return vwap;
}

// Calculate Donchian Channels
function calculateDonchian(
  highs: number[],
  lows: number[],
  period: number = 20
): { upper: number[]; lower: number[]; middle: number[] } {
  const upper: number[] = [];
  const lower: number[] = [];
  const middle: number[] = [];
  
  for (let i = 0; i < highs.length; i++) {
    if (i < period - 1) {
      upper.push(NaN);
      lower.push(NaN);
      middle.push(NaN);
    } else {
      const highSlice = highs.slice(i - period + 1, i + 1);
      const lowSlice = lows.slice(i - period + 1, i + 1);
      const highestHigh = Math.max(...highSlice);
      const lowestLow = Math.min(...lowSlice);
      
      upper.push(highestHigh);
      lower.push(lowestLow);
      middle.push((highestHigh + lowestLow) / 2);
    }
  }
  
  return { upper, lower, middle };
}

export interface StrategyExecutionResult {
  trades: Array<{ date: string; type: "buy" | "sell"; price: number }>;
  equity: number[];
  signals: Array<{ date: string; type: "entry" | "exit"; price: number }>;
}

/**
 * Execute a strategy and return trading signals
 */
export function executeStrategy(
  strategy: StrategyDefinition,
  params: Record<string, number>,
  symbol: string,
  days: number = 365,
  providedData?: Array<{
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>
): StrategyExecutionResult {
  const basePrice = getBasePrice(symbol);
  const historicalData = providedData ?? generateCandleData(symbol, basePrice, days);
  const prices = historicalData.map((d) => d.close);
  const highs = historicalData.map((d) => d.high);
  const lows = historicalData.map((d) => d.low);
  const volumes = historicalData.map((d) => d.volume);
  const dates = historicalData.map((d) => d.date);

  const trades: Array<{ date: string; type: "buy" | "sell"; price: number }> = [];
  const signals: Array<{ date: string; type: "entry" | "exit"; price: number }> = [];
  const equity: number[] = [];
  
  let position: "long" | "none" = "none";
  let entryPrice = 0;
  let capital = 10000000; // 1천만원
  let shares = 0;

  // Execute based on strategy ID
  switch (strategy.id) {
    case "sma_crossover": {
      const shortMA = calculateMA(prices, params.shortMA || 10);
      const longMA = calculateMA(prices, params.longMA || 50);
      
      for (let i = 1; i < prices.length; i++) {
        if (isNaN(shortMA[i]) || isNaN(longMA[i]) || 
            isNaN(shortMA[i - 1]) || isNaN(longMA[i - 1])) {
          equity.push(capital + shares * prices[i]);
          continue;
        }
        
        // Golden cross
        if (shortMA[i - 1] <= longMA[i - 1] && shortMA[i] > longMA[i] && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        // Death cross
        else if (shortMA[i - 1] >= longMA[i - 1] && shortMA[i] < longMA[i] && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    case "ema_crossover": {
      const shortEMA = calculateEMA(prices, params.shortEMA || 12);
      const longEMA = calculateEMA(prices, params.longEMA || 26);
      
      for (let i = 1; i < prices.length; i++) {
        if (isNaN(shortEMA[i]) || isNaN(longEMA[i]) || 
            isNaN(shortEMA[i - 1]) || isNaN(longEMA[i - 1])) {
          equity.push(capital + shares * prices[i]);
          continue;
        }
        
        if (shortEMA[i - 1] <= longEMA[i - 1] && shortEMA[i] > longEMA[i] && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        else if (shortEMA[i - 1] >= longEMA[i - 1] && shortEMA[i] < longEMA[i] && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    case "macd_signal": {
      const { macd, signal } = calculateMACD(
        prices,
        params.fastPeriod || 12,
        params.slowPeriod || 26,
        params.signalPeriod || 9
      );
      
      for (let i = 1; i < prices.length; i++) {
        if (isNaN(macd[i]) || isNaN(signal[i]) || 
            isNaN(macd[i - 1]) || isNaN(signal[i - 1])) {
          equity.push(capital + shares * prices[i]);
          continue;
        }
        
        if (macd[i - 1] <= signal[i - 1] && macd[i] > signal[i] && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        else if (macd[i - 1] >= signal[i - 1] && macd[i] < signal[i] && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    case "donchian_breakout": {
      const { upper, lower } = calculateDonchian(highs, lows, params.period || 20);
      
      for (let i = 1; i < prices.length; i++) {
        if (isNaN(upper[i]) || isNaN(lower[i])) {
          equity.push(capital + shares * prices[i]);
          continue;
        }
        
        const direction = params.direction || 0;
        if (direction === 0) {
          // Upward breakout
          if (prices[i - 1] <= upper[i - 1] && prices[i] > upper[i] && position === "none") {
            shares = Math.floor(capital / prices[i]);
            if (shares > 0) {
              capital -= shares * prices[i];
              position = "long";
              entryPrice = prices[i];
              trades.push({ date: dates[i], type: "buy", price: prices[i] });
              signals.push({ date: dates[i], type: "entry", price: prices[i] });
            }
          }
          else if (prices[i] < lower[i] && position === "long") {
            capital += shares * prices[i];
            trades.push({ date: dates[i], type: "sell", price: prices[i] });
            signals.push({ date: dates[i], type: "exit", price: prices[i] });
            shares = 0;
            position = "none";
          }
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    case "n_day_breakout": {
      const period = params.period || 20;
      
      for (let i = period; i < prices.length; i++) {
        const highestHigh = Math.max(...highs.slice(i - period, i));
        const lowestLow = Math.min(...lows.slice(i - period, i));
        
        if (prices[i] > highestHigh && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        else if (prices[i] < lowestLow && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    case "atr_breakout": {
      const atr = calculateATR(highs, lows, prices, params.atrPeriod || 14);
      const multiplier = params.multiplier || 2;
      
      for (let i = 1; i < prices.length; i++) {
        if (isNaN(atr[i])) {
          equity.push(capital + shares * prices[i]);
          continue;
        }
        
        const upperBand = prices[i - 1] + atr[i] * multiplier;
        const lowerBand = prices[i - 1] - atr[i] * multiplier;
        
        if (prices[i] > upperBand && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        else if (prices[i] < lowerBand && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    case "rsi_mean_reversion": {
      const rsi = calculateRSI(prices, params.rsiPeriod || 14);
      const oversold = params.oversold || 30;
      const overbought = params.overbought || 70;
      
      for (let i = 1; i < prices.length; i++) {
        if (isNaN(rsi[i]) || isNaN(rsi[i - 1])) {
          equity.push(capital + shares * prices[i]);
          continue;
        }
        
        if (rsi[i - 1] <= oversold && rsi[i] > oversold && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        else if (rsi[i - 1] >= overbought && rsi[i] < overbought && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    case "bollinger_mean_reversion": {
      const { upper, lower } = calculateBollingerBands(
        prices,
        params.period || 20,
        params.stdDev || 2
      );
      
      for (let i = 1; i < prices.length; i++) {
        if (isNaN(upper[i]) || isNaN(lower[i])) {
          equity.push(capital + shares * prices[i]);
          continue;
        }
        
        if (prices[i - 1] >= lower[i - 1] && prices[i] < lower[i] && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        else if (prices[i - 1] <= upper[i - 1] && prices[i] > upper[i] && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    case "absolute_momentum": {
      const period = params.period || 12;
      
      for (let i = period; i < prices.length; i++) {
        const returnPct = ((prices[i] - prices[i - period]) / prices[i - period]) * 100;
        
        if (returnPct > 0 && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        else if (returnPct < 0 && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    case "fiftytwo_week_high": {
      const period = params.period || 252;
      const threshold = params.threshold || 2;
      
      for (let i = period; i < prices.length; i++) {
        const highestHigh = Math.max(...highs.slice(i - period, i));
        const distanceFromHigh = ((prices[i] - highestHigh) / highestHigh) * 100;
        
        if (distanceFromHigh >= -threshold && distanceFromHigh <= threshold && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        else if (distanceFromHigh < -threshold * 2 && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    case "vwap_mean_reversion": {
      const vwap = calculateVWAP(prices, volumes, 20);
      const deviation = params.deviation || 2;
      
      for (let i = 1; i < prices.length; i++) {
        if (isNaN(vwap[i])) {
          equity.push(capital + shares * prices[i]);
          continue;
        }
        
        const deviationPct = ((prices[i] - vwap[i]) / vwap[i]) * 100;
        
        if (deviationPct < -deviation && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        else if (deviationPct > deviation && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    case "stochastic_reversal": {
      const { k, d } = calculateStochastic(
        highs,
        lows,
        prices,
        params.kPeriod || 14,
        params.dPeriod || 3
      );
      const oversold = params.oversold || 20;
      const overbought = params.overbought || 80;
      
      for (let i = 1; i < prices.length; i++) {
        if (isNaN(k[i]) || isNaN(d[i])) {
          equity.push(capital + shares * prices[i]);
          continue;
        }
        
        if (k[i] < oversold && d[i] < oversold && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        else if (k[i] > overbought && d[i] > overbought && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
      break;
    }
    
    default:
      // Default: simple momentum strategy
      for (let i = 10; i < prices.length; i++) {
        const momentum = ((prices[i] - prices[i - 10]) / prices[i - 10]) * 100;
        
        if (momentum > 5 && position === "none") {
          shares = Math.floor(capital / prices[i]);
          if (shares > 0) {
            capital -= shares * prices[i];
            position = "long";
            entryPrice = prices[i];
            trades.push({ date: dates[i], type: "buy", price: prices[i] });
            signals.push({ date: dates[i], type: "entry", price: prices[i] });
          }
        }
        else if (momentum < -5 && position === "long") {
          capital += shares * prices[i];
          trades.push({ date: dates[i], type: "sell", price: prices[i] });
          signals.push({ date: dates[i], type: "exit", price: prices[i] });
          shares = 0;
          position = "none";
        }
        
        equity.push(capital + shares * prices[i]);
      }
  }

  // Close final position
  if (position === "long" && prices.length > 0) {
    capital += shares * prices[prices.length - 1];
    trades.push({
      date: dates[dates.length - 1],
      type: "sell",
      price: prices[prices.length - 1],
    });
  }

  return { trades, equity, signals };
}
