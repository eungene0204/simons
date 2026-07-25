import { NextResponse } from 'next/server'
import { requireAdmin } from '@/lib/server/adminAuth'
import { fetchBackend } from '@/lib/server/backend'

export const dynamic = 'force-dynamic'

// KG 시각화 데이터(FR-STR-070c) — 백엔드가 합성한 지식그래프(시드+정본+학습 오버레이)
// 전체를 프록시한다. 합성 로직의 SOT는 backend/engine/knowledge_graph.py이며 여기서
// 파일을 직접 읽어 재합성하지 않는다(정본을 두 번 적지 않는다).
export async function GET() {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  try {
    const res = await fetchBackend('/knowledge/graph', { timeoutMs: 15_000 })
    if (!res.ok) {
      return NextResponse.json({ error: '백엔드 그래프 조회 실패' }, { status: 502 })
    }
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ error: '백엔드에 연결할 수 없습니다' }, { status: 502 })
  }
}
