'use client'

import { useEffect, useState } from 'react'
import { adminFetch, formatDateTime, ErrorNotice } from './shared'

interface OverviewData {
  totalUsers: number
  todaySignups: number
  usersByPlan: Record<string, number>
  backtestsThisMonth: number
  activeVirtualAccounts: number
  totalStrategies: number
  recentAdminActions: {
    id: string
    adminEmail: string
    action: string
    targetType: string | null
    targetId: string | null
    createdAt: string
  }[]
  revenueFunnel?: {
    windowDays: number
    limitConversion: { users: number; converted: number; byCode: Record<string, number> }
    signupSources: { source: string; signups: number; backtested: number; paid: number }[]
  }
}

const LIMIT_LABELS: Record<string, string> = {
  PLAN_LIMIT_BACKTESTS: '백테스트',
  PLAN_LIMIT_STRATEGIES: '저장 전략',
  PLAN_LIMIT_ACCOUNTS: '가상계좌',
}

function percent(part: number, whole: number): string {
  return whole > 0 ? `${Math.round((part / whole) * 100)}%` : '—'
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flat-card rounded-xl px-5 py-4">
      <p className="text-xs font-bold text-gray-500">{label}</p>
      <p className="mt-1.5 text-2xl font-black text-white">{value}</p>
    </div>
  )
}

export default function OverviewTab() {
  const [data, setData] = useState<OverviewData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    adminFetch<OverviewData>('/api/admin/overview')
      .then(setData)
      .catch((e) => setError(e.message))
  }, [])

  if (error) return <ErrorNotice message={error} />
  if (!data) return <p className="text-sm font-bold text-gray-600">불러오는 중…</p>

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
        <StatCard label="전체 사용자" value={data.totalUsers.toLocaleString()} />
        <StatCard label="오늘 가입" value={data.todaySignups.toLocaleString()} />
        <StatCard label="현재 주기 백테스트" value={data.backtestsThisMonth.toLocaleString()} />
        <StatCard label="활성 가상계좌" value={data.activeVirtualAccounts.toLocaleString()} />
        <StatCard label="전략 총 개수" value={data.totalStrategies.toLocaleString()} />
        <StatCard label="Free" value={(data.usersByPlan.FREE ?? 0).toLocaleString()} />
        <StatCard label="Pro" value={(data.usersByPlan.PRO ?? 0).toLocaleString()} />
        <StatCard label="Premium" value={(data.usersByPlan.PREMIUM ?? 0).toLocaleString()} />
      </div>

      {data.revenueFunnel && (
        <div className="grid gap-3 md:grid-cols-2">
          <div className="flat-card rounded-xl px-5 py-4">
            <p className="mb-3 text-xs font-bold text-gray-500">
              한도 도달 → 14일 안 결제 (최근 {data.revenueFunnel.windowDays}일 도달)
            </p>
            <p className="text-2xl font-black text-white">
              {data.revenueFunnel.limitConversion.converted.toLocaleString()} /{' '}
              {data.revenueFunnel.limitConversion.users.toLocaleString()}명
              <span className="ml-2 text-sm text-gray-400">
                {percent(data.revenueFunnel.limitConversion.converted, data.revenueFunnel.limitConversion.users)}
              </span>
            </p>
            <ul className="mt-2 space-y-1 text-xs font-bold text-gray-400">
              {Object.entries(data.revenueFunnel.limitConversion.byCode).map(([code, n]) => (
                <li key={code}>
                  {LIMIT_LABELS[code] ?? code} 한도 {n.toLocaleString()}명
                </li>
              ))}
            </ul>
          </div>
          <div className="flat-card rounded-xl px-5 py-4">
            <p className="mb-3 text-xs font-bold text-gray-500">
              가입 유입 경로 (최근 {data.revenueFunnel.windowDays}일 가입)
            </p>
            {data.revenueFunnel.signupSources.length === 0 ? (
              <p className="text-sm font-bold text-gray-600">기록이 없습니다</p>
            ) : (
              <table className="w-full text-xs font-bold">
                <thead className="text-gray-500">
                  <tr>
                    <th className="text-left">경로(utm_source)</th>
                    <th className="text-right">가입</th>
                    <th className="text-right">백테스트</th>
                    <th className="text-right">결제</th>
                  </tr>
                </thead>
                <tbody className="text-gray-200">
                  {data.revenueFunnel.signupSources.map((r) => (
                    <tr key={r.source}>
                      <td>{r.source}</td>
                      <td className="text-right">{r.signups.toLocaleString()}</td>
                      <td className="text-right">{r.backtested.toLocaleString()}</td>
                      <td className="text-right">{r.paid.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      <div className="flat-card rounded-xl px-5 py-4">
        <p className="mb-3 text-xs font-bold text-gray-500">최근 관리자 작업</p>
        {data.recentAdminActions.length === 0 ? (
          <p className="text-sm font-bold text-gray-600">기록이 없습니다</p>
        ) : (
          <ul className="space-y-2">
            {data.recentAdminActions.map((a) => (
              <li key={a.id} className="flex items-center justify-between text-sm">
                <span className="font-bold text-gray-200">
                  {a.action}
                  <span className="ml-2 text-xs font-bold text-gray-500">
                    {a.targetType ?? ''} {a.targetId ?? ''}
                  </span>
                </span>
                <span className="text-xs font-bold text-gray-500">
                  {a.adminEmail} · {formatDateTime(a.createdAt)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
