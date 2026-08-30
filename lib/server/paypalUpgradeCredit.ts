// 업그레이드 크레딧 계산 — 남은 하위 플랜 기간의 가치를 상위 플랜 일수로 환산한다.
//
// 정책(2026-08-31 확정): 업그레이드는 즉시 전환 + 상위 플랜 월액 즉시 청구. 대신 이미 결제한
// 하위 플랜의 남은 기간 가치를 버리지 않고 상위 플랜 기간으로 바꿔 첫 주기에 더한다.
// 예: PRO($19) 15일 남음 → $9.50 → PREMIUM($39) 기준 약 7일 → 첫 주기 37일.
// PayPal이 일할계산을 안 해주므로 금액이 아니라 기간으로 얹는 방식이다.

export const UPGRADE_CYCLE_DAYS = 30; // 월 주기를 일수로 환산하는 기준

/** 남은 하위 플랜 가치를 상위 플랜 일수로 바꾼 크레딧(내림, 0 이상) */
export function upgradeCreditDays(input: {
  nextBillingAt: Date;
  now: Date;
  fromMonthlyPrice: number;
  toMonthlyPrice: number;
}): number {
  const msLeft = input.nextBillingAt.getTime() - input.now.getTime();
  if (msLeft <= 0 || input.toMonthlyPrice <= 0) return 0;
  const daysLeft = Math.min(UPGRADE_CYCLE_DAYS + 1, Math.ceil(msLeft / 86_400_000));
  const remainingValue = (input.fromMonthlyPrice / UPGRADE_CYCLE_DAYS) * daysLeft;
  return Math.floor(remainingValue / (input.toMonthlyPrice / UPGRADE_CYCLE_DAYS));
}

/** 업그레이드 첫 주기 길이 — 기본 30일 + 크레딧 */
export function upgradeFirstPeriodDays(input: {
  nextBillingAt: Date;
  now: Date;
  fromMonthlyPrice: number;
  toMonthlyPrice: number;
}): number {
  return UPGRADE_CYCLE_DAYS + upgradeCreditDays(input);
}
