import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = request.nextUrl
    const symbols = searchParams.get('symbols')
    if (!symbols) {
      return NextResponse.json({ error: 'symbols required' }, { status: 400 })
    }

    const query = new URLSearchParams({ symbols })
    const as_of = searchParams.get('as_of')
    if (as_of) query.set('as_of', as_of)

    const res = await fetch(`${BACKEND}/news/risk-alerts?${query}`, { cache: 'no-store' })
    if (!res.ok) {
      return NextResponse.json({ alerts: {}, as_of: new Date().toISOString() })
    }
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ alerts: {}, as_of: new Date().toISOString() })
  }
}
