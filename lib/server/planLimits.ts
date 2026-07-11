// 플랜별 한도 enforcement 및 사용량 조회
//
// 가상계좌 수 / 저장 전략 수 / 월 백테스트 횟수를 사용자의 현재 플랜(User.planTier)에 따라 제한한다.
// 월 백테스트 사용량은 구독 시작일(planStartDate) 기준 롤링 1개월 주기로 초기화된다.
// 구독 이력이 없는 사용자(FREE, planStartDate 없음)는 가입일(createdAt) 기준 롤링 1개월 주기를 쓴다.
// (가입일마저 없는 비정상 데이터는 KST 캘린더 월로 폴백한다.)
// 가상계좌 수 / 저장 전략 수는 주기 리셋 없이 상시 캡으로 유지된다.

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
    findMany?: (args?: any) => Promise<any[]>;
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

/** 현재 달 키 "YYYY-MM" (KST 기준) — 주기 앵커(구독 시작일·가입일)가 모두 없을 때의 폴백 */
export function currentUsageMonth(now: Date = new Date()): string {
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const year = kst.getUTCFullYear();
  const month = String(kst.getUTCMonth() + 1).padStart(2, "0");
  return `${year}-${month}`;
}

/** date의 n개월 후 날짜. 목표 월의 말일을 넘는 day는 말일로 clamp(예: 1/31 + 1개월 = 2/28) */
export function addMonthsClamped(date: Date, months: number): Date {
  const day = date.getUTCDate();
  const target = new Date(
    Date.UTC(
      date.getUTCFullYear(),
      date.getUTCMonth() + months,
      1,
      date.getUTCHours(),
      date.getUTCMinutes(),
      date.getUTCSeconds(),
      date.getUTCMilliseconds()
    )
  );
  const daysInTargetMonth = new Date(
    Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)
  ).getUTCDate();
  target.setUTCDate(Math.min(day, daysInTargetMonth));
  return target;
}

/**
 * 구독 시작일(planStartDate)을 기준으로 한 현재 결제 주기(1개월)를 계산한다.
 * 여러 달이 경과했어도 now를 포함하는 주기까지 굴려서(rolling) 반환한다.
 */
export function currentPlanCycle(
  planStartDate: Date,
  now: Date = new Date()
): { start: Date; end: Date } {
  let start = planStartDate;
  let end = addMonthsClamped(planStartDate, 1);
  let guard = 0;
  while (end.getTime() <= now.getTime() && guard < 2400) {
    start = end;
    end = addMonthsClamped(start, 1);
    guard++;
  }
  return { start, end };
}

/**
 * 사용량(백테스트 횟수 등) 리셋 기준 주기를 식별하는 키.
 * 주기 앵커(유료 플랜은 구독 시작일, FREE는 가입일)가 있으면 그 롤링 주기 시작일,
 * 없으면 KST 캘린더 월로 폴백한다.
 */
export function currentUsagePeriodKey(
  cycleAnchor?: Date | null,
  now: Date = new Date()
): string {
  if (!cycleAnchor) return currentUsageMonth(now);
  return currentPlanCycle(cycleAnchor, now).start.toISOString();
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
  return applyPlanOverride(base, override);
}

/** 플랜 기본값에 PlanConfig 오버라이드 한 건을 병합한다 (override가 없으면 기본값 그대로) */
function applyPlanOverride(base: Plan, override: any): Plan {
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
 * 월 백테스트 1회 소비 — 현재 사용량 주기(구독 시작일, 미구독 시 가입일 기준 롤링 1개월)가
 * 바뀌었으면 카운트를 리셋한 뒤 한도를 검사하고 +1 한다.
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
      planStartDate: true,
      createdAt: true,
      backtestUsageMonth: true,
      backtestCountThisMonth: true,
    },
  });
  if (!user) throw new Error("USER_NOT_FOUND");

  const plan = await getEffectivePlan(client, user.planTier);
  const periodKey = currentUsagePeriodKey(
    user.planStartDate ?? user.createdAt,
    now
  );
  const usedThisPeriod =
    user.backtestUsageMonth === periodKey ? user.backtestCountThisMonth : 0;

  if (usedThisPeriod >= plan.monthlyBacktestLimit) {
    throw new Error(PLAN_LIMIT_BACKTESTS);
  }

  await client.user.update({
    where: { id: userId },
    data: {
      backtestUsageMonth: periodKey,
      backtestCountThisMonth: usedThisPeriod + 1,
    },
  });
}

export interface PlanUsage {
  plan: Plan;
  /** 유료 플랜은 구독 시작일, FREE는 가입일 기준 현재 사용량 주기 시작일 */
  planStartDate: Date | null;
  /** 현재 사용량 주기 종료일 = 주기 앵커(구독 시작일·가입일) 기준 롤링 1개월 — 백테스트 횟수 리셋 시점 */
  planEndDate: Date | null;
  /** 자동결제(빌링) 구독 상태 — 자동갱신 구독이 없으면 null */
  subscription: {
    planId: string;
    nextBillingAt: Date | null;
    /** 해지 예약됨 — 다음 결제일에 청구 없이 FREE 전환 */
    canceled: boolean;
  } | null;
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
  // DB가 원격(Supabase)이라 왕복 지연이 커서, planConfig 오버라이드까지 포함해
  // 모든 조회를 한 번의 병렬 배치(1왕복)로 실행한다. planConfig는 planTier를 알기
  // 전에 조회해야 하므로 전체(≤플랜 수)를 읽어 병합 시점에 고른다.
  const [user, accountsUsed, strategiesUsed, overrides] = await Promise.all([
    client.user.findUnique({
      where: { id: userId },
      select: {
        planTier: true,
        planStartDate: true,
        createdAt: true,
        backtestUsageMonth: true,
        backtestCountThisMonth: true,
        subscriptionPlanId: true,
        nextBillingAt: true,
        subscriptionCanceledAt: true,
      },
    }),
    countActiveAccounts(client, userId),
    countSavedStrategies(client, userId),
    client.planConfig?.findMany?.() ?? null,
  ]);

  const base = getPlan(user?.planTier);
  const plan = overrides
    ? applyPlanOverride(
        base,
        overrides.find((o) => o.planId === base.planId) ?? null
      )
    : await getEffectivePlan(client, user?.planTier);
  // 사용량 주기 앵커: 유료 플랜은 구독 시작일, FREE는 가입일
  const cycleAnchor: Date | null = user?.planStartDate ?? user?.createdAt ?? null;
  const cycle = cycleAnchor ? currentPlanCycle(cycleAnchor, now) : null;
  const periodKey = currentUsagePeriodKey(cycleAnchor, now);
  // 표시용 시작일: 유료 플랜은 구독 시작일 그대로(기존 동작), FREE는 현재 주기 시작일
  const planStartDate: Date | null = user?.planStartDate ?? cycle?.start ?? null;
  const backtestsUsed =
    user?.backtestUsageMonth === periodKey ? user.backtestCountThisMonth : 0;

  return {
    plan,
    planStartDate,
    planEndDate: cycle?.end ?? null,
    subscription: user?.subscriptionPlanId
      ? {
          planId: user.subscriptionPlanId,
          nextBillingAt: user.nextBillingAt ?? null,
          canceled: user.subscriptionCanceledAt != null,
        }
      : null,
    accounts: { used: accountsUsed, limit: plan.maxVirtualAccounts },
    strategies: {
      used: strategiesUsed,
      limit: plan.maxStrategies,
      unlimited: plan.isUnlimitedStrategies,
    },
    backtests: { used: backtestsUsed, limit: plan.monthlyBacktestLimit },
  };
}
