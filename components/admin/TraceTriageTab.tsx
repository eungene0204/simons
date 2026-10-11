'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  adminFetch,
  formatDateTime,
  ErrorNotice,
  LoadingRow,
  EmptyRow,
  thClass,
  tdClass,
  inputClass,
  actionBtnClass,
} from './shared'

// 응답 형태 — backend/observability/triage.py::load + api/observability_routes.py
interface TriageSample {
  trace_id: string
  ts: string | null
  turn_kind: string | null
  model: string | null
  user_input: string
  detail: string | null
}

interface TriageGroup {
  signal: string
  tier: string
  label: string
  key: string
  count: number
  sessions: number
  environments: string[]
  samples: TriageSample[]
}

interface TriageResponse {
  range: [string, string] | null
  total: number
  groups: TriageGroup[]
  tiers: string[]
  retention_days: number
}

const TIER_TONE: Record<string, string> = {
  '결함 후보': 'bg-red-500/15 text-red-300',
  '확인 필요': 'bg-amber-500/15 text-amber-300',
  '제품 공백': 'bg-sky-500/15 text-sky-300',
  인프라: 'bg-white/10 text-gray-300',
}

function TierBadge({ tier }: { tier: string }) {
  return (
    <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${TIER_TONE[tier] ?? 'bg-white/10 text-gray-300'}`}>
      {tier}
    </span>
  )
}

function SampleList({ samples }: { samples: TriageSample[] }) {
  return (
    <ul className="mt-2 space-y-2 whitespace-normal">
      {samples.map((s) => (
        <li key={`${s.trace_id}-${s.ts}`} className="rounded-lg bg-white/[0.03] px-3 py-2">
          <p className="text-xs font-bold text-gray-500">
            <span className="font-mono text-gray-300">{s.trace_id}</span>
            {' · '}
            {formatDateTime(s.ts)}
            {s.turn_kind && ` · ${s.turn_kind}`}
            {s.model && ` · ${s.model}`}
          </p>
          {s.user_input && <p className="mt-1 text-sm text-gray-200">입력: {s.user_input}</p>}
          {s.detail && <p className="mt-0.5 text-sm text-gray-400">근거: {s.detail}</p>}
        </li>
      ))}
    </ul>
  )
}

export default function TraceTriageTab() {
  const [days, setDays] = useState(0) // 0 = 보관 중 전체
  const [tier, setTier] = useState('')
  const [data, setData] = useState<TriageResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  // 기간을 연달아 바꾸면 늦게 온 이전 응답이 새 결과를 덮는다 — 마지막 요청만 반영한다.
  const requestSeq = useRef(0)

  const load = useCallback(async () => {
    const seq = ++requestSeq.current
    setLoading(true)
    setError('')
    try {
      const query = days ? `?days=${days}` : ''
      const result = await adminFetch<TriageResponse>(`/api/admin/trace-triage${query}`)
      if (seq === requestSeq.current) setData(result)
    } catch (e) {
      if (seq === requestSeq.current) setError(e instanceof Error ? e.message : '조회 실패')
    } finally {
      if (seq === requestSeq.current) setLoading(false)
    }
  }, [days])

  useEffect(() => {
    load()
  }, [load])

  const groups = (data?.groups ?? []).filter((g) => !tier || g.tier === tier)
  const tierCount = (name: string) =>
    (data?.groups ?? []).filter((g) => g.tier === name).reduce((sum, g) => sum + g.count, 0)
  const retention = data?.retention_days ?? 3

  return (
    <div className="space-y-4">
      {error && <ErrorNotice message={error} />}

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className={`${inputClass} w-40`}
        >
          <option value={0}>보관 중 전체({retention}일)</option>
          <option value={1}>오늘</option>
          {retention >= 2 && <option value={2}>최근 2일</option>}
        </select>
        <button
          className={`${actionBtnClass} ${tier === '' ? 'bg-white/10 text-white' : ''}`}
          onClick={() => setTier('')}
        >
          전체
        </button>
        {(data?.tiers ?? []).map((name) => (
          <button
            key={name}
            className={`${actionBtnClass} ${tier === name ? 'bg-white/10 text-white' : ''}`}
            onClick={() => setTier(name)}
          >
            {name} {tierCount(name)}
          </button>
        ))}
        <button className={actionBtnClass} onClick={load}>
          새로고침
        </button>
        <p className="ml-auto text-xs font-bold text-gray-600">
          원문 {retention}일 보관 · 판정은 구조 신호만
        </p>
      </div>

      {data && (
        <p className="text-xs font-bold text-gray-500">
          {data.range ? `${data.range[0]} ~ ${data.range[1]}` : '보관 중인 Trace 없음'} · Trace {data.total}건 · 묶음{' '}
          {data.groups.length}개
        </p>
      )}

      <div className="flat-card overflow-x-auto rounded-xl">
        <table className="w-full">
          <thead className="border-b border-white/5">
            <tr>
              <th className={thClass}>등급</th>
              <th className={thClass}>신호</th>
              <th className={thClass}>판별 키</th>
              <th className={thClass}>건수</th>
              <th className={thClass}>세션</th>
              <th className={thClass}>환경</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <LoadingRow colSpan={6} />
            ) : groups.length === 0 ? (
              <EmptyRow colSpan={6} label="실패 후보가 없습니다" />
            ) : (
              groups.map((g) => {
                const id = `${g.signal}|${g.key}`
                const open = expanded === id
                return (
                  <tr
                    key={id}
                    onClick={() => setExpanded(open ? null : id)}
                    className="cursor-pointer border-b border-white/5 align-top last:border-0 hover:bg-white/[0.03]"
                  >
                    <td className={tdClass}>
                      <TierBadge tier={g.tier} />
                    </td>
                    <td className={`${tdClass} max-w-72 whitespace-normal`}>
                      <p className="font-mono text-xs text-gray-300">{g.signal}</p>
                      <p className="text-xs text-gray-500">{g.label}</p>
                    </td>
                    <td className={`${tdClass} max-w-[36rem] whitespace-normal`}>
                      <span className={open ? '' : 'line-clamp-2'}>{g.key}</span>
                      {open && <SampleList samples={g.samples} />}
                    </td>
                    <td className={tdClass}>{g.count}</td>
                    <td className={tdClass}>{g.sessions}</td>
                    <td className={tdClass}>{g.environments.join(', ')}</td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
