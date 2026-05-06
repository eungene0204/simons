import { NextRequest, NextResponse } from 'next/server'
import { getStockAPIProvider } from '@/lib/stock-api'
import { cache, cacheKeys, cacheTTL } from '@/lib/cache'
import { StockAPIError } from '@/lib/stock-api/base'

export const dynamic = "force-dynamic";

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
    const cacheKey = cacheKeys.overview(symbol)
    const cached = cache.get(cacheKey)
    if (cached) {
      return NextResponse.json(cached)
    }

    // Fetch from API
    const provider = getStockAPIProvider()
    const overview = await provider.getOverview(symbol)

    if (!overview) {
      return NextResponse.json(
        { error: 'Stock overview not found' },
        { status: 404 }
      )
    }

    // Cache the result
    cache.set(cacheKey, overview, cacheTTL.overview)

    return NextResponse.json(overview)
  } catch (error) {
    console.error('Stock overview API error:', error)

    if (error instanceof StockAPIError) {
      return NextResponse.json(
        { error: error.message, code: error.code },
        { status: error.statusCode || 500 }
      )
    }

    return NextResponse.json(
      { error: 'Failed to fetch stock overview' },
      { status: 500 }
    )
  }
}

