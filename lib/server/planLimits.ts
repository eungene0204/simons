// 플랜별 한도 enforcement 및 사용량 조회
//
// 가상계좌 수 / 저장 전략 수 / 월 백테스트 횟수를 사용자의 현재 플랜(User.planTier)에 따라 제한한다.
// 월 백테스트 사용량은 달력 월(KST) 기준으로 초기화된다.

import { Plan, getPlan } from "@/lib/plans";

// PrismaClient 또는 TransactionClient 모두 받을 수 있는 최소 인터페이스
type PlanLimitClient = {
  user: {
    findUnique: (args: any) => Promise<any>;
    update: (args: any) => Promise<any>;
  };
  virtualAccount: {
    count: (args: any) => Promise<number>;
  };
  strategy: {
    count: (args: any) => Promise<number>;
  };
  // 관리자 콘솔의 플랜 한도 오버라이드(PlanConfig). 없으면 기본값 사용.
  planConfig?: {
    findUnique: (args: any) => Promise<any>;
  };
};

export const PLAN_LIMIT_ACCOUNTS = "PLAN_LIMIT_ACCOUNTS";
export const PLAN_LIMIT_STRATEGIES = "PLAN_LIMIT_STRATEGIES";
export const PLAN_LIMIT_BACKTESTS = "PLAN_LIMIT_BACKTESTS";

export const PLAN_LIMIT_MESSAGES: Record<string, string> = {
  [PLAN_LIMIT_ACCOUNTS]:
    "현재 플랜의 가상계좌 수 한도에 도달했습니다. 요금제를 업그레이드하면 더 많은 가상계좌를 만들 수 있습니다.",
  [PLAN_LIMIT_STRATEGIES]:
    "현재 플랜의 저장 가능 전략 수 한도에 도달했습니다. 요금제를 업그레이드하면 더 많은 전략을 저장할 수 있습니다.",
  [PLAN_LIMIT_BACKTESTS]:
    "이번 달 백테스트 한도를 모두 사용했습니다. 요금제를 업그레이드하면 더 많은 백테스트를 실행할 수 있습니다.",
};

/** 현재 달 키 "YYYY-MM" (KST 기준) */
export function currentUsageMonth(now: Date = new Date()): string {
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const year = kst.getUTCFullYear();
  const month = String(kst.getUTCMonth() + 1).padStart(2, "0");
  return `${year}-${month}`;
}

/**
 * 플랜 기본값(lib/plans.ts)에 관리자 콘솔의 PlanConfig 오버라이드를 병합한다.
 * 오버라이드 필드가 null이면 기본값 유지, maxStrategies가 -1이면 무제한.
 */
export async function getEffectivePlan(
  client: PlanLimitClient,
  planTier?: string | null
): Promise<Plan> {
  const base = getPlan(planTier);
  if (!client.planConfig) return base;

  const override = await client.planConfig.findUnique({
    where: { planId: base.planId },
  });
  if (!override) return base;

  const unlimitedStrategies =
    override.maxStrategies == null
      ? base.isUnlimitedStrategies
      : override.maxStrategies === -1;

  return {
    ...base,
    monthlyBacktestLimit:
      override.monthlyBacktestLimit ?? base.monthlyBacktestLimit,
    maxVirtualAccounts: override.maxVirtualAccounts ?? base.maxVirtualAccounts,
    maxStrategies:
      override.maxStrategies == null
        ? base.maxStrategies
        : unlimitedStrategies
          ? Infinity
          : override.maxStrategies,
    isUnlimitedStrategies: unlimitedStrategies,
  };
}

/** 사용자의 현재 플랜 */
export async function getUserPlan(
  client: PlanLimitClient,
  userId: number
): Promise<Plan> {
  const user = await client.user.findUnique({
    where: { id: userId },
    select: { planTier: true },
  });
  return getEffectivePlan(client, user?.planTier);
}

