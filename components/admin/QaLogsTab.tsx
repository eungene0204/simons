'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  adminFetch,
  formatDateTime,
  Pagination,
  ErrorNotice,
  LoadingRow,
  EmptyRow,
  thClass,
  tdClass,
  inputClass,
  actionBtnClass,
} from './shared'

interface QaLog {
  id: string
  userId: number | null
  userEmail: string | null
  sessionId: string
  turnIndex: number
  question: string
  answer: string
  answerKind: string
  chipAnswer: boolean
  latencyMs: number | null
  createdAt: string
}

interface QaLogResponse {
  total: number
  page: number
  pageSize: number
  logs: QaLog[]
}

// 답변 종류 — app/analytics/new/qaLog.ts의 QaAnswerKind와 같은 값이다.
const ANSWER_KINDS: { id: string; label: string }[] = [
  { id: '', label: '전체' },
  { id: 'strategy', label: '전략 요약' },
  { id: 'coach', label: '코치 답변' },
  { id: 'info', label: '안내' },
  { id: 'clarification', label: '되묻기' },
  { id: 'text', label: '산문' },
  { id: 'error', label: '오류' },
]

const KIND_LABEL: Record<string, string> = Object.fromEntries(
  ANSWER_KINDS.filter((k) => k.id).map((k) => [k.id, k.label])
)

function KindBadge({ kind }: { kind: string }) {
  const tone =
    kind === 'error'
      ? 'bg-red-500/15 text-red-300'
      : kind === 'clarification'
        ? 'bg-amber-500/15 text-amber-300'
        : kind === 'strategy'
          ? 'bg-emerald-500/15 text-emerald-300'
          : 'bg-white/10 text-gray-300'
  return (
    <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${tone}`}>
      {KIND_LABEL[kind] ?? kind}
    </span>
  )
}

function formatLatency(ms: number | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
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
  const [expandedId, setExpandedId] = useState<string | null>(null)

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

      <div className="flat-card overflow-x-auto rounded-xl">
        <table className="w-full">
          <thead className="border-b border-white/5">
            <tr>
              <th className={thClass}>시간</th>
              <th className={thClass}>사용자</th>
              <th className={thClass}>종류</th>
              <th className={thClass}>질문</th>
              <th className={thClass}>답변</th>
              <th className={thClass}>소요</th>
              <th className={thClass}>대화</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <LoadingRow colSpan={7} />
            ) : !data || data.logs.length === 0 ? (
              <EmptyRow colSpan={7} />
            ) : (
              data.logs.map((log) => {
                const expanded = expandedId === log.id
                return (
                  <tr
                    key={log.id}
                    onClick={() => setExpandedId(expanded ? null : log.id)}
                    className="cursor-pointer border-b border-white/5 align-top last:border-0 hover:bg-white/[0.03]"
                  >
                    <td className={tdClass}>{formatDateTime(log.createdAt)}</td>
                    <td className={tdClass}>
                      {log.userEmail ?? <span className="text-gray-600">비로그인</span>}
                    </td>
                    <td className={tdClass}>
                      <KindBadge kind={log.answerKind} />
                    </td>
                    <td className={`${tdClass} max-w-80 whitespace-normal`}>
                      <span className={expanded ? '' : 'line-clamp-2'}>{log.question}</span>
                      {log.chipAnswer && (
                        <span className="ml-1 text-[11px] font-bold text-gray-600">(칩 선택)</span>
                      )}
                    </td>
                    <td className={`${tdClass} max-w-[32rem] whitespace-pre-wrap text-gray-400`}>
                      <span className={expanded ? '' : 'line-clamp-2'}>{log.answer}</span>
                    </td>
                    <td className={tdClass}>{formatLatency(log.latencyMs)}</td>
                    <td className={tdClass}>
                      <button
                        className={actionBtnClass}
                        onClick={(e) => {
                          e.stopPropagation()
                          setSessionId(log.sessionId)
                          setPage(1)
                        }}
                      >
                        #{log.turnIndex} 전체보기
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
        {data && (
          <div className="px-4 pb-4">
            <Pagination
              page={data.page}
              total={data.total}
              pageSize={data.pageSize}
              onChange={setPage}
            />
          </div>
        )}
      </div>
    </div>
  )
}
