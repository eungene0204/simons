import { totalContributed } from '@/lib/virtual-account/contributions';
import { NextRequest, NextResponse } from 'next/server'
import { getCurrentUser } from '@/lib/get-user'
import { cache } from '@/lib/cache'
import { prisma } from '@/lib/prisma'
import { getAccountSettlementValues, moneyToNumber, resolveAccountTotalValue } from '@/lib/server/assetService'
import { fetchLivePriceMap, positionsMarketValue } from '@/lib/server/accountValuation'
import { getRequestRegion } from '@/lib/geo/server'
import { REGION_CURRENCY } from '@/lib/geo/region'

export async function GET(request: NextRequest) {
  try {
    const user = await getCurrentUser()

    if (!user) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      )
    }

    // Check cache first
    // 수익률은 이 화면 지역의 통화 계좌만 합산한다(원화·달러를 환율 없이 섞지 않는다).
    const currency = REGION_CURRENCY[getRequestRegion()]
    const cacheKey = `user:info:${user.id}:${currency}`
    const cached = cache.get(cacheKey)
    if (cached) {
      console.log('Returning cached user info')
      return NextResponse.json(cached)
    }

    const [watchlistCount, accounts, totalUsers] = await Promise.all([
      prisma.watchlistSymbol.count({
        where: { userId: user.id },
      }),
      prisma.virtualAccount.findMany({
        where: { userId: user.id, currency },
        include: {
          VirtualPosition: {
            select: {
              symbol: true,
              quantity: true,
              avgPrice: true,
              currentPrice: true,
            },
          },
        },
      }),
      prisma.user.count(),
    ])

    const [settlementValues, priceMap] = await Promise.all([
      getAccountSettlementValues(prisma, accounts.map((account) => account.id)),
      fetchLivePriceMap(accounts.flatMap((account) => account.VirtualPosition.map((p) => p.symbol))),
    ])

    const accountCount = accounts.length
    // 수익률의 분모는 총 납입액이다(정액 적립식 — 납입이 없는 계좌는 초기 자본과 같다).
    const totalInitialCash = accounts.reduce(
      (sum, account) => sum + totalContributed(account.initialCash, account.contributedCash), 0)
    const totalValue = accounts.reduce((sum, account) => {
      const liveValue =
        moneyToNumber(account.currentCash) + positionsMarketValue(account.VirtualPosition, priceMap)
      return sum + resolveAccountTotalValue(account, liveValue, settlementValues)
    }, 0)

    const currentReturnRate =
      totalInitialCash > 0 ? ((totalValue - totalInitialCash) / totalInitialCash) * 100 : 0

    const userInfo = {
      watchlistCount,
      accountCount,
      currentReturnRate,
      returnRateRank: null,
      totalUsers,
    }

    // Cache for 30 seconds
    cache.set(cacheKey, userInfo, 30)
    return NextResponse.json(userInfo)
  } catch (error) {
    console.error('User info API error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch user info' },
      { status: 500 }
    )
  }
}