/** 활성(ACTIVE) 가상계좌 수 */
export function countActiveAccounts(
  client: PlanLimitClient,
  userId: number
): Promise<number> {
  return client.virtualAccount.count({
    where: { userId, status: "ACTIVE" },
  });
}

/** 저장된(isSaved) 전략 수 */
export function countSavedStrategies(
  client: PlanLimitClient,
  userId: number
): Promise<number> {
  return client.strategy.count({
    where: { userId, isSaved: true },
  });
}

/** 가상계좌 생성 가능 여부 검증 — 초과 시 PLAN_LIMIT_ACCOUNTS throw */
export async function assertCanCreateAccount(
  client: PlanLimitClient,
  userId: number
): Promise<void> {
  const [plan, used] = await Promise.all([
    getUserPlan(client, userId),
    countActiveAccounts(client, userId),
  ]);
  if (used >= plan.maxVirtualAccounts) {
    throw new Error(PLAN_LIMIT_ACCOUNTS);
  }
}

/** 신규 전략 저장 가능 여부 검증 — 초과 시 PLAN_LIMIT_STRATEGIES throw */
export async function assertCanSaveStrategy(
  client: PlanLimitClient,
  userId: number
): Promise<void> {
  const plan = await getUserPlan(client, userId);
  if (plan.isUnlimitedStrategies) return;
  const used = await countSavedStrategies(client, userId);
  if (used >= plan.maxStrategies) {
    throw new Error(PLAN_LIMIT_STRATEGIES);
  }
}

/**
 * 월 백테스트 1회 소비 — 달력 월이 바뀌었으면 카운트를 리셋한 뒤 한도를 검사하고 +1 한다.
 * 한도 초과 시 PLAN_LIMIT_BACKTESTS throw (이때 카운트는 증가하지 않는다).
 */
export async function consumeBacktestQuota(
  client: PlanLimitClient,
  userId: number,
  now: Date = new Date()
): Promise<void> {
  const user = await client.user.findUnique({
    where: { id: userId },
    select: {
      planTier: true,
      backtestUsageMonth: true,
      backtestCountThisMonth: true,
    },
  });
  if (!user) throw new Error("USER_NOT_FOUND");

  const plan = await getEffectivePlan(client, user.planTier);
  const month = currentUsageMonth(now);
  const usedThisMonth =
    user.backtestUsageMonth === month ? user.backtestCountThisMonth : 0;

  if (usedThisMonth >= plan.monthlyBacktestLimit) {
    throw new Error(PLAN_LIMIT_BACKTESTS);
  }

  await client.user.update({
    where: { id: userId },
    data: {
      backtestUsageMonth: month,
      backtestCountThisMonth: usedThisMonth + 1,
    },
  });
}

export interface PlanUsage {
  plan: Plan;
  accounts: { used: number; limit: number };
  strategies: { used: number; limit: number; unlimited: boolean };
  backtests: { used: number; limit: number };
}

/** UI용 사용량 요약 (백테스트 카운트는 증가시키지 않음) */
export async function getUserUsage(
  client: PlanLimitClient,
  userId: number,
  now: Date = new Date()
): Promise<PlanUsage> {
  const [user, accountsUsed, strategiesUsed] = await Promise.all([
    client.user.findUnique({
      where: { id: userId },
      select: {
        planTier: true,
        backtestUsageMonth: true,
        backtestCountThisMonth: true,
      },
    }),
    countActiveAccounts(client, userId),
    countSavedStrategies(client, userId),
  ]);

  const plan = await getEffectivePlan(client, user?.planTier);
  const month = currentUsageMonth(now);
  const backtestsUsed =
    user?.backtestUsageMonth === month ? user.backtestCountThisMonth : 0;

  return {
    plan,
    accounts: { used: accountsUsed, limit: plan.maxVirtualAccounts },
    strategies: {
      used: strategiesUsed,
      limit: plan.maxStrategies,
      unlimited: plan.isUnlimitedStrategies,
    },
    backtests: { used: backtestsUsed, limit: plan.monthlyBacktestLimit },
  };
}
