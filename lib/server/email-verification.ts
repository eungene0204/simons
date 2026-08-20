// 이메일 가입 인증번호 공용 유틸.
// route.ts에는 HTTP 메서드 외 export를 두면 안 되므로(비표준 export=배포 빌드만 깨짐)
// 순수 함수는 이 형제 모듈에 둔다.

import { createHash } from 'crypto'

export const CODE_TTL_MS = 10 * 60 * 1000
export const MAX_CODE_ATTEMPTS = 5

// 폼 필드 형식 검증(구조화 입력) — 자연어 해석이 아니다.
export function normalizeEmail(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  const email = raw.trim().toLowerCase()
  if (email.length === 0 || email.length > 254) return null
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return null
  return email
}

export function hashVerificationCode(code: string): string {
  return createHash('sha256').update(code).digest('hex')
}

// 비밀번호 정책: 8~72자(bcrypt 유효 입력 한계), 영문과 숫자 각 1자 이상.
export function isAcceptablePassword(password: unknown): password is string {
  if (typeof password !== 'string') return false
  if (password.length < 8 || password.length > 72) return false
  return /[A-Za-z]/.test(password) && /\d/.test(password)
}
