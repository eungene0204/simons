import { NextRequest, NextResponse } from 'next/server'
import { getStockAPIProvider } from '@/lib/stock-api'
import { cache, cacheKeys, cacheTTL } from '@/lib/cache'
import { StockAPIError } from '@/lib/stock-api/base'

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const symbol = searchParams.get('symbol')

    if (!symbol) {
      return NextResponse.json(
        { error: 'Symbol parameter is required' },
        { status: 400 }
      )
    }

    // Check cache first
    const cacheKey = cacheKeys.quote(symbol)
    const cached = cache.get(cacheKey)
    if (cached) {
      return NextResponse.json(cached)
    }

    // Fetch from API
    const provider = getStockAPIProvider()
    const quote = await provider.getQuote(symbol)

    if (!quote) {
      return NextResponse.json(
        { error: 'Stock not found' },
        { status: 404 }
      )
    }

    // Cache the result
    cache.set(cacheKey, quote, cacheTTL.quote)

    return NextResponse.json(quote)
  } catch (error) {
    console.error('Stock quote API error:', error)

    if (error instanceof StockAPIError) {
      return NextResponse.json(
        { error: error.message, code: error.code },
        { status: error.statusCode || 500 }
      )
    }

    return NextResponse.json(
      { error: 'Failed to fetch stock quote' },
      { status: 500 }
    )
  }
}


