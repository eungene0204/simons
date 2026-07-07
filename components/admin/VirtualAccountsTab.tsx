'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  adminFetch,
  formatKrw,
  StatusBadge,
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

interface AccountRow {
  id: string
  name: string
  status: string
  userEmail: string | null
  strategyName: string | null
  initialCash: number
  totalValue: number
  returnPct: number
  orderCount: number
}

interface AccountsResponse {
  total: number
  page: number
  pageSize: number
  accounts: AccountRow[]
}

export default function VirtualAccountsTab() {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<AccountsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ page: String(page) })
      if (q) params.set('q', q)
      if (status) params.set('status', status)
      setData(await adminFetch<AccountsResponse>(`/api/admin/accounts?${params}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    } finally {
      setLoading(false)
    }
  }, [q, status, page])

  useEffect(() => {
    load()
  }, [load])

  const runAction = async (account: AccountRow, action: string) => {
    if (
      (action === 'reset' &&
        !window.confirm(`"${account.name}" 계좌를 초기화할까요? 포지션/주문이 삭제됩니다.`)) ||
      (action === 'delete' && !window.confirm(`"${account.name}" 계좌를 삭제할까요?`))
    ) {
      return
    }
    setBusy(true)
    setError('')
    try {
      await adminFetch('/api/admin/accounts', {
        method: 'PATCH',
        body: JSON.stringify({ accountId: account.id, action }),
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

      <div className="flex flex-wrap gap-2">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setPage(1)
          }}
          placeholder="사용자 이메일 검색"
          className={`${inputClass} w-56`}
        />
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value)
            setPage(1)
          }}
          className={inputClass}
        >
          <option value="">모든 상태</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="PAUSED">PAUSED</option>
          <option value="CLOSED">CLOSED</option>
        </select>
      </div>

      <div className="flat-card overflow-x-auto rounded-xl">
        <table className="w-full">
          <thead className="border-b border-white/5">
            <tr>
              <th className={thClass}>계좌명</th>
              <th className={thClass}>사용자</th>
              <th className={thClass}>상태</th>
              <th className={thClass}>초기 자금</th>
              <th className={thClass}>평가금</th>
              <th className={thClass}>수익률</th>
              <th className={thClass}>거래</th>
              <th className={thClass}>연결 전략</th>
              <th className={thClass}>작업</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <LoadingRow colSpan={9} />
            ) : !data || data.accounts.length === 0 ? (
              <EmptyRow colSpan={9} />
            ) : (
              data.accounts.map((a) => (
                <tr key={a.id} className="border-b border-white/5 last:border-0">
                  <td className={`${tdClass} font-bold`}>{a.name}</td>
                  <td className={tdClass}>{a.userEmail ?? '—'}</td>
                  <td className={tdClass}>
                    <StatusBadge status={a.status} />
                  </td>
                  <td className={tdClass}>{formatKrw(a.initialCash)}</td>
                  <td className={tdClass}>{formatKrw(a.totalValue)}</td>
                  <td
                    className={`${tdClass} font-bold ${
                      a.returnPct > 0
                        ? 'text-[var(--main-red)]'
                        : a.returnPct < 0
                          ? 'text-[var(--main-blue)]'
                          : ''
                    }`}
                  >
                    {a.returnPct >= 0 ? '+' : ''}
                    {a.returnPct.toFixed(2)}%
                  </td>
                  <td className={tdClass}>{a.orderCount}</td>
                  <td className={`${tdClass} max-w-40 truncate`}>{a.strategyName ?? '—'}</td>
                  <td className={tdClass}>
                    <div className="flex gap-1.5">
                      {a.status === 'ACTIVE' && (
                        <button disabled={busy} onClick={() => runAction(a, 'pause')} className={actionBtnClass}>
                          일시 중지
                        </button>
                      )}
                      {a.status === 'PAUSED' && (
                        <button disabled={busy} onClick={() => runAction(a, 'resume')} className={actionBtnClass}>
                          재개
                        </button>
                      )}
                      <button disabled={busy} onClick={() => runAction(a, 'reset')} className={dangerBtnClass}>
                        초기화
                      </button>
                      <button disabled={busy} onClick={() => runAction(a, 'delete')} className={dangerBtnClass}>
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
