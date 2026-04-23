import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

const SEED_IMPACT: Record<string, object> = {
  '005930': {
    symbol: '005930',
    risk_alert_level: 'low',
    latest_alpha: {
      value: 0.64,
      direction: 'long',
      confidence: 0.78,
      event_type: 'earnings_beat',
      risk_alert: 'none',
      article_title: '삼성전자, 2분기 영업이익 10조 돌파…반도체 업황 회복 본격화',
    },
    _source: 'seed',
  },
}

export async function GET(
  request: NextRequest,
  { params }: { params: { symbol: string } }
) {
  try {
    const { searchParams } = request.nextUrl
    const query = searchParams.get('as_of') ? `?as_of=${searchParams.get('as_of')}` : ''
    const res = await fetch(`${BACKEND}/news/impact/${params.symbol}${query}`, { next: { revalidate: 60 } })

    if (!res.ok) {
      return NextResponse.json(
        SEED_IMPACT[params.symbol] ?? { symbol: params.symbol, risk_alert_level: 'none', signals: [] }
      )
    }

    const data = await res.json()
    if (!data.latest_alpha && SEED_IMPACT[params.symbol]) {
      return NextResponse.json(SEED_IMPACT[params.symbol])
    }
    return NextResponse.json(data)
  } catch {
    return NextResponse.json(
      SEED_IMPACT[params.symbol] ?? { symbol: params.symbol, risk_alert_level: 'none', signals: [] }
    )
  }
}
