import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'
import {
  coachCacheKey,
  getCachedCoachJson,
  getCoachJsonInFlight,
  rememberCoachJson,
  setCoachJsonInFlight,
} from './cache'

type CoachProxyBody = {
  action?: 'create_session' | 'follow_up'
  session_id?: string
}

// Modal serverless GPU cold-start 실측(2026-06): 콜드 컨테이너로의 첫 POST는 body가 유실되어
// 백엔드가 (1) 본문 없는 GET으로 컨테이너를 깨우고(_ollama_ensure_warm, 예산 200s) → (2) 그
// 다음 POST를 재시도(_OLLAMA_RETRY_BUDGET_S=320s)한다. 콜드 추론(로드~60s+첫추론~70s)까지
// 합치면 한 요청 worst-case ~520s. 프록시가 백엔드보다 먼저 끊지 않도록 넉넉히 크게 둔다.
const COACH_TIMEOUT_MS = 560_000

async function forwardLegacyCoach(body: unknown) {
  const res = await fetchBackend('/strategy/coach', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
    timeoutMs: COACH_TIMEOUT_MS,
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw Object.assign(new Error(err.detail ?? res.statusText), { status: res.status })
  }

  return await res.json()
}

async function forwardCoachSession(body: unknown) {
  const payload = body as CoachProxyBody
  const isFollowUp = payload?.action === 'follow_up'
  const { action: _action, session_id: sessionId, ...rest } = (payload ?? {}) as Record<string, unknown>
  const backendPath = isFollowUp ? '/strategy/coach/sessions/follow-up' : '/strategy/coach/sessions'
  const backendBody = isFollowUp ? { ...rest, session_id: sessionId } : rest

  const res = await fetchBackend(backendPath, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(backendBody),
    cache: 'no-store',
    timeoutMs: COACH_TIMEOUT_MS,
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    if (!isFollowUp && (res.status === 404 || res.status === 405)) {
      return NextResponse.json(await forwardLegacyCoach(rest))
    }
    throw Object.assign(new Error(err.detail ?? res.statusText), { status: res.status })
  }

  const data = await res.json()
  const response = NextResponse.json(data)
  const backendSessionId = res.headers.get('x-coach-session-id')
  if (backendSessionId) {
    response.headers.set('X-Coach-Session-Id', backendSessionId)
  }
  return response
}

export async function POST(req: NextRequest) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON' }, { status: 400 })
  }

  try {
    const action = (body as CoachProxyBody)?.action
    if (action === 'create_session' || action === 'follow_up') {
      return await forwardCoachSession(body)
    }

    const key = await coachCacheKey(body)
    const cached = getCachedCoachJson(key)
    if (cached) {
      return NextResponse.json({ ...cached, cached: true })
    }

    let pending = getCoachJsonInFlight(key)
    if (!pending) {
      pending = setCoachJsonInFlight(key, (async () => {
        const data = await forwardLegacyCoach(body)
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
