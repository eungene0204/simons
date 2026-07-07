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
        <StatCard label="이번 달 백테스트" value={data.backtestsThisMonth.toLocaleString()} />
        <StatCard label="활성 가상계좌" value={data.activeVirtualAccounts.toLocaleString()} />
        <StatCard label="전략 총 개수" value={data.totalStrategies.toLocaleString()} />
        <StatCard label="Free" value={(data.usersByPlan.FREE ?? 0).toLocaleString()} />
        <StatCard label="Pro" value={(data.usersByPlan.PRO ?? 0).toLocaleString()} />
        <StatCard label="Premium" value={(data.usersByPlan.PREMIUM ?? 0).toLocaleString()} />
      </div>

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
