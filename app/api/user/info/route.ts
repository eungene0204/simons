import { NextRequest, NextResponse } from 'next/server'
import { getCurrentUser } from '@/lib/get-user'
import { cache } from '@/lib/cache'
import { prisma } from '@/lib/prisma'
import { getAccountSettlementValues, moneyToNumber, resolveAccountTotalValue } from '@/lib/server/assetService'

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
    const cacheKey = `user:info:${user.id}`
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
        where: { userId: user.id },
        include: {
          VirtualPosition: {
            select: {
              quantity: true,
              avgPrice: true,
              currentPrice: true,
            },
          },
        },
      }),
      prisma.user.count(),
    ])

    const settlementValues = await getAccountSettlementValues(prisma, accounts.map((account) => account.id))

    const accountCount = accounts.length
    const totalInitialCash = accounts.reduce((sum, account) => sum + moneyToNumber(account.initialCash), 0)
    const totalValue = accounts.reduce((sum, account) => {
      const positionsValue = account.VirtualPosition.reduce((positionSum, position) => {
        const currentPrice = moneyToNumber(position.currentPrice ?? position.avgPrice)
        return positionSum + position.quantity * currentPrice
      }, 0)

      const liveValue = moneyToNumber(account.currentCash) + positionsValue
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
