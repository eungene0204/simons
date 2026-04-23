import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'

export async function POST(req: NextRequest) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON' }, { status: 400 })
  }

  try {
    const res = await fetchBackend('/strategy/coach/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      timeoutMs: 120_000,
    })

    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      return NextResponse.json(err, { status: res.status })
    }

    return new Response(res.body, {
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    })
  } catch (e: any) {
    return NextResponse.json(
      { detail: `Coach stream proxy error: ${e.message}` },
      { status: 500 }
    )
  }
}
