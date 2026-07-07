'use client'

// 관리자 콘솔 탭들이 공유하는 최소 유틸/프리미티브

export async function adminFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.error || `요청 실패 (${res.status})`)
  }
  return res.json()
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(
    d.getDate()
  ).padStart(2, '0')}`
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  return `${formatDate(value)} ${String(d.getHours()).padStart(2, '0')}:${String(
    d.getMinutes()
  ).padStart(2, '0')}`
}

export function formatKrw(value: number): string {
  return `${Math.round(value).toLocaleString()}원`
}

export function PlanBadge({ plan }: { plan: string }) {
  const styles: Record<string, string> = {
    FREE: 'bg-gray-500/15 text-gray-400',
    PRO: 'bg-sky-500/15 text-sky-400',
    PREMIUM: 'bg-purple-500/15 text-purple-400',
  }
  return (
    <span
      className={`inline-flex rounded-md px-2 py-0.5 text-xs font-bold ${styles[plan] ?? styles.FREE}`}
    >
      {plan}
    </span>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    ACTIVE: 'bg-emerald-500/15 text-emerald-400',
    PAUSED: 'bg-amber-500/15 text-amber-400',
    SUSPENDED: 'bg-amber-500/15 text-amber-400',
    CLOSED: 'bg-gray-500/15 text-gray-400',
    DELETED: 'bg-red-500/15 text-red-400',
  }
  return (
    <span
      className={`inline-flex rounded-md px-2 py-0.5 text-xs font-bold ${styles[status] ?? 'bg-gray-500/15 text-gray-400'}`}
    >
      {status}
    </span>
  )
}

export function Pagination({
  page,
  total,
  pageSize,
  onChange,
}: {
  page: number
  total: number
  pageSize: number
  onChange: (page: number) => void
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="mt-4 flex items-center justify-between text-xs font-bold text-gray-500">
      <span>
        총 {total.toLocaleString()}건 · {page}/{totalPages} 페이지
      </span>
      <div className="flex gap-2">
        <button
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          className="rounded-md border border-white/10 px-3 py-1.5 text-gray-300 disabled:opacity-30"
        >
          이전
        </button>
        <button
          onClick={() => onChange(page + 1)}
          disabled={page >= totalPages}
          className="rounded-md border border-white/10 px-3 py-1.5 text-gray-300 disabled:opacity-30"
        >
          다음
        </button>
      </div>
    </div>
  )
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm font-bold text-red-400">
      {message}
    </div>
  )
}

export function LoadingRow({ colSpan }: { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="py-10 text-center text-sm font-bold text-gray-600">
        불러오는 중…
      </td>
    </tr>
  )
}

export function EmptyRow({ colSpan, label = '데이터가 없습니다' }: { colSpan: number; label?: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="py-10 text-center text-sm font-bold text-gray-600">
        {label}
      </td>
    </tr>
  )
}

export const thClass =
  'px-3 py-2.5 text-left text-xs font-bold text-gray-500 whitespace-nowrap'
export const tdClass = 'px-3 py-2.5 text-sm text-gray-200 whitespace-nowrap'
export const actionBtnClass =
  'rounded-md border border-white/10 px-2.5 py-1 text-xs font-bold text-gray-300 hover:bg-white/5'
export const dangerBtnClass =
  'rounded-md border border-red-500/30 px-2.5 py-1 text-xs font-bold text-red-400 hover:bg-red-500/10'
export const inputClass =
  'rounded-md border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-white placeholder:text-gray-600 focus:border-white/25 focus:outline-none'
