import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'

// 개별 종목 분석(규칙 기반 추천 + LLM 설명)을 백엔드 Stock Analysis Agent에 위임한다.
export async function POST(req: NextRequest) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON' }, { status: 400 })
  }

  try {
    const res = await fetchBackend('/stock/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      timeoutMs: 120_000,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      return NextResponse.json({ detail: err.detail ?? res.statusText }, { status: res.status })
    }
    return NextResponse.json(await res.json())
  } catch (e: any) {
    return NextResponse.json({ detail: `Stock analyze proxy error: ${e.message}` }, { status: 500 })
  }
}
