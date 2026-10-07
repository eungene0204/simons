import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import BacktestsTab from './BacktestsTab'
import { adminFetch } from './shared'

vi.mock('./shared', () => ({
  adminFetch: vi.fn(), formatDateTime: (v: string) => v,
  PlanBadge: () => null, Pagination: () => null, ErrorNotice: () => null,
  LoadingRow: () => null, EmptyRow: () => null,
  thClass: '', tdClass: '', actionBtnClass: '',
}))

beforeEach(() => { vi.resetAllMocks() })

it('labels saved results honestly and ignores an older user detail response', async () => {
  let resolveFirst!: (v: unknown) => void
  let resolveSecond!: (v: unknown) => void
  vi.mocked(adminFetch).mockImplementation((url) => {
    if (url.includes('userId=1')) return new Promise((r) => { resolveFirst = r }) as any
    if (url.includes('userId=2')) return new Promise((r) => { resolveSecond = r }) as any
    return Promise.resolve({ total: 2, page: 1, pageSize: 20, users: [1, 2].map((id) => ({
      id, email: `user${id}`, planTier: 'FREE', used: 1, limit: 50, remaining: 49, runTotal: 1,
    })) }) as any
  })
  render(<BacktestsTab />)
  await screen.findByText('user1')
  expect(screen.getByText('최근 저장 결과')).toBeInTheDocument()
  fireEvent.click(screen.getAllByText('보기')[0])
  fireEvent.click(screen.getByText('보기'))
  await act(async () => resolveSecond({ recentRuns: [{ id: 'b', strategyName: 'second result', savedAt: 'today' }] }))
  await waitFor(() => expect(screen.getByText('second result')).toBeInTheDocument())
  await act(async () => resolveFirst({ recentRuns: [{ id: 'a', strategyName: 'first result', savedAt: 'yesterday' }] }))
  expect(screen.queryByText('first result')).not.toBeInTheDocument()
  expect(screen.getByText('second result')).toBeInTheDocument()
})
