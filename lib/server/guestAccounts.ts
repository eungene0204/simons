// 게스트(테스터) 계정 — 운영자가 발급한 아이디·비밀번호로 /guest에서 입장하는 특별 계정.
//
// 별도 테이블을 두지 않는다. User 행을 그대로 쓰되
//   - 이메일 = `<아이디>@guest.nullstock.im` (합성 도메인 — 수신 불가, 게스트 판별의 유일한 기준)
//   - 이름   = 아이디 그대로
//   - 플랜   = PREMIUM (발급 시 확정, 결제·자동갱신 없음)
// 관리자 콘솔(Users 탭)은 이 도메인으로 게스트를 걸러 본다.
// 아이디·비밀번호 형식 검증은 폼 필드(구조화 입력) 검증이지 자연어 해석이 아니다.

import { randomInt } from 'crypto'

export const GUEST_EMAIL_DOMAIN = 'guest.nullstock.im'
export const GUEST_ID_PREFIX = 'guest_'
export const GUEST_PASSWORD_LENGTH = 5

const GUEST_ID_PATTERN = /^guest_\d{4}$/
// 손으로 옮겨 적기 쉬운 글자만 — 0/o, 1/l/i 처럼 헷갈리는 글자는 뺀다.
const PASSWORD_ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'

/** 폼에서 온 아이디를 정규화(공백 제거·소문자)하고 형식이 맞을 때만 돌려준다. */
export function normalizeGuestId(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  const guestId = raw.trim().toLowerCase()
  return GUEST_ID_PATTERN.test(guestId) ? guestId : null
}

export function guestEmailFromId(guestId: string): string {
  return `${guestId}@${GUEST_EMAIL_DOMAIN}`
}

export function isGuestEmail(email: string): boolean {
  return email.endsWith(`@${GUEST_EMAIL_DOMAIN}`)
}

/** guest_ + 네 자리 숫자(1000~9999 — 앞자리 0 없음) */
export function generateGuestId(): string {
  return `${GUEST_ID_PREFIX}${randomInt(1000, 10000)}`
}

/** 소문자·숫자 5자 */
export function generateGuestPassword(): string {
  let out = ''
  for (let i = 0; i < GUEST_PASSWORD_LENGTH; i++) {
    out += PASSWORD_ALPHABET[randomInt(PASSWORD_ALPHABET.length)]
  }
  return out
}
