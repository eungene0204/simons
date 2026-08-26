import type { PlanId } from "@/lib/plans";
import type { Region } from "@/lib/geo/region";

/** 지역별 가격표 — 플랜 구성(한도 등)은 lib/plans.ts 공통, 가격·통화만 지역별이다. */
export interface RegionPricing {
  region: Region;
  currency: "KRW" | "USD";
  planOrder: readonly PlanId[];
  /** 플랜별 월 가격 (KRW는 원 단위 정수, USD는 달러 단위) */
  monthlyPrice: Record<PlanId, number>;
  /** 플랜별 계좌당 초기 모의 투자금 (KRW는 원 단위, USD는 달러 단위) */
  initialInvestmentAmount: Record<PlanId, number>;
}
