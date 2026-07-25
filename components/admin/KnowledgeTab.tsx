'use client'

import { useCallback, useEffect, useState } from 'react'
import { adminFetch, ErrorNotice, formatDateTime } from './shared'
import KnowledgeGraphView from './KnowledgeGraphView'

// 지식그래프 학습 검토(FR-STR-070b) — 인터넷 검색으로 학습된 용어(어휘집)와 관계
// 엣지를 검토한다. 엣지는 출처 교차지지(≥2)로 자동 verified 승격되며, 여기서 사후
// 반려하거나 pending을 수동 승인한다. verified만 지식그래프에 합성된다.
// 'KG 시각화' 서브탭(FR-STR-070c)은 합성 그래프 전체를 포스 레이아웃으로 표시한다.

interface LearnedEdge {
  type: string
  target: string
  target_name: string
  support?: number // 수동 등록(proposed_by=manual) 엣지엔 출처 수가 없다
  status: 'verified' | 'pending' | 'rejected'
  evidence: string[]
  proposed_by?: string
}

// 수동 엣지 관계 유형 — 라우트 MANUAL_EDGE_TYPES와 동일 목록(백엔드 로더가 재검증)
const MANUAL_EDGE_TYPES = [
  'related_company', 'related_to', 'is_a', 'part_of', 'belongs_to',
  'uses', 'supplier', 'competitor', 'invests_in',
]

interface LearnedTerm {
  key: string
  term: string
  definition: string | null
  sector: string | null
  searched_at: string | null
  sources: { title: string; link: string }[]
  edges: LearnedEdge[]
}

const STATUS_LABEL: Record<LearnedEdge['status'], { label: string; cls: string }> = {
  verified: { label: '검증됨', cls: 'bg-emerald-500/15 text-emerald-400' },
  pending: { label: '검토 대기', cls: 'bg-amber-500/15 text-amber-400' },
  rejected: { label: '반려됨', cls: 'bg-red-500/15 text-red-400' },
}

const SUB_TABS = [
  { id: 'review', label: '학습 검토' },
  { id: 'graph', label: 'KG 시각화' },
] as const

type SubTabId = (typeof SUB_TABS)[number]['id']

// 수동 엣지 추가(FR-STR-070b ⑦) — 검색·공시가 모두 놓치는 롱테일 관계를 근거와 함께
// 직접 편입한다(예: 'LB인베스트먼트=하이브 초기 투자사'). 관리자 행위=사람 검증이라
// 즉시 verified. 타깃은 company:<종목코드> 또는 그래프 개념 id. 모듈 레벨 정의 —
// 부모 안에 정의하면 렌더마다 새 컴포넌트 타입이 돼 입력 중 리마운트된다(아래 관례).
function AddEdgeForm({ termKey, busy, onSubmit }: {
  termKey: string
  busy: boolean
  onSubmit: (p: Record<string, unknown>) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [type, setType] = useState('related_company')
  const [target, setTarget] = useState('')
  const [targetName, setTargetName] = useState('')
  const [note, setNote] = useState('')
  if (!open) {
    return (
      <button
        disabled={busy}
        onClick={() => setOpen(true)}
        className="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] font-bold text-gray-400 hover:bg-white/5 hover:text-gray-200 disabled:opacity-50"
      >
        + 수동 엣지 추가
      </button>
    )
  }
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-black/20 p-2">
      <select
        value={type}
        onChange={(e) => setType(e.target.value)}
        className="rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-[11px] font-bold text-gray-200"
      >
        {MANUAL_EDGE_TYPES.map((v) => (
          <option key={v} value={v}>{v}</option>
        ))}
      </select>
      <input
        value={target}
        onChange={(e) => setTarget(e.target.value)}
        placeholder="타깃 (company:309960 또는 개념 id)"
        className="w-56 rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-[11px] font-bold text-gray-200 placeholder:text-gray-600"
      />
      <input
        value={targetName}
        onChange={(e) => setTargetName(e.target.value)}
        placeholder="표시명 (예: LB인베스트먼트)"
        className="w-40 rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-[11px] font-bold text-gray-200 placeholder:text-gray-600"
      />
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="근거 (예: 하이브 초기 투자사)"
        className="w-64 rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-[11px] font-bold text-gray-200 placeholder:text-gray-600"
      />
      <button
        disabled={busy || !target.trim()}
        onClick={async () => {
          await onSubmit({
            action: 'addEdge', key: termKey, type,
            target: target.trim(), targetName: targetName.trim(), note: note.trim(),
          })
          setOpen(false)
          setTarget(''); setTargetName(''); setNote('')
        }}
        className="rounded-lg bg-emerald-500/10 px-2.5 py-1 text-[11px] font-bold text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-50"
      >
        추가
      </button>
      <button
        disabled={busy}
        onClick={() => setOpen(false)}
        className="rounded-lg px-2 py-1 text-[11px] font-bold text-gray-500 hover:text-gray-300"
      >
        취소
      </button>
    </div>
  )
}

