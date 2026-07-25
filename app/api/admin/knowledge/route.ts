import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'
import { requireAdmin, writeAuditLog } from '@/lib/server/adminAuth'

export const dynamic = 'force-dynamic'

// 지식그래프 학습 검토(FR-STR-070b) — term_grounding이 인터넷 검색으로 학습한
// 용어(어휘집)와 관계 엣지를 조회하고, 자동 승격(출처 교차지지 ≥2)된 엣지를
// 사후 반려하거나 pending 엣지를 수동 승인한다. 어휘집 파일이 SOT이며 백엔드
// KG 로더는 파일 mtime으로 자동 재로드한다(별도 동기화 불필요).

function lexiconPath(): string {
  return process.env.TERM_LEXICON_PATH ?? path.join(process.cwd(), 'data', 'term_lexicon.json')
}

async function readLexicon(): Promise<Record<string, any>> {
  try {
    const raw = await fs.readFile(lexiconPath(), 'utf-8')
    const data = JSON.parse(raw)
    return data && typeof data === 'object' ? data : {}
  } catch {
    return {}
  }
}

async function writeLexicon(lexicon: Record<string, any>): Promise<void> {
  const target = lexiconPath()
  const tmp = `${target}.tmp`
  await fs.writeFile(tmp, JSON.stringify(lexicon, null, 1), 'utf-8')
  await fs.rename(tmp, target)
}

// GET: 학습 용어·엣지 전체 목록
export async function GET() {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  const lexicon = await readLexicon()
  const terms = Object.entries(lexicon).map(([key, entry]: [string, any]) => ({
    key,
    term: entry?.term ?? key,
    definition: entry?.definition ?? null,
    sector: entry?.sector ?? null,
    searched_at: entry?.searched_at ?? null,
    sources: entry?.sources ?? [],
    edges: Array.isArray(entry?.edges) ? entry.edges : [],
  }))
  terms.sort((a, b) => String(b.searched_at ?? '').localeCompare(String(a.searched_at ?? '')))
  return NextResponse.json({ terms })
}

// 수동 엣지에 허용하는 관계 유형 — 백엔드 학습 엣지 허용 목록(_LEARNED_EDGE_TYPES)
// + 관련 기업/지분 관계. 백엔드 KG 로더가 EDGE_TYPES·정본 심볼로 재검증하므로
// 여기 검증은 UX용 1차 게이트다(목록 밖 유형·엉뚱한 타깃은 그래프에 합성되지 않음).
const MANUAL_EDGE_TYPES = [
  'related_company', 'related_to', 'is_a', 'part_of', 'belongs_to',
  'uses', 'supplier', 'competitor', 'invests_in',
]

// PATCH: 학습 데이터 검토 작업 — approveEdge | rejectEdge | deleteTerm | addEdge
export async function PATCH(request: NextRequest) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Not Found' }, { status: 404 })

  let body: any
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 })
  }
  const { action, key } = body ?? {}
  if (typeof key !== 'string' || !key) {
    return NextResponse.json({ error: 'key is required' }, { status: 400 })
  }

  const lexicon = await readLexicon()
  const entry = lexicon[key]
  if (!entry) return NextResponse.json({ error: 'Term not found' }, { status: 404 })

  if (action === 'deleteTerm') {
    // 잘못 학습된 용어 제거 — 어휘집에서 지우면 다음 언급 시 재검색으로 다시 학습된다.
    delete lexicon[key]
    await writeLexicon(lexicon)
    await writeAuditLog(admin, {
      action: 'knowledge.deleteTerm',
      targetType: 'term',
      targetId: key,
      before: entry,
    })
    return NextResponse.json({ ok: true })
  }

  if (action === 'addEdge') {
    // 수동 엣지 추가(FR-STR-070b ⑦) — 검색·공시가 모두 놓치는 롱테일 관계
    // (예: 'LB인베스트먼트=하이브 초기 투자사')를 관리자가 근거와 함께 직접 편입한다.
    // 관리자 행위 자체가 사람 검증이므로 즉시 verified — 감사 로그에 남는다.
    const { target, type, targetName, note } = body ?? {}
    if (typeof target !== 'string' || !target || typeof type !== 'string' || !type) {
      return NextResponse.json({ error: 'target and type are required' }, { status: 400 })
    }
    if (!MANUAL_EDGE_TYPES.includes(type)) {
      return NextResponse.json({ error: `Unsupported edge type: ${type}` }, { status: 400 })
    }
    const edges: any[] = Array.isArray(entry.edges) ? entry.edges : []
    if (edges.some((e) => e?.target === target && e?.type === type)) {
      return NextResponse.json({ error: 'Edge already exists' }, { status: 409 })
    }
    const edge: Record<string, unknown> = {
      type,
      target,
      target_name: typeof targetName === 'string' && targetName ? targetName : target,
      status: 'verified',
      proposed_by: 'manual',
      evidence: [],
    }
    if (typeof note === 'string' && note.trim()) edge.note = note.trim()
    entry.edges = [...edges, edge]
    await writeLexicon(lexicon)
    await writeAuditLog(admin, {
      action: 'knowledge.addEdge',
      targetType: 'edge',
      targetId: `${key} -${type}→ ${target}`,
      after: edge,
    })
    return NextResponse.json({ ok: true, edge })
  }

  if (action === 'approveEdge' || action === 'rejectEdge') {
    const { target, type } = body ?? {}
    const edges: any[] = Array.isArray(entry.edges) ? entry.edges : []
    const edge = edges.find((e) => e?.target === target && e?.type === type)
    if (!edge) return NextResponse.json({ error: 'Edge not found' }, { status: 404 })
    const before = { ...edge }
    edge.status = action === 'approveEdge' ? 'verified' : 'rejected'
    await writeLexicon(lexicon)
    await writeAuditLog(admin, {
      action: `knowledge.${action}`,
      targetType: 'edge',
      targetId: `${key} -${type}→ ${target}`,
      before,
      after: { ...edge },
    })
    return NextResponse.json({ ok: true, edge })
  }

  return NextResponse.json({ error: 'Unknown action' }, { status: 400 })
}
