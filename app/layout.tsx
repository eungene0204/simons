import type { Metadata, Viewport } from "next";
import { Noto_Serif_KR } from "next/font/google";
import "./globals.css";
import TopMenuBar from "@/components/layout/TopMenuBar";
import ScrollToTop from "@/components/layout/ScrollToTop";
import VisualViewportInset from "@/components/layout/VisualViewportInset";
import QueryProvider from "@/components/providers/QueryProvider";
import { OrderAccountProvider } from "@/contexts/OrderAccountContext";
import ChunkErrorRecovery from "@/components/ChunkErrorRecovery";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";
import { getRequestLanguage } from "@/lib/i18n/server";
import { GoogleAnalytics } from "@next/third-parties/google";
import {
  buildOpenGraph,
  SITE_DESCRIPTION,
  SITE_KEYWORDS,
  SITE_NAME,
  SITE_TITLE,
  siteUrl,
  siteVerification,
} from "@/lib/seo/site";

// 큰 제목(display) 전용 세리프 — 마케팅 전단지(docs/marketing/flyer_intro_dark.html)와 같은
// Noto Serif KR을 next/font로 자체 호스팅한다(빌드 시 내려받아 unicode-range 조각으로 서빙,
// 런타임에 Google 요청 없음). 본문 스택(tailwind sans/inter/outfit=Arial 우선, 2026-07-25)은
// 건드리지 않는다 — `font-serif` 클래스를 단 h1만 이 서체를 쓴다(UI_GUIDELINES §3).
const displaySerif = Noto_Serif_KR({
  weight: ["500", "600", "700"],
  subsets: ["latin"],
  display: "swap",
  variable: "--font-serif",
});

// viewport-fit=cover가 있어야 env(safe-area-inset-*)이 0이 아닌 값을 준다 — 하단 고정 요소가
// iOS 홈 인디케이터 위에 머무는 전제(2026-09-08).
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

// 전 페이지 공통 메타 — 문구 정본은 lib/seo/site.ts. 하위 페이지는 `title`만 주면
// "<페이지> | 널스탁" 템플릿이 붙는다(홈은 absolute로 사이트 제목 그대로).
// 파비콘·OG 이미지는 app/icon.png·apple-icon.png·opengraph-image.png 파일 규약이 자동 배선한다.
export function generateMetadata(): Metadata {
  const language = getRequestLanguage();
  const title = SITE_TITLE[language];
  const description = SITE_DESCRIPTION[language];
  return {
    metadataBase: new URL(siteUrl()),
    applicationName: SITE_NAME[language],
    title: { default: title, template: `%s | ${SITE_NAME[language]}` },
    description,
    keywords: SITE_KEYWORDS[language],
    robots: { index: true, follow: true },
    openGraph: buildOpenGraph(language, {
      title,
      description,
      url: language === "en" ? "/us" : "/",
    }),
    twitter: { card: "summary_large_image", title, description },
    verification: siteVerification(),
  };
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const language = getRequestLanguage();

  return (
    <html lang={language} className={displaySerif.variable}>
      <body className="page-transition bg-[var(--background)] text-white font-inter antialiased">
        <LanguageProvider initialLanguage={language}>
          <QueryProvider>
            <ChunkErrorRecovery />
            <ScrollToTop />
            <VisualViewportInset />
            <OrderAccountProvider>
              <TopMenuBar />
              {children}
            </OrderAccountProvider>
          </QueryProvider>
        </LanguageProvider>
        {process.env.NEXT_PUBLIC_GA_ID && (
          <GoogleAnalytics gaId={process.env.NEXT_PUBLIC_GA_ID} />
        )}
      </body>
    </html>
  );
}
