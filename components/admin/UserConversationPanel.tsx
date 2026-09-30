'use client'

import { useCallback, useEffect, useState } from 'react'
import { adminFetch, formatDateTime, Pagination, ErrorNotice, actionBtnClass } from './shared'
import StrategySnapshotView, { type StrategySnapshot, type StrategySource } from './StrategySnapshotView'

// Users 탭에서 사용자를 고르면 그 사용자가 전략연구소에 입력한 내용과 우리의 응답을 보여 준다.
// 기본은 전략 카드가 뜬 턴만(입력한 전략과 해석) — 되묻기·안내까지 전부 보려면 토글을 끈다.

interface ConversationLog {
  id: string
  sessionId: string
  turnIndex: number
  question: string
  answer: string
  answerKind: string
  chipAnswer: boolean
  createdAt: string
  strategy: StrategySnapshot | null
  strategySource: StrategySource | null
}

interface ConversationResponse {
  total: number
  page: number
  pageSize: number
  logs: ConversationLog[]
}

export default function UserConversationPanel({ userId, email }: { userId: number; email: string }) {
  const [strategyOnly, setStrategyOnly] = useState(true)
  const [page, setPage] = useState(1)
  const [data, setData] = useState<ConversationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ userId: String(userId), page: String(page) })
      if (strategyOnly) params.set('strategyOnly', '1')
      setData(await adminFetch<ConversationResponse>(`/api/admin/qa-logs?${params}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    } finally {
      setLoading(false)
    }
  }, [userId, page, strategyOnly])

  useEffect(() => {
    load()
  }, [load])

  return (
    <section className="flat-card space-y-3 rounded-xl px-5 py-4" data-testid="user-conversation-panel">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-black text-white">{email} — 입력한 전략과 응답</p>
        <button
          className={`${actionBtnClass} ml-auto`}
          onClick={() => {
            setStrategyOnly((v) => !v)
            setPage(1)
          }}
        >
          {strategyOnly ? '모든 대화 보기' : '전략 카드만 보기'}
        </button>
      </div>
      <p className="text-xs font-bold text-gray-600">
        전략 카드 내용은 2026-09-30부터 기록됩니다. 그 전 턴은 사용자 대화 기록(최근 30개 대화)이
        남아 있을 때만 복원됩니다.
      </p>

      {error && <ErrorNotice message={error} />}
      {loading ? (
        <p className="py-6 text-center text-sm font-bold text-gray-500">불러오는 중...</p>
      ) : !data || data.logs.length === 0 ? (
        <p className="py-6 text-center text-sm font-bold text-gray-500">
          {strategyOnly ? '전략 카드가 나온 대화가 없습니다' : '대화 기록이 없습니다'}
        </p>
      ) : (
        <ol className="space-y-3">
          {data.logs.map((log) => (
            <li key={log.id} className="rounded-lg border border-white/5 px-3 py-2.5">
              <p className="mb-1.5 text-[11px] font-bold text-gray-600">
                {formatDateTime(log.createdAt)} · 대화 {log.sessionId.slice(0, 8)} #{log.turnIndex}
                {log.chipAnswer && ' · 칩 선택'}
              </p>
              <p className="whitespace-pre-wrap text-sm font-bold text-gray-100">{log.question}</p>
              <details className="mt-1.5">
                <summary className="cursor-pointer text-[11px] font-bold text-gray-500">응답 텍스트</summary>
                <p className="mt-1 whitespace-pre-wrap text-xs text-gray-400">{log.answer}</p>
              </details>
              {log.strategy && (
                <div className="mt-2">
                  <StrategySnapshotView strategy={log.strategy} source={log.strategySource} />
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
      {data && (
        <Pagination page={data.page} total={data.total} pageSize={data.pageSize} onChange={setPage} />
      )}
    </section>
  )
}
