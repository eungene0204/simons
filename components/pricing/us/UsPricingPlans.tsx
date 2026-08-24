"use client";

// 글로벌 서비스(/us) 요금제 카드 — 한국 요금제 카드(components/pricing/PricingPlans)와
// 동일한 레이아웃·기능 목록을 영어·USD로 표시한다.
//
// 결제 배선만 다르다: 토스페이먼츠 체크아웃(심사 영역)은 여기서 일절 쓰지 않으며,
// PayPal 배선 전까지 CTA는 비활성 안내로 둔다.
//
// 상호작용은 없지만 phosphor-react가 createContext를 쓰므로 클라이언트 컴포넌트여야 한다
// (RSC에서 임포트하면 렌더 시점에 터진다).

import { Check, X, Lightning, Rocket, Crown } from "phosphor-react";
import { PLANS, Plan, PlanId } from "@/lib/plans";
import { US_PRICING } from "@/lib/pricing/us";

function formatUsd(value: number) {
  return `$${value.toLocaleString("en-US")}`;
}

function formatCount(value: number) {
  return value.toLocaleString("en-US");
}

const PLAN_ICONS: Record<PlanId, typeof Lightning> = {
  FREE: Lightning,
  PRO: Rocket,
  PREMIUM: Crown,
};

const PLAN_DESCRIPTIONS: Record<PlanId, string> = {
  FREE: "Build your first strategy and try a backtest",
  PRO: "Research and simulate several strategies at once",
  PREMIUM: "Research and validate strategies at a professional level",
};

type FeatureRow = { label: string; included: boolean };

function planFeatures(planId: PlanId, plan: Plan): FeatureRow[] {
  return [
    {
      label: `${formatUsd(US_PRICING.initialInvestmentAmount[planId])} simulated starting capital per account`,
      included: true,
    },
    {
      label: `${formatCount(plan.maxVirtualAccounts)} simulation virtual account${
        plan.maxVirtualAccounts > 1 ? "s" : ""
      }`,
      included: true,
    },
    {
      label: plan.isUnlimitedStrategies
        ? "Unlimited saved strategies"
        : `${formatCount(plan.maxStrategies)} saved strategies`,
      included: true,
    },
    { label: `${formatCount(plan.monthlyBacktestLimit)} backtests / month`, included: true },
    { label: "AI report", included: planId !== "FREE" },
    { label: "Backtest result export (CSV/JSON)", included: planId !== "FREE" },
    { label: "Walk-forward validation", included: planId === "PREMIUM" },
    { label: "Monte Carlo simulation", included: planId === "PREMIUM" },
  ];
}

interface UsPricingPlansProps {
  currentPlanId: PlanId;
}

export default function UsPricingPlans({ currentPlanId }: UsPricingPlansProps) {
  return (
    <div>
      <div
        data-testid="pricing-plan-grid"
        className="grid grid-cols-1 items-stretch gap-6 lg:grid-cols-3"
      >
        {US_PRICING.planOrder.map((planId) => {
          const plan = PLANS[planId];
          const Icon = PLAN_ICONS[planId];
          const isCurrent = planId === currentPlanId;
          const features = planFeatures(planId, plan);

          return (
            <div
              key={planId}
              data-testid={`pricing-plan-card-${planId}`}
              className="relative flex h-full flex-col rounded-3xl border border-white/[0.08] bg-[#0a0a0a] px-8 py-10 transition-transform duration-200 ease-out hover:-translate-y-1.5 xl:px-9"
            >
              {/* 헤더: 아이콘 + 플랜명 */}
              <div className="flex items-center gap-3">
                <span
                  className={`flex h-11 w-11 items-center justify-center rounded-xl bg-white/[0.06] ${
                    isCurrent ? "text-blue-400" : "text-white"
                  }`}
                >
                  <Icon size={22} weight="fill" />
                </span>
                <h2 className="text-xl font-black tracking-tight text-white">{plan.name}</h2>
              </div>

              <p className="mt-6 text-sm font-bold leading-relaxed text-gray-400">
                {PLAN_DESCRIPTIONS[planId]}
              </p>

              {/* 가격 */}
              <div className="mt-9 flex items-end gap-1">
                <span className="text-4xl font-black tracking-tight text-white">
                  {formatUsd(US_PRICING.monthlyPrice[planId])}
                </span>
                <span className="pb-1 text-sm font-bold text-gray-500">/ month</span>
              </div>

              {/* 기능 목록 */}
              <ul className="mt-10 flex-1 space-y-6">
                {features.map((feature) => (
                  <li key={feature.label} className="flex items-center gap-3">
                    {feature.included ? (
                      <Check size={18} weight="bold" className="shrink-0 text-blue-400" />
                    ) : (
                      <X size={18} weight="bold" className="shrink-0 text-gray-600" />
                    )}
                    <span
                      className={`text-sm font-bold xl:whitespace-nowrap ${
                        feature.included ? "text-gray-200" : "text-gray-600"
                      }`}
                    >
                      {feature.label}
                    </span>
                  </li>
                ))}
              </ul>

              {/* CTA — PayPal 배선 전까지 비활성 안내 */}
              <button
                type="button"
                disabled
                className={`mt-10 w-full rounded-2xl px-4 py-4 text-sm font-black transition-colors disabled:cursor-not-allowed ${
                  isCurrent
                    ? "bg-white/[0.04] text-gray-500"
                    : "border border-white/[0.12] text-white disabled:opacity-60"
                }`}
              >
                {isCurrent
                  ? "Current plan"
                  : planId === "FREE"
                  ? "Included at sign-up"
                  : "Coming soon"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
