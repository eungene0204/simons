import type { Metadata } from "next";
import StrategyLabPage from "./analytics/page";
import { PrivacyPolicyPage } from "@/components/landing/PrivacyPolicyPage";
import { TermsOfServicePage } from "@/components/landing/TermsOfServicePage";
import { getRequestLanguage } from "@/lib/i18n/server";

export function generateMetadata(): Metadata {
  const description =
    getRequestLanguage() === "en"
      ? "Turn your investment ideas into strategies and simulate them"
      : "투자 아이디어를 전략으로 만들고 전략을 시뮬레이션 하세요";
  return {
    title: "nullStock",
    description,
    openGraph: { title: "nullStock", description, type: "website" },
  };
}

type HomePageProps = {
  searchParams?: {
    legal?: string | string[];
  };
};

export default function HomePage({ searchParams }: HomePageProps) {
  const legalView = Array.isArray(searchParams?.legal)
    ? searchParams.legal[0]
    : searchParams?.legal;
  // 요청 언어를 서버 렌더에 고정한다 — 약관·개인정보처리방침은 서버 컴포넌트다.
  getRequestLanguage();

  if (legalView === "terms") {
    return <TermsOfServicePage />;
  }

  if (legalView === "privacy") {
    return <PrivacyPolicyPage />;
  }

  return <StrategyLabPage />;
}
