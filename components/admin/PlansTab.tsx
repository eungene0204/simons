'use client'

import { useCallback, useEffect, useState } from 'react'
import { adminFetch, ErrorNotice, actionBtnClass, inputClass } from './shared'

interface PlanRow {
  planId: string
  name: string
  monthlyPrice: number
  defaults: {
    monthlyBacktestLimit: number
    maxStrategies: number // -1 = 무제한
    maxVirtualAccounts: number
  }
  overrides: {
    monthlyBacktestLimit: number | null
    maxStrategies: number | null
    maxVirtualAccounts: number | null
  }
}

const FIELDS = [
  { key: 'monthlyBacktestLimit', label: '월 백테스트 한도' },
  { key: 'maxStrategies', label: '전략 개수 (-1 = 무제한)' },
  { key: 'maxVirtualAccounts', label: '가상계좌 개수' },
] as const

type FieldKey = (typeof FIELDS)[number]['key']

export default function PlansTab() {
  const [plans, setPlans] = useState<PlanRow[]>([])
  const [drafts, setDrafts] = useState<Record<string, Record<FieldKey, string>>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async () => {
    setError('')
    try {
      const res = await adminFetch<{ plans: PlanRow[] }>('/api/admin/plans')
      setPlans(res.plans)
      const next: Record<string, Record<FieldKey, string>> = {}
      for (const p of res.plans) {
        next[p.planId] = {
          monthlyBacktestLimit: String(
            p.overrides.monthlyBacktestLimit ?? p.defaults.monthlyBacktestLimit
          ),
          maxStrategies: String(p.overrides.maxStrategies ?? p.defaults.maxStrategies),
          maxVirtualAccounts: String(
            p.overrides.maxVirtualAccounts ?? p.defaults.maxVirtualAccounts
          ),
        }
      }
      setDrafts(next)
      setLoaded(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const save = async (plan: PlanRow) => {
    const draft = drafts[plan.planId]
    if (!draft) return
    setBusy(true)
    setError('')
    try {
      // 기본값과 같으면 null(오버라이드 해제), 다르면 해당 값으로 저장
      const payload: Record<string, unknown> = { planId: plan.planId }
      for (const f of FIELDS) {
        const n = Number(draft[f.key])
        if (!Number.isInteger(n)) {
          throw new Error(`${f.label} 값이 올바르지 않습니다.`)
        }
        payload[f.key] = n === plan.defaults[f.key] ? null : n
      }
      await adminFetch('/api/admin/plans', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '저장 실패')
    } finally {
      setBusy(false)
    }
  }

  if (!loaded && !error) {
    return <p className="text-sm font-bold text-gray-600">불러오는 중…</p>
  }

  return (
    <div className="space-y-4">
      {error && <ErrorNotice message={error} />}
      <p className="text-xs font-bold text-gray-500">
        기본값과 다른 값을 저장하면 오버라이드로 적용되고, 기본값과 같게 저장하면 오버라이드가
        해제됩니다. 사용자 개별 플랜 변경은 Users 탭에서 수행합니다.
      </p>

      <div className="grid gap-4 lg:grid-cols-3">
        {plans.map((p) => {
          const draft = drafts[p.planId]
          const hasOverride = FIELDS.some((f) => p.overrides[f.key] != null)
          return (
            <div key={p.planId} className="flat-card rounded-xl px-5 py-4">
              <div className="mb-4 flex items-center justify-between">
                <p className="text-base font-black text-white">{p.name}</p>
                <span className="text-xs font-bold text-gray-500">
                  월 {p.monthlyPrice.toLocaleString()}원
                  {hasOverride && (
                    <span className="ml-2 rounded-md bg-amber-500/15 px-1.5 py-0.5 text-amber-400">
                      오버라이드
                    </span>
                  )}
                </span>
              </div>

              <div className="space-y-3">
                {FIELDS.map((f) => (
                  <div key={f.key}>
                    <label className="mb-1 block text-xs font-bold text-gray-500">
                      {f.label}
                      <span className="ml-1.5 text-gray-600">기본 {p.defaults[f.key]}</span>
                    </label>
                    <input
                      type="number"
                      value={draft?.[f.key] ?? ''}
                      onChange={(e) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [p.planId]: { ...prev[p.planId], [f.key]: e.target.value },
                        }))
                      }
                      className={`${inputClass} w-full`}
                    />
                  </div>
                ))}
              </div>

              <button
                disabled={busy}
                onClick={() => save(p)}
                className={`${actionBtnClass} mt-4 w-full py-2`}
              >
                저장
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
