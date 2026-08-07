import { NextResponse } from 'next/server'
import { requireAdmin } from '@/lib/server/adminAuth'
import { fetchBackend } from '@/lib/server/backend'

export const dynamic = 'force-dynamic'

// 지표 온톨로지 시각화 데이터 — 백엔드가 합성한 온톨로지(분류 계층+잎+합성 개념)
// 전체를 프록시한다. 합성 로직의 SOT는 backend/strategy_conversation/registry/
// concept_ontology.py이며 여기서 시드 파일을 직접 읽어 재합성하지 않는다.
export async function GET() {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const res = await fetchBackend('/ontology/graph', { timeoutMs: 15_000 })
    if (!res.ok) {
      return NextResponse.json({ error: '백엔드 온톨로지 조회 실패' }, { status: 502 })
    }
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ error: '백엔드에 연결할 수 없습니다' }, { status: 502 })
  }
}
