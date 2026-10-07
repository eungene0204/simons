'use client'

import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import {
  adminFetch,
  formatDateTime,
  PlanBadge,
  Pagination,
  ErrorNotice,
  LoadingRow,
  EmptyRow,
  thClass,
  tdClass,
  actionBtnClass,
} from './shared'

interface UsageRow {
  id: number
  email: string
  planTier: string
  used: number
  limit: number
  remaining: number
  runTotal: number
}

interface UsageResponse {
  total: number
  page: number
  pageSize: number
  users: UsageRow[]
}

interface RecentRun {
  id: string
  strategyName: string
  savedAt: string
}

export default function BacktestsTab() {
  const [page, setPage] = useState(1)
  const [data, setData] = useState<UsageResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [expandedUserId, setExpandedUserId] = useState<number | null>(null)
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([])
  const [recentLoading, setRecentLoading] = useState(false)
  const recentRequest = useRef(0)

  const load = useCallback(async () => {
    recentRequest.current += 1
    setExpandedUserId(null)
    setRecentRuns([])
    setLoading(true)
    setError('')
    try {
      setData(await adminFetch<UsageResponse>(`/api/admin/backtests?page=${page}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    load()
  }, [load])

  const adjust = async (userId: number, action: 'reset' | 'increase' | 'decrease') => {
    setBusy(true)
    setError('')
    try {
      await adminFetch('/api/admin/backtests', {
        method: 'PATCH',
        body: JSON.stringify({ userId, action }),
      })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '작업 실패')
    } finally {
      setBusy(false)
    }
  }

  const toggleRecent = async (userId: number) => {
    const requestId = ++recentRequest.current
    if (expandedUserId === userId) {
      setExpandedUserId(null)
      return
    }
    setExpandedUserId(userId)
    setRecentRuns([])
    setRecentLoading(true)
    setError('')
    try {
      const res = await adminFetch<{ recentRuns: RecentRun[] }>(
        `/api/admin/backtests?userId=${userId}`
      )
      if (requestId === recentRequest.current) setRecentRuns(res.recentRuns)
    } catch (e) {
      if (requestId === recentRequest.current) setError(e instanceof Error ? e.message : '조회 실패')
    } finally {
      if (requestId === recentRequest.current) setRecentLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      {error && <ErrorNotice message={error} />}
      <p className="text-xs font-bold text-gray-500">
        사용량 기준: 사용자별 결제 주기(구독 시작일, 미구독은 가입일 기준 1개월).
        누적 요청은 2026-09-30부터 집계하며 실패한 실행도 포함합니다. 저장 결과는 실행 이력과 다릅니다.
      </p>

      <div className="flat-card overflow-x-auto rounded-xl">
        <table className="w-full">
          <thead className="border-b border-white/5">
            <tr>
              <th className={thClass}>이메일</th>
              <th className={thClass}>플랜</th>
              <th className={thClass}>현재 주기 사용량</th>
              <th className={thClass}>남은 횟수</th>
              <th className={thClass}>누적 요청</th>
              <th className={thClass}>사용량 조정</th>
              <th className={thClass}>최근 저장 결과</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <LoadingRow colSpan={7} />
            ) : !data || data.users.length === 0 ? (
              <EmptyRow colSpan={7} />
            ) : (
              data.users.map((u) => (
                <Fragment key={u.id}>
                  <tr className="border-b border-white/5 last:border-0">
                    <td className={`${tdClass} font-bold`}>{u.email}</td>
                    <td className={tdClass}>
                      <PlanBadge plan={u.planTier} />
                    </td>
                    <td className={tdClass}>
                      {u.used}/{u.limit}
                    </td>
                    <td className={tdClass}>{u.remaining}</td>
                    <td className={tdClass}>{u.runTotal}</td>
                    <td className={tdClass}>
                      <div className="flex gap-1.5">
                        <button
                          disabled={busy}
                          onClick={() => adjust(u.id, 'reset')}
                          className={actionBtnClass}
                        >
                          초기화
                        </button>
                        <button
                          disabled={busy}
                          onClick={() => adjust(u.id, 'increase')}
                          className={actionBtnClass}
                        >
                          +1
                        </button>
                        <button
                          disabled={busy}
                          onClick={() => adjust(u.id, 'decrease')}
                          className={actionBtnClass}
                        >
                          -1
                        </button>
                      </div>
                    </td>
                    <td className={tdClass}>
                      <button onClick={() => toggleRecent(u.id)} className={actionBtnClass}>
                        {expandedUserId === u.id ? '접기' : '보기'}
                      </button>
                    </td>
                  </tr>
                  {expandedUserId === u.id && (
                    <tr className="border-b border-white/5">
                      <td colSpan={7} className="bg-white/[0.02] px-6 py-3">
                        {recentLoading ? (
                          <p className="text-xs font-bold text-gray-500">불러오는 중...</p>
                        ) : recentRuns.length === 0 ? (
                          <p className="text-xs font-bold text-gray-600">저장된 결과가 없습니다</p>
                        ) : (
                          <ul className="space-y-1">
                            {recentRuns.map((r) => (
                              <li key={r.id} className="flex justify-between text-xs font-bold">
                                <span className="text-gray-300">{r.strategyName}</span>
                                <span className="text-gray-500">{formatDateTime(r.savedAt)}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
        {data && (
          <div className="px-4 pb-4">
            <Pagination page={data.page} total={data.total} pageSize={data.pageSize} onChange={setPage} />
          </div>
        )}
      </div>
    </div>
  )
}
