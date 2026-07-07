'use client'

import { Fragment, useCallback, useEffect, useState } from 'react'
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
}

interface UsageResponse {
  total: number
  page: number
  pageSize: number
  month: string
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

  const load = useCallback(async () => {
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
    if (expandedUserId === userId) {
      setExpandedUserId(null)
      return
    }
    try {
      const res = await adminFetch<{ recentRuns: RecentRun[] }>(
        `/api/admin/backtests?userId=${userId}`
      )
      setRecentRuns(res.recentRuns)
      setExpandedUserId(userId)
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    }
  }

  return (
    <div className="space-y-4">
      {error && <ErrorNotice message={error} />}
      {data && (
        <p className="text-xs font-bold text-gray-500">기준 월: {data.month}</p>
      )}

      <div className="flat-card overflow-x-auto rounded-xl">
        <table className="w-full">
          <thead className="border-b border-white/5">
            <tr>
              <th className={thClass}>이메일</th>
              <th className={thClass}>플랜</th>
              <th className={thClass}>이번 달 사용량</th>
              <th className={thClass}>남은 횟수</th>
              <th className={thClass}>사용량 조정</th>
              <th className={thClass}>최근 실행</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <LoadingRow colSpan={6} />
            ) : !data || data.users.length === 0 ? (
              <EmptyRow colSpan={6} />
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
                      <td colSpan={6} className="bg-white/[0.02] px-6 py-3">
                        {recentRuns.length === 0 ? (
                          <p className="text-xs font-bold text-gray-600">최근 기록이 없습니다</p>
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
