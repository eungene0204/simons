'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  adminFetch,
  formatDate,
  formatDateTime,
  PlanBadge,
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

interface AdminUser {
  id: number
  email: string
  name: string
  planTier: string
  role: string
  status: string
  createdAt: string
  lastLoginAt: string | null
  strategyCount: number
  accountCount: number
  backtestsUsed: number
  backtestLimit: number
}

interface UsersResponse {
  total: number
  page: number
  pageSize: number
  users: AdminUser[]
}

export default function UsersTab() {
  const [q, setQ] = useState('')
  const [plan, setPlan] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('createdAt')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<UsersResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<AdminUser | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ page: String(page), sort })
      if (q) params.set('q', q)
      if (plan) params.set('plan', plan)
      if (status) params.set('status', status)
      const res = await adminFetch<UsersResponse>(`/api/admin/users?${params}`)
      setData(res)
      setSelected((prev) => res.users.find((u) => u.id === prev?.id) ?? prev)
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    } finally {
      setLoading(false)
    }
  }, [q, plan, status, sort, page])

  useEffect(() => {
    load()
  }, [load])

  const runAction = async (action: string, extra: Record<string, unknown> = {}) => {
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      await adminFetch('/api/admin/users', {
        method: 'PATCH',
        body: JSON.stringify({ userId: selected.id, action, ...extra }),
      })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '작업 실패')
    } finally {
      setBusy(false)
    }
  }

  const adjustUsage = async (action: 'reset' | 'increase' | 'decrease') => {
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      await adminFetch('/api/admin/backtests', {
        method: 'PATCH',
        body: JSON.stringify({ userId: selected.id, action }),
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

      {/* 검색/필터 */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setPage(1)
          }}
          placeholder="이메일 검색"
          className={`${inputClass} w-56`}
        />
        <select
          value={plan}
          onChange={(e) => {
            setPlan(e.target.value)
            setPage(1)
          }}
          className={inputClass}
        >
          <option value="">모든 플랜</option>
          <option value="FREE">Free</option>
          <option value="PRO">Pro</option>
          <option value="PREMIUM">Premium</option>
        </select>
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
          <option value="SUSPENDED">SUSPENDED</option>
          <option value="DELETED">DELETED</option>
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} className={inputClass}>
          <option value="createdAt">가입일순</option>
          <option value="lastLoginAt">최근 로그인순</option>
          <option value="email">이메일순</option>
        </select>
      </div>

      <div className="flex gap-4">
        {/* 목록 */}
        <div className="flat-card min-w-0 flex-1 overflow-x-auto rounded-xl">
          <table className="w-full">
            <thead className="border-b border-white/5">
              <tr>
                <th className={thClass}>이메일</th>
                <th className={thClass}>플랜</th>
                <th className={thClass}>상태</th>
                <th className={thClass}>전략</th>
                <th className={thClass}>계좌</th>
                <th className={thClass}>백테스트</th>
                <th className={thClass}>가입일</th>
                <th className={thClass}>최근 로그인</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <LoadingRow colSpan={8} />
              ) : !data || data.users.length === 0 ? (
                <EmptyRow colSpan={8} />
              ) : (
                data.users.map((u) => (
                  <tr
                    key={u.id}
                    onClick={() => setSelected(u)}
                    className={`cursor-pointer border-b border-white/5 last:border-0 hover:bg-white/[0.03] ${
                      selected?.id === u.id ? 'bg-white/[0.05]' : ''
                    }`}
                  >
                    <td className={`${tdClass} font-bold`}>{u.email}</td>
                    <td className={tdClass}>
                      <PlanBadge plan={u.planTier} />
                    </td>
                    <td className={tdClass}>
                      <StatusBadge status={u.status} />
                    </td>
                    <td className={tdClass}>{u.strategyCount}</td>
                    <td className={tdClass}>{u.accountCount}</td>
                    <td className={tdClass}>
                      {u.backtestsUsed}/{u.backtestLimit}
                    </td>
                    <td className={tdClass}>{formatDate(u.createdAt)}</td>
                    <td className={tdClass}>{formatDateTime(u.lastLoginAt)}</td>
                  </tr>
                ))
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

        {/* 상세 패널 */}
        {selected && (
          <div className="flat-card w-72 shrink-0 self-start rounded-xl px-5 py-4">
            <div className="mb-4 flex items-start justify-between">
              <div className="min-w-0">
                <p className="truncate text-sm font-black text-white">{selected.email}</p>
                <p className="text-xs font-bold text-gray-500">
                  {selected.name} · ID {selected.id}
                  {selected.role === 'ADMIN' && ' · ADMIN'}
                </p>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-xs font-bold text-gray-600 hover:text-gray-400"
              >
                닫기
              </button>
            </div>

            <dl className="mb-4 space-y-1.5 text-sm">
              <div className="flex justify-between">
                <dt className="font-bold text-gray-500">플랜</dt>
                <dd>
                  <PlanBadge plan={selected.planTier} />
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="font-bold text-gray-500">상태</dt>
                <dd>
                  <StatusBadge status={selected.status} />
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="font-bold text-gray-500">백테스트 사용량</dt>
                <dd className="font-bold text-gray-200">
                  {selected.backtestsUsed}/{selected.backtestLimit}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="font-bold text-gray-500">가입일</dt>
                <dd className="font-bold text-gray-200">{formatDate(selected.createdAt)}</dd>
              </div>
            </dl>

            <p className="mb-1.5 text-xs font-bold text-gray-500">플랜 변경</p>
            <div className="mb-4 flex gap-1.5">
              {['FREE', 'PRO', 'PREMIUM'].map((p) => (
                <button
                  key={p}
                  disabled={busy || selected.planTier === p}
                  onClick={() => runAction('changePlan', { planTier: p })}
                  className={`${actionBtnClass} disabled:opacity-30`}
                >
                  {p}
                </button>
              ))}
            </div>

            <p className="mb-1.5 text-xs font-bold text-gray-500">백테스트 사용량</p>
            <div className="mb-4 flex gap-1.5">
              <button disabled={busy} onClick={() => adjustUsage('reset')} className={actionBtnClass}>
                초기화
              </button>
              <button disabled={busy} onClick={() => adjustUsage('increase')} className={actionBtnClass}>
                +1
              </button>
              <button disabled={busy} onClick={() => adjustUsage('decrease')} className={actionBtnClass}>
                -1
              </button>
            </div>

            <p className="mb-1.5 text-xs font-bold text-gray-500">계정</p>
            <div className="flex flex-wrap gap-1.5">
              {selected.status !== 'SUSPENDED' && (
                <button disabled={busy} onClick={() => runAction('suspend')} className={dangerBtnClass}>
                  정지
                </button>
              )}
              {selected.status !== 'ACTIVE' && (
                <button disabled={busy} onClick={() => runAction('activate')} className={actionBtnClass}>
                  활성화
                </button>
              )}
              {selected.status !== 'DELETED' && (
                <button
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(`${selected.email} 사용자를 삭제할까요?`)) {
                      runAction('delete')
                    }
                  }}
                  className={dangerBtnClass}
                >
                  삭제
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
