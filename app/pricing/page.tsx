import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getSessionUserId } from "@/lib/get-user";
import { ACCOUNT_ACCESS_SELECT, isAccountUsable } from "@/lib/accountAccess";
import { prisma } from "@/lib/prisma";
import { getPlan } from "@/lib/plans";
import { getEffectivePlans } from "@/lib/server/effectivePlans";
import { isGuestEmail } from "@/lib/server/guestAccounts";
import PricingPlans from "@/components/pricing/PricingPlans";
import PricingViewTracker from "@/components/pricing/PricingViewTracker";
import { t } from "@/lib/i18n";
import { getRequestLanguage } from "@/lib/i18n/server";
import { getRequestRegion } from "@/lib/geo/server";
import UsPricingPage from "@/components/pricing/us/UsPricingPage";
import type { Metadata } from "next";
import { buildOpenGraph } from "@/lib/seo/site";

const PRICING_META = {
  ko: { title: "요금제", description: "널스탁 퀀트 백테스트 플랫폼의 플랜별 백테스트 횟수·가상계좌·검증 기능을 비교하세요." },
  en: { title: "Pricing", description: "Compare NullStock plans — backtest quota, virtual accounts, and validation features for U.S. stock strategies." },
} as const;

export function generateMetadata(): Metadata {
  const language = getRequestLanguage();
  const { title, description } = PRICING_META[language];
  const path = language === "en" ? "/us/pricing" : "/pricing";
  return {
    title,
    description,
    openGraph: buildOpenGraph(language, { title, description, url: path }),
    alternates: { canonical: path },
  };
}

export default async function PricingPage() {
  // 글로벌 서비스(/us/pricing)는 영어·USD 전용 트리로 완전히 분리한다 —
  // 아래 한국(토스페이먼츠) 경로는 심사 중이라 그대로 둔다.
  if (getRequestRegion() === "us") {
    return (
      <>
        <PricingViewTracker />
        <UsPricingPage />
      </>
    );
  }

  // 세션 확인(DB 없음) → 계정 상태·플랜·구독을 한 조회로 읽고, 플랜 한도는 그와 병렬로 읽는다.
  // 원격 DB라 조회를 직렬로 기다리면 클릭 후 화면이 멈춘 듯 보인다 — 왕복을 한 번으로 묶는다.
  const userId = await getSessionUserId();
  if (userId == null) {
    redirect("/");
  }

  const [record, plans] = await Promise.all([
    prisma.user.findUnique({
      where: { id: userId },
      select: {
        name: true,
        email: true,
        ...ACCOUNT_ACCESS_SELECT,
        planTier: true,
        subscriptionPlanId: true,
        billingCycle: true,
        nextBillingAt: true,
        subscriptionCanceledAt: true,
        paymentProvider: true,
      },
    }),
    getEffectivePlans(),
  ]);
  // 정지(SUSPENDED)·삭제(DELETED)·이용 기한이 지난 계정은 유효한 토큰이 있어도 세션을 인정하지 않는다(getCurrentUser와 동일 기준).
  if (!record || !isAccountUsable(record)) {
    redirect("/");
  }
  const currentPlan = getPlan(record?.planTier);
  // 자동결제(빌링) 구독 상태 — 다음 결제일/해지 여부를 플랜 카드에 표시한다
  const subscription = record?.subscriptionPlanId
    ? {
        cycle: record.billingCycle === "yearly" ? ("yearly" as const) : ("monthly" as const),
        nextBillingAt: record.nextBillingAt?.toISOString() ?? null,
        canceled: record.subscriptionCanceledAt != null,
        // 계정은 KR/US 공용이라 글로벌(/us)에서 PayPal로 결제한 사용자도 이 화면에 온다 —
        // PayPal 구독이면 토스 결제 버튼을 잠그고 글로벌 요금제로 안내한다(이중 청구 방지)
        provider: record.paymentProvider === "paypal" ? ("paypal" as const) : ("toss" as const),
      }
    : null;

  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return (
    <DashboardLayout userName={record.name || t("게스트")}>
      <PricingViewTracker />
      <div className="min-h-[calc(100dvh-var(--top-menu-bar-height,76px))] bg-[var(--background)] px-5 py-6 text-white sm:px-8 lg:px-10">
        <div className="mx-auto flex min-h-[calc(100dvh-var(--top-menu-bar-height,76px)-3rem)] w-full max-w-7xl flex-col">
          <div className="text-center">
            <h1 className="text-4xl font-black tracking-[-0.04em] text-white md:text-6xl">
              {t("플랜을 선택하세요")}
            </h1>
            <p className="mt-2 text-sm font-bold text-gray-500">
              {t("초기 모의 투자금과 가상계좌 수에 따라 더 많은 전략을 검증할 수 있습니다.")}
            </p>
          </div>

          <div className="mt-14">
            <PricingPlans
              currentPlanId={currentPlan.planId}
              subscription={subscription}
              plans={plans}
              isGuest={isGuestEmail(record.email)}
            />
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
