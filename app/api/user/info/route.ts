import { NextRequest, NextResponse } from 'next/server'
import { getCurrentUser } from '@/lib/get-user'
import { cache } from '@/lib/cache'

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

    // Generate mock user info data
    // In a real application, this would come from the database
    const userInfo = {
      watchlistCount: Math.floor(Math.random() * 50) + 10, // 10-60개
      accountCount: Math.floor(Math.random() * 5) + 1, // 1-6개
      currentReturnRate: (Math.random() * 20 - 10).toFixed(2), // -10% ~ +10%
      returnRateRank: Math.floor(Math.random() * 1000) + 1, // 1-1000위
      totalUsers: 10000, // 전체 사용자 수
    }

    // Convert return rate to number
    userInfo.currentReturnRate = parseFloat(userInfo.currentReturnRate as any)

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

