import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import TraceTriageTab from './TraceTriageTab'
import { adminFetch } from './shared'

vi.mock('./shared', () => ({
  adminFetch: vi.fn(), formatDateTime: (v: string) => v,
  ErrorNotice: ({ message }: { message: string }) => <p>{message}</p>,
  LoadingRow: () => null, EmptyRow: ({ label }: { label: string }) => <tr><td>{label}</td></tr>,
  thClass: '', tdClass: '', inputClass: '', actionBtnClass: '',
}))

const group = (signal: string, tier: string, count: number) => ({
  signal, tier, label: `${signal} 설명`, key: `${signal}-key`, count, sessions: 1,
  environments: ['production'],
  samples: [{ trace_id: `${signal}-trace`, ts: 't', turn_kind: 'create', model: 'm', user_input: `${signal} 입력`, detail: '근거 문장' }],
})
const body = (groups: unknown[], total = 5) => ({
  range: ['2026-10-09', '2026-10-11'], total, groups,
  tiers: ['결함 후보', '확인 필요', '제품 공백', '인프라'], retention_days: 3,
})

beforeEach(() => { vi.resetAllMocks() })

it('shows groups, filters by tier and expands samples on click', async () => {
  vi.mocked(adminFetch).mockResolvedValue(body([group('planner_error', '결함 후보', 50), group('infra_error', '인프라', 4)]) as any)
  render(<TraceTriageTab />)
  await screen.findByText('planner_error')
  expect(screen.getByText('결함 후보 50')).toBeInTheDocument()
  expect(screen.getByText(/Trace 5건 · 묶음 2개/)).toBeInTheDocument()

  fireEvent.click(screen.getByText('인프라 4'))
  expect(screen.queryByText('planner_error')).not.toBeInTheDocument()
  expect(screen.getByText('infra_error')).toBeInTheDocument()

  expect(screen.queryByText('입력: infra_error 입력')).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('infra_error'))
  expect(screen.getByText('입력: infra_error 입력')).toBeInTheDocument()
  expect(screen.getByText('infra_error-trace')).toBeInTheDocument()
})

it('requests the chosen period and ignores a slower earlier response', async () => {
  let resolveAll!: (v: unknown) => void
  vi.mocked(adminFetch).mockImplementation((url) => {
    if (url === '/api/admin/trace-triage') return new Promise((r) => { resolveAll = r }) as any
    return Promise.resolve(body([group('ask_repeat', '결함 후보', 1)], 1)) as any
  })
  render(<TraceTriageTab />)
  fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } })
  await screen.findByText('ask_repeat')
  expect(adminFetch).toHaveBeenLastCalledWith('/api/admin/trace-triage?days=1')
  await act(async () => resolveAll(body([group('planner_error', '결함 후보', 50)])))
  await waitFor(() => expect(screen.getByText('ask_repeat')).toBeInTheDocument())
  expect(screen.queryByText('planner_error')).not.toBeInTheDocument()
})

it('shows an empty state when nothing failed', async () => {
  vi.mocked(adminFetch).mockResolvedValue({ ...body([], 0), range: null } as any)
  render(<TraceTriageTab />)
  await screen.findByText('실패 후보가 없습니다')
  expect(screen.getByText(/보관 중인 Trace 없음/)).toBeInTheDocument()
})
