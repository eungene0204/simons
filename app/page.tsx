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

function BusinessFooter() {
  const businessInfoItems = [
    { label: "상호명", value: process.env.COMPANY_NAME },
    { label: "대표자명", value: process.env.BUSINESS_REPRESENTATIVE_NAME },
    { label: "사업자등록번호", value: process.env.BUSINESS_REGISTRATION_NUMBER },
    { label: "이메일", value: process.env.BUSINESS_EMAIL },
  ];

  return (
    <footer className="border-t border-white/[0.08] bg-[#050505] px-6 py-6 text-xs font-bold text-gray-500">
      <dl className="mx-auto grid max-w-6xl gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
        {businessInfoItems.map((item) => (
          <div key={item.label} className="flex min-w-0 gap-2">
            <dt className="shrink-0 text-gray-600">{item.label}</dt>
            <dd className="min-w-0 truncate text-gray-400">{item.value || "미정"}</dd>
          </div>
        ))}
      </dl>
    </footer>
  );
}

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

  return (
    <>
      <StrategyLabPage />
      <BusinessFooter />
    </>
  );
}
