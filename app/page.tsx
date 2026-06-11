import type { Metadata } from "next";
import { redirect } from "next/navigation";
import CTASection from "@/components/landing/CTASection";
import FeatureSection from "@/components/landing/FeatureSection";
import HeroSection from "@/components/landing/HeroSection";
import ScreenshotSection from "@/components/landing/ScreenshotSection";
import { getCurrentUser } from "@/lib/get-user";

export const metadata: Metadata = {
  title: "Simons | AI 투자 전략 연구 플랫폼",
  description:
    "AI가 투자 전략을 설계하고 백테스트하고 검증합니다. 자연어 전략 생성, 전략 DSL 자동화, AI 코치까지 한 곳에서 시작하세요.",
  openGraph: {
    title: "Simons | AI 투자 전략 연구 플랫폼",
    description:
      "몇 분 안에 전략을 만들고, 과거 데이터로 검증하고, AI 코치로 개선하세요.",
    type: "website",
  },
};

export default async function LandingPage() {
  const user = await getCurrentUser();

  if (user) {
    redirect("/analytics");
  }

  return (
    <main
      className="min-h-screen bg-[#050505] text-white"
      style={{ paddingTop: "calc(var(--top-menu-bar-height, 76px) + 24px)" }}
    >
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-24 px-4 pb-24 sm:px-6 lg:px-8">
        <HeroSection />
        <FeatureSection />
        <ScreenshotSection />
        <CTASection />
      </div>
    </main>
  );
}
