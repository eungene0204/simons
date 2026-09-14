// 검색 노출(SEO) 정본 — 사이트 URL·제목·설명·키워드·구조화 데이터를 한곳에 둔다.
//
// 지역(kr=한국어, us=영어)마다 문구가 다르므로 언어를 인자로 받는다. 표현은 규제 안전 원칙을
// 따른다(CLAUDE.md) — "연구·백테스트·시뮬레이션 플랫폼"이며 추천·전망·수익 보장 문구를 쓰지 않는다.
// 이 모듈은 순수 함수·상수만 담는다(next 의존 없음) — layout·page·sitemap·robots·테스트가 공유한다.

import type { Metadata } from "next";
import type { Language } from "@/lib/i18n";

export const DEFAULT_SITE_URL = "https://www.nullstock.im";

/** 배포 도메인(.env `DOMAIN`) 기준 절대 URL 루트. 미설정이면 정식 도메인. */
export function siteUrl(): string {
  return process.env.DOMAIN ? `https://${process.env.DOMAIN}` : DEFAULT_SITE_URL;
}

export const SITE_NAME: Record<Language, string> = {
  ko: "널스탁",
  en: "NullStock",
};

/** 홈(랜딩) 제목 — 검색어 '퀀트'·'백테스트'가 앞쪽에 오도록 둔다. */
export const SITE_TITLE: Record<Language, string> = {
  ko: "널스탁 | 퀀트 전략 백테스트·시뮬레이션 플랫폼",
  en: "NullStock | Quant Strategy Backtesting Platform for U.S. Stocks",
};

export const SITE_DESCRIPTION: Record<Language, string> = {
  ko: "자연어로 퀀트 투자 전략을 설계하고 과거 데이터로 백테스트하세요. 한국 주식 백테스팅, 워크포워드·몬테카를로 검증, 모의투자 시뮬레이션까지 한곳에서 진행하는 투자 연구 플랫폼입니다.",
  en: "Design quant trading strategies in plain English and backtest them on historical U.S. stock data. Walk-forward and Monte Carlo validation plus paper-trading simulation in one research platform.",
};

export const SITE_KEYWORDS: Record<Language, string[]> = {
  ko: [
    "퀀트",
    "백테스트",
    "백테스팅",
    "퀀트 투자",
    "퀀트 전략",
    "주식 백테스트",
    "전략 시뮬레이션",
    "모의투자",
    "워크포워드",
    "몬테카를로 시뮬레이션",
    "널스탁",
  ],
  en: [
    "quant",
    "backtest",
    "backtesting",
    "quantitative investing",
    "trading strategy backtest",
    "stock backtesting platform",
    "walk-forward analysis",
    "Monte Carlo simulation",
    "paper trading",
    "NullStock",
  ],
};

export const OG_LOCALE: Record<Language, string> = {
  ko: "ko_KR",
  en: "en_US",
};

/** 홈 hreflang 쌍 — 지오 리다이렉트가 크롤러 색인을 한쪽으로 몰지 않도록 양쪽을 안내한다. */
export const HOME_LANGUAGE_ALTERNATES = {
  "ko-KR": "/",
  "en-US": "/us",
  "x-default": "/",
} as const;

/** 페이지별 Open Graph — Next는 openGraph를 얕게 덮어쓰므로 siteName·locale을 매번 채운다. */
export function buildOpenGraph(
  language: Language,
  page: { title: string; description: string; url: string },
): NonNullable<Metadata["openGraph"]> {
  return {
    type: "website",
    siteName: SITE_NAME[language],
    locale: OG_LOCALE[language],
    title: page.title,
    description: page.description,
    url: page.url,
  };
}

/**
 * 검색엔진 소유 확인 메타 — 구글 서치콘솔·네이버 서치어드바이저 값은 .env에서 읽는다.
 * (한국어 검색 노출은 네이버 등록이 필수다.) 둘 다 없으면 undefined를 돌려 메타를 찍지 않는다.
 */
export function siteVerification(
  env: Record<string, string | undefined> = process.env,
): Metadata["verification"] | undefined {
  const google = env.GOOGLE_SITE_VERIFICATION?.trim();
  const naver = env.NAVER_SITE_VERIFICATION?.trim();
  if (!google && !naver) return undefined;
  return {
    ...(google ? { google } : {}),
    ...(naver ? { other: { "naver-site-verification": naver } } : {}),
  };
}

const FEATURE_LIST: Record<Language, string[]> = {
  ko: [
    "자연어 퀀트 전략 설계",
    "과거 데이터 백테스트 (CAGR·MDD·샤프 비율·거래 통계)",
    "워크포워드 분석·몬테카를로 시뮬레이션",
    "가상계좌 모의투자 시뮬레이션",
  ],
  en: [
    "Natural-language quant strategy design",
    "Historical backtesting (CAGR, MDD, Sharpe ratio, trade statistics)",
    "Walk-forward analysis and Monte Carlo simulation",
    "Paper-trading simulation with virtual accounts",
  ],
};

/**
 * 홈 구조화 데이터(JSON-LD) — Organization·WebSite·WebApplication 그래프.
 * 설명 문구는 SITE_DESCRIPTION과 같다(연구·시뮬레이션 플랫폼 — 추천·전망 표현 없음).
 */
export function buildHomeJsonLd(language: Language, base: string = siteUrl()): Record<string, unknown> {
  const homeUrl = language === "en" ? `${base}/us` : base;
  const organizationId = `${base}/#organization`;
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": organizationId,
        name: SITE_NAME[language],
        alternateName: language === "en" ? "널스탁" : "NullStock",
        url: base,
        logo: `${base}/nullStock.png`,
      },
      {
        "@type": "WebSite",
        "@id": `${homeUrl}/#website`,
        url: homeUrl,
        name: SITE_NAME[language],
        description: SITE_DESCRIPTION[language],
        inLanguage: language === "en" ? "en-US" : "ko-KR",
        publisher: { "@id": organizationId },
      },
      {
        "@type": "WebApplication",
        name: SITE_NAME[language],
        url: homeUrl,
        applicationCategory: "FinanceApplication",
        operatingSystem: "Web",
        description: SITE_DESCRIPTION[language],
        featureList: FEATURE_LIST[language],
        offers: {
          "@type": "Offer",
          price: "0",
          priceCurrency: language === "en" ? "USD" : "KRW",
        },
        publisher: { "@id": organizationId },
      },
    ],
  };
}

/** `<script type="application/ld+json">` 본문 — `</script>` 조기 종료를 막기 위해 `<`를 이스케이프한다. */
export function serializeJsonLd(data: Record<string, unknown>): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

/** 로그인 뒤에서만 쓰는 앱 화면 — 색인 대상이 아니다(양 지역 프리픽스 모두 차단). */
export const PRIVATE_PATHS = [
  "/api/",
  "/console",
  "/dashboard",
  "/backtest",
  "/analytics",
  "/assets",
  "/virtual-account",
  "/watchlist",
  "/stock-order",
  "/stock/",
  "/kospi",
  "/login",
  "/register",
  "/guest",
] as const;

export function robotsDisallowPaths(): string[] {
  return PRIVATE_PATHS.flatMap((path) => [path, `/us${path}`]);
}
