'use client'

import { useCallback, useEffect, useState } from 'react'
import { adminFetch, Pagination, ErrorNotice, inputClass, actionBtnClass } from './shared'
import QaTurnCard, { ANSWER_KINDS, type QaTurn } from './QaTurnCard'

interface QaLog extends QaTurn {
  userId: number | null
  userEmail: string | null
  latencyMs: number | null
}

interface QaLogResponse {
  total: number
  page: number
  pageSize: number
  logs: QaLog[]
}

export default function QaLogsTab() {
  const [email, setEmail] = useState('')
  const [keyword, setKeyword] = useState('')
  const [answerKind, setAnswerKind] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<QaLogResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ page: String(page) })
      if (email) params.set('email', email)
      if (keyword) params.set('keyword', keyword)
      if (answerKind) params.set('answerKind', answerKind)
      if (sessionId) params.set('sessionId', sessionId)
      setData(await adminFetch<QaLogResponse>(`/api/admin/qa-logs?${params}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    } finally {
      setLoading(false)
    }
  }, [email, keyword, answerKind, sessionId, page])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="space-y-4">
      {error && <ErrorNotice message={error} />}

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value)
            setPage(1)
          }}
          placeholder="질문·답변 내용 검색"
          className={`${inputClass} w-64`}
        />
        <input
          value={email}
          onChange={(e) => {
            setEmail(e.target.value)
            setPage(1)
          }}
          placeholder="사용자 이메일"
          className={`${inputClass} w-56`}
        />
        <select
          value={answerKind}
          onChange={(e) => {
            setAnswerKind(e.target.value)
            setPage(1)
          }}
          className={`${inputClass} w-32`}
        >
          {ANSWER_KINDS.map((k) => (
            <option key={k.id} value={k.id}>
              {k.label}
            </option>
          ))}
        </select>
        {sessionId && (
          <button
            className={actionBtnClass}
            onClick={() => {
              setSessionId('')
              setPage(1)
            }}
          >
            대화 필터 해제
          </button>
        )}
        <p className="ml-auto text-xs font-bold text-gray-600">
          대화 기록은 삭제할 수 없습니다
        </p>
      </div>

      {sessionId && (
        <p className="text-xs font-bold text-gray-400">
          대화 {sessionId.slice(0, 8)}의 전체 흐름 — 첫 턴부터 순서대로
        </p>
      )}

      {loading ? (
        <p className="py-10 text-center text-sm font-bold text-gray-500">불러오는 중...</p>
      ) : !data || data.logs.length === 0 ? (
        <p className="py-10 text-center text-sm font-bold text-gray-500">데이터가 없습니다</p>
      ) : (
        <ol className="space-y-3">
          {data.logs.map((log) => (
            <li key={log.id}>
              <QaTurnCard
                turn={log}
                showUser
                action={
                  sessionId ? undefined : (
                    <button
                      className={actionBtnClass}
                      onClick={() => {
                        setSessionId(log.sessionId)
                        setPage(1)
                      }}
                    >
                      대화 전체보기
                    </button>
                  )
                }
              />
            </li>
          ))}
        </ol>
      )}
      {data && (
        <Pagination page={data.page} total={data.total} pageSize={data.pageSize} onChange={setPage} />
      )}
    </div>
  )
}
