import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'

// 사용자 입력의 intent(STRATEGY_ADVICE / STOCK_ANALYSIS / GENERAL_INVESTMENT / UNKNOWN)를 분류한다.
export async function POST(req: NextRequest) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON' }, { status: 400 })
  }

  try {
    const res = await fetchBackend('/query/classify', {
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
    return NextResponse.json({ detail: `Intent classify proxy error: ${e.message}` }, { status: 500 })
  }
}
