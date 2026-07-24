'use client'

import { useCallback, useEffect, useState } from 'react'
import { adminFetch, ErrorNotice, formatDateTime } from './shared'

// 지식그래프 학습 검토(FR-STR-070b) — 인터넷 검색으로 학습된 용어(어휘집)와 관계
// 엣지를 검토한다. 엣지는 출처 교차지지(≥2)로 자동 verified 승격되며, 여기서 사후
// 반려하거나 pending을 수동 승인한다. verified만 지식그래프에 합성된다.

interface LearnedEdge {
  type: string
  target: string
  target_name: string
  support: number
  status: 'verified' | 'pending' | 'rejected'
  evidence: string[]
}

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

export default function KnowledgeTab() {
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
                  <span className="text-[11px] text-gray-500">출처 {e.support}개</span>
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
