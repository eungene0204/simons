"use client";

import { useState } from "react";
import { useConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useRouter } from "next/navigation";
import { Check, X, Lightning, Rocket, Crown } from "phosphor-react";
import {
  PLANS,
  PLAN_ORDER,
  Plan,
  PlanId,
  YEARLY_DISCOUNT_PERCENT,
  priceFor,
  yearlyDiscountPercent,
  type BillingCycle,
} from "@/lib/plans";
import PaymentCheckout from "@/components/pricing/PaymentCheckout";
import { getLocale, t } from "@/lib/i18n";

function formatWon(value: number) {
  return `₩${value.toLocaleString("ko-KR")}`;
}

function formatCount(value: number) {
  return value.toLocaleString("ko-KR");
}

function formatInitialInvestmentAmount(value: number) {
  if (value === 10_000_000) return t("천 만원");
  if (value === 50_000_000) return t("5천 만원");
  if (value === 100_000_000) return t("1억원");
  return formatWon(value);
}

const PLAN_ICONS: Record<PlanId, typeof Lightning> = {
  FREE: Lightning,
  PRO: Rocket,
  PREMIUM: Crown,
};

const PLAN_DESCRIPTIONS: Record<PlanId, string> = {
  FREE: "처음 전략을 만들고 백테스트를 경험해 보세요",
  PRO: "여러 전략을 동시에 연구하고 시뮬레이션 해보세요",
  PREMIUM: "전문가 수준으로 전략을 연구하고 검증 해보세요",
};

type FeatureRow = { label: string; included: boolean };

const PREMIUM_VALIDATION_FEATURES = [
  "워크포워드(walk-forward) 검증",
  "몬테카를로(Monte Carlo Simulation) 검증",
] as const;

function planFeatures(planId: PlanId, plan: Plan): FeatureRow[] {
  return [
    { label: t("월 백테스트 {0}회", formatCount(plan.monthlyBacktestLimit)), included: true },
    {
      label: t("계좌당 초기 모의 투자금 {0}", formatInitialInvestmentAmount(plan.initialInvestmentAmount)),
      included: true,
    },
    { label: t("시뮬레이션 가상계좌 {0}개", formatCount(plan.maxVirtualAccounts)), included: true },
    {
      label: plan.isUnlimitedStrategies
        ? t("전략 무제한 저장")
        : t("전략 {0}개 저장", formatCount(plan.maxStrategies)),
      included: true,
    },
    { label: t("AI 리포트"), included: planId !== "FREE" },
    { label: t("백테스트 결과 익스포트 (CSV/JSON)"), included: planId !== "FREE" },
    ...PREMIUM_VALIDATION_FEATURES.map((label) => ({
      label: t(label),
      included: planId === "PREMIUM",
    })),
  ];
}

interface PricingPlansProps {
  currentPlanId: PlanId;
  /** 자동결제(빌링) 구독 상태 — 유료 플랜 자동갱신 중일 때만 존재 */
  subscription?: {
    /** 청구 주기 — 미지정은 월간(연간 도입 이전 구독) */
    cycle?: BillingCycle;
    nextBillingAt: string | null;
    canceled: boolean;
  } | null;
  /**
   * 표시할 플랜 정의 — 서버가 관리자 한도 오버라이드(PlanConfig)를 병합해 넘긴다.
   * 생략하면 기본값(lib/plans.ts). 실제 한도 강제와 같은 값을 보여주기 위함.
   */
  plans?: Record<PlanId, Plan>;
}

function formatBillingDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString(getLocale(), { year: "numeric", month: "long", day: "numeric" });
}

