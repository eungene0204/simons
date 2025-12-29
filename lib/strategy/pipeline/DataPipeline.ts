import { getStockAPIProvider } from "@/lib/stock-api";
import { StockHistoricalData } from "@/types/stock";
import { StrategyDSL } from "@/types/strategy";
import { FeatureCalculators } from "./FeatureCalculators";
import { DataCache } from "./DataCache";

export interface StrategyDataset {
  symbol: string;
  dates: string[];
  prices: {
    open: number[];
    high: number[];
    low: number[];
    close: number[];
    volume: number[];
  };
  features: Record<string, number[] | any>;
}

export class DataPipeline {
  private apiProvider = getStockAPIProvider();
  private cache = new DataCache();

  async getDatasetForStrategy(
    strategy: StrategyDSL,
    period: string = "full"
  ): Promise<StrategyDataset[]> {
    // 1. Identify required symbols (From Step 1 Universe - mock for now since Step 1 state is complex)
    // For now, we'll use a placeholder symbol or the one defined in the strategy if applicable
    const symbols = ["AAPL"]; // Mock symbol

    const datasets: StrategyDataset[] = [];

    for (const symbol of symbols) {
      // 2. Check Cache
      const cacheKey = `dataset_${symbol}_${period}`;
      const cached = await this.cache.get(cacheKey);
      if (cached) {
        datasets.push(cached);
        continue;
      }

      // 3. Ingest: Fetch Raw Data
      const rawData = await this.apiProvider.getHistoricalData(symbol, "daily", period);
      if (!rawData || rawData.length === 0) continue;

      // 4. Pre-process: Sort and validate
      const sortedData = rawData.sort((a, b) => a.date.localeCompare(b.date));
      
      const dates = sortedData.map(d => d.date);
      const opens = sortedData.map(d => d.open);
      const highs = sortedData.map(d => d.high);
      const lows = sortedData.map(d => d.low);
      const closes = sortedData.map(d => d.close);
      const volumes = sortedData.map(d => d.volume);

      // 5. Transform: Feature Engine
      const features: Record<string, number[] | any> = {};

      // Extract required features from StrategyDSL entry/exit conditions
      const allConditions = [
        ...strategy.entry.conditions,
        ...strategy.exit.conditions
      ];

      for (const condition of allConditions) {
        if (condition.type === "indicator") {
          this.calculateFeature(condition, closes, features);
        }
      }

      const dataset: StrategyDataset = {
        symbol,
        dates,
        prices: {
          open: opens,
          high: highs,
          low: lows,
          close: closes,
          volume: volumes
        },
        features
      };

      // 6. Cache Result
      await this.cache.set(cacheKey, dataset);
      datasets.push(dataset);
    }

    return datasets;
  }

  private calculateFeature(condition: any, prices: number[], features: Record<string, any>) {
    const { id, params } = condition;
    
    switch (id) {
      case "ma_crossover":
        const short = params.shortMA || 5;
        const long = params.longMA || 20;
        features[`sma_${short}`] = FeatureCalculators.calculateSMA(prices, short);
        features[`sma_${long}`] = FeatureCalculators.calculateSMA(prices, long);
        break;
      case "rsi":
        const period = params.period || 14;
        features[`rsi_${period}`] = FeatureCalculators.calculateRSI(prices, period);
        break;
      case "macd":
        const fast = params.fastPeriod || 12;
        const slow = params.slowPeriod || 26;
        const signal = params.signalPeriod || 9;
        features[`macd_${fast}_${slow}_${signal}`] = FeatureCalculators.calculateMACD(prices, fast, slow, signal);
        break;
      case "bollinger_bands":
        const bPeriod = params.period || 20;
        const stdDev = params.stdDev || 2;
        features[`bollinger_${bPeriod}_${stdDev}`] = FeatureCalculators.calculateBollingerBands(prices, bPeriod, stdDev);
        break;
      // Add more indicators as needed
    }
  }
}
