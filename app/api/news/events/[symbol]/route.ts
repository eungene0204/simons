import { NextRequest, NextResponse } from 'next/server'
import { backendPathSegment } from '@/lib/server/backend'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(
  request: NextRequest,
  { params }: { params: { symbol: string } }
) {
  try {
    const { searchParams } = request.nextUrl
    const query = new URLSearchParams()
    if (searchParams.get('limit')) query.set('limit', searchParams.get('limit')!)
    if (searchParams.get('as_of')) query.set('as_of', searchParams.get('as_of')!)

    const q = query.toString()
    const symbolSegment = backendPathSegment(params.symbol)
    if (!symbolSegment) return NextResponse.json({ error: '잘못된 요청입니다.' }, { status: 400 })
    const url = `${BACKEND}/news/events/${symbolSegment}${q ? `?${q}` : ''}`
    const res = await fetch(url, { next: { revalidate: 60 } })

    if (!res.ok) {
      return NextResponse.json({ symbol: params.symbol, events: [], total: 0 })
    }
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ symbol: params.symbol, events: [], total: 0 })
  }
}
