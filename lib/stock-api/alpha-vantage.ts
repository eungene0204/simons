// Alpha Vantage API Provider
import axios from 'axios'
import type { StockAPIProvider } from './base'
import { StockAPIError, withRetry } from './base'
import type {
  StockQuote,
  StockHistoricalData,
  StockSearchResult,
  StockOverview,
  StockNews,
  StockTimeSeries,
} from '@/types/stock'

const ALPHA_VANTAGE_BASE_URL = 'https://www.alphavantage.co/query'
const API_KEY = process.env.ALPHA_VANTAGE_API_KEY

export class AlphaVantageProvider implements StockAPIProvider {
  private async makeRequest(params: Record<string, string>) {
    if (!API_KEY) {
      throw new StockAPIError('Alpha Vantage API key is not configured', 'NO_API_KEY')
    }

    return withRetry(async () => {
      const response = await axios.get(ALPHA_VANTAGE_BASE_URL, {
        params: {
          ...params,
          apikey: API_KEY,
        },
        timeout: 10000,
      })

      if (response.data['Error Message']) {
        throw new StockAPIError(
          response.data['Error Message'],
          'API_ERROR',
          400
        )
      }

      if (response.data['Note']) {
        throw new StockAPIError(
          'API rate limit exceeded. Please try again later.',
          'RATE_LIMIT',
          429
        )
      }

      return response.data
    })
  }

  async getQuote(symbol: string): Promise<StockQuote | null> {
    try {
      const data = await this.makeRequest({
        function: 'GLOBAL_QUOTE',
        symbol: symbol.toUpperCase(),
      })

      const quote = data['Global Quote']
      if (!quote || Object.keys(quote).length === 0) {
        return null
      }

      const price = parseFloat(quote['05. price'])
      const previousClose = parseFloat(quote['08. previous close'])
      const change = price - previousClose
      const changePercent = (change / previousClose) * 100

      return {
        symbol: quote['01. symbol'],
        name: quote['01. symbol'], // Alpha Vantage doesn't provide name in quote
        price,
        change,
        changePercent,
        volume: parseInt(quote['06. volume']) || 0,
        high: parseFloat(quote['03. high']),
        low: parseFloat(quote['04. low']),
        open: parseFloat(quote['02. open']),
        previousClose,
        timestamp: new Date(),
      }
    } catch (error) {
      console.error('Alpha Vantage getQuote error:', error)
      throw error
    }
  }

  async searchStock(query: string): Promise<StockSearchResult[]> {
    try {
      const data = await this.makeRequest({
        function: 'SYMBOL_SEARCH',
        keywords: query,
      })

      const matches = data.bestMatches || []
      return matches.map((match: any) => ({
        symbol: match['1. symbol'],
        name: match['2. name'],
        type: match['3. type'],
        region: match['4. region'],
        currency: match['8. currency'],
        matchScore: parseFloat(match['9. matchScore']),
      }))
    } catch (error) {
      console.error('Alpha Vantage searchStock error:', error)
      return []
    }
  }

  async getHistoricalData(
    symbol: string,
    interval: string = 'daily',
    period: string = 'compact'
  ): Promise<StockHistoricalData[]> {
    try {
      const functionMap: Record<string, string> = {
        daily: 'TIME_SERIES_DAILY',
        weekly: 'TIME_SERIES_WEEKLY',
        monthly: 'TIME_SERIES_MONTHLY',
      }

      const functionName = functionMap[interval] || 'TIME_SERIES_DAILY'
      const data = await this.makeRequest({
        function: functionName,
        symbol: symbol.toUpperCase(),
        outputsize: period === 'full' ? 'full' : 'compact',
      })

      const timeSeriesKey = data[`Time Series (Daily)`] || 
                            data[`Weekly Time Series`] || 
                            data[`Monthly Time Series`] || {}

      const historicalData: StockHistoricalData[] = []
      for (const [date, values] of Object.entries(timeSeriesKey as Record<string, any>)) {
        historicalData.push({
          symbol: symbol.toUpperCase(),
          date,
          open: parseFloat(values['1. open']),
          high: parseFloat(values['2. high']),
          low: parseFloat(values['3. low']),
          close: parseFloat(values['4. close']),
          volume: parseInt(values['5. volume']),
          adjustedClose: parseFloat(values['5. adjusted close']),
        })
      }

      return historicalData.sort((a, b) => a.date.localeCompare(b.date))
    } catch (error) {
      console.error('Alpha Vantage getHistoricalData error:', error)
      return []
    }
  }

  async getOverview(symbol: string): Promise<StockOverview | null> {
    try {
      const data = await this.makeRequest({
        function: 'OVERVIEW',
        symbol: symbol.toUpperCase(),
      })

      if (!data.Symbol) {
        return null
      }

      return {
        symbol: data.Symbol,
        name: data.Name,
        description: data.Description,
        sector: data.Sector,
        industry: data.Industry,
        marketCap: data.MarketCapitalization ? parseInt(data.MarketCapitalization) : undefined,
        peRatio: data.PERatio ? parseFloat(data.PERatio) : undefined,
        pbr: data.PriceToBookRatio ? parseFloat(data.PriceToBookRatio) : undefined,
        beta: data.Beta ? parseFloat(data.Beta) : undefined,
        eps: data.EPS ? parseFloat(data.EPS) : undefined,
      }
    } catch (error) {
      console.error('Alpha Vantage getOverview error:', error)
      return null
    }
  }

  async getNews(symbol: string, limit: number = 10): Promise<StockNews[]> {
    // Alpha Vantage doesn't have a news endpoint in free tier
    // This would need to be implemented with a different provider
    return []
  }

  async getTimeSeries(
    symbol: string,
    interval: StockTimeSeries['interval']
  ): Promise<StockTimeSeries | null> {
    try {
      const intervalMap: Record<string, string> = {
        '1min': '1',
        '5min': '5',
        '15min': '15',
        '30min': '30',
        '60min': '60',
        daily: 'daily',
        weekly: 'weekly',
        monthly: 'monthly',
      }

      const avInterval = intervalMap[interval] || 'daily'
      
      if (avInterval === 'daily' || avInterval === 'weekly' || avInterval === 'monthly') {
        const data = await this.getHistoricalData(symbol, avInterval, 'compact')
        return {
          symbol: symbol.toUpperCase(),
          interval,
          data,
        }
      }

      // For intraday intervals, use TIME_SERIES_INTRADAY
      const functionName = 'TIME_SERIES_INTRADAY'
      const apiData = await this.makeRequest({
        function: functionName,
        symbol: symbol.toUpperCase(),
        interval: avInterval,
        outputsize: 'compact',
      })

      const timeSeriesKey = apiData[`Time Series (${avInterval}min)`] || {}
      const historicalData: StockHistoricalData[] = []

      for (const [dateTime, values] of Object.entries(timeSeriesKey as Record<string, any>)) {
        historicalData.push({
          symbol: symbol.toUpperCase(),
          date: dateTime,
          open: parseFloat(values['1. open']),
          high: parseFloat(values['2. high']),
          low: parseFloat(values['3. low']),
          close: parseFloat(values['4. close']),
          volume: parseInt(values['5. volume']),
        })
      }

      return {
        symbol: symbol.toUpperCase(),
        interval,
        data: historicalData.sort((a, b) => a.date.localeCompare(b.date)),
      }
    } catch (error) {
      console.error('Alpha Vantage getTimeSeries error:', error)
      return null
    }
  }
}