export default function PricingPlans({
  currentPlanId,
  subscription,
  plans = PLANS,
}: PricingPlansProps) {
  const router = useRouter();
  const currentCycle: BillingCycle = subscription?.cycle === "yearly" ? "yearly" : "monthly";
  const [billingCycle, setBillingCycle] = useState<BillingCycle>(currentCycle);
  const [pendingPlanId, setPendingPlanId] = useState<PlanId | null>(null);
  const [checkoutPlanId, setCheckoutPlanId] = useState<PlanId | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 자동갱신 구독 중이면 FREE 카드의 버튼은 "즉시 전환"이 아니라 해지 예약이다 —
  // 설정 모달·/us와 같은 의미(남은 결제 기간까지 이용). 서버(/api/user/plan)가 분기한다.
  const hasActiveSubscription = Boolean(subscription && !subscription.canceled);
  // 연간 구독은 1년치를 미리 낸 상태라 즉시 재결제로 갈아타면 남은 기간(최대 11개월)이 소멸한다.
  // 만료일까지는 유료 플랜 변경 버튼을 잠근다(해지는 언제든 가능). 서버도 같은 규칙을 강제한다
  // (/api/payment/order).
  const isYearlyLocked = hasActiveSubscription && currentCycle === "yearly";
  const { confirm, dialog: confirmDialog } = useConfirmDialog();

  const handleSelect = async (planId: PlanId) => {
    if (planId === currentPlanId || pendingPlanId) return;

    // 유료 플랜은 토스페이먼츠 자동결제(빌링) 체크아웃 모달을 연다
    if (planId !== "FREE") {
      setCheckoutPlanId(planId);
      return;
    }

    if (
      hasActiveSubscription &&
      !(await confirm({
        title: t("자동갱신을 해지할까요?"),
        message: t("이미 결제된 기간에는 계속 이용할 수 있습니다."),
        confirmLabel: t("해지"),
        danger: true,
      }))
    ) {
      return;
    }

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
      setError(t("플랜 변경에 실패했습니다. 잠시 후 다시 시도해주세요."));
    } finally {
      setPendingPlanId(null);
    }
  };

  return (
    <div>
      {confirmDialog}
      {error ? (
        <p className="mb-4 text-sm font-black text-[var(--main-red)]">{error}</p>
      ) : null}

      {/* 결제 주기 선택 — 연간은 1년치를 한 번에 결제하고 그만큼 할인된다 */}
      <div className="mb-8 flex justify-center">
        <div
          data-testid="billing-cycle-toggle"
          role="group"
          aria-label={t("결제 주기")}
          className="inline-flex rounded-xl border border-white/[0.08] bg-white/[0.03] p-1"
        >
          {(["monthly", "yearly"] as const).map((cycle) => (
            <button
              key={cycle}
              type="button"
              aria-pressed={billingCycle === cycle}
              onClick={() => setBillingCycle(cycle)}
              className={`rounded-lg px-5 py-2.5 text-xs font-black transition-colors ${
                billingCycle === cycle
                  ? "bg-[var(--chat-accent)] text-[var(--chat-accent-ink)]"
                  : "text-[var(--text-label)] hover:text-white"
              }`}
            >
              {cycle === "monthly"
                ? t("월간 결제")
                : t("연간 결제 · {0}% 할인", String(YEARLY_DISCOUNT_PERCENT))}
            </button>
          ))}
        </div>
      </div>

      {isYearlyLocked ? (
        <p
          data-testid="yearly-lock-notice"
          className="mb-6 text-center text-xs font-bold text-[var(--text-label)]"
        >
          {t("연간 구독 기간 중에는 플랜을 변경할 수 없습니다. 만료일 이후 변경할 수 있습니다.")}
        </p>
      ) : null}

      <div
        data-testid="pricing-plan-grid"
        className="grid grid-cols-1 items-stretch gap-6 lg:grid-cols-3"
      >
        {PLAN_ORDER.map((planId) => {
          const plan = plans[planId];
          const Icon = PLAN_ICONS[planId];
          // 무료 플랜은 주기 개념이 없다 — 어느 탭에서도 월 ₩0으로 그대로 보여준다.
          const isPaidCycleShown = plan.monthlyPrice > 0;
          const monthlyEquivalent = Math.round(plan.yearlyPrice / 12);
          const discountPercent = yearlyDiscountPercent(plan);
          // 같은 플랜이라도 결제 주기가 다르면 "현재 이용 중"이 아니다(월간 → 연간 전환 경로).
          const isCurrent =
            planId === currentPlanId && (!isPaidCycleShown || billingCycle === currentCycle);
          const features = planFeatures(planId, plan);
          const description = t(PLAN_DESCRIPTIONS[planId]);
          // 해지 예약된 구독은 만료일에 FREE로 내려간다 — 다시 누를 동작이 없다.
          const isCancellationScheduled = planId === "FREE" && subscription?.canceled === true;
          // 연간 구독 중에는 유료 플랜 변경만 막는다 — 해지(FREE 카드)는 항상 열어 둔다.
          const isChangeLocked = isYearlyLocked && isPaidCycleShown;

          return (
            <div
              key={planId}
              data-testid={`pricing-plan-card-${planId}`}
              className="relative flex h-full flex-col rounded-2xl border border-white/[0.08] bg-[var(--background)] px-8 py-10 transition-transform duration-200 ease-out hover:-translate-y-1.5 xl:px-9"
            >
              {/* 헤더: 아이콘 + 플랜명 */}
              <div className="flex items-center gap-3">
                <span
                  className={`flex h-11 w-11 items-center justify-center rounded-xl bg-white/[0.06] ${
                    isCurrent ? "text-[var(--chat-accent)]" : "text-white"
                  }`}
                >
                  <Icon size={22} weight="fill" />
                </span>
                <h2 className="text-xl font-black tracking-tight text-white">{plan.name}</h2>
              </div>

              <p className="mt-6 text-sm font-bold leading-relaxed text-gray-400">
                {description}
              </p>

              {/* 가격 */}
              <div className="mt-9 flex items-end gap-1">
                <span className="text-4xl font-black tracking-tight text-white">
                  {formatWon(priceFor(plan, isPaidCycleShown ? billingCycle : "monthly"))}
                </span>
                <span className="pb-1 text-sm font-bold text-[var(--text-label)]">
                  {isPaidCycleShown && billingCycle === "yearly" ? t("/ 년") : t("/ 월")}
                </span>
                <span className="pb-1 text-sm font-bold text-[var(--text-label)]">{t("(VAT 포함)")}</span>
              </div>
              {/* 연간 결제일 때만 월 환산 금액을 덧붙인다 — 월간 요금과 비교할 기준을 준다 */}
              <p className="mt-2 h-4 text-xs font-bold text-[var(--text-label)]">
                {isPaidCycleShown && billingCycle === "yearly"
                  ? t("월 {0} 꼴 · {1}% 할인", formatWon(monthlyEquivalent), String(discountPercent))
                  : ""}
              </p>

              {/* 기능 목록 */}
              <ul className="mt-10 flex-1 space-y-6">
                {features.map((feature) => (
                  <li key={feature.label} className="flex items-center gap-3">
                    {feature.included ? (
                      <Check size={18} weight="bold" className="shrink-0 text-[var(--chat-accent)]" />
                    ) : (
                      <X size={18} weight="bold" className="shrink-0 text-gray-500" />
                    )}
                    <span
                      className={`text-sm font-bold xl:whitespace-nowrap ${
                        feature.included ? "text-gray-200" : "text-[var(--text-label)]"
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
                disabled={
                  isCurrent || pendingPlanId !== null || isCancellationScheduled || isChangeLocked
                }
                onClick={() => void handleSelect(planId)}
                className={`mt-10 w-full rounded-xl px-4 py-4 text-sm font-black transition-colors disabled:cursor-not-allowed ${
                  isCurrent
                    ? "bg-white/[0.04] text-[var(--text-label)]"
                    : planId === "FREE"
                    ? "border border-white/[0.12] text-white hover:bg-white/[0.06] disabled:opacity-60"
                    : "bg-[var(--chat-accent)] text-[var(--chat-accent-ink)] hover:brightness-110 active:translate-y-[1px] disabled:opacity-60"
                }`}
              >
                {isCurrent
                  ? t("현재 이용 중")
                  : pendingPlanId === planId
                  ? t("변경 중...")
                  : planId === "FREE"
                  ? isCancellationScheduled
                    ? t("해지 예약됨")
                    : hasActiveSubscription
                    ? t("구독 해지")
                    : t("무료로 전환")
                  : planId === currentPlanId
                  ? // 같은 플랜을 다른 주기로 다시 결제하는 경로
                    billingCycle === "yearly"
                    ? t("연간 결제로 전환")
                    : t("월간 결제로 전환")
                  : t("구독 시작하기")}
              </button>

              {/* 자동갱신 상태 — 현재 이용 중인 유료 플랜에만 표시 */}
              {isCurrent && planId !== "FREE" && subscription ? (
                <div
                  data-testid="subscription-renewal-status"
                  className="mt-4 text-center text-xs font-bold text-[var(--text-label)]"
                >
                  {subscription.canceled ? (
                    <p>
                      {t("해지 예약됨 · {0}까지 이용 가능합니다", formatBillingDate(subscription.nextBillingAt))}
                    </p>
                  ) : (
                    <p>{t("다음 결제일: {0}", formatBillingDate(subscription.nextBillingAt))}</p>
                  )}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {checkoutPlanId ? (
        <PaymentCheckout
          planId={checkoutPlanId}
          billingCycle={billingCycle}
          onClose={() => setCheckoutPlanId(null)}
        />
      ) : null}
    </div>
  );
}
