// Stock API Factory
import { AlphaVantageProvider } from './alpha-vantage'
import type { StockAPIProvider } from './base'

export type APIProvider = 'alpha-vantage' | 'yahoo' | 'iex'

let currentProvider: StockAPIProvider | null = null

export function getStockAPIProvider(): StockAPIProvider {
  if (currentProvider) {
    return currentProvider
  }

  const provider = (process.env.STOCK_API_PROVIDER || 'alpha-vantage') as APIProvider

  switch (provider) {
    case 'alpha-vantage':
      currentProvider = new AlphaVantageProvider()
      break
    // Future providers can be added here
    // case 'yahoo':
    //   currentProvider = new YahooProvider()
    //   break
    // case 'iex':
    //   currentProvider = new IEXProvider()
    //   break
    default:
      currentProvider = new AlphaVantageProvider()
  }

  return currentProvider
}

// Reset provider (useful for testing or switching providers)
export function resetProvider() {
  currentProvider = null
}

