// @ts-nocheck
// Simple in-memory cache for stock data
// In production, consider using Redis or similar

interface CacheEntry<T> {
  data: T
  expiresAt: number
}

class Cache {
  private cache: Map<string, CacheEntry<any>> = new Map()

  set<T>(key: string, data: T, ttlSeconds: number = 300): void {
    const expiresAt = Date.now() + ttlSeconds * 1000
    this.cache.set(key, { data, expiresAt })
  }

  get<T>(key: string): T | null {
    const entry = this.cache.get(key)

    if (!entry) {
      return null
    }

    if (Date.now() > entry.expiresAt) {
      this.cache.delete(key)
      return null
    }

    return entry.data as T
  }

  has(key: string): boolean {
    const entry = this.cache.get(key)
    if (!entry) return false

    if (Date.now() > entry.expiresAt) {
      this.cache.delete(key)
      return false
    }

    return true
  }

  delete(key: string): void {
    this.cache.delete(key)
  }

  clear(): void {
    this.cache.clear()
  }

  // Clean expired entries
  cleanup(): void {
    const now = Date.now()
    for (const [key, entry] of this.cache.entries()) {
      if (now > entry.expiresAt) {
        this.cache.delete(key)
      }
    }
  }
}

// Singleton instance
export const cache = new Cache()

// Cache key generators
export const cacheKeys = {
  quote: (symbol: string) => `quote:${symbol.toUpperCase()}`,
  search: (query: string) => `search:${query.toLowerCase()}`,
  historical: (symbol: string, interval: string, period: string) =>
    `historical:${symbol.toUpperCase()}:${interval}:${period}`,
  overview: (symbol: string) => `overview:${symbol.toUpperCase()}`,
  news: (symbol: string, limit: number) => `news:${symbol.toUpperCase()}:${limit}`,
  timeSeries: (symbol: string, interval: string) =>
    `timeseries:${symbol.toUpperCase()}:${interval}`,
}

// TTL configurations (in seconds)
export const cacheTTL = {
  quote: 60, // 1 minute for real-time quotes
  search: 3600, // 1 hour for search results
  historical: 300, // 5 minutes for historical data
  overview: 3600, // 1 hour for overview data
  news: 1800, // 30 minutes for news
  timeSeries: 60, // 1 minute for time series
}

// Periodically cleanup expired entries (every 5 minutes)
if (typeof setInterval !== 'undefined') {
  setInterval(() => {
    cache.cleanup()
  }, 5 * 60 * 1000)
}


