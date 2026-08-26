import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'

// 사용자 입력의 intent(STRATEGY_ADVICE / STOCK_ANALYSIS / GENERAL_INVESTMENT / UNKNOWN)를 분류한다.
// STOCK_ANALYSIS는 종목 분석이 아니라 '추천 불가 안내 + 전략 설계 전환'(suggested_reply)이다.
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
      // 분류 LLM은 워밍업 시 ~3초지만 콜드/경합 시 68초 실측(2026-08-26 트레이스
      // 16632690d244 — "hello"가 67.9s 만에 GREETING). 30초에서 끊으면 호출부 폴백이
      // STRATEGY_ADVICE로 강등해 인사가 전략 파싱 레인으로 새고, 사용자에게는
      // "인사 룰이 없는 것"처럼 보인다. 잘못된 레인이 늦은 정답보다 나쁘다 — 예산을
      // 실측 worst-case 위로 두고, 조기 중단은 사용자의 '대화 종료'(chatSignal)가 담당한다.
      timeoutMs: 120_000,
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
