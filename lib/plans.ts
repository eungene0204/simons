// 요금제(플랜) 정의 — 가상계좌 시뮬레이션 한도 및 계좌당 초기 투자금
//
// 핵심 원칙: 초기 투자금은 실제 돈이 아니라 가상계좌 시뮬레이션을 위한 모의 투자금이다.
// "자산/충전/포인트/크레딧/지급/리워드/캐시" 같은 표현은 사용하지 않는다.

export type PlanId = "FREE" | "PRO" | "PREMIUM";

export interface Plan {
  planId: PlanId;
  /** 사용자 노출 라벨 */
  name: string;
  /** 한 줄 설명 (요금제 페이지) */
  description: string;
  /** 월 가격 (원) */
  monthlyPrice: number;
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
    description: "처음 전략을 만들어보고 백테스트를 경험하는 플랜",
    monthlyPrice: 0,
    initialInvestmentAmount: 10_000_000,
    maxVirtualAccounts: 1,
    maxStrategies: 3,
    monthlyBacktestLimit: 30,
    isUnlimitedStrategies: false,
  },
  PRO: {
    planId: "PRO",
    name: "Pro",
    description: "전략을 본격적으로 만들고 검증하는 개인 투자자용 플랜",
    monthlyPrice: 19_000,
    initialInvestmentAmount: 50_000_000,
    maxVirtualAccounts: 10,
    maxStrategies: 50,
    monthlyBacktestLimit: 100,
    isUnlimitedStrategies: false,
  },
  PREMIUM: {
    planId: "PREMIUM",
    name: "Premium",
    description: "여러 전략을 동시에 연구하고 고급 시뮬레이션을 운영하는 플랜",
    monthlyPrice: 39_000,
    initialInvestmentAmount: 100_000_000,
    maxVirtualAccounts: 30,
    maxStrategies: Infinity,
    monthlyBacktestLimit: 500,
    isUnlimitedStrategies: true,
  },
};

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
