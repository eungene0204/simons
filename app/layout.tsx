import type { Metadata, Viewport } from "next";
import "./globals.css";
import TopMenuBar from "@/components/layout/TopMenuBar";
import ScrollToTop from "@/components/layout/ScrollToTop";
import VisualViewportInset from "@/components/layout/VisualViewportInset";
import QueryProvider from "@/components/providers/QueryProvider";
import { OrderAccountProvider } from "@/contexts/OrderAccountContext";
import ChunkErrorRecovery from "@/components/ChunkErrorRecovery";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";
import { getRequestLanguage } from "@/lib/i18n/server";
import { EmailLoginOptionProvider } from "@/components/providers/EmailLoginOptionProvider";
import { isEmailSignupEnabled } from "@/lib/server/email-verification";
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

// Keep display headings on the local serif stack so production builds do not depend on
// Google's font endpoint being available. Korean glyphs already use the browser fallback
// because the previous next/font configuration downloaded only the Latin subset.
const displaySerifStyle = {
  "--font-serif": '"Noto Serif KR", "Apple Myungjo", Georgia, serif',
} as React.CSSProperties;

// viewport-fit=cover가 있어야 env(safe-area-inset-*)이 0이 아닌 값을 준다 — 하단 고정 요소가
// iOS 홈 인디케이터 위에 머무는 전제(2026-09-08).
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

// 전 페이지 공통 메타 — 문구 정본은 lib/seo/site.ts. robots는 기본값(색인 허용)이라 내지 않는다 —
// 명시하면 404 페이지에 Next의 noindex와 함께 index가 겹쳐 찍힌다. 하위 페이지는 `title`만 주면
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
    openGraph: buildOpenGraph(language, {
      title,
      description,
      url: language === "en" ? "/us" : "/",
    }),
    // 제목·설명은 싣지 않는다 — 하위 페이지가 홈 문구를 물려받지 않고 각자의 og:title·og:description을 쓰게 한다.
    twitter: { card: "summary_large_image" },
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
    <html lang={language} style={displaySerifStyle}>
      <head>
        {/* AdSense 사이트 소유권 확인·광고 스크립트 — KR 전용(/us는 제외) */}
        {language !== "en" && (
          <script
            async
            src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-8335444243080631"
            crossOrigin="anonymous"
          />
        )}
      </head>
      <body className="page-transition bg-[var(--background)] text-white font-inter antialiased">
        <LanguageProvider initialLanguage={language}>
          <QueryProvider>
            <ChunkErrorRecovery />
            <ScrollToTop />
            <VisualViewportInset />
            <OrderAccountProvider>
              <EmailLoginOptionProvider enabled={isEmailSignupEnabled()}>
                <TopMenuBar />
                {children}
              </EmailLoginOptionProvider>
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
