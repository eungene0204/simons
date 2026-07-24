import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'

// 결정적 조건 플로우의 '전략 확정': 누적된 ParsedStrategy를 재해석(LLM 재파싱) 없이
// 그대로 백테스트 요청으로 컴파일한다 — 재파싱이 이미 확정된 조건을 잃는 사고 방지.
export async function POST(req: NextRequest) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON' }, { status: 400 })
  }

  try {
    const res = await fetchBackend('/strategy/compile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      timeoutMs: 30_000,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      return NextResponse.json({ detail: err.detail ?? res.statusText }, { status: res.status })
    }
    return NextResponse.json(await res.json())
  } catch (e: any) {
    return NextResponse.json({ detail: `Strategy compile proxy error: ${e.message}` }, { status: 500 })
  }
}
