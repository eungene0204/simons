// 요금제(플랜) 정의 — 가상계좌 시뮬레이션 한도 및 계좌당 초기 투자금
//
// 핵심 원칙: 초기 투자금은 실제 돈이 아니라 가상계좌 시뮬레이션을 위한 모의 투자금이다.
// "자산/충전/포인트/크레딧/지급/리워드/캐시" 같은 표현은 사용하지 않는다.

export type PlanId = "FREE" | "PRO" | "PREMIUM";

/** 청구 주기 — 월간(1개월마다 갱신) 또는 연간(12개월마다 갱신, 선불) */
export type BillingCycle = "monthly" | "yearly";

export interface Plan {
  planId: PlanId;
  /** 사용자 노출 라벨 */
  name: string;
  /** 한 줄 설명 (요금제 페이지) */
  description: string;
  /** 월 가격 (원) */
  monthlyPrice: number;
  /** 연 가격 (원) — 1년치를 한 번에 결제할 때의 금액. 월 가격 × 12에서 20% 이상 할인된 값 */
  yearlyPrice: number;
  /** 계좌당 초기 투자금 (원) */
  initialInvestmentAmount: number;
  /** 생성 가능 가상계좌 수 */
  maxVirtualAccounts: number;
  /** 저장 가능 전략 수 (무제한이면 Infinity) */
  maxStrategies: number;
  /** 월 백테스트 가능 횟수 */
  monthlyBacktestLimit: number;
  /** 전략 수 무제한 여부 */
  isUnlimitedStrategies: boolean;
}

export const PLANS: Record<PlanId, Plan> = {
  FREE: {
    planId: "FREE",
    name: "Free",
    description: "처음 전략을 만들고 백테스트를 경험하는 플랜",
    monthlyPrice: 0,
    yearlyPrice: 0,
    initialInvestmentAmount: 10_000_000,
    maxVirtualAccounts: 1,
    maxStrategies: 3,
    monthlyBacktestLimit: 50,
    isUnlimitedStrategies: false,
  },
  PRO: {
    planId: "PRO",
    name: "Pro",
    description: "투자 전략을 꾸준히 연구하고 검증하는 플랜",
    monthlyPrice: 25_000,
    yearlyPrice: 240_000, // 300,000원(25,000×12)에서 20% 할인
    initialInvestmentAmount: 50_000_000,
    maxVirtualAccounts: 10,
    maxStrategies: 50,
    monthlyBacktestLimit: 500,
    isUnlimitedStrategies: false,
  },
  PREMIUM: {
    planId: "PREMIUM",
    name: "Premium",
    description: "여러 전략을 동시에 연구하고 지속적으로 검증하는 플랜",
    monthlyPrice: 49_000,
    yearlyPrice: 470_000, // 588,000원(49,000×12)에서 20% 할인 후 천원 단위 정리
    initialInvestmentAmount: 100_000_000,
    maxVirtualAccounts: 30,
    maxStrategies: Infinity,
    monthlyBacktestLimit: 1000,
    isUnlimitedStrategies: true,
  },
};

/** 유효한 청구 주기인지 검증 */
export function isValidBillingCycle(value: unknown): value is BillingCycle {
  return value === "monthly" || value === "yearly";
}

/** 해당 주기의 1회 결제 금액 (원) */
export function priceFor(plan: Plan, cycle: BillingCycle): number {
  return cycle === "yearly" ? plan.yearlyPrice : plan.monthlyPrice;
}

/**
 * 연간 결제로 아끼는 비율 (%, 내림) — 표기한 할인율이 실제보다 커지지 않도록 버림한다.
 * 비율을 실수로 먼저 계산하면 부동소수 오차로 20%가 19%로 떨어지므로 정수 금액으로 나눈다.
 */
export function yearlyDiscountPercent(plan: Plan): number {
  if (plan.monthlyPrice <= 0) return 0;
  const twelveMonths = plan.monthlyPrice * 12;
  return Math.floor(((twelveMonths - plan.yearlyPrice) * 100) / twelveMonths);
}

/**
 * 모든 유료 플랜에서 보장되는 연간 할인율 (%) — 요금제 페이지의 "N% 할인" 표기용.
 * 플랜마다 실제 할인율이 달라도 이 값 이상은 항상 할인된다.
 */
export const YEARLY_DISCOUNT_PERCENT: number = Math.min(
  ...(["PRO", "PREMIUM"] as const).map((planId) => yearlyDiscountPercent(PLANS[planId]))
);

/** 결제 주문명 — 토스 결제 내역에 그대로 남는다 */
export function orderNameFor(plan: Plan, cycle: BillingCycle): string {
  return `널스탁 ${plan.name} 플랜 ${cycle === "yearly" ? "연간" : "월"} 이용료`;
}

/** 요금제 페이지 노출 순서 */
export const PLAN_ORDER: PlanId[] = ["FREE", "PRO", "PREMIUM"];

/** planTier 문자열(대소문자 무관)을 Plan으로 해석. 미지정/미일치 시 FREE 폴백. */
export function getPlan(planTier?: string | null): Plan {
  const key = (planTier ?? "").toUpperCase();
  if (key === "PRO") return PLANS.PRO;
  if (key === "PREMIUM") return PLANS.PREMIUM;
  return PLANS.FREE;
}

/** 유효한 planId인지 검증 */
export function isValidPlanId(value: unknown): value is PlanId {
  return value === "FREE" || value === "PRO" || value === "PREMIUM";
}