export default function KnowledgeTab() {
  const [subTab, setSubTab] = useState<SubTabId>('review')
  const [terms, setTerms] = useState<LearnedTerm[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async () => {
    setError('')
    try {
      const res = await adminFetch<{ terms: LearnedTerm[] }>('/api/admin/knowledge')
      setTerms(res.terms)
      setLoaded(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const patch = async (payload: Record<string, unknown>) => {
    setBusy(true)
    setError('')
    try {
      await adminFetch('/api/admin/knowledge', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '저장 실패')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-1">
        {SUB_TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setSubTab(t.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-colors ${
              subTab === t.id
                ? 'bg-white/10 text-white'
                : 'text-gray-500 hover:bg-white/5 hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {subTab === 'graph' ? <KnowledgeGraphView /> : renderReview()}
    </div>
  )

  // 학습 검토 서브탭 — 기존 검토 UI(FR-STR-070b)를 그대로 렌더링한다.
  // 컴포넌트가 아닌 렌더 함수로 호출한다(렌더마다 새 컴포넌트 타입 → 리마운트 방지).
  function renderReview() {
    if (!loaded && !error) {
      return <p className="text-sm font-bold text-gray-600">불러오는 중…</p>
    }
    return (
      <div className="space-y-4">
      {error && <ErrorNotice message={error} />}
      <p className="text-xs font-bold text-gray-500">
        인터넷 검색으로 학습된 용어와 관계입니다. 관계 엣지는 서로 다른 출처 2개 이상이
        지지하면 자동 검증되며, 검증된 엣지만 지식그래프에 편입됩니다. 잘못 학습된 용어를
        삭제하면 다음 언급 시 재검색으로 다시 학습됩니다.
      </p>
      {terms.length === 0 && (
        <p className="text-sm font-bold text-gray-600">학습된 용어가 없습니다.</p>
      )}
      {terms.map((t) => (
        <div key={t.key} className="rounded-xl border border-white/10 bg-white/5 p-4 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-black text-white">{t.term}</span>
                {t.sector && (
                  <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-[11px] font-bold text-sky-400">
                    {t.sector}
                  </span>
                )}
                <span className="text-[11px] font-bold text-gray-500">
                  {formatDateTime(t.searched_at)}
                </span>
              </div>
              {t.definition && (
                <p className="mt-1 text-xs font-bold text-gray-400">{t.definition}</p>
              )}
            </div>
            <button
              disabled={busy}
              onClick={() => {
                if (window.confirm(`'${t.term}' 학습 데이터를 삭제할까요?`)) {
                  patch({ action: 'deleteTerm', key: t.key })
                }
              }}
              className="shrink-0 rounded-lg bg-red-500/10 px-2.5 py-1 text-[11px] font-bold text-red-400 hover:bg-red-500/20 disabled:opacity-50"
            >
              용어 삭제
            </button>
          </div>
          <AddEdgeForm termKey={t.key} busy={busy} onSubmit={patch} />
          {t.edges.length > 0 && (
            <ul className="space-y-1.5">
              {t.edges.map((e) => (
                <li
                  key={`${e.type}:${e.target}`}
                  className="flex flex-wrap items-center gap-2 text-xs font-bold text-gray-300"
                >
                  <span>
                    {t.term} <span className="text-gray-500">–{e.type}→</span> {e.target_name}
                  </span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] ${STATUS_LABEL[e.status].cls}`}>
                    {STATUS_LABEL[e.status].label}
                  </span>
                  <span className="text-[11px] text-gray-500">
                    {e.proposed_by === 'manual' ? '수동 등록' : `출처 ${e.support ?? 0}개`}
                  </span>
                  {e.status !== 'verified' && (
                    <button
                      disabled={busy}
                      onClick={() => patch({ action: 'approveEdge', key: t.key, target: e.target, type: e.type })}
                      className="rounded-lg bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-50"
                    >
                      승인
                    </button>
                  )}
                  {e.status !== 'rejected' && (
                    <button
                      disabled={busy}
                      onClick={() => patch({ action: 'rejectEdge', key: t.key, target: e.target, type: e.type })}
                      className="rounded-lg bg-red-500/10 px-2 py-0.5 text-[11px] text-red-400 hover:bg-red-500/20 disabled:opacity-50"
                    >
                      반려
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
      </div>
    )
  }
}
