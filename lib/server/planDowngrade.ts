// FREE 강등 시 백테스트 사용량 이월
//
// 사용량 주기의 앵커는 유료 플랜이면 구독 시작일(planStartDate), FREE면 가입일(createdAt)이다.
// 강등으로 planStartDate가 비워지면 주기 키가 바뀌어 이번 주기에 이미 쓴 횟수가 0으로 보였다
// (2026-09-03 감사) — 강등 직후 FREE 한도를 통째로 새로 받는 셈이다. 강등할 때 현재 주기의
// 사용 횟수를 새 앵커(가입일) 기준 주기 키로 옮겨 적어 그대로 이어지게 한다.
import { currentUsagePeriodKey } from "@/lib/server/planLimits";

export interface UsageCarrySource {
  planStartDate?: Date | null;
  createdAt?: Date | null;
  backtestUsageMonth?: string | null;
  backtestCountThisMonth?: number | null;
}

export interface UsageCarry {
  backtestUsageMonth: string;
  backtestCountThisMonth: number;
}

export function backtestUsageCarryOnDowngrade(
  user: UsageCarrySource,
  now: Date = new Date()
): UsageCarry {
  const paidPeriodKey = currentUsagePeriodKey(user.planStartDate ?? user.createdAt ?? null, now);
  const usedThisPeriod =
    user.backtestUsageMonth === paidPeriodKey ? (user.backtestCountThisMonth ?? 0) : 0;
  return {
    backtestUsageMonth: currentUsagePeriodKey(user.createdAt ?? null, now),
    // 음수 = 업그레이드 때 얹어 준 잔여 횟수(보너스). 유료 혜택이므로 FREE로 가져가지 않는다.
    backtestCountThisMonth: Math.max(0, usedThisPeriod),
  };
}

/** 강등 시 사용량 이월에 필요한 User 필드 select */
export const USAGE_CARRY_SELECT = {
  planStartDate: true,
  createdAt: true,
  backtestUsageMonth: true,
  backtestCountThisMonth: true,
} as const;
