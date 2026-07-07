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
} from './shared'

interface AuditLog {
  id: string
  adminEmail: string
  action: string
  targetType: string | null
  targetId: string | null
  targetUserId: number | null
  beforeJson: string | null
  afterJson: string | null
  ip: string | null
  createdAt: string
}

interface AuditResponse {
  total: number
  page: number
  pageSize: number
  logs: AuditLog[]
}

export default function AuditLogsTab() {
  const [action, setAction] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<AuditResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ page: String(page) })
      if (action) params.set('action', action)
      setData(await adminFetch<AuditResponse>(`/api/admin/audit?${params}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    } finally {
      setLoading(false)
    }
  }, [action, page])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="space-y-4">
      {error && <ErrorNotice message={error} />}

      <div className="flex items-center justify-between">
        <input
          value={action}
          onChange={(e) => {
            setAction(e.target.value)
            setPage(1)
          }}
          placeholder="작업 종류 검색 (예: USER_SUSPEND)"
          className={`${inputClass} w-72`}
        />
        <p className="text-xs font-bold text-gray-600">감사 로그는 삭제할 수 없습니다</p>
      </div>

      <div className="flat-card overflow-x-auto rounded-xl">
        <table className="w-full">
          <thead className="border-b border-white/5">
            <tr>
              <th className={thClass}>시간</th>
              <th className={thClass}>관리자</th>
              <th className={thClass}>작업</th>
              <th className={thClass}>대상</th>
              <th className={thClass}>변경 전</th>
              <th className={thClass}>변경 후</th>
              <th className={thClass}>IP</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <LoadingRow colSpan={7} />
            ) : !data || data.logs.length === 0 ? (
              <EmptyRow colSpan={7} />
            ) : (
              data.logs.map((log) => (
                <tr key={log.id} className="border-b border-white/5 last:border-0 align-top">
                  <td className={tdClass}>{formatDateTime(log.createdAt)}</td>
                  <td className={tdClass}>{log.adminEmail}</td>
                  <td className={`${tdClass} font-bold`}>{log.action}</td>
                  <td className={tdClass}>
                    {log.targetType ?? '—'}
                    {log.targetId && (
                      <span className="ml-1 text-xs text-gray-500">{log.targetId}</span>
                    )}
                  </td>
                  <td className={`${tdClass} max-w-52`}>
                    <code className="block truncate text-xs text-gray-500">
                      {log.beforeJson ?? '—'}
                    </code>
                  </td>
                  <td className={`${tdClass} max-w-52`}>
                    <code className="block truncate text-xs text-gray-500">
                      {log.afterJson ?? '—'}
                    </code>
                  </td>
                  <td className={tdClass}>{log.ip ?? '—'}</td>
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
