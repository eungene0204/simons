import { describe, expect, it } from 'vitest'
import {
  GUEST_EMAIL_DOMAIN,
  generateGuestId,
  generateGuestInviteSecret,
  guestEmailFromId,
  guestInviteUrl,
  isGuestEmail,
  normalizeGuestId,
  parseGuestInviteCode,
} from './guestAccounts'

describe('게스트 계정 아이디·입장 링크', () => {
  it('아이디는 guest_ + 네 자리 숫자다', () => {
    for (let i = 0; i < 200; i++) {
      const id = generateGuestId()
      expect(id).toMatch(/^guest_\d{4}$/)
      expect(normalizeGuestId(id)).toBe(id)
    }
  })

  it('입장 링크 비밀값은 256비트 base64url 43자이며 매번 다르다', () => {
    const seen = new Set<string>()
    for (let i = 0; i < 200; i++) {
      const secret = generateGuestInviteSecret()
      expect(secret).toMatch(/^[A-Za-z0-9_-]{43}$/)
      seen.add(secret)
    }
    expect(seen.size).toBe(200)
  })

  it('입장 링크는 코드를 # 뒤에 두고, 코드는 아이디·비밀값으로 왕복한다', () => {
    const secret = generateGuestInviteSecret()
    const url = guestInviteUrl('guest_1234', secret)
    expect(url).toBe(`https://www.nullstock.im/guest#guest_1234.${secret}`)
    expect(parseGuestInviteCode(url.split('#')[1])).toEqual({ guestId: 'guest_1234', secret })
  })

  it('형식이 다른 입장 코드는 null이다', () => {
    const secret = generateGuestInviteSecret()
    expect(parseGuestInviteCode(`guest_1234.${secret.slice(1)}`)).toBeNull()
    expect(parseGuestInviteCode(`guest_12.${secret}`)).toBeNull()
    expect(parseGuestInviteCode(`admin.${secret}`)).toBeNull()
    expect(parseGuestInviteCode(`guest_1234${secret}`)).toBeNull()
    expect(parseGuestInviteCode(`guest_1234.${secret.slice(0, 42)}!`)).toBeNull()
    expect(parseGuestInviteCode('')).toBeNull()
    expect(parseGuestInviteCode(undefined)).toBeNull()
  })

  it('폼 입력은 공백을 걷어내고 소문자로 정규화하며, 형식이 다르면 null이다', () => {
    expect(normalizeGuestId('  Guest_1234 ')).toBe('guest_1234')
    expect(normalizeGuestId('guest_12')).toBeNull()
    expect(normalizeGuestId('guest_12345')).toBeNull()
    expect(normalizeGuestId('admin')).toBeNull()
    expect(normalizeGuestId('guest_1234@guest.nullstock.im')).toBeNull()
    expect(normalizeGuestId(1234)).toBeNull()
    expect(normalizeGuestId(undefined)).toBeNull()
  })

  it('아이디 ↔ 합성 이메일 왕복, 일반 회원 이메일은 게스트가 아니다', () => {
    const email = guestEmailFromId('guest_1234')
    expect(email).toBe(`guest_1234@${GUEST_EMAIL_DOMAIN}`)
    expect(isGuestEmail(email)).toBe(true)
    expect(isGuestEmail('someone@nullstock.im')).toBe(false)
    expect(isGuestEmail('guest_1234@gmail.com')).toBe(false)
    // 이메일이 없으면 게스트가 아니다 — 라우트 가드가 던지지 않고 일반 경로로 흘러간다
    expect(isGuestEmail(null)).toBe(false)
    expect(isGuestEmail(undefined)).toBe(false)
  })
})
