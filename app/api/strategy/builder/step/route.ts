import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/server/backend'

// [규제 안전] 열린 종목 추천 전환 직후 진입하는 전략 빌더 대화의 한 턴을 처리한다.
// 짧은 답변을 전략 필드로 누적하고, 완성되면 백테스트 프롬프트를 합성해 돌려준다.
//
// 백엔드 step-stream(SSE)을 그대로 파이프한다 — 인터넷 검색 그라운딩(FR-STR-069) 진입 시
// stage:"searching" 이벤트가 먼저 흘러 프론트가 '검색 중...'을 표시할 수 있다.
// 클라이언트 헬퍼는 content-type으로 SSE/JSON을 분기하므로 URL 계약은 그대로다.
export async function POST(req: NextRequest) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON' }, { status: 400 })
  }

  try {
    const res = await fetchBackend('/strategy/builder/step-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      // 검색 그라운딩(용어 추출 LLM + 네이버 검색 + 매핑 LLM)이 수십 초까지 걸릴 수 있다.
      timeoutMs: 120_000,
    })
    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      return NextResponse.json({ detail: err.detail ?? res.statusText }, { status: res.status })
    }
    return new NextResponse(res.body, {
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    })
  } catch (e: any) {
    return NextResponse.json({ detail: `Strategy builder proxy error: ${e.message}` }, { status: 500 })
  }
}
