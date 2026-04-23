import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(
  request: NextRequest,
  { params }: { params: { symbol: string } }
) {
  try {
    const { searchParams } = request.nextUrl
    const query = new URLSearchParams()
    if (searchParams.get('signal_type')) query.set('signal_type', searchParams.get('signal_type')!)
    if (searchParams.get('as_of')) query.set('as_of', searchParams.get('as_of')!)
    if (searchParams.get('limit')) query.set('limit', searchParams.get('limit')!)

    const q = query.toString()
    const url = `${BACKEND}/news/signals/${params.symbol}${q ? `?${q}` : ''}`
    const res = await fetch(url, { cache: 'no-store' })

    if (!res.ok) {
      return NextResponse.json({ symbol: params.symbol, signals: [], as_of: new Date().toISOString() })
    }
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ symbol: params.symbol, signals: [], as_of: new Date().toISOString() })
  }
}
