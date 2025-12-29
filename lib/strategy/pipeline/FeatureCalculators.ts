import { StockHistoricalData } from "@/types/stock";

/**
 * Technical Indicator Calculation Functions (Vectorized approach)
 */

export class FeatureCalculators {
  // Simple Moving Average
  static calculateSMA(prices: number[], period: number): number[] {
    const sma: number[] = new Array(prices.length).fill(NaN);
    if (prices.length < period) return sma;

    let sum = 0;
    for (let i = 0; i < period; i++) {
      sum += prices[i];
    }
    sma[period - 1] = sum / period;

    for (let i = period; i < prices.length; i++) {
      sum = sum - prices[i - period] + prices[i];
      sma[i] = sum / period;
    }
    return sma;
  }

  // Exponential Moving Average
  static calculateEMA(prices: number[], period: number): number[] {
    const ema: number[] = new Array(prices.length).fill(NaN);
    if (prices.length === 0) return ema;

    const multiplier = 2 / (period + 1);
    
    // Initial value is SMA or first price
    let sum = 0;
    const startIdx = Math.min(period, prices.length);
    for (let i = 0; i < startIdx; i++) sum += prices[i];
    ema[startIdx - 1] = sum / startIdx;

    for (let i = startIdx; i < prices.length; i++) {
      ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1];
    }
    return ema;
  }

  // Relative Strength Index (RSI)
  static calculateRSI(prices: number[], period: number): number[] {
    const rsi: number[] = new Array(prices.length).fill(NaN);
    if (prices.length <= period) return rsi;

    let avgGain = 0;
    let avgLoss = 0;

    // First period calculation
    for (let i = 1; i <= period; i++) {
      const change = prices[i] - prices[i - 1];
      if (change > 0) avgGain += change;
      else avgLoss += Math.abs(change);
    }

    avgGain /= period;
    avgLoss /= period;
    rsi[period] = 100 - (100 / (1 + avgGain / avgLoss));

    // Subsequent calculations using Wilder's Smoothing
    for (let i = period + 1; i < prices.length; i++) {
      const change = prices[i] - prices[i - 1];
      const gain = change > 0 ? change : 0;
      const loss = change < 0 ? Math.abs(change) : 0;

      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;

      if (avgLoss === 0) rsi[i] = 100;
      else rsi[i] = 100 - (100 / (1 + avgGain / avgLoss));
    }

    return rsi;
  }

  // MACD (Moving Average Convergence Divergence)
  static calculateMACD(
    prices: number[],
    fastPeriod: number = 12,
    slowPeriod: number = 26,
    signalPeriod: number = 9
  ): { macd: number[]; signal: number[]; histogram: number[] } {
    const fastEMA = this.calculateEMA(prices, fastPeriod);
    const slowEMA = this.calculateEMA(prices, slowPeriod);
    
    const macd: number[] = fastEMA.map((f, i) => f - slowEMA[i]);
    const signal = this.calculateEMA(macd.filter(v => !isNaN(v)), signalPeriod);
    
    // Pad signal with NaN to match original length
    const paddedSignal = new Array(macd.length).fill(NaN);
    const offset = macd.findIndex(v => !isNaN(v)) + (signalPeriod - 1);
    for (let i = 0; i < signal.length; i++) {
      if (i + offset < paddedSignal.length) {
        paddedSignal[i + offset] = signal[i];
      }
    }

    const histogram = macd.map((m, i) => m - paddedSignal[i]);

    return { macd, signal: paddedSignal, histogram };
  }

  // Bollinger Bands
  static calculateBollingerBands(
    prices: number[],
    period: number = 20,
    stdDev: number = 2
  ): { upper: number[]; middle: number[]; lower: number[] } {
    const middle = this.calculateSMA(prices, period);
    const upper: number[] = new Array(prices.length).fill(NaN);
    const lower: number[] = new Array(prices.length).fill(NaN);

    for (let i = period - 1; i < prices.length; i++) {
      const slice = prices.slice(i - period + 1, i + 1);
      const mean = middle[i];
      const variance = slice.reduce((sum, p) => sum + Math.pow(p - mean, 2), 0) / period;
      const sd = Math.sqrt(variance);
      upper[i] = mean + stdDev * sd;
      lower[i] = mean - stdDev * sd;
    }

    return { upper, middle, lower };
  }
}
