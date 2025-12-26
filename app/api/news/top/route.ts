import { NextRequest, NextResponse } from 'next/server'
import { cache } from '@/lib/cache'

export async function GET(request: NextRequest) {
  try {
    // Check cache first
    const cacheKey = 'news:top'
    const cached = cache.get(cacheKey)
    if (cached) {
      console.log('Returning cached news data')
      return NextResponse.json(cached)
    }

    console.log('Generating mock news data...')

    // Generate mock news data
    const mockNews = [
      {
        id: 1,
        title: "코스피, 2650선 돌파하며 상승세 지속... 기관 매수세 확대",
        source: "한국경제",
        publishedAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2 hours ago
        category: "시장동향",
      },
      {
        id: 2,
        title: "미국 연준 금리 동결 결정... 글로벌 시장 안정세 기대",
        source: "조선일보",
        publishedAt: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(), // 5 hours ago
        category: "글로벌",
      },
      {
        id: 3,
        title: "반도체 업종, 3분기 실적 호조에 상승... 삼성전자 5% 급등",
        source: "매일경제",
        publishedAt: new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString(), // 8 hours ago
        category: "기업",
      },
      {
        id: 4,
        title: "원화 강세 지속... 환율 1350원대 하락",
        source: "연합뉴스",
        publishedAt: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(), // 12 hours ago
        category: "환율",
      },
      {
        id: 5,
        title: "바이오 업종, 신약 개발 호재로 상승... 셀트리온 주목",
        source: "동아일보",
        publishedAt: new Date(Date.now() - 15 * 60 * 60 * 1000).toISOString(), // 15 hours ago
        category: "기업",
      },
    ]

    const response = {
      news: mockNews,
    }

    // Cache for 5 minutes
    cache.set(cacheKey, response, 300)
    return NextResponse.json(response)
  } catch (error) {
    console.error('News API error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch news', news: [] },
      { status: 500 }
    )
  }
}

