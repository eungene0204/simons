import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'
const CACHE_TTL_MS = 24 * 60 * 60 * 1000      // 24 hours when articles exist
const CACHE_TTL_EMPTY_MS = 60 * 60 * 1000    // 1 hour retry when no articles found
const FETCH_LOCK_MS = 3 * 60 * 1000       // 3-minute lock to prevent double-fetch

async function fetchArticlesFromBackend(symbol: string, pageSize: number): Promise<object[]> {
  try {
    const res = await fetch(`${BACKEND}/news/symbol/${symbol}?page_size=${pageSize}`, {
      cache: 'no-store',
    })
    if (!res.ok) return []
    const data = await res.json()
    return data.items ?? []
  } catch {
    return []
  }
}

async function triggerIngest(symbol: string): Promise<void> {
  const res = await fetch(`${BACKEND}/news/ingest-and-analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbols: [symbol], max_per_provider: 30 }),
    cache: 'no-store',
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.status.toString())
    throw new Error(`Ingest failed: ${text}`)
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { symbol: string } }
) {
  const { symbol } = params
  const { searchParams } = request.nextUrl
  const forceRefresh = searchParams.get('forceRefresh') === 'true'
  const pageSize = parseInt(searchParams.get('page_size') ?? '20', 10)
  const now = new Date()

  // 1. Check cache — use shorter TTL when no articles were found last time
  const cache = await prisma.newsFetchCache.findUnique({ where: { symbol } })
  const ttl = cache?.articleCount === 0 ? CACHE_TTL_EMPTY_MS : CACHE_TTL_MS
  const isFresh = cache && now.getTime() - cache.fetchedAt.getTime() < ttl

  if (isFresh && !forceRefresh) {
    const articles = await fetchArticlesFromBackend(symbol, pageSize)
    return NextResponse.json({
      articles,
      fetchedAt: cache.fetchedAt.toISOString(),
      cached: true,
      revalidating: false,
    })
  }

  // 2. Single-flight: another request is already fetching
  const isLocked =
    cache?.isFetching === true &&
    cache.fetchingUntil !== null &&
    cache.fetchingUntil > now

  if (isLocked) {
    const articles = await fetchArticlesFromBackend(symbol, pageSize)
    return NextResponse.json({
      articles,
      fetchedAt: cache?.fetchedAt?.toISOString() ?? null,
      cached: false,
      revalidating: true,
    })
  }

  // 3. Acquire fetch lock
  const fetchingUntil = new Date(now.getTime() + FETCH_LOCK_MS)
  await prisma.newsFetchCache.upsert({
    where: { symbol },
    create: {
      symbol,
      fetchedAt: cache?.fetchedAt ?? now,
      articleCount: cache?.articleCount ?? 0,
      isFetching: true,
      fetchingUntil,
    },
    update: { isFetching: true, fetchingUntil },
  })

  // 4. Fetch fresh news and update cache
  try {
    await triggerIngest(symbol)
    const articles = await fetchArticlesFromBackend(symbol, pageSize)
    await prisma.newsFetchCache.update({
      where: { symbol },
      data: {
        fetchedAt: now,
        articleCount: articles.length,
        isFetching: false,
        fetchingUntil: null,
      },
    })
    return NextResponse.json({
      articles,
      fetchedAt: now.toISOString(),
      cached: false,
      revalidating: false,
    })
  } catch {
    // Release lock; return stale articles if available
    await prisma.newsFetchCache
      .update({ where: { symbol }, data: { isFetching: false, fetchingUntil: null } })
      .catch(() => {})

    const articles = await fetchArticlesFromBackend(symbol, pageSize)
    return NextResponse.json({
      articles,
      fetchedAt: cache?.fetchedAt?.toISOString() ?? null,
      cached: false,
      revalidating: false,
      error: 'fetch_failed',
    })
  }
}
