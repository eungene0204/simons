import type { Metadata } from "next";
import StrategyLabPage from "./analytics/page";
import { HomeLanding } from "@/components/landing/HomeLanding";
import { PrivacyPolicyPage } from "@/components/landing/PrivacyPolicyPage";
import { getSessionUserId } from "@/lib/get-user";
import { TermsOfServicePage } from "@/components/landing/TermsOfServicePage";
import { HomeStructuredData } from "@/components/seo/HomeStructuredData";
import { getRequestLanguage } from "@/lib/i18n/server";
import {
  buildOpenGraph,
  HOME_LANGUAGE_ALTERNATES,
  SITE_DESCRIPTION,
  SITE_NAME,
  SITE_TITLE,
} from "@/lib/seo/site";

type LegalView = "terms" | "privacy";

const LEGAL_TITLES: Record<LegalView, Record<"ko" | "en", string>> = {
  terms: { ko: "서비스 이용약관", en: "Terms of Service" },
  privacy: { ko: "개인정보처리방침", en: "Privacy Policy" },
};

function legalViewFrom(searchParams: HomePageProps["searchParams"]): LegalView | null {
  const value = Array.isArray(searchParams?.legal) ? searchParams.legal[0] : searchParams?.legal;
  return value === "terms" || value === "privacy" ? value : null;
}

export function generateMetadata({ searchParams }: HomePageProps): Metadata {
  const language = getRequestLanguage();
  const home = language === "en" ? "/us" : "/";
  const legalView = legalViewFrom(searchParams);

  // 약관·개인정보처리방침은 같은 경로의 쿼리 뷰다 — 제목만 바꾸고 canonical·hreflang은 내지 않는다.
  // Next 14.2는 루트 경로의 canonical에서 쿼리를 떨어뜨리므로(`/?legal=terms` → `/`) 홈 canonical을
  // 물려주면 약관이 홈으로 정규화된다 — 차라리 canonical을 비운다(실측 2026-09-13).
  // 루트 page.tsx는 루트 layout과 같은 세그먼트라 `%s | 널스탁` 템플릿을 받지 않는다 — 직접 붙인다.
  if (legalView) {
    return {
      title: { absolute: `${LEGAL_TITLES[legalView][language]} | ${SITE_NAME[language]}` },
      alternates: null,
    };
  }

  const title = SITE_TITLE[language];
  const description = SITE_DESCRIPTION[language];
  return {
    title: { absolute: title },
    description,
    openGraph: buildOpenGraph(language, { title, description, url: home }),
    // 지역별 대체 URL — 지오 리다이렉트가 크롤러 색인을 한쪽으로 몰지 않도록 안내한다.
    alternates: {
      canonical: home,
      languages: { ...HOME_LANGUAGE_ALTERNATES },
    },
  };
}

type HomePageProps = {
  searchParams?: {
    legal?: string | string[];
    prompt?: string | string[];
  };
};

// `/`는 비로그인 방문자에게 소개 페이지를, 이미 도구를 쓰는 쪽에는 전략연구소를 그대로 보여준다.
// - 로그인 사용자: 로그인 후 이동·로고가 모두 `/`를 가리키므로 종전대로 도구.
// - `?prompt=` 링크("이 전략 그대로 열기", X 글): 소개 페이지에 막히면 안 된다.
// - 영어(/us) 트리: 소개 페이지는 한국어 전용이라 종전대로 도구.
// 도구의 고정 주소는 `/analytics`다(메뉴·소개 페이지의 시작 버튼).
function opensStrategyLab(searchParams: HomePageProps["searchParams"], signedIn: boolean, language: string) {
  if (signedIn || language === "en") return true;
  const prompt = Array.isArray(searchParams?.prompt) ? searchParams.prompt[0] : searchParams?.prompt;
  return Boolean(prompt?.trim());
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const legalView = legalViewFrom(searchParams);
  // 요청 언어를 서버 렌더에 고정한다 — 약관·개인정보처리방침은 서버 컴포넌트다.
  const language = getRequestLanguage();

  if (legalView === "terms") {
    return <TermsOfServicePage />;
  }

  if (legalView === "privacy") {
    return <PrivacyPolicyPage />;
  }

  const signedIn = (await getSessionUserId()) != null;

  return (
    <>
      <HomeStructuredData language={language} />
      {opensStrategyLab(searchParams, signedIn, language) ? <StrategyLabPage /> : <HomeLanding />}
    </>
  );
}
