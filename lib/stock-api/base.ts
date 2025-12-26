// Base Stock API Interface
import type {
  StockQuote,
  StockHistoricalData,
  StockSearchResult,
  StockOverview,
  StockNews,
  StockTimeSeries,
  APIError,
} from '@/types/stock'

export interface StockAPIProvider {
  // Get real-time quote
  getQuote(symbol: string): Promise<StockQuote | null>

  // Search for stocks
  searchStock(query: string): Promise<StockSearchResult[]>

  // Get historical data
  getHistoricalData(
    symbol: string,
    interval?: string,
    period?: string
  ): Promise<StockHistoricalData[]>

  // Get stock overview/fundamentals
  getOverview(symbol: string): Promise<StockOverview | null>

  // Get stock news
  getNews(symbol: string, limit?: number): Promise<StockNews[]>

  // Get time series data
  getTimeSeries(
    symbol: string,
    interval: StockTimeSeries['interval']
  ): Promise<StockTimeSeries | null>
}

export class StockAPIError extends Error {
  constructor(
    message: string,
    public code?: string,
    public statusCode?: number
  ) {
    super(message)
    this.name = 'StockAPIError'
  }
}

// Retry configuration
export interface RetryConfig {
  maxRetries: number
  retryDelay: number
  backoffMultiplier: number
}

export const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  retryDelay: 1000, // 1 second
  backoffMultiplier: 2,
}

// Retry helper function
export async function withRetry<T>(
  fn: () => Promise<T>,
  config: RetryConfig = DEFAULT_RETRY_CONFIG
): Promise<T> {
  let lastError: Error

  for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
    try {
      return await fn()
    } catch (error) {
      lastError = error as Error

      if (attempt < config.maxRetries) {
        const delay = config.retryDelay * Math.pow(config.backoffMultiplier, attempt)
        await new Promise((resolve) => setTimeout(resolve, delay))
        continue
      }

      throw lastError
    }
  }

  throw lastError!
}


