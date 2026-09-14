import { describe, expect, it } from 'vitest'
import {
  GUEST_EMAIL_DOMAIN,
  generateGuestId,
  generateGuestPassword,
  guestEmailFromId,
  isGuestEmail,
  normalizeGuestId,
} from './guestAccounts'

describe('게스트 계정 아이디·비밀번호', () => {
  it('아이디는 guest_ + 네 자리 숫자다', () => {
    for (let i = 0; i < 200; i++) {
      const id = generateGuestId()
      expect(id).toMatch(/^guest_\d{4}$/)
      expect(normalizeGuestId(id)).toBe(id)
    }
  })

  it('비밀번호는 5자이며 헷갈리는 글자(0/o/1/l/i)와 대문자를 쓰지 않는다', () => {
    for (let i = 0; i < 200; i++) {
      const pw = generateGuestPassword()
      expect(pw).toHaveLength(5)
      expect(pw).toMatch(/^[a-z0-9]+$/)
      expect(pw).not.toMatch(/[01oli]/)
    }
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
  })
})
