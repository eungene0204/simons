import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'
import {
  coachCacheKey,
  getCachedCoachJson,
  getCoachJsonInFlight,
  rememberCoachJson,
  setCoachJsonInFlight,
} from './cache'

export async function POST(req: NextRequest) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON' }, { status: 400 })
  }

  try {
    const key = await coachCacheKey(body)
    const cached = getCachedCoachJson(key)
    if (cached) {
      return NextResponse.json({ ...cached, cached: true })
    }

    let pending = getCoachJsonInFlight(key)
    if (!pending) {
      pending = setCoachJsonInFlight(key, (async () => {
        const res = await fetchBackend('/strategy/coach', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          cache: 'no-store',
          timeoutMs: 30_000,
        })

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }))
          throw Object.assign(new Error(err.detail ?? res.statusText), { status: res.status })
        }

        const data = await res.json()
        rememberCoachJson(key, data)
        return data
      })())
    }

    const data = await pending
    return NextResponse.json({ ...data, cached: false })
  } catch (e: any) {
    if (e?.status) {
      return NextResponse.json({ detail: e.message }, { status: e.status })
    }

    return NextResponse.json(
      { detail: `Coach proxy error: ${e.message}` },
      { status: 500 }
    )
  }
}
