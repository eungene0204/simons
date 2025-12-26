import { NextRequest, NextResponse } from 'next/server'
import { getStockAPIProvider } from '@/lib/stock-api'
import { cache, cacheKeys, cacheTTL } from '@/lib/cache'
import { StockAPIError } from '@/lib/stock-api/base'

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const symbol = searchParams.get('symbol')
    const interval = searchParams.get('interval') || 'daily'
    const period = searchParams.get('period') || 'compact'

    if (!symbol) {
      return NextResponse.json(
        { error: 'Symbol parameter is required' },
        { status: 400 }
      )
    }

    // Check cache first
    const cacheKey = cacheKeys.historical(symbol, interval, period)
    const cached = cache.get(cacheKey)
    if (cached) {
      return NextResponse.json(cached)
    }

    // Fetch from API
    const provider = getStockAPIProvider()
    const data = await provider.getHistoricalData(symbol, interval, period)

    // Cache the result
    cache.set(cacheKey, data, cacheTTL.historical)

    return NextResponse.json(data)
  } catch (error) {
    console.error('Stock historical data API error:', error)

    if (error instanceof StockAPIError) {
      return NextResponse.json(
        { error: error.message, code: error.code },
        { status: error.statusCode || 500 }
      )
    }

    return NextResponse.json(
      { error: 'Failed to fetch historical data' },
      { status: 500 }
    )
  }
}


