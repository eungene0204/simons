'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  adminFetch,
  formatDate,
  Pagination,
  ErrorNotice,
  LoadingRow,
  EmptyRow,
  thClass,
  tdClass,
  actionBtnClass,
  dangerBtnClass,
  inputClass,
} from './shared'

interface StrategyRow {
  id: string
  name: string
  strategyType: string
  isSaved: boolean
  indicators: string[]
  userEmail: string | null
  linkedAccounts: number
  backtestCount: number
  createdAt: string
  updatedAt: string
}

interface StrategiesResponse {
  total: number
  page: number
  pageSize: number
  strategies: StrategyRow[]
}

export default function StrategiesTab() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<StrategiesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ page: String(page) })
      if (q) params.set('q', q)
      setData(await adminFetch<StrategiesResponse>(`/api/admin/strategies?${params}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    } finally {
      setLoading(false)
    }
  }, [q, page])

  useEffect(() => {
    load()
  }, [load])

  const runAction = async (strategy: StrategyRow, action: 'deactivate' | 'delete') => {
    if (action === 'delete' && !window.confirm(`"${strategy.name}" 전략을 삭제할까요?`)) {
      return
    }
    setBusy(true)
    setError('')
    try {
      await adminFetch('/api/admin/strategies', {
        method: 'PATCH',
        body: JSON.stringify({ strategyId: strategy.id, action }),
      })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '작업 실패')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {error && <ErrorNotice message={error} />}

      <input
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setPage(1)
        }}
        placeholder="전략명 또는 사용자 이메일 검색"
        className={`${inputClass} w-72`}
      />

      <div className="flat-card overflow-x-auto rounded-xl">
        <table className="w-full">
          <thead className="border-b border-white/5">
            <tr>
              <th className={thClass}>전략명</th>
              <th className={thClass}>사용자</th>
              <th className={thClass}>유형/지표</th>
              <th className={thClass}>연결 계좌</th>
              <th className={thClass}>백테스트</th>
              <th className={thClass}>생성일</th>
              <th className={thClass}>수정일</th>
              <th className={thClass}>작업</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <LoadingRow colSpan={8} />
            ) : !data || data.strategies.length === 0 ? (
              <EmptyRow colSpan={8} />
            ) : (
              data.strategies.map((s) => (
                <tr key={s.id} className="border-b border-white/5 last:border-0">
                  <td className={`${tdClass} max-w-56 truncate font-bold`}>
                    {s.name}
                    {!s.isSaved && (
                      <span className="ml-2 text-xs font-bold text-gray-600">(비활성)</span>
                    )}
                  </td>
                  <td className={tdClass}>{s.userEmail ?? '—'}</td>
                  <td className={`${tdClass} max-w-56`}>
                    <span className="font-bold text-gray-300">{s.strategyType}</span>
                    {s.indicators.length > 0 && (
                      <span className="ml-2 truncate text-xs font-bold text-gray-500">
                        {s.indicators.join(', ')}
                      </span>
                    )}
                  </td>
                  <td className={tdClass}>{s.linkedAccounts}</td>
                  <td className={tdClass}>{s.backtestCount}</td>
                  <td className={tdClass}>{formatDate(s.createdAt)}</td>
                  <td className={tdClass}>{formatDate(s.updatedAt)}</td>
                  <td className={tdClass}>
                    <div className="flex gap-1.5">
                      {s.isSaved && (
                        <button
                          disabled={busy}
                          onClick={() => runAction(s, 'deactivate')}
                          className={actionBtnClass}
                        >
                          비활성화
                        </button>
                      )}
                      <button
                        disabled={busy}
                        onClick={() => runAction(s, 'delete')}
                        className={dangerBtnClass}
                      >
                        삭제
                      </button>
                    </div>
                  </td>
                </tr>
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
