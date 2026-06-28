"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, X, Lightning, Rocket, Crown } from "phosphor-react";
import { PLANS, PLAN_ORDER, Plan, PlanId } from "@/lib/plans";

function formatWon(value: number) {
  return `₩${value.toLocaleString("ko-KR")}`;
}

function formatCount(value: number) {
  return value.toLocaleString("ko-KR");
}

function formatInitialInvestmentAmount(value: number) {
  if (value === 10_000_000) return "천 만원";
  if (value === 50_000_000) return "5천 만원";
  if (value === 100_000_000) return "1억원";
  return formatWon(value);
}

const PLAN_ICONS: Record<PlanId, typeof Lightning> = {
  FREE: Lightning,
  PRO: Rocket,
  PREMIUM: Crown,
};

type FeatureRow = { label: string; included: boolean };

function planFeatures(plan: Plan): FeatureRow[] {
  return [
    {
      label: `계좌당 초기 모의 투자금 ${formatInitialInvestmentAmount(plan.initialInvestmentAmount)}`,
      included: true,
    },
    { label: `시뮬레이션 가상계좌 ${formatCount(plan.maxVirtualAccounts)}개`, included: true },
    {
      label: plan.isUnlimitedStrategies
        ? "전략 무제한 저장"
        : `전략 ${formatCount(plan.maxStrategies)}개 저장`,
      included: true,
    },
    { label: `월 백테스트 ${formatCount(plan.monthlyBacktestLimit)}회`, included: true },
  ];
}

interface PricingPlansProps {
  currentPlanId: PlanId;
}

export default function PricingPlans({ currentPlanId }: PricingPlansProps) {
  const router = useRouter();
  const [pendingPlanId, setPendingPlanId] = useState<PlanId | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSelect = async (planId: PlanId) => {
    if (planId === currentPlanId || pendingPlanId) return;
    setPendingPlanId(planId);
    setError(null);
    try {
      const res = await fetch("/api/user/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ planId }),
      });
      if (!res.ok) throw new Error("Failed to change plan");
      router.refresh();
    } catch {
      setError("플랜 변경에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setPendingPlanId(null);
    }
  };

  return (
    <div>
      {error ? (
        <p className="mb-4 text-sm font-black text-[var(--main-red)]">{error}</p>
      ) : null}
      <div
        data-testid="pricing-plan-grid"
        className="grid grid-cols-1 items-stretch gap-6 lg:grid-cols-3"
      >
        {PLAN_ORDER.map((planId) => {
          const plan = PLANS[planId];
          const Icon = PLAN_ICONS[planId];
          const isCurrent = planId === currentPlanId;
          const features = planFeatures(plan);

          return (
            <div
              key={planId}
              data-testid={`pricing-plan-card-${planId}`}
              className="relative flex h-full flex-col rounded-3xl border border-white/[0.08] bg-[#0a0a0a] p-10 transition-transform duration-200 ease-out hover:-translate-y-1.5"
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
                {plan.description}
              </p>

              {/* 가격 */}
              <div className="mt-9 flex items-end gap-1">
                <span className="text-4xl font-black tracking-tight text-white">
                  {formatWon(plan.monthlyPrice)}
                </span>
                <span className="pb-1 text-sm font-bold text-gray-500">/ 월</span>
                <span className="pb-1 text-sm font-bold text-gray-500">(VAT 포함)</span>
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
                      className={`text-sm font-bold ${
                        feature.included ? "text-gray-200" : "text-gray-600"
                      }`}
                    >
                      {feature.label}
                    </span>
                  </li>
                ))}
              </ul>

              {/* CTA */}
              <button
                type="button"
                disabled={isCurrent || pendingPlanId !== null}
                onClick={() => void handleSelect(planId)}
                className={`mt-10 w-full rounded-2xl px-4 py-4 text-sm font-black transition-colors disabled:cursor-not-allowed ${
                  isCurrent
                    ? "bg-white/[0.04] text-gray-500"
                    : "border border-white/[0.12] text-white hover:bg-white/[0.06] disabled:opacity-60"
                }`}
              >
                {isCurrent
                  ? "현재 이용 중"
                  : pendingPlanId === planId
                  ? "변경 중..."
                  : planId === "FREE"
                  ? "무료로 전환"
                  : "구독 시작하기"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
