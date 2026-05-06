import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(request: NextRequest) {
  const url = request.nextUrl.searchParams.get('url')
  if (!url) return NextResponse.json({ body: null })

  try {
    const res = await fetch(
      `${BACKEND}/news/fetch-body?url=${encodeURIComponent(url)}`,
      { cache: 'no-store' }
    )
    if (!res.ok) return NextResponse.json({ body: null })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ body: null })
  }
}
