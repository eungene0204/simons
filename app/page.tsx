import type { Metadata } from "next";
import StrategyLabPage from "./analytics/page";
import { PrivacyPolicyPage } from "@/components/landing/PrivacyPolicyPage";
import { TermsOfServicePage } from "@/components/landing/TermsOfServicePage";

export const metadata: Metadata = {
  title: "nullStock",
  description: "투자 아이디어를 전략으로 만들고 전략을 시뮬레이션 하세요",
  openGraph: {
    title: "nullStock",
    description: "투자 아이디어를 전략으로 만들고 전략을 시뮬레이션 하세요",
    type: "website",
  },
};

type HomePageProps = {
  searchParams?: {
    legal?: string | string[];
  };
};

export default function HomePage({ searchParams }: HomePageProps) {
  const legalView = Array.isArray(searchParams?.legal)
    ? searchParams.legal[0]
    : searchParams?.legal;

  if (legalView === "terms") {
    return <TermsOfServicePage />;
  }

  if (legalView === "privacy") {
    return <PrivacyPolicyPage />;
  }

  return <StrategyLabPage />;
}
