import { describe, expect, it } from 'vitest'
import { isAccountUsable } from './accountAccess'

// 이용 기한(2026-09-17 게스트 입장 링크) — 기한 시각부터 로그인·세션 모두 거부한다.
describe('isAccountUsable', () => {
  const expiresAt = new Date('2026-10-01T00:00:00+09:00')

  it('기한이 없으면 ACTIVE만 본다', () => {
    expect(isAccountUsable({ status: 'ACTIVE', accessExpiresAt: null })).toBe(true)
    expect(isAccountUsable({ status: 'SUSPENDED', accessExpiresAt: null })).toBe(false)
    expect(isAccountUsable({ status: 'DELETED', accessExpiresAt: null })).toBe(false)
  })

  it('기한 직전까지는 쓸 수 있고, 기한 시각부터 막힌다', () => {
    const user = { status: 'ACTIVE', accessExpiresAt: expiresAt }
    expect(isAccountUsable(user, new Date('2026-09-30T23:59:59.999+09:00'))).toBe(true)
    expect(isAccountUsable(user, new Date('2026-10-01T00:00:00+09:00'))).toBe(false)
    expect(isAccountUsable(user, new Date('2026-10-02T12:00:00+09:00'))).toBe(false)
  })

  it('기한 안이어도 정지 계정은 막힌다', () => {
    expect(
      isAccountUsable({ status: 'SUSPENDED', accessExpiresAt: expiresAt }, new Date('2026-09-20T00:00:00+09:00'))
    ).toBe(false)
  })
})
