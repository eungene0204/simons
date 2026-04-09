import { NextRequest, NextResponse } from 'next/server'
import { cache, cacheKeys, cacheTTL } from '@/lib/cache'
import { fetchStockPriceSnapshots } from '@/lib/server/stock-prices'

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

    const quotes = await fetchStockPriceSnapshots([symbol], {
      subscribe: true,
      mode: 'standard',
    })
    const quote = quotes[symbol]

    if (!quote || quote.price <= 0) {
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

    return NextResponse.json(
      { error: 'Failed to fetch stock quote' },
      { status: 500 }
    )
  }
}
