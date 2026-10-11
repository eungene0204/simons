import { NextResponse } from 'next/server'
import { requireAdmin } from '@/lib/server/adminAuth'
import { fetchBackend } from '@/lib/server/backend'

export const dynamic = 'force-dynamic'

// 운영 콘솔 실패 분류 — 백엔드가 Trace(원문 3일 보관)를 구조 신호로 묶은 결과를 프록시한다.
// 분류 로직의 SOT는 backend/observability/triage.py이며 여기서 Trace를 직접 읽지 않는다.
// 응답에 사용자 발화 표본이 들어가므로 관리자 확인이 이 라우트의 유일한 관문이다
// (백엔드는 외부에 노출되지 않는다).
export async function GET(req: Request) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  const days = Number(new URL(req.url).searchParams.get('days'))
  const path = Number.isInteger(days) && days >= 1 ? `/admin/trace-triage?days=${days}` : '/admin/trace-triage'
  try {
    const res = await fetchBackend(path, { timeoutMs: 30_000 })
    if (!res.ok) {
      return NextResponse.json({ error: '백엔드 실패 분류 조회 실패' }, { status: 502 })
    }
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ error: '백엔드에 연결할 수 없습니다' }, { status: 502 })
  }
}
