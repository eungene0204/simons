// 게스트(테스터) 계정 — 운영자가 발급한 입장 링크(또는 아이디·비밀번호)로 /guest에서 입장하는 특별 계정.
//
// 별도 테이블을 두지 않는다. User 행을 그대로 쓰되
//   - 이메일 = `<아이디>@guest.nullstock.im` (합성 도메인 — 수신 불가, 게스트 판별의 유일한 기준)
//   - 이름   = 아이디 그대로
//   - 플랜   = PREMIUM (발급 시 확정, 결제·자동갱신 없음)
// 관리자 콘솔(Users 탭)은 이 도메인으로 게스트를 걸러 본다.
// 아이디·비밀번호·입장 코드 형식 검증은 구조화 입력 검증이지 자연어 해석이 아니다.
//
// 입장 링크(2026-09-17): `https://www.nullstock.im/guest#<아이디>.<비밀값>`
//   - 비밀값 = 32바이트 난수(base64url 43자)이며 그 계정의 비밀번호 자체다(DB에는 bcrypt 해시만).
//     별도 테이블·서명 키 없이 링크를 검증하고, 링크를 폐기하려면 비밀번호를 새로 뽑거나 계정을 지운다.
//   - 코드를 `#` 뒤(프래그먼트)에 두는 이유: 프래그먼트는 서버 요청·접속 로그·Referer에 실리지 않는다.
//     화면이 읽어 POST 본문으로만 보낸다.

import { randomBytes, randomInt } from 'crypto'
import { siteUrl } from '../seo/site'

// 게스트가 막히는 동작의 API 응답 문구. 화면은 자기 사전(t())으로 같은 뜻을 안내하고,
// 이 문구는 API를 직접 부른 경우의 안내다(백엔드는 완성 문장을 표시 정본으로 삼지 않는다).
export const GUEST_PAYMENT_BLOCKED_MESSAGE =
  '특별 계정은 Premium 기능을 모두 이용할 수 있어 결제가 필요하지 않습니다. 요금제 결제와 변경은 일반 계정에서만 이용할 수 있습니다.'
export const GUEST_DELETE_BLOCKED_MESSAGE =
  '특별 계정은 직접 삭제할 수 없습니다. 이용을 마치셨다면 계정을 발급해 드린 담당자에게 알려 주세요.'

export const GUEST_EMAIL_DOMAIN = 'guest.nullstock.im'
export const GUEST_ID_PREFIX = 'guest_'
const GUEST_INVITE_SECRET_BYTES = 32

const GUEST_ID_PATTERN = /^guest_\d{4}$/
const GUEST_INVITE_PATTERN = /^(guest_\d{4})\.([A-Za-z0-9_-]{43})$/

/** 폼에서 온 아이디를 정규화(공백 제거·소문자)하고 형식이 맞을 때만 돌려준다. */
export function normalizeGuestId(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  const guestId = raw.trim().toLowerCase()
  return GUEST_ID_PATTERN.test(guestId) ? guestId : null
}

export function guestEmailFromId(guestId: string): string {
  return `${guestId}@${GUEST_EMAIL_DOMAIN}`
}

/** 이메일이 없으면(조회 실패·비정상 행) 게스트가 아니다 — 가드가 일반 회원을 막는 쪽으로 기울지 않는다. */
export function isGuestEmail(email: string | null | undefined): boolean {
  return typeof email === 'string' && email.endsWith(`@${GUEST_EMAIL_DOMAIN}`)
}

/** guest_ + 네 자리 숫자(1000~9999 — 앞자리 0 없음) */
export function generateGuestId(): string {
  return `${GUEST_ID_PREFIX}${randomInt(1000, 10000)}`
}

/** 입장 링크 비밀값 — 32바이트 난수(256비트), base64url 43자. 계정 비밀번호로 저장한다. */
export function generateGuestInviteSecret(): string {
  return randomBytes(GUEST_INVITE_SECRET_BYTES).toString('base64url')
}

/** 입장 코드 = `<아이디>.<비밀값>` — 링크의 `#` 뒤에 붙는다. */
export function guestInviteCode(guestId: string, secret: string): string {
  return `${guestId}.${secret}`
}

export function guestInviteUrl(guestId: string, secret: string): string {
  return `${siteUrl()}/guest#${guestInviteCode(guestId, secret)}`
}

/** 화면이 보낸 입장 코드를 아이디·비밀값으로 나눈다. 형식이 다르면 null(DB를 보지 않는다). */
export function parseGuestInviteCode(raw: unknown): { guestId: string; secret: string } | null {
  if (typeof raw !== 'string') return null
  const match = GUEST_INVITE_PATTERN.exec(raw.trim())
  return match ? { guestId: match[1], secret: match[2] } : null
}
