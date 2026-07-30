import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'

// 되돌리기 대상 판정(설계 스펙 § 19). 대화는 무상태라 변경 이력을 요청에 실어 보낸다.
// 판정만 하고 복원은 스냅샷을 들고 있는 클라이언트가 결정론으로 수행한다.
export async function POST(req: NextRequest) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON' }, { status: 400 })
  }

  try {
    const res = await fetchBackend('/strategy/rollback/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      timeoutMs: 60_000,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      return NextResponse.json({ detail: err.detail ?? res.statusText }, { status: res.status })
    }
    return NextResponse.json(await res.json())
  } catch (e: any) {
    return NextResponse.json({ detail: `Rollback resolve proxy error: ${e.message}` }, { status: 500 })
  }
}
