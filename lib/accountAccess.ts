// 계정을 지금 쓸 수 있는지 — 로그인과 세션 인정이 함께 쓰는 기준.
// status가 ACTIVE여도 이용 기한(accessExpiresAt)이 지났으면 쓸 수 없다. 기한은 요청 시각에 판정하므로
// 만료를 반영하는 예약 작업이 없어도 그 시각부터 바로 막힌다(2026-09-17 게스트 입장 링크 기한).

export type AccountAccessFields = {
  status: string
  accessExpiresAt: Date | null
}

export const ACCOUNT_ACCESS_SELECT = { status: true, accessExpiresAt: true } as const

export function isAccountUsable(user: AccountAccessFields, now: Date = new Date()): boolean {
  if (user.status !== 'ACTIVE') return false
  return user.accessExpiresAt == null || now.getTime() < user.accessExpiresAt.getTime()
}
