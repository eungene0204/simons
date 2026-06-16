import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'
import {
  coachCacheKey,
  getCachedCoachStream,
  getCoachStreamInFlight,
  rememberCoachStream,
  setCoachStreamInFlight,
} from '../cache'

const STREAM_HEADERS = {
  'Content-Type': 'text/event-stream',
  'Cache-Control': 'no-cache, no-transform',
  'Connection': 'keep-alive',
  'X-Accel-Buffering': 'no',
}

function streamFromText(text: string) {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text))
      controller.close()
    },
  })
}

export async function POST(req: NextRequest) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON' }, { status: 400 })
  }

  try {
    const key = await coachCacheKey(body)
    const cached = getCachedCoachStream(key)
    if (cached) {
      return new Response(streamFromText(cached), {
        status: 200,
        headers: STREAM_HEADERS,
      })
    }

    const pending = getCoachStreamInFlight(key)
    if (pending) {
      const text = await pending
      return new Response(streamFromText(text), {
        status: 200,
        headers: STREAM_HEADERS,
      })
    }

    const res = await fetchBackend('/strategy/coach/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      timeoutMs: 180_000,
    })

    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      return NextResponse.json(err, { status: res.status })
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    const chunks: Uint8Array[] = []

    let resolveCaptured: (value: string) => void = () => {}
    let rejectCaptured: (reason?: unknown) => void = () => {}
    const captured = new Promise<string>((resolve, reject) => {
      resolveCaptured = resolve
      rejectCaptured = reject
    })
    setCoachStreamInFlight(key, captured)

    const stream = new ReadableStream({
      async pull(controller) {
        try {
          const { done, value } = await reader.read()
          if (done) {
            const text = chunks.map((chunk) => decoder.decode(chunk, { stream: true })).join('') + decoder.decode()
            rememberCoachStream(key, text)
            resolveCaptured(text)
            controller.close()
            return
          }

          chunks.push(value)
          controller.enqueue(value)
        } catch (error) {
          rejectCaptured(error)
          controller.error(error)
        }
      },
    })

    return new Response(stream, {
      status: 200,
      headers: STREAM_HEADERS,
    })
  } catch (e: any) {
    return NextResponse.json(
      { detail: `Coach stream proxy error: ${e.message}` },
      { status: 500 }
    )
  }
}
