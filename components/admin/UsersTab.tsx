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
import { PRORATED_REFUND_ENABLED } from '@/lib/plans'

interface AdminUser {
  id: number
  email: string
  name: string
  isGuest: boolean
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

// 중도 해지 정산(부분 환불) 미리보기 — 약관 제12조 제9항
interface RefundPreview {
  available: boolean
  reason?: string
  planId?: string
  billingCycle?: string
  paidAmount?: number
  paidAt?: string
  periodEnd?: string
  totalDays?: number
  usedDays?: number
  remainingDays?: number
  refundAmount?: number
  usage?: {
    backtestsThisPeriod: number
    strategiesSincePaid: number
    accountsSincePaid: number
    validationsSincePaid: number
  }
}

interface UsersResponse {
  total: number
  page: number
  pageSize: number
  users: AdminUser[]
}

// 게스트(테스터) 계정 표시 — 이메일이 합성 도메인(guest.nullstock.im)이면 서버가 isGuest를 준다.
function GuestBadge() {
  return (
    <span className="ml-1.5 inline-flex rounded-md bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-bold text-amber-400">
      GUEST
    </span>
  )
}

export default function UsersTab() {
  const [q, setQ] = useState('')
  const [plan, setPlan] = useState('')
  const [status, setStatus] = useState('')
  const [kind, setKind] = useState('')
  const [sort, setSort] = useState('createdAt')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<UsersResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<AdminUser | null>(null)
  const [busy, setBusy] = useState(false)
  const [refund, setRefund] = useState<RefundPreview | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ page: String(page), sort })
      if (q) params.set('q', q)
      if (plan) params.set('plan', plan)
      if (status) params.set('status', status)
      if (kind) params.set('kind', kind)
      const res = await adminFetch<UsersResponse>(`/api/admin/users?${params}`)
      setData(res)
      setSelected((prev) => res.users.find((u) => u.id === prev?.id) ?? prev)
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    } finally {
      setLoading(false)
    }
  }, [q, plan, status, kind, sort, page])

  useEffect(() => {
    load()
  }, [load])

  // 선택이 바뀌면 앞 사용자의 정산액을 반드시 버린다 — 남아 있으면 엉뚱한 사람에게 집행된다.
  useEffect(() => {
    setRefund(null)
  }, [selected?.id])

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

  const loadRefundPreview = async () => {
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      setRefund(
        await adminFetch<RefundPreview>(`/api/admin/users/refund?userId=${selected.id}`)
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : '정산액 조회 실패')
    } finally {
      setBusy(false)
    }
  }

  // prorated = 일할 정산(약관 12조 9항), full = 미사용 전액 환불(12조 2항)
  const executeRefund = async (mode: 'prorated' | 'full') => {
    if (!selected || !refund?.available) return
    const amount = mode === 'full' ? refund.paidAmount : refund.refundAmount
    if (!amount) return
    setBusy(true)
    setError('')
    try {
      await adminFetch('/api/admin/users/refund', {
        method: 'POST',
        body: JSON.stringify({ userId: selected.id, mode, expectedRefundAmount: amount }),
      })
      setRefund(null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '환불 집행 실패')
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
        <select
          value={kind}
          onChange={(e) => {
            setKind(e.target.value)
            setPage(1)
          }}
          className={inputClass}
        >
          <option value="">모든 계정</option>
          <option value="guest">게스트 계정</option>
          <option value="member">일반 회원</option>
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
                    <td className={`${tdClass} font-bold`}>
                      {u.email}
                      {u.isGuest && <GuestBadge />}
                    </td>
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
                  {selected.isGuest && <GuestBadge />}
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

            <p className="mb-1.5 text-xs font-bold text-gray-500">중도 해지 정산</p>
            <div className="mb-4 space-y-2">
              <button
                disabled={busy}
                onClick={loadRefundPreview}
                className={actionBtnClass}
                data-testid="refund-preview-button"
              >
                정산액 확인
              </button>
              {refund && !refund.available && (
                <p className="text-xs font-bold text-gray-500">{refund.reason}</p>
              )}
              {refund?.available && (
                <div className="space-y-2" data-testid="refund-preview">
                  <dl className="space-y-1 text-xs font-bold">
                    <div className="flex justify-between">
                      <dt className="text-gray-500">결제 금액</dt>
                      <dd className="text-gray-200">
                        {refund.paidAmount?.toLocaleString('ko-KR')}원 (
                        {refund.billingCycle === 'yearly' ? '연간' : '월간'})
                      </dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-gray-500">이용 / 전체</dt>
                      <dd className="text-gray-200">
                        {refund.usedDays}일 / {refund.totalDays}일
                      </dd>
                    </div>
                    {PRORATED_REFUND_ENABLED && (
                      <div className="flex justify-between">
                        <dt className="text-gray-500">일할 환불액</dt>
                        <dd className="text-gray-200">
                          {refund.refundAmount?.toLocaleString('ko-KR')}원
                        </dd>
                      </div>
                    )}
                    {/* 결제 이후 유료 기능 사용 흔적 — 2항(미사용 전액 환불) 판단 근거 */}
                    <div className="flex justify-between" data-testid="refund-usage-evidence">
                      <dt className="text-gray-500">결제 후 사용</dt>
                      <dd className="text-gray-200">
                        백테스트 {refund.usage?.backtestsThisPeriod ?? 0} · 전략{' '}
                        {refund.usage?.strategiesSincePaid ?? 0} · 계좌{' '}
                        {refund.usage?.accountsSincePaid ?? 0} · 검증{' '}
                        {refund.usage?.validationsSincePaid ?? 0}
                      </dd>
                    </div>
                  </dl>
                  <div className="flex flex-wrap gap-1.5">
                    {PRORATED_REFUND_ENABLED && (
                    <button
                      disabled={busy || !refund.refundAmount}
                      onClick={() => {
                        if (
                          window.confirm(
                            `${selected.email} 사용자에게 일할 정산 ${refund.refundAmount?.toLocaleString('ko-KR')}원을 환불하고 즉시 FREE로 전환합니다. 진행할까요?`
                          )
                        ) {
                          executeRefund('prorated')
                        }
                      }}
                      className={dangerBtnClass}
                      data-testid="refund-execute-button"
                    >
                      일할 환불 집행
                    </button>
                    )}
                    <button
                      disabled={busy || !refund.paidAmount}
                      onClick={() => {
                        if (
                          window.confirm(
                            `[약관 12조 2항] ${selected.email} 사용자에게 결제 금액 전액 ${refund.paidAmount?.toLocaleString('ko-KR')}원을 환불하고 즉시 FREE로 전환합니다. 결제 후 유료 기능을 사용하지 않았는지 확인했습니까?`
                          )
                        ) {
                          executeRefund('full')
                        }
                      }}
                      className={dangerBtnClass}
                      data-testid="refund-full-button"
                    >
                      전액 환불 (2항)
                    </button>
                  </div>
                </div>
              )}
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
