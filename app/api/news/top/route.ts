import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = request.nextUrl
    const params = new URLSearchParams()
    if (searchParams.get('page')) params.set('page', searchParams.get('page')!)
    if (searchParams.get('page_size')) params.set('page_size', searchParams.get('page_size')!)
    if (searchParams.get('scope')) params.set('scope', searchParams.get('scope')!)
    if (searchParams.get('as_of')) params.set('as_of', searchParams.get('as_of')!)

    const query = params.toString()
    const url = `${BACKEND}/news/top${query ? `?${query}` : ''}`

    const res = await fetch(url, { next: { revalidate: 60 } })

    if (!res.ok) {
      // Backend unavailable — return structured empty response
      return NextResponse.json({ items: [], total: 0, page: 1, page_size: 20 })
    }

    const data = await res.json()
    return NextResponse.json(data)
  } catch {
    // Backend not running — graceful degradation
    return NextResponse.json({ items: [], total: 0, page: 1, page_size: 20 })
  }
}
